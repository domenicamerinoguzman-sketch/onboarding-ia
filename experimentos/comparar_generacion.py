"""Comparación pareada de dos modos de generación sobre las mismas preguntas.

    python -m experimentos.comparar_generacion --a llm_local_qwen2.5_3b --b extractivo

Lee resultados/v1/generacion_<etiqueta>_<conjunto>.csv de ambos modos y calcula, por conjunto:
exactitud y tasa de respuesta errónea de cada modo, diferencia con IC 95 % por bootstrap pareado
(5000 remuestreos, semilla 20260928), prueba de McNemar exacta sobre la exactitud, exactitud por
tipo de pregunta y derivaciones del LLM en preguntas que sí tenían respuesta.
Salida: resultados/v1/comparacion_<a>_vs_<b>.json
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from src.lectura import leer_csv

SALIDA = Path(__file__).resolve().parent.parent / "resultados" / "v1"


def comparar(a: str, b: str, conjunto: str) -> dict:
    A = {r["id"]: r for r in leer_csv(SALIDA / f"generacion_{a}_{conjunto}.csv")}
    B = {r["id"]: r for r in leer_csv(SALIDA / f"generacion_{b}_{conjunto}.csv")}
    ids = sorted(set(A) & set(B))
    ca, cb = (np.array([int(X[i]["correcta"]) for i in ids]) for X in (A, B))
    ea, eb = (np.array([X[i]["accion"] == "responder" and X[i]["correcta"] == "0" for i in ids], dtype=float) for X in (A, B))
    solo_a, solo_b = int(((ca == 1) & (cb == 0)).sum()), int(((ca == 0) & (cb == 1)).sum())
    idx = np.random.default_rng(20260928).integers(0, len(ids), (5000, len(ids)))
    ic = lambda x, y: [round(float(v), 4) for v in np.percentile(x[idx].mean(1) - y[idx].mean(1), [2.5, 97.5])]
    por_tipo = {}
    for t in sorted({A[i]["tipo"] for i in ids}):
        s = [k for k, i in enumerate(ids) if A[i]["tipo"] == t]
        por_tipo[t] = dict(n=len(s), **{a: round(float(ca[s].mean()), 4), b: round(float(cb[s].mean()), 4)})
    deriva_a = [i for i in ids if A[i]["tipo"] != "fuera_alcance" and A[i]["accion"] != "responder"
                and B[i]["accion"] == "responder" and B[i]["correcta"] == "1"]
    return dict(n=len(ids),
                exactitud={a: round(float(ca.mean()), 4), b: round(float(cb.mean()), 4),
                           "diferencia": round(float(ca.mean() - cb.mean()), 4), "ic95_bootstrap": ic(ca, cb),
                           "mcnemar_p": round(float(binomtest(solo_a, solo_a + solo_b).pvalue), 4) if solo_a + solo_b else 1.0,
                           f"solo_acierta_{a}": solo_a, f"solo_acierta_{b}": solo_b},
                tasa_respuesta_erronea={a: round(float(ea.mean()), 4), b: round(float(eb.mean()), 4),
                                        "diferencia": round(float(ea.mean() - eb.mean()), 4), "ic95_bootstrap": ic(ea, eb)},
                exactitud_por_tipo=por_tipo,
                derivaciones_de_a_en_preguntas_que_b_acertaba=dict(n=len(deriva_a), ids=deriva_a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="llm_local_qwen2.5_3b")
    ap.add_argument("--b", default="extractivo")
    ap.add_argument("--conjuntos", default="reservado,desarrollo")
    x = ap.parse_args()
    res = dict(a=x.a, b=x.b, **{c: comparar(x.a, x.b, c) for c in x.conjuntos.split(",")})
    (SALIDA / f"comparacion_{x.a}_vs_{x.b}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
