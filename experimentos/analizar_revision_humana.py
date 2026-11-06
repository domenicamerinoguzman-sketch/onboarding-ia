"""Analiza la revisión humana independiente de una muestra de respuestas del asistente.

Entrada: los dos archivos que generó experimentos/evaluar_generacion.py, ya llenos por dos
revisores que trabajaron por separado (rúbrica en docs/rubrica_revision_humana.md):
    resultados/v1/revision_humana_<etiqueta>_revisor1.csv
    resultados/v1/revision_humana_<etiqueta>_revisor2.csv
Opcional: revision_humana_<etiqueta>_consenso.csv con los desacuerdos resueltos por discusión.

    python -m experimentos.analizar_revision_humana --etiqueta llm_local_qwen2.5_3b

Salida: resultados/v1/revision_humana_<etiqueta>_analisis.json con
- acuerdo entre revisores (porcentaje y kappa de Cohen; kappa ponderada para la utilidad);
- acción correcta, tasa de alucinación humana y utilidad, con IC 95 % de Wilson;
- respuestas que el verificador automático aceptó pero los revisores juzgaron no fieles;
- lista de desacuerdos para resolver si no hay archivo de consenso.
"""
import argparse
import json
import math
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from src.lectura import leer_csv

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "resultados" / "v1"


def wilson(exitos: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = exitos / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, c - m), 4), round(min(1.0, c + m), 4)]


def leer(ruta: Path) -> dict[str, dict]:
    return {r["id"]: r for r in leer_csv(ruta)}


def valor(v: str, permitidos: set[str]) -> str:
    v = (v or "").strip().upper().replace("N/A", "NA")
    if v not in permitidos:
        raise ValueError(v)
    return v


def validar(rev: dict[str, dict], nombre: str) -> list[str]:
    errores = []
    for i, r in rev.items():
        try:
            valor(r["revision_correcta"], {"0", "1"})
            fiel = valor(r["revision_fiel"], {"0", "1", "NA"})
            if r.get("accion") == "responder" and fiel == "NA":
                errores.append(f"{nombre} {i}: 'revision_fiel' no puede ser NA si el asistente respondió")
            if r.get("accion") == "responder":
                valor(r["revision_util"], {"1", "2", "3", "4", "5"})
        except ValueError as e:
            errores.append(f"{nombre} {i}: valor no válido '{e}'")
    return errores


def proporcion(xs: list[int]) -> dict:
    return dict(n=len(xs), valor=round(sum(xs) / len(xs), 4) if xs else None, ic95=wilson(sum(xs), len(xs)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etiqueta", default="llm_local_qwen2.5_3b")
    a = ap.parse_args()
    base = SALIDA / f"revision_humana_{a.etiqueta}"
    r1, r2 = leer(Path(f"{base}_revisor1.csv")), leer(Path(f"{base}_revisor2.csv"))
    errores = validar(r1, "revisor1") + validar(r2, "revisor2")
    if set(r1) != set(r2):
        errores.append("los dos archivos no tienen las mismas preguntas")
    if errores:
        raise SystemExit("Corrija la revisión antes de analizar:\n- " + "\n- ".join(errores))

    ids = sorted(r1)
    get = lambda r, i, c: valor(r[i][c], {"0", "1", "2", "3", "4", "5", "NA"})
    respondidas = [i for i in ids if r1[i].get("accion") == "responder"]
    acuerdo = {}
    for campo, lista in (("revision_correcta", ids), ("revision_fiel", respondidas), ("revision_util", respondidas)):
        x = [get(r1, i, campo) for i in lista]
        y = [get(r2, i, campo) for i in lista]
        k = cohen_kappa_score(x, y, weights="quadratic" if campo == "revision_util" else None) if len(set(x + y)) > 1 else 1.0
        acuerdo[campo] = dict(n=len(lista), porcentaje=round(sum(p == q for p, q in zip(x, y)) / len(lista), 4) if lista else None,
                              kappa=round(float(k), 4), tipo_kappa="ponderada cuadrática" if campo == "revision_util" else "Cohen")
    desacuerdos = [dict(id=i, campo=c, revisor1=r1[i][c], revisor2=r2[i][c]) for i in ids
                   for c in ("revision_correcta", "revision_fiel") if r1[i][c].strip().upper() != r2[i][c].strip().upper()]

    ruta_cons = Path(f"{base}_consenso.csv")
    if ruta_cons.exists():
        cons = leer(ruta_cons)
        err = validar(cons, "consenso")
        if err:
            raise SystemExit("Corrija el consenso:\n- " + "\n- ".join(err))
        fuente = "consenso"
    else:
        cons, fuente = None, "acuerdo (solo casos en que ambos revisores coinciden)"

    def final(i, campo):
        if cons:
            return get(cons, i, campo)
        p, q = get(r1, i, campo), get(r2, i, campo)
        return p if p == q else None

    correcta = [int(v) for i in ids if (v := final(i, "revision_correcta")) is not None]
    fiel = [int(v) for i in respondidas if (v := final(i, "revision_fiel")) not in (None, "NA")]
    util = [(int(get(r1, i, "revision_util")) + int(get(r2, i, "revision_util"))) / 2 for i in respondidas]

    gen = SALIDA / f"generacion_{a.etiqueta}_reservado.csv"
    pasadas_por_alto = []
    if gen.exists():
        auto = {r["id"]: r for r in leer_csv(gen)}
        pasadas_por_alto = [i for i in respondidas if auto.get(i, {}).get("fiel") == "1" and final(i, "revision_fiel") == "0"]

    informe = dict(
        etiqueta=a.etiqueta, muestra=len(ids), respondidas=len(respondidas), base_de_los_resultados=fuente,
        acuerdo_entre_revisores=acuerdo,
        accion_correcta=proporcion(correcta),
        tasa_alucinacion_humana=proporcion([1 - x for x in fiel]),
        utilidad=dict(media=round(sum(util) / len(util), 3) if util else None,
                      proporcion_4_o_mas=proporcion([int(u >= 4) for u in util])),
        no_fieles_que_paso_el_verificador=dict(cantidad=len(pasadas_por_alto), ids=pasadas_por_alto),
        desacuerdos_pendientes=[] if cons else desacuerdos,
        nota="Muestra aleatoria de 30 respuestas del conjunto reservado; los IC de Wilson son amplios con este tamaño.",
    )
    destino = Path(f"{base}_analisis.json")
    destino.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: informe[k] for k in ("acuerdo_entre_revisores", "accion_correcta", "tasa_alucinacion_humana",
                                              "utilidad", "no_fieles_que_paso_el_verificador")}, ensure_ascii=False, indent=1))
    if desacuerdos and not cons:
        print(f"\n{len(desacuerdos)} desacuerdos: resuélvalos y guarde {ruta_cons.name} para el resultado final.")


if __name__ == "__main__":
    main()
