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
from .preprocesamiento import quitar_tildes, tokenizar
from .sinonimos import cargar_sinonimos, expandir


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
    """Okapi BM25 con parámetros k1 (saturación de frecuencia) y b (normalización por longitud).

    sinonimos=True expande la consulta con data/sinonimos.json antes de puntuar (v1.0).
    """

    def __init__(self, pasajes, k1=1.2, b=0.75, stopwords=True, stemming=True, incluir_titulos=True,
                 sinonimos=False):
        self.k1, self.b, self.sinonimos = k1, b, sinonimos
        self.opts = dict(stopwords=stopwords, stemming=stemming)
        self.docs = [Counter(tokenizar(texto_indexado(p, incluir_titulos), **self.opts)) for p in pasajes]
        self.largos = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.promedio = self.largos.mean()
        n = len(self.docs)
        df = Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.idf_desconocido = math.log(1 + (n + 0.5) / 0.5)  # término ausente del corpus

    def terminos(self, pregunta: str) -> set[str]:
        return set(tokenizar(expandir(pregunta) if self.sinonimos else pregunta, **self.opts))

    def puntuar(self, pregunta: str) -> np.ndarray:
        q = self.terminos(pregunta)
        s = np.zeros(len(self.docs))
        for i, d in enumerate(self.docs):
            norm = self.k1 * (1 - self.b + self.b * self.largos[i] / self.promedio)
            for t in q:
                f = d.get(t, 0)
                if f:
                    s[i] += self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return s

    def contribuciones(self, pregunta: str, i: int) -> dict[str, float]:
        """Descomposición exacta del puntaje del pasaje i por término (interpretabilidad)."""
        d, out = self.docs[i], {}
        norm = self.k1 * (1 - self.b + self.b * self.largos[i] / self.promedio)
        for t in self.terminos(pregunta):
            f = d.get(t, 0)
            if f:
                out[t] = self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def cobertura(self, pregunta: str, i: int) -> float:
        """Fracción de la «masa IDF» de la consulta ORIGINAL presente en el pasaje i.

        Se calcula sin expansión de sinónimos: mide cuánto de lo que el usuario escribió
        está respaldado por el pasaje. Los términos ausentes de todo el corpus pesan con el
        IDF máximo, porque suelen indicar un tema fuera del alcance (p. ej. «hipotecario»).
        Un término cuyo sinónimo sí aparece en el pasaje cuenta como cubierto.
        """
        originales = set(tokenizar(pregunta, **self.opts))
        if not originales:
            return 0.0
        d = self.docs[i]
        total = cubierto = 0.0
        for t in originales:
            w = self.idf.get(t, self.idf_desconocido)
            total += w
            if t in d or (self.sinonimos and _cubierto_por_sinonimo(t, pregunta, d, self.opts)):
                cubierto += w
        return cubierto / total


def _cubierto_por_sinonimo(termino: str, pregunta: str, doc: Counter, opts: dict) -> bool:
    """True si alguna expansión disparada por una frase que contiene `termino` aparece en el pasaje."""
    normal = quitar_tildes(pregunta.lower())
    for clave, patron, destino in cargar_sinonimos():
        if patron.search(normal):
            if termino in tokenizar(clave, **opts) and any(t in doc for t in tokenizar(destino, **opts)):
                return True
    return False


class RecuperadorHibrido:
    """Fusión lineal de BM25 (palabras) y TF-IDF de n-gramas de caracteres (3-5).

    puntaje = BM25 + peso_char × coseno_char. El componente de caracteres tolera erratas,
    variantes morfológicas y palabras compuestas que el BM25 por raíces no empareja.
    """

    def __init__(self, pasajes, peso_char=5.0, sinonimos=False, **bm25):
        self.bm25 = RecuperadorBM25(pasajes, sinonimos=sinonimos, **bm25)
        self.char = RecuperadorTFIDF(pasajes, analizador="char", ngramas=(3, 5),
                                     stopwords=bm25.get("stopwords", True),
                                     stemming=bm25.get("stemming", True),
                                     incluir_titulos=bm25.get("incluir_titulos", True))
        self.peso_char, self.sinonimos = peso_char, sinonimos

    def puntuar(self, pregunta: str) -> np.ndarray:
        q = expandir(pregunta) if self.sinonimos else pregunta
        return self.bm25.puntuar(pregunta) + self.peso_char * self.char.puntuar(q)

    def contribuciones(self, pregunta: str, i: int) -> dict[str, float]:
        out = self.bm25.contribuciones(pregunta, i)
        q = expandir(pregunta) if self.sinonimos else pregunta
        out["[similitud de caracteres]"] = float(self.peso_char * self.char.puntuar(q)[i])
        return out

    def cobertura(self, pregunta: str, i: int) -> float:
        return self.bm25.cobertura(pregunta, i)


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
    if modelo == "hibrido":
        return RecuperadorHibrido(pasajes, **c)
    return RecuperadorBM25(pasajes, **c)


def describir(config: dict) -> str:
    if config["modelo"] == "baseline":
        return "baseline"
    base = (f"{config['modelo']}"
            + (f"-{config['analizador']}{config['ngramas']}" if config["modelo"] == "tfidf"
               else f"(k1={config['k1']},b={config['b']})"))
    if config["modelo"] == "hibrido":
        base += f"+char×{config['peso_char']}"
    if config.get("sinonimos"):
        base += "+sinonimos"
    flags = [n for n, k in (("raices", "stemming"), ("sin_vacias", "stopwords"),
                            ("titulos", "incluir_titulos")) if config[k]]
    return base + ("[" + ",".join(flags) + "]" if flags else "")
