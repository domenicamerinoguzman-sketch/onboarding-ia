"""Recuperadores de pasajes: baseline por palabras clave, TF-IDF y BM25.

Todos exponen puntuar(pregunta) -> vector de puntajes (uno por pasaje).
Los recuperadores se construyen solo con el corpus; las preguntas no intervienen
en su ajuste, así que no hay fuga de información hacia la evaluación.
"""
import math
import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .corpus import Pasaje
from .preprocesamiento import tokenizar


def texto_indexado(p: Pasaje, incluir_titulos: bool) -> str:
    return f"{p.documento}. {p.titulo}. {p.texto}" if incluir_titulos else p.texto


class BaselinePalabrasClave:
    """Baseline: cuenta palabras de la pregunta presentes en el pasaje (sin normalización)."""

    nombre = "baseline_palabras_clave"

    def __init__(self, pasajes: list[Pasaje]):
        self.conjuntos = [set(re.findall(r"\w+", p.texto.lower())) for p in pasajes]

    def puntuar(self, pregunta: str) -> np.ndarray:
        q = set(re.findall(r"\w+", pregunta.lower()))
        return np.array([len(q & c) for c in self.conjuntos], dtype=float)


class RecuperadorTFIDF:
    def __init__(self, pasajes, analizador="word", ngramas=(1, 1), stopwords=True,
                 stemming=True, incluir_titulos=True):
        docs = [texto_indexado(p, incluir_titulos) for p in pasajes]
        if analizador == "word":
            self.vec = TfidfVectorizer(
                tokenizer=lambda t: tokenizar(t, stopwords, stemming), lowercase=False,
                token_pattern=None, ngram_range=ngramas, sublinear_tf=True)
        else:  # n-gramas de caracteres dentro de palabras, sobre texto normalizado
            self.vec = TfidfVectorizer(
                preprocessor=lambda t: " ".join(tokenizar(t, stopwords, stemming)),
                analyzer="char_wb", ngram_range=ngramas, sublinear_tf=True)
        self.matriz = self.vec.fit_transform(docs)

    def puntuar(self, pregunta: str) -> np.ndarray:
        return (self.matriz @ self.vec.transform([pregunta]).T).toarray().ravel()


class RecuperadorBM25:
    """Okapi BM25 con parámetros k1 (saturación de frecuencia) y b (normalización por longitud)."""

    def __init__(self, pasajes, k1=1.2, b=0.75, stopwords=True, stemming=True, incluir_titulos=True):
        self.k1, self.b = k1, b
        self.opts = dict(stopwords=stopwords, stemming=stemming)
        self.docs = [Counter(tokenizar(texto_indexado(p, incluir_titulos), **self.opts)) for p in pasajes]
        self.largos = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.promedio = self.largos.mean()
        n = len(self.docs)
        df = Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def puntuar(self, pregunta: str) -> np.ndarray:
        q = set(tokenizar(pregunta, **self.opts))
        s = np.zeros(len(self.docs))
        for i, d in enumerate(self.docs):
            norm = self.k1 * (1 - self.b + self.b * self.largos[i] / self.promedio)
            for t in q:
                f = d.get(t, 0)
                if f:
                    s[i] += self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return s


def espacio_hiperparametros() -> list[dict]:
    """Rejilla de configuraciones evaluadas por el modelo ajustado (120 combinaciones)."""
    grid = []
    for stem in (False, True):
        for stop in (False, True):
            for tit in (False, True):
                comunes = dict(stemming=stem, stopwords=stop, incluir_titulos=tit)
                for analizador, ng in (("word", (1, 1)), ("word", (1, 2)), ("char", (3, 5))):
                    grid.append(dict(modelo="tfidf", analizador=analizador, ngramas=ng, **comunes))
                for k1 in (0.9, 1.2, 1.5, 2.0):
                    for b in (0.5, 0.75, 0.9):
                        grid.append(dict(modelo="bm25", k1=k1, b=b, **comunes))
    return grid


def construir(config: dict, pasajes):
    c = dict(config)
    modelo = c.pop("modelo")
    if modelo == "baseline":
        return BaselinePalabrasClave(pasajes)
    if modelo == "tfidf":
        return RecuperadorTFIDF(pasajes, **c)
    return RecuperadorBM25(pasajes, **c)


def describir(config: dict) -> str:
    if config["modelo"] == "baseline":
        return "baseline"
    base = (f"{config['modelo']}"
            + (f"-{config['analizador']}{config['ngramas']}" if config["modelo"] == "tfidf"
               else f"(k1={config['k1']},b={config['b']})"))
    flags = [n for n, k in (("raices", "stemming"), ("sin_vacias", "stopwords"),
                            ("titulos", "incluir_titulos")) if config[k]]
    return base + ("[" + ",".join(flags) + "]" if flags else "")
