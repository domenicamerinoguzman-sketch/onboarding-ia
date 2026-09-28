"""Asistente de consultas de inducción (etapa de recuperación del RAG).

Devuelve el pasaje de política más pertinente con su fuente, o deriva la consulta a
Talento Humano cuando la confianza es baja. No genera texto libre: la etapa generativa
(LLM) está especificada en prompts/ pero no se ejecutó en este prototipo.

Uso:
    python -m src.asistente "¿Cuándo me entregan la computadora?"
"""
import json
import sys
from pathlib import Path

import numpy as np

from .corpus import cargar_corpus
from .recuperadores import RecuperadorBM25

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = json.loads((RAIZ / "config" / "modelo_final.json").read_text(encoding="utf-8"))


class Asistente:
    def __init__(self, config: dict = CONFIG):
        self.pasajes = cargar_corpus()
        p = config["recuperador"]
        self.modelo = RecuperadorBM25(self.pasajes, k1=p["k1"], b=p["b"], stopwords=p["stopwords"],
                                      stemming=p["stemming"], incluir_titulos=p["incluir_titulos"])
        self.umbral = config["umbral_derivacion"]
        self.k = config["pasajes_contexto"]

    def responder(self, pregunta: str) -> dict:
        s = self.modelo.puntuar(pregunta)
        orden = np.argsort(-s)[: self.k]
        candidatos = [dict(id=self.pasajes[i].id, documento=self.pasajes[i].documento,
                           titulo=self.pasajes[i].titulo, puntaje=round(float(s[i]), 3)) for i in orden]
        if s[orden[0]] < self.umbral:
            return dict(accion="derivar_talento_humano", motivo="confianza de recuperación bajo el umbral",
                        puntaje_top1=round(float(s[orden[0]]), 3), umbral=self.umbral, candidatos=candidatos)
        top = self.pasajes[orden[0]]
        return dict(accion="responder", fuente=f"{top.documento} > {top.titulo} ({top.id})",
                    pasaje=top.texto, puntaje_top1=round(float(s[orden[0]]), 3), umbral=self.umbral,
                    candidatos=candidatos, revision_humana="respuesta citada; la política vigente prevalece")


if __name__ == "__main__":
    pregunta = " ".join(sys.argv[1:]) or "¿Cuándo me entregan la computadora?"
    print(json.dumps(Asistente().responder(pregunta), ensure_ascii=False, indent=2))
