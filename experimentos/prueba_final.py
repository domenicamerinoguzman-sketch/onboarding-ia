"""Prueba final sobre el conjunto reservado (data/prueba_reservada.csv).

Las 110 preguntas se redactaron DESPUÉS de congelar el modelo v1.0 (ver historial de Git) y
no se usaron para elegir umbrales, sinónimos ni configuraciones. Cada sistema se aplica tal
como quedó configurado, con su umbral fijo:

    A0  baseline de palabras clave (umbral elegido con las 162 preguntas de desarrollo)
    A4  modelo adoptado en v0.2 (config/modelo_v0.2.json)
    v1  modelo final v1.0 (config/modelo_final.json)

Reporta exactitud, respuestas erróneas, Hit@k, derivación, exactitud por tipo, IC 95 % por
bootstrap (5000 remuestreos) y McNemar exacta v1 frente a A4 y frente a A0.

    python -m experimentos.prueba_final
"""
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from src.corpus import cargar_corpus, cargar_preguntas
from src.evaluacion import decisiones, desempatar, elegir_umbral, metricas, resumen_por_pregunta
from src.recuperadores import construir

RAIZ = Path(__file__).resolve().parent.parent
RUTA_RESERVADA = RAIZ / "data" / "prueba_reservada.csv"
SALIDA = RAIZ / "resultados" / "v1"
SEMILLA, N_BOOTSTRAP = 20260928, 5000


def oro_de(preguntas, ids):
    return np.array([ids.index(q["pasaje_correcto"]) if q["pasaje_correcto"] != "NINGUNO" else -1 for q in preguntas])


def sistemas(pasajes, desarrollo, ids):
    """Devuelve {nombre: (recuperador, umbral)} con umbrales fijados SOLO con desarrollo."""
    v02 = json.loads((RAIZ / "config" / "modelo_v0.2.json").read_text(encoding="utf-8"))
    v1 = json.loads((RAIZ / "config" / "modelo_final.json").read_text(encoding="utf-8"))
    base = construir(dict(modelo="baseline"), pasajes)
    oro_dev = oro_de(desarrollo, ids)
    res_dev = resumen_por_pregunta(desempatar(np.vstack([base.puntuar(q["pregunta"]) for q in desarrollo]), SEMILLA), oro_dev)
    u_base = elegir_umbral(res_dev, np.arange(len(desarrollo)))
    return {
        "A0 Baseline palabras clave": (base, u_base),
        "A4 BM25 (v0.2)": (construir(v02["recuperador"], pasajes), v02["umbral_derivacion"]),
        "v1 Final (sinónimos + caracteres)": (construir(v1["recuperador"], pasajes), v1["umbral_derivacion"]),
    }


def ci95(v):
    return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    pasajes = cargar_corpus()
    ids = [p.id for p in pasajes]
    desarrollo, reservada = cargar_preguntas(), cargar_preguntas(RUTA_RESERVADA)
    oro = oro_de(reservada, ids)
    tipos = np.array([q["tipo"] for q in reservada])
    n, todos = len(reservada), np.arange(len(reservada))
    rng = np.random.default_rng(SEMILLA)
    idx = rng.integers(0, n, size=(N_BOOTSTRAP, n))

    informe = dict(conjunto=dict(preguntas=n, por_tipo={t: int((tipos == t).sum()) for t in np.unique(tipos)},
                                 nota="Redactado después de congelar el modelo; ninguna decisión usó estas preguntas."),
                   sistemas={}, comparaciones=[])
    dec, top1 = {}, {}
    for nombre, (r, u) in sistemas(pasajes, desarrollo, ids).items():
        res = resumen_por_pregunta(desempatar(np.vstack([r.puntuar(q["pregunta"]) for q in reservada]), SEMILLA), oro)
        d = decisiones(res, u, todos)
        dec[nombre], top1[nombre] = d, res["top1"]
        m = metricas(d)
        m["umbral"] = round(float(u), 3)
        m["ic95_exactitud"] = ci95(d["correcta"].astype(float)[idx].mean(1))
        m["ic95_respuesta_erronea"] = ci95(d["erronea"].astype(float)[idx].mean(1))
        m["exactitud_por_tipo"] = {t: float(d["correcta"][tipos == t].mean()) for t in np.unique(tipos)}
        informe["sistemas"][nombre] = m

    v1, a4, a0 = "v1 Final (sinónimos + caracteres)", "A4 BM25 (v0.2)", "A0 Baseline palabras clave"
    for a, b in ((a4, v1), (a0, v1), (a0, a4)):
        ca, cb = dec[a]["correcta"], dec[b]["correcta"]
        sb, sa = int((~ca & cb).sum()), int((ca & ~cb).sum())
        dif = cb.astype(float)[idx].mean(1) - ca.astype(float)[idx].mean(1)
        dife = dec[b]["erronea"].astype(float)[idx].mean(1) - dec[a]["erronea"].astype(float)[idx].mean(1)
        informe["comparaciones"].append(dict(
            A=a, B=b, solo_B_acierta=sb, solo_A_acierta=sa,
            p_mcnemar_exacta=float(binomtest(sb, sb + sa, 0.5).pvalue) if sb + sa else 1.0,
            diferencia_exactitud=float(cb.mean() - ca.mean()), ic95_diferencia_exactitud=ci95(dif),
            diferencia_erronea=float(dec[b]["erronea"].mean() - dec[a]["erronea"].mean()),
            ic95_diferencia_erronea=ci95(dife)))

    (SALIDA / "prueba_final.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (SALIDA / "prueba_final_predicciones.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "tipo", "pasaje_correcto", "a4_top1", "a4_deriva", "a4_correcta",
                    "v1_top1", "v1_deriva", "v1_correcta", "pregunta"])
        for i, q in enumerate(reservada):
            w.writerow([q["id"], q["tipo"], q["pasaje_correcto"], ids[top1[a4][i]], int(dec[a4]["deriva"][i]),
                        int(dec[a4]["correcta"][i]), ids[top1[v1][i]], int(dec[v1]["deriva"][i]),
                        int(dec[v1]["correcta"][i]), q["pregunta"]])
    for nombre, m in informe["sistemas"].items():
        print(f"{nombre:36s} exact={m['exactitud_asistente']:.3f} {m['ic95_exactitud']} err={m['respuesta_erronea']:.3f} "
              f"hit1={m['hit1']:.3f} hit3={m['hit3']:.3f} rec_der={m['recall_derivacion']:.3f} "
              f"prec_der={m['precision_derivacion']:.3f} tipos={ {k: round(v, 3) for k, v in m['exactitud_por_tipo'].items()} }")
    for c in informe["comparaciones"]:
        print(f"{c['B']} vs {c['A']}: dif={c['diferencia_exactitud']:+.3f} IC={c['ic95_diferencia_exactitud']} "
              f"McNemar p={c['p_mcnemar_exacta']:.4g} (solo B {c['solo_B_acierta']}, solo A {c['solo_A_acierta']}); "
              f"dif err={c['diferencia_erronea']:+.3f} IC={c['ic95_diferencia_erronea']}")


if __name__ == "__main__":
    main()
