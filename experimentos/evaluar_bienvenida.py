"""Evaluación del borrador de correo de bienvenida redactado por el LLM (segundo componente de IA).

Paso 1 (generar): redacta un borrador para cada caso sintético (S1–S8 y C-DEMO-01..03) en dos
variantes, con documentos pendientes y con expediente completo (22 borradores), los pasa por la
guarda determinista y deja dos copias de una planilla para revisión humana independiente.

    python -m experimentos.evaluar_bienvenida generar --modo llm_local       (requiere Ollama)
    python -m experimentos.evaluar_bienvenida generar --modo extractivo      (solo plantilla; prueba el flujo)

Paso 2 (analizar), cuando dos revisores llenaron sus copias por separado
(rúbrica en docs/rubrica_bienvenida_ia.md):

    python -m experimentos.evaluar_bienvenida analizar --etiqueta llm_local_qwen2.5_3b

Salidas en resultados/v1/: bienvenida_<etiqueta>.json, revision_bienvenida_<etiqueta>_revisor{1,2}.csv
y revision_bienvenida_<etiqueta>_analisis.json. Ningún resultado se reporta antes de la revisión.
"""
import argparse
import csv
import json
import platform
import statistics
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from src.asistente import cargar_config
from src.bienvenida_ia import RedactorBienvenida
from src.flujos.orquestador import DOCUMENTOS, Orquestador
from src.generacion import GeneradorOllama
from src.lectura import leer_csv

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "resultados" / "v1"
ARCHIVOS_CASOS = [RAIZ / "data" / "casos_estudio.json", RAIZ / "data" / "casos_demo.json"]
COLUMNAS_REVISION = ["rev_datos_correctos", "rev_afirmacion_inventada", "rev_personalizacion", "rev_tono", "rev_enviaria",
                     "rev_comentario"]


def casos() -> list[dict]:
    salida = []
    for ruta in ARCHIVOS_CASOS:
        for c in json.loads(ruta.read_text(encoding="utf-8"))["casos"]:
            base = dict(nombre=c["nombre"], cargo=c["cargo"], area=c["area"], fecha_ingreso=c["fecha_ingreso"],
                        modalidad=c["modalidad"])
            pendientes = [dict(id=d, estado=c.get("documentos", {}).get(d, "pendiente")) for d in DOCUMENTOS]
            if not any(x["estado"] != "entregado" for x in pendientes):  # asegura una variante con pendientes
                pendientes[1]["estado"] = "pendiente"
            salida.append(dict(base, id=f"{c['id']}-pendientes", documentos=pendientes))
            salida.append(dict(base, id=f"{c['id']}-completo", documentos=[dict(id=d, estado="entregado") for d in DOCUMENTOS]))
    return salida


