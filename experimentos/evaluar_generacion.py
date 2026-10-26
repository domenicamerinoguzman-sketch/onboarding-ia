"""Evaluación de extremo a extremo del asistente (recuperación + generación + guardas).

    python -m experimentos.evaluar_generacion --modo extractivo          # siempre disponible
    python -m experimentos.evaluar_generacion --modo llm_local           # requiere Ollama
    python -m experimentos.evaluar_generacion --modo llm_local --modelo llama3.2:3b

Métricas (sobre el conjunto reservado y, por separado, el de desarrollo):
- exactitud_extremo_a_extremo: pregunta dentro del alcance -> responde citando el pasaje
  correcto; fuera del alcance -> deriva a Talento Humano.
- tasa_fidelidad_verificada: proporción de respuestas entregadas que pasan la guarda de salida
  (cita un pasaje recuperado y toda cifra está en el pasaje citado). Es una medida automática y
  parcial de groundedness: no detecta afirmaciones falsas sin cifras.
- tasa_descarte_llm: respuestas del LLM rechazadas por la guarda y sustituidas por el respaldo.
- derivaciones_del_llm: preguntas que el LLM derivó aunque la recuperación superó el umbral.
- latencia: media, mediana y percentil 95 (segundos por consulta).

Además guarda todas las respuestas en CSV, con columnas vacías para la revisión humana de una
muestra (rúbrica en docs/rubrica_revision_humana.md).
"""
import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np

from src.asistente import Asistente, cargar_config
from src.corpus import cargar_preguntas

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "resultados" / "v1"
CONJUNTOS = {"reservado": RAIZ / "data" / "prueba_reservada.csv", "desarrollo": RAIZ / "data" / "preguntas_evaluacion.csv"}
TAMANO_MUESTRA_HUMANA = 30


def evaluar(asistente: Asistente, preguntas: list[dict]) -> tuple[dict, list[dict]]:
    filas = []
    for q in preguntas:
        r = asistente.responder(q["pregunta"])
        gen = r.get("generacion") or {}
        ver = gen.get("verificacion") or {}
        fuente_id = (r.get("fuente") or "").rsplit("(", 1)[-1].rstrip(")") if r.get("fuente") else ""
        dentro = q["pasaje_correcto"] != "NINGUNO"
        correcta = (r["accion"] == "responder" and fuente_id == q["pasaje_correcto"]) if dentro else r["accion"] != "responder"
        filas.append(dict(id=q["id"], tipo=q["tipo"], pasaje_correcto=q["pasaje_correcto"], accion=r["accion"],
                          fuente=fuente_id, correcta=int(correcta), modo=gen.get("modo", ""),
                          fiel=ver.get("fiel", ""), motivo_modo=gen.get("motivo", r.get("motivo", "")),
                          llm_descartada=gen.get("respuesta_llm_descartada", ""),
                          latencia_s=r["latencia_total_s"], pregunta=q["pregunta"], respuesta=r["respuesta"],
                          revision_correcta="", revision_fiel="", revision_util="", revision_comentario=""))
    entregadas = [f for f in filas if f["accion"] == "responder"]
    llm = [f for f in filas if f["motivo_modo"] and ("LLM" in f["motivo_modo"] and "verificada" in f["motivo_modo"]
                                                     or "descartada" in f["motivo_modo"])]
    lat = np.array([f["latencia_s"] for f in filas])
    tipos = sorted({f["tipo"] for f in filas})
    m = dict(
        preguntas=len(filas),
        exactitud_extremo_a_extremo=float(np.mean([f["correcta"] for f in filas])),
        exactitud_por_tipo={t: float(np.mean([f["correcta"] for f in filas if f["tipo"] == t])) for t in tipos},
        respuestas_entregadas=len(entregadas),
        respuestas_erroneas=sum(1 for f in filas if f["accion"] == "responder" and not f["correcta"]),
        tasa_fidelidad_verificada=float(np.mean([f["fiel"] is True for f in entregadas])) if entregadas else None,
        respuestas_llm=len(llm),
        tasa_descarte_llm=(sum("descartada" in f["motivo_modo"] for f in llm) / len(llm)) if llm else None,
        derivaciones_del_llm=sum(1 for f in filas if "pasajes no contienen" in str(f["motivo_modo"])),
        latencia_s=dict(media=float(lat.mean()), mediana=float(np.median(lat)), p95=float(np.percentile(lat, 95))),
    )
    return m, filas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["extractivo", "llm_local"], default="extractivo")
    ap.add_argument("--modelo", default=None, help="modelo de Ollama (por defecto, el de config/modelo_final.json)")
    a = ap.parse_args()
    config = cargar_config()
    if a.modelo:
        config["generacion"]["modelo_ollama"] = a.modelo
    asistente = Asistente(config=config, modo=a.modo)
    etiqueta = a.modo if a.modo == "extractivo" else f"llm_local_{config['generacion']['modelo_ollama'].replace(':', '_')}"
    SALIDA.mkdir(parents=True, exist_ok=True)
    informe = dict(modo=a.modo, modelo=config["generacion"]["modelo_ollama"] if a.modo == "llm_local" else None,
                   version=config["version"], umbral=config["umbral_derivacion"], conjuntos={})
    for nombre, ruta in CONJUNTOS.items():
        m, filas = evaluar(asistente, cargar_preguntas(ruta))
        informe["conjuntos"][nombre] = m
        with (SALIDA / f"generacion_{etiqueta}_{nombre}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=filas[0].keys())
            w.writeheader()
            w.writerows(filas)
        if nombre == "reservado":
            rng = random.Random(20260928)
            muestra = rng.sample(filas, min(TAMANO_MUESTRA_HUMANA, len(filas)))
            with (SALIDA / f"revision_humana_{etiqueta}.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["id", "pregunta", "respuesta", "fuente", "pasaje_correcto",
                                                  "revision_correcta", "revision_fiel", "revision_util", "revision_comentario"])
                w.writeheader()
                w.writerows({k: x[k] for k in w.fieldnames} for x in muestra)
        print(nombre, json.dumps(m, ensure_ascii=False))
    (SALIDA / f"generacion_{etiqueta}.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n",
                                                        encoding="utf-8")


if __name__ == "__main__":
    main()
