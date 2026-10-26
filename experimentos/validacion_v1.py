"""Validación cruzada de las mejoras de v1.0 frente al modelo adoptado en v0.2 (A4).

Usa EXACTAMENTE el mismo protocolo que experimentos/validacion_cruzada.py: validación
cruzada estratificada repetida 5 × 10 con la semilla 20260928 (mismas 50 particiones),
umbrales elegidos solo con las preguntas de entrenamiento de cada pliegue, McNemar exacta
por repetición y bootstrap pareado (5000 remuestreos) sobre la repetición 0.

Variantes (ablación; cada una agrega un ajuste):
    A4  BM25 adoptado en v0.2 (referencia)
    B1  A4 + expansión con diccionario de sinónimos
    B2  A4 + componente de n-gramas de caracteres (híbrido, peso fijo 5)
    B3  B1 + B2
    B4  B3 + derivación con dos señales (puntaje y cobertura)    <- candidato v1.0
    B5  A4 + derivación con dos señales (aporte aislado de la cobertura)

ADVERTENCIA DE FUGA: el diccionario de sinónimos se redactó mirando los errores de v0.2
sobre estas mismas 162 preguntas. Por eso la mejora de B1/B3/B4 en este experimento es
OPTIMISTA. La evidencia principal de generalización es el conjunto de prueba reservado
(experimentos/prueba_final.py), escrito después de congelar el modelo.

    python -m experimentos.validacion_v1
"""
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import binomtest
from sklearn.model_selection import RepeatedStratifiedKFold

from src.corpus import cargar_corpus, cargar_preguntas
from src.evaluacion import decisiones, desempatar, elegir_reglas, elegir_umbral, metricas, resumen_por_pregunta
from src.recuperadores import construir

SEMILLA = 20260928
N_PLIEGUES, N_REPETICIONES, N_BOOTSTRAP = 5, 10, 5000
SALIDA = Path(__file__).resolve().parent.parent / "resultados" / "v1"

BM25 = dict(k1=1.2, b=0.75, stemming=True, stopwords=True, incluir_titulos=True)
# (configuración del recuperador, ¿usa cobertura en la derivación?)
VARIANTES = {
    "A4 BM25 (v0.2)": (dict(modelo="bm25", **BM25), False),
    "B1 A4 + sinónimos": (dict(modelo="bm25", sinonimos=True, **BM25), False),
    "B2 A4 + caracteres": (dict(modelo="hibrido", peso_char=5.0, **BM25), False),
    "B3 sinónimos + caracteres": (dict(modelo="hibrido", peso_char=5.0, sinonimos=True, **BM25), False),
    "B4 B3 + derivación por cobertura": (dict(modelo="hibrido", peso_char=5.0, sinonimos=True, **BM25), True),
    "B5 A4 + derivación por cobertura": (dict(modelo="bm25", **BM25), True),
}
REFERENCIA, CANDIDATO = "A4 BM25 (v0.2)", "B4 B3 + derivación por cobertura"
CLAVES = ["exactitud_asistente", "respuesta_erronea", "hit1", "hit3", "mrr5",
          "precision_derivacion", "recall_derivacion"]


