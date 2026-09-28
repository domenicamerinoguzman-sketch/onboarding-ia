"""Normalización de texto en español para la recuperación de pasajes."""
import re
import unicodedata
from functools import lru_cache

from nltk.stem.snowball import SpanishStemmer

# Lista corta de palabras vacías (sin tildes, porque se aplican tras normalizar).
STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes aqui asi aun bajo bien cada como con
contra cual cuales cualquier cuando cuanto cuanta cuantos cuantas de del desde donde dos e el ella
ellas ello ellos en entre era eres es esa esas ese eso esos esta estas este esto estos estoy fue
ha hace hacer hasta hay he la las le les lo los mas me mi mis mucho muy nada ni no nos nosotros o
otra otro para pero poco por porque puede pueden puedo que quien se sea ser si sin sobre son su
sus tal tambien tan tanto te tengo tener tiene tienen todo todos tu tus un una uno unos unas y ya
yo debo debe deben hago dan dar da
""".split())

_stemmer = SpanishStemmer()


def quitar_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=50000)
def _raiz(token: str) -> str:
    return _stemmer.stem(token)


def tokenizar(texto: str, stopwords: bool = True, stemming: bool = True) -> list[str]:
    """Minúsculas, sin tildes, tokens alfanuméricos; opcionalmente sin palabras vacías y con raíces."""
    tokens = re.findall(r"[a-z0-9ñ]+", quitar_tildes(texto.lower()))
    if stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    if stemming:
        tokens = [_raiz(t) for t in tokens]
    return tokens