def generar(a) -> None:
    config = cargar_config()
    if a.url:
        config["generacion"]["url_ollama"] = a.url
    g = config["generacion"]
    llm = a.modo == "llm_local" and GeneradorOllama(g["modelo_ollama"], g["url_ollama"]).disponible()
    if a.modo == "llm_local" and not llm:
        raise SystemExit(f"Ollama no responde en {g['url_ollama']} o falta {g['modelo_ollama']}. Ejecute: ollama pull {g['modelo_ollama']}")
    etiqueta = a.etiqueta or (f"llm_local_{g['modelo_ollama'].replace(':', '_')}" if llm else "plantilla")
    redactor, cal = RedactorBienvenida(config, forzar=None if llm else "extractivo"), Orquestador().calendario
    filas = []
    for c in casos():
        b = redactor.borrador(c, cal, llm)
        filas.append(dict(id=c["id"], cargo=c["cargo"], area=c["area"], modalidad=c["modalidad"], origen=b["origen"],
                          verificado=bool(b.get("verificacion") and b["verificacion"]["fiel"]),
                          motivos_verificacion=(b.get("verificacion") or {}).get("motivos", []),
                          latencia_s=b["latencia_s"], datos=b["datos"], texto=b["texto"],
                          borrador_descartado=b.get("borrador_descartado")))
        print(f"{c['id']:<22} {b['origen']:<10} {b['motivo'][:70]}")
    lat = [f["latencia_s"] for f in filas if f["origen"] == "llm_local" or f["borrador_descartado"]]
    resumen = dict(etiqueta=etiqueta, modelo=g["modelo_ollama"] if llm else None, prompt="prompts/bienvenida_v1.txt",
                   temperatura=g["temperatura"], borradores=len(filas),
                   aceptados_por_la_guarda=sum(f["origen"] == "llm_local" for f in filas),
                   descartados_por_la_guarda=sum(bool(f["borrador_descartado"]) for f in filas),
                   latencia_mediana_s=statistics.median(lat) if lat else None,
                   entorno=dict(sistema=platform.platform(), python=platform.python_version()),
                   nota="Resultado de la guarda automática. La calidad se reporta solo después de la revisión humana.")
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"bienvenida_{etiqueta}.json").write_text(json.dumps(dict(resumen=resumen, borradores=filas), ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
    for n in (1, 2):
        with (SALIDA / f"revision_bienvenida_{etiqueta}_revisor{n}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["id", "origen", "datos_del_ingreso", "correo"] + COLUMNAS_REVISION)
            for x in filas:
                w.writerow([x["id"], x["origen"], x["datos"], x["texto"]] + [""] * len(COLUMNAS_REVISION))
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"Planillas para revisión: resultados/v1/revision_bienvenida_{etiqueta}_revisor1.csv y _revisor2.csv")


def analizar(a) -> None:
    base = SALIDA / f"revision_bienvenida_{a.etiqueta}"
    r1 = {r["id"]: r for r in leer_csv(Path(f"{base}_revisor1.csv"))}
    r2 = {r["id"]: r for r in leer_csv(Path(f"{base}_revisor2.csv"))}
    ids = sorted(set(r1) & set(r2))
    ia = [i for i in ids if r1[i]["origen"] == "llm_local"]
    errores = [f"{i}: falta {c}" for i in ids for r in (r1[i], r2[i]) for c in COLUMNAS_REVISION[:5] if not r[c].strip()]
    if errores:
        raise SystemExit("Planillas incompletas:\n- " + "\n- ".join(errores[:20]))
    v = lambda r, c: int(r[c])
    kappa = lambda c, pond=None: (round(float(cohen_kappa_score([v(r1[i], c) for i in ia], [v(r2[i], c) for i in ia], weights=pond)), 3)
                                  if len({v(r1[i], c) for i in ia} | {v(r2[i], c) for i in ia}) > 1 else 1.0)
    # Criterio conservador: basta que un revisor marque una afirmación inventada o un dato incorrecto.
    inventada = [i for i in ia if v(r1[i], "rev_afirmacion_inventada") or v(r2[i], "rev_afirmacion_inventada")]
    incorrecto = [i for i in ia if not (v(r1[i], "rev_datos_correctos") and v(r2[i], "rev_datos_correctos"))]
    media = lambda c: round(statistics.mean((v(r1[i], c) + v(r2[i], c)) / 2 for i in ia), 2) if ia else None
    enviaria = [i for i in ia if min(v(r1[i], "rev_enviaria"), v(r2[i], "rev_enviaria")) >= 1]
    res = dict(etiqueta=a.etiqueta, borradores_de_ia_revisados=len(ia),
               con_afirmacion_inventada=len(inventada), ids_inventada=inventada,
               con_dato_incorrecto=len(incorrecto), ids_incorrecto=incorrecto,
               personalizacion_media=media("rev_personalizacion"), tono_medio=media("rev_tono"),
               proporcion_enviable_sin_cambios_o_menores=round(len(enviaria) / len(ia), 3) if ia else None,
               kappa=dict(afirmacion_inventada=kappa("rev_afirmacion_inventada"), datos_correctos=kappa("rev_datos_correctos"),
                          personalizacion=kappa("rev_personalizacion", "quadratic"), enviaria=kappa("rev_enviaria", "quadratic")),
               criterios="docs/rubrica_bienvenida_ia.md (fijados antes de la revisión)")
    (Path(f"{base}_analisis.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="accion", required=True)
    g = sub.add_parser("generar")
    g.add_argument("--modo", choices=["llm_local", "extractivo"], default="llm_local")
    g.add_argument("--url", default=None)
    g.add_argument("--etiqueta", default=None)
    n = sub.add_parser("analizar")
    n.add_argument("--etiqueta", required=True)
    a = ap.parse_args()
    generar(a) if a.accion == "generar" else analizar(a)


if __name__ == "__main__":
    main()
