"""Fija el umbral de derivación del modelo final (BM25 k1=1.2, b=0.75, con normalización
y títulos) usando las 162 preguntas, y lo guarda en config/modelo_final.json.

El desempeño esperado de este procedimiento NO se mide aquí: se estima con
experimentos/validacion_cruzada.py, donde el umbral se elige solo con datos de entrenamiento.

    python -m experimentos.ajustar_modelo_final
"""
import json
from pathlib import Path

import numpy as np

from src.corpus import cargar_corpus, cargar_preguntas
from src.evaluacion import desempatar, elegir_umbral, resumen_por_pregunta
from src.recuperadores import RecuperadorBM25

PARAMS = dict(k1=1.2, b=0.75, stopwords=True, stemming=True, incluir_titulos=True)
RUTA = Path(__file__).resolve().parent.parent / "config" / "modelo_final.json"


def main():
    pasajes, preguntas = cargar_corpus(), cargar_preguntas()
    ids = [p.id for p in pasajes]
    oro = np.array([ids.index(q["pasaje_correcto"]) if q["pasaje_correcto"] != "NINGUNO" else -1
                    for q in preguntas])
    r = RecuperadorBM25(pasajes, **PARAMS)
    res = resumen_por_pregunta(desempatar(np.vstack([r.puntuar(q["pregunta"]) for q in preguntas])), oro)
    umbral = round(elegir_umbral(res, np.arange(len(preguntas))), 3)
    config = dict(version="0.2.0", recuperador=dict(modelo="bm25", **PARAMS),
                  umbral_derivacion=umbral, pasajes_contexto=3,
                  nota="Umbral elegido con las 162 preguntas sintéticas; desempeño estimado por validación cruzada.")
    RUTA.parent.mkdir(exist_ok=True)
    RUTA.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(config, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
