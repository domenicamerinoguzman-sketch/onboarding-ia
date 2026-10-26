"""Expansión de consultas con un diccionario de sinónimos del dominio.

La expansión agrega a la consulta los términos del vocabulario de las políticas que
corresponden a expresiones coloquiales ("carnet" -> "credencial"). No reemplaza la consulta
original: solo añade términos, para que la recuperación léxica (BM25) los pueda emparejar.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from .preprocesamiento import quitar_tildes

RUTA_SINONIMOS = Path(__file__).resolve().parent.parent / "data" / "sinonimos.json"


@lru_cache(maxsize=4)
def cargar_sinonimos(ruta: str = str(RUTA_SINONIMOS)) -> tuple[tuple[str, re.Pattern, str], ...]:
    """Tupla de (clave normalizada, patrón, términos de destino), frases largas primero."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))["expansiones"]
    claves = sorted(datos, key=lambda k: -len(k))
    salida = []
    for k in claves:
        if datos[k].strip():
            clave = quitar_tildes(k.lower())
            salida.append((clave, re.compile(r"\b" + re.escape(clave) + r"\b"), datos[k]))
    return tuple(salida)


def expandir(pregunta: str, ruta: str = str(RUTA_SINONIMOS)) -> str:
    """Devuelve la pregunta original seguida de los términos de expansión que apliquen."""
    normal = quitar_tildes(pregunta.lower())
    extra = [destino for _, patron, destino in cargar_sinonimos(ruta) if patron.search(normal)]
    return pregunta if not extra else pregunta + " " + " ".join(extra)


def expansiones_aplicadas(pregunta: str, ruta: str = str(RUTA_SINONIMOS)) -> list[str]:
    """Lista legible de las expansiones usadas (para trazabilidad en la respuesta)."""
    normal = quitar_tildes(pregunta.lower())
    return [f"{clave} -> {destino}" for clave, patron, destino in cargar_sinonimos(ruta)
            if patron.search(normal)]
