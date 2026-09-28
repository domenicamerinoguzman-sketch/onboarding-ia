"""Carga del corpus de políticas y del set de preguntas de evaluación."""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CORPUS = RAIZ / "data" / "corpus" / "politicas_induccion.md"
RUTA_PREGUNTAS = RAIZ / "data" / "preguntas_evaluacion.csv"


@dataclass
class Pasaje:
    id: str
    documento: str
    titulo: str
    texto: str


def cargar_corpus(ruta: Path = RUTA_CORPUS) -> list[Pasaje]:
    """Divide el markdown en pasajes: '# DOCxx nombre' abre documento, '## Pxx | título' abre pasaje."""
    pasajes, documento, actual = [], "", None
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        m_doc = re.match(r"^# (DOC\d+) (.+)$", linea)
        m_pas = re.match(r"^## (P\d+) \| (.+)$", linea)
        if m_doc:
            documento = m_doc.group(2).strip()
        elif m_pas:
            actual = Pasaje(m_pas.group(1), documento, m_pas.group(2).strip(), "")
            pasajes.append(actual)
        elif actual is not None and linea.strip():
            actual.texto = (actual.texto + " " + linea.strip()).strip()
    return pasajes


def cargar_preguntas(ruta: Path = RUTA_PREGUNTAS) -> list[dict]:
    with ruta.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))
