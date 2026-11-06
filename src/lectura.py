"""Lectura tolerante de archivos CSV llenados a mano o guardados desde Excel."""
import csv
from pathlib import Path


def leer_csv(ruta: Path | str) -> list[dict]:
    """Acepta coma o punto y coma (Excel en español), UTF-8 (con o sin BOM) o Windows-1252.

    Quita espacios de encabezados y valores, y descarta filas vacías.
    """
    datos = Path(ruta).read_bytes()
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = datos.decode("cp1252")
    lineas = texto.splitlines()
    if not lineas:
        return []
    sep = ";" if lineas[0].count(";") > lineas[0].count(",") else ","
    filas = []
    for r in csv.DictReader(lineas, delimiter=sep):
        fila = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        if any(fila.values()):
            filas.append(fila)
    return filas


def numero(v: str) -> float | None:
    """'12,5' o '12.5' -> 12.5; vacío -> None."""
    v = (v or "").strip().replace(" ", "")
    if not v:
        return None
    if "," in v and "." not in v:
        v = v.replace(",", ".")
    return float(v)