def ci95(v):
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def resumen_modelo(config, pasajes, textos, oro):
    r = construir(config, pasajes)
    matriz = desempatar(np.vstack([r.puntuar(t) for t in textos]), SEMILLA)
    top1 = matriz.argmax(axis=1)
    cob = np.array([r.cobertura(t, int(i)) if hasattr(r, "cobertura") else 1.0 for t, i in zip(textos, top1)])
    return resumen_por_pregunta(matriz, oro, cob)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    pasajes, preguntas = cargar_corpus(), cargar_preguntas()
    ids = [p.id for p in pasajes]
    oro = np.array([ids.index(q["pasaje_correcto"]) if q["pasaje_correcto"] != "NINGUNO" else -1 for q in preguntas])
    tipos = np.array([q["tipo"] for q in preguntas])
    textos = [q["pregunta"] for q in preguntas]
    n, dentro = len(preguntas), oro >= 0

    res = {m: resumen_modelo(c, pasajes, textos, oro) for m, (c, _) in VARIANTES.items()}
    cv = RepeatedStratifiedKFold(n_splits=N_PLIEGUES, n_repeats=N_REPETICIONES, random_state=SEMILLA)
    campos = ("correcta", "erronea", "rr", "deriva", "hit1", "hit3")
    oof = {m: [{c: np.zeros(n) for c in campos} for _ in range(N_REPETICIONES)] for m in VARIANTES}
    por_pliegue, entren, umbrales = ({m: [] for m in VARIANTES} for _ in range(3))

    for k, (tr, te) in enumerate(cv.split(np.zeros(n), tipos)):
        rep = k // N_PLIEGUES
        for m, (_, usa_cob) in VARIANTES.items():
            u, c = elegir_reglas(res[m], tr) if usa_cob else (elegir_umbral(res[m], tr), 0.0)
            umbrales[m].append((u, c))
            d = decisiones(res[m], u, te, c)
            por_pliegue[m].append(metricas(d))
            entren[m].append(metricas(decisiones(res[m], u, tr, c)))
            for campo in campos:
                oof[m][rep][campo][te] = d[campo]

    informe = dict(configuracion_experimento=dict(
        semilla=SEMILLA, pliegues=N_PLIEGUES, repeticiones=N_REPETICIONES, preguntas=n,
        advertencia="Diccionario de sinónimos redactado con el análisis de errores de estas mismas "
                    "preguntas: la mejora de B1, B3 y B4 es optimista. Ver resultados/v1/prueba_final.json."),
        modelos={})
    for m in VARIANTES:
        por_rep = [metricas(dict(correcta=o["correcta"].astype(bool), erronea=o["erronea"].astype(bool),
                                 deriva=o["deriva"].astype(bool), dentro=dentro, hit1=o["hit1"].astype(bool),
                                 hit3=o["hit3"].astype(bool), rr=o["rr"])) for o in oof[m]]
        fila = {}
        for c in CLAVES:
            vp = np.array([x[c] for x in por_pliegue[m]], float)
            vr = np.array([x[c] for x in por_rep], float)
            ve = np.array([x[c] for x in entren[m]], float)
            fila[c] = dict(media=float(np.nanmean(vr)), de_entre_repeticiones=float(np.nanstd(vr, ddof=1)),
                           de_entre_pliegues=float(np.nanstd(vp, ddof=1)), min_pliegue=float(np.nanmin(vp)),
                           max_pliegue=float(np.nanmax(vp)), media_entrenamiento=float(np.nanmean(ve)))
        fila["exactitud_por_tipo"] = {t: float(np.mean([o["correcta"][tipos == t].mean() for o in oof[m]]))
                                      for t in ("directa", "parafraseada", "fuera_alcance")}
        u = np.array([x[0] for x in umbrales[m]])
        cb = np.array([x[1] for x in umbrales[m]])
        fila["umbrales_elegidos"] = dict(puntaje_mediana=float(np.median(u)), puntaje_rango=[float(u.min()), float(u.max())],
                                         cobertura_frecuencias={str(k): v for k, v in Counter(cb.round(2).tolist()).most_common()})
        informe["modelos"][m] = fila

    rng = np.random.default_rng(SEMILLA)
    idx = rng.integers(0, n, size=(N_BOOTSTRAP, n))
    comparaciones = []
    pares = [(REFERENCIA, m) for m in VARIANTES if m != REFERENCIA] + [("B3 sinónimos + caracteres", CANDIDATO)]
    for a, b in pares:
        pruebas = []
        for rep in range(N_REPETICIONES):
            ca, cb_ = oof[a][rep]["correcta"].astype(bool), oof[b][rep]["correcta"].astype(bool)
            sb, sa = int((~ca & cb_).sum()), int((ca & ~cb_).sum())
            pruebas.append(dict(repeticion=rep, solo_B_acierta=sb, solo_A_acierta=sa,
                                p_mcnemar_exacta=float(binomtest(sb, sb + sa, 0.5).pvalue) if sb + sa else 1.0))
        boots = {}
        for c in ("correcta", "erronea"):
            va, vb = oof[a][0][c][idx].mean(1), oof[b][0][c][idx].mean(1)
            boots[c] = dict(diferencia_B_menos_A=ci95(vb - va),
                            diferencia_puntual=float(oof[b][0][c].mean() - oof[a][0][c].mean()))
        ps = [p["p_mcnemar_exacta"] for p in pruebas]
        comparaciones.append(dict(A=a, B=b, p_mcnemar_rango=[min(ps), max(ps)], pruebas_por_repeticion=pruebas,
                                  bootstrap_repeticion_0=boots))
    informe["comparaciones_pareadas"] = comparaciones

    (SALIDA / "metricas_validacion_v1.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n",
                                                        encoding="utf-8")
    with (SALIDA / "predicciones_fuera_de_pliegue_v1_rep0.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "tipo", "pasaje_correcto", "a4_correcta", "b4_correcta", "b4_deriva", "pregunta"])
        for i, q in enumerate(preguntas):
            w.writerow([q["id"], q["tipo"], q["pasaje_correcto"], int(oof[REFERENCIA][0]["correcta"][i]),
                        int(oof[CANDIDATO][0]["correcta"][i]), int(oof[CANDIDATO][0]["deriva"][i]), q["pregunta"]])

    for m, fila in informe["modelos"].items():
        print(f"{m:36s} exact={fila['exactitud_asistente']['media']:.3f}±{fila['exactitud_asistente']['de_entre_pliegues']:.3f} "
              f"err={fila['respuesta_erronea']['media']:.3f} hit1={fila['hit1']['media']:.3f} "
              f"hit3={fila['hit3']['media']:.3f} rec_der={fila['recall_derivacion']['media']:.3f} "
              f"tipos={ {k: round(v, 3) for k, v in fila['exactitud_por_tipo'].items()} }")
    for c in comparaciones:
        print(f"{c['B']} vs {c['A']}: dif={c['bootstrap_repeticion_0']['correcta']['diferencia_puntual']:+.3f} "
              f"IC={[round(x, 3) for x in c['bootstrap_repeticion_0']['correcta']['diferencia_B_menos_A']]} "
              f"McNemar p∈{[round(x, 4) for x in c['p_mcnemar_rango']]}")


if __name__ == "__main__":
    main()
