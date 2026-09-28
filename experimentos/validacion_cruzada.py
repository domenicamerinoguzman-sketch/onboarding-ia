"""Validación cruzada estratificada repetida (10 x 5) del baseline y del modelo ajustado.

En cada pliegue, el umbral de derivación y (para el modelo ajustado) la configuración de
hiperparámetros se eligen SOLO con las preguntas de entrenamiento; las preguntas de prueba
se usan una única vez para medir. Ejecutar desde la raíz del repositorio:

    python -m experimentos.validacion_cruzada
"""
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, wilcoxon
from sklearn.model_selection import RepeatedStratifiedKFold

from src.corpus import cargar_corpus, cargar_preguntas
from src.evaluacion import decisiones, desempatar, elegir_umbral, metricas, resumen_por_pregunta
from src.recuperadores import construir, describir, espacio_hiperparametros

SEMILLA = 20260928
N_PLIEGUES, N_REPETICIONES, N_BOOTSTRAP = 5, 10, 5000
SALIDA = Path(__file__).resolve().parent.parent / "resultados"

# Variantes fijas para medir el aporte de cada ajuste (ablación). La última se elige por rejilla.
VARIANTES = {
    "A0 Baseline palabras clave": dict(modelo="baseline"),
    "A1 TF-IDF sin preprocesar": dict(modelo="tfidf", analizador="word", ngramas=(1, 1),
                                      stemming=False, stopwords=False, incluir_titulos=False),
    "A2 + normalización (vacías, raíces)": dict(modelo="tfidf", analizador="word", ngramas=(1, 1),
                                                stemming=True, stopwords=True, incluir_titulos=False),
    "A3 + títulos en el índice": dict(modelo="tfidf", analizador="word", ngramas=(1, 1),
                                      stemming=True, stopwords=True, incluir_titulos=True),
    "A4 BM25 por defecto": dict(modelo="bm25", k1=1.2, b=0.75, stemming=True, stopwords=True,
                                incluir_titulos=True),
}
AJUSTADO = "A5 Ajustado (rejilla de 120 configuraciones)"


def ci95(valores):
    return [float(np.percentile(valores, 2.5)), float(np.percentile(valores, 97.5))]


