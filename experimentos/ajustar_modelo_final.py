"""Fija el umbral de derivación del modelo final v1.0 (variante B3: BM25 k1=1,2 y b=0,75 con
normalización, títulos y sinónimos, más n-gramas de caracteres con peso 5) usando las 162
preguntas de desarrollo, y lo guarda en config/modelo_final.json.

El desempeño esperado de este procedimiento NO se mide aquí:
- se estima con experimentos/validacion_v1.py (umbral elegido solo en entrenamiento), y
- se verifica con experimentos/prueba_final.py, sobre preguntas reservadas que no se usaron
  para ninguna decisión.

La configuración de v0.2 se conserva en config/modelo_v0.2.json.

    python -m experimentos.ajustar_modelo_final
"""
import json
from pathlib import Path

import numpy as np

from src.corpus import cargar_corpus, cargar_preguntas
from src.evaluacion import desempatar, elegir_umbral, resumen_por_pregunta
from src.recuperadores import construir

VERSION = "1.0.0"
RECUPERADOR = dict(modelo="hibrido", k1=1.2, b=0.75, stopwords=True, stemming=True,
                   incluir_titulos=True, sinonimos=True, peso_char=5.0)
RUTA = Path(__file__).resolve().parent.parent / "config" / "modelo_final.json"


def main():
    pasajes, preguntas = cargar_corpus(), cargar_preguntas()
    ids = [p.id for p in pasajes]
    oro = np.array([ids.index(q["pasaje_correcto"]) if q["pasaje_correcto"] != "NINGUNO" else -1
                    for q in preguntas])
    r = construir(RECUPERADOR, pasajes)
    res = resumen_por_pregunta(desempatar(np.vstack([r.puntuar(q["pregunta"]) for q in preguntas])), oro)
    umbral = round(elegir_umbral(res, np.arange(len(preguntas))), 3)
    config = dict(
        version=VERSION,
        recuperador=RECUPERADOR,
        umbral_derivacion=umbral,
        pasajes_contexto=3,
        generacion=dict(
            modo="dual",
            backend_preferido="ollama",
            modelo_ollama="qwen2.5:3b",
            url_ollama="http://localhost:11434",
            temperatura=0.0,
            max_tokens=220,
            timeout_s=60,
            prompt="prompts/respuesta_rag_v2.txt",
            respaldo="extractivo",
        ),
        nota=("Umbral elegido con las 162 preguntas de desarrollo; desempeño estimado por validación "
              "cruzada (resultados/v1/) y verificado en el conjunto reservado (resultados/v1/prueba_final.json)."),
    )
    RUTA.parent.mkdir(exist_ok=True)
    RUTA.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(config, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