def main():
    SALIDA.mkdir(exist_ok=True)
    pasajes = cargar_corpus()
    preguntas = cargar_preguntas()
    ids = [p.id for p in pasajes]
    oro = np.array([ids.index(q["pasaje_correcto"]) if q["pasaje_correcto"] != "NINGUNO" else -1
                    for q in preguntas])
    tipos = np.array([q["tipo"] for q in preguntas])
    textos = [q["pregunta"] for q in preguntas]

    def resumen(config):
        r = construir(config, pasajes)
        return resumen_por_pregunta(desempatar(np.vstack([r.puntuar(t) for t in textos]), SEMILLA), oro)

    fijos = {n: resumen(c) for n, c in VARIANTES.items()}
    rejilla = espacio_hiperparametros()
    res_rejilla = [resumen(c) for c in rejilla]

    cv = RepeatedStratifiedKFold(n_splits=N_PLIEGUES, n_repeats=N_REPETICIONES, random_state=SEMILLA)
    nombres = list(VARIANTES) + [AJUSTADO]
    n = len(preguntas)
    # Predicciones fuera de pliegue por repetición: correcta/erronea/rr/deriva/top1 por pregunta.
    oof = {m: [dict(correcta=np.zeros(n, bool), erronea=np.zeros(n, bool), rr=np.zeros(n),
                    deriva=np.zeros(n, bool), hit1=np.zeros(n, bool), hit3=np.zeros(n, bool),
                    top1=np.zeros(n, int)) for _ in range(N_REPETICIONES)] for m in nombres}
    por_pliegue = {m: [] for m in nombres}
    entrenamiento = {m: [] for m in nombres}
    seleccion = []

    for k, (tr, te) in enumerate(cv.split(np.zeros(n), tipos)):
        rep = k // N_PLIEGUES
        elegidos = {}
        for m, res in fijos.items():
            elegidos[m] = (res, elegir_umbral(res, tr))
        # Modelo ajustado: mejor configuración + umbral según exactitud en entrenamiento (desempate: MRR).
        mejor = None
        for j, res in enumerate(res_rejilla):
            u = elegir_umbral(res, tr)
            d = decisiones(res, u, tr)
            clave = (d["correcta"].mean(), d["rr"][d["dentro"]].mean())
            if mejor is None or clave > mejor[0]:
                mejor = (clave, j, u)
        _, j, u = mejor
        elegidos[AJUSTADO] = (res_rejilla[j], u)
        seleccion.append(dict(pliegue=k, repeticion=rep, configuracion=describir(rejilla[j]),
                              umbral=round(u, 4)))

        for m, (res, u) in elegidos.items():
            d_te = decisiones(res, u, te)
            por_pliegue[m].append(metricas(d_te))
            entrenamiento[m].append(metricas(decisiones(res, u, tr)))
            for campo in ("correcta", "erronea", "rr", "deriva", "hit1", "hit3"):
                oof[m][rep][campo][te] = d_te[campo]
            oof[m][rep]["top1"][te] = res["top1"][te]

    dentro = oro >= 0
    informe = dict(configuracion_experimento=dict(
        semilla=SEMILLA, pliegues=N_PLIEGUES, repeticiones=N_REPETICIONES,
        preguntas=n, dentro_alcance=int(dentro.sum()), fuera_alcance=int((~dentro).sum()),
        por_tipo=dict(Counter(tipos)), pasajes=len(pasajes), configuraciones_rejilla=len(rejilla)),
        modelos={})

    claves = ["exactitud_asistente", "respuesta_erronea", "hit1", "hit3", "mrr5",
              "precision_derivacion", "recall_derivacion"]
    for m in nombres:
        por_rep = []
        for rep in range(N_REPETICIONES):
            o = oof[m][rep]
            por_rep.append(metricas(dict(correcta=o["correcta"], erronea=o["erronea"], deriva=o["deriva"],
                                         dentro=dentro, hit1=o["hit1"], hit3=o["hit3"], rr=o["rr"])))
        fila = {}
        for c in claves:
            vp = np.array([x[c] for x in por_pliegue[m]], float)
            vr = np.array([x[c] for x in por_rep], float)
            ve = np.array([x[c] for x in entrenamiento[m]], float)
            fila[c] = dict(media=float(np.nanmean(vr)), de_entre_repeticiones=float(np.nanstd(vr, ddof=1)),
                           de_entre_pliegues=float(np.nanstd(vp, ddof=1)),
                           min_pliegue=float(np.nanmin(vp)), max_pliegue=float(np.nanmax(vp)),
                           media_entrenamiento=float(np.nanmean(ve)))
        # Exactitud por tipo de pregunta (promedio de las 10 repeticiones).
        fila["exactitud_por_tipo"] = {
            t: float(np.mean([oof[m][r]["correcta"][tipos == t].mean() for r in range(N_REPETICIONES)]))
            for t in ("directa", "parafraseada", "fuera_alcance")}
        informe["modelos"][m] = fila

    # Pruebas pareadas sobre las predicciones fuera de pliegue de cada repetición:
    # McNemar exacta (acierto por pregunta) y Wilcoxon (rango recíproco, preguntas dentro del alcance).
    # Bootstrap pareado (5000 remuestreos de preguntas) sobre la repetición 0.
    rng = np.random.default_rng(SEMILLA)
    base, final = "A0 Baseline palabras clave", "A4 BM25 por defecto"
    pares = [(base, final), (base, AJUSTADO), (final, AJUSTADO)]
    idx = rng.integers(0, n, size=(N_BOOTSTRAP, n))
    idx_in = rng.integers(0, dentro.sum(), size=(N_BOOTSTRAP, int(dentro.sum())))
    comparaciones = []
    for a_nom, b_nom in pares:
        pruebas = []
        for rep in range(N_REPETICIONES):
            ca, cb = oof[a_nom][rep]["correcta"], oof[b_nom][rep]["correcta"]
            solo_b, solo_a = int((~ca & cb).sum()), int((ca & ~cb).sum())
            p_mc = binomtest(solo_b, solo_b + solo_a, 0.5).pvalue if solo_b + solo_a else 1.0
            ra, rb = oof[a_nom][rep]["rr"][dentro], oof[b_nom][rep]["rr"][dentro]
            p_w = float(wilcoxon(rb, ra, zero_method="wilcox").pvalue) if np.any(ra != rb) else 1.0
            pruebas.append(dict(repeticion=rep, solo_B_acierta=solo_b, solo_A_acierta=solo_a,
                                p_mcnemar_exacta=float(p_mc), p_wilcoxon_rr=p_w))
        boots = {}
        for c in ("correcta", "erronea"):
            va = oof[a_nom][0][c].astype(float)[idx].mean(axis=1)
            vb = oof[b_nom][0][c].astype(float)[idx].mean(axis=1)
            boots[c] = dict(A=ci95(va), B=ci95(vb), diferencia_B_menos_A=ci95(vb - va),
                            diferencia_puntual=float(oof[b_nom][0][c].mean() - oof[a_nom][0][c].mean()))
        va = oof[a_nom][0]["rr"][dentro][idx_in].mean(1)
        vb = oof[b_nom][0]["rr"][dentro][idx_in].mean(1)
        boots["mrr5"] = dict(A=ci95(va), B=ci95(vb), diferencia_B_menos_A=ci95(vb - va))
        comparaciones.append(dict(
            A=a_nom, B=b_nom, pruebas_por_repeticion=pruebas,
            p_mcnemar_rango=[min(p["p_mcnemar_exacta"] for p in pruebas), max(p["p_mcnemar_exacta"] for p in pruebas)],
            p_wilcoxon_rango=[min(p["p_wilcoxon_rr"] for p in pruebas), max(p["p_wilcoxon_rr"] for p in pruebas)],
            bootstrap_repeticion_0=boots))
    informe["comparaciones_pareadas"] = comparaciones
    aj = AJUSTADO
    informe["seleccion_hiperparametros"] = dict(Counter(s["configuracion"] for s in seleccion).most_common())

    (SALIDA / "metricas_validacion.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (SALIDA / "seleccion_por_pliegue.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=seleccion[0].keys())
        w.writeheader(); w.writerows(seleccion)
    with (SALIDA / "predicciones_fuera_de_pliegue_rep0.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "tipo", "pasaje_correcto", "baseline_top1", "baseline_deriva", "baseline_correcta",
                    "ajustado_top1", "ajustado_deriva", "ajustado_correcta", "pregunta"])
        for i, q in enumerate(preguntas):
            w.writerow([q["id"], q["tipo"], q["pasaje_correcto"],
                        ids[oof[base][0]["top1"][i]], int(oof[base][0]["deriva"][i]), int(oof[base][0]["correcta"][i]),
                        ids[oof[aj][0]["top1"][i]], int(oof[aj][0]["deriva"][i]), int(oof[aj][0]["correcta"][i]),
                        q["pregunta"]])
    print(json.dumps({m: {c: round(v["media"], 3) for c, v in informe["modelos"][m].items()
                          if isinstance(v, dict) and "media" in v} for m in nombres}, ensure_ascii=False, indent=1))
    for c in comparaciones:
        print(c["A"], "vs", c["B"], "McNemar p", c["p_mcnemar_rango"], "Wilcoxon p", c["p_wilcoxon_rango"])
        print("  ", json.dumps(c["bootstrap_repeticion_0"]))
    print(informe["seleccion_hiperparametros"])


if __name__ == "__main__":
    main()
