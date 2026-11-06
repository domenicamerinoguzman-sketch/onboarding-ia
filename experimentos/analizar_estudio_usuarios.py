"""Analiza el estudio con usuarios de Talento Humano y colaboradores nuevos (OE4 y OE5).

Entradas (data/reales/, anonimizadas; NO se suben a GitHub). Plantillas en data/reales/plantillas/:
- sesiones_analistas.csv: minutos por tarea en las sesiones cronometradas (diseño cruzado:
  cada analista procesa cuatro casos de forma manual y cuatro con el prototipo, en orden AB o BA).
- cuestionario_usuarios.csv: SUS (10 ítems, 1–5) y preguntas de satisfacción (1–5).
- tareas_usabilidad.csv: resultado de cada escenario de la prueba de usabilidad del asistente.
Opcional: resultados/validacion_empirica/linea_base.json (de linea_base_real.py) para estimar la
reducción sobre el proceso completo.

    python -m experimentos.analizar_estudio_usuarios              # datos reales
    python -m experimentos.analizar_estudio_usuarios --ejemplo    # datos de ejemplo SINTÉTICOS

Criterios definidos ANTES de recoger datos (protocolo, docs/validacion_empirica/):
- OE4: reducción del tiempo de las tareas medidas ≥ 50 %. «Cumple con holgura» si el límite
  inferior del IC 95 % es ≥ 50 %; «cumple (estimación puntual)» si solo la estimación puntual lo es.
- OE5: ≥ 85 % de participantes con satisfacción general ≥ 4 (escala 1–5), con la misma regla.
  El SUS se interpreta con el umbral de 68 (promedio de referencia).
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import wilcoxon

from src.lectura import leer_csv, numero

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = {t["id"]: t for t in json.loads((RAIZ / "config" / "flujo_onboarding.json").read_text(encoding="utf-8"))["tareas"]}
FLUJO["T99"] = dict(nombre="Otra actividad del onboarding", to_be="manual")
ESCENARIOS = {r["escenario"]: r for r in leer_csv(RAIZ / "validacion" / "escenarios_usabilidad.csv")}
PAR_DE_CASO = {"S1": 1, "S5": 1, "S2": 2, "S6": 2, "S3": 3, "S7": 3, "S4": 4, "S8": 4}  # casos equivalentes
SEMILLA, N_BOOT, META_TIEMPO, META_SATISFACCION, SUS_REFERENCIA = 20260928, 5000, 0.50, 0.85, 68


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, c - m), 4), round(min(1.0, c + m), 4)]


def veredicto(punto, ic, meta):
    if punto is None:
        return "PENDIENTE"
    if ic and ic[0] >= meta:
        return "cumple con holgura (límite inferior del IC ≥ meta)"
    if punto >= meta:
        return "cumple (estimación puntual); el IC incluye valores bajo la meta"
    return "no cumple"


# ------------------------------------------------------------------ sesiones (OE4)
def validar_sesiones(filas):
    err = []
    for k, f in enumerate(filas, 2):
        if f.get("condicion") not in ("manual", "prototipo"):
            err.append(f"sesiones fila {k}: condicion debe ser manual o prototipo")
        if f.get("tarea") not in FLUJO:
            err.append(f"sesiones fila {k}: tarea '{f.get('tarea')}' no existe")
        if f.get("caso") not in PAR_DE_CASO:
            err.append(f"sesiones fila {k}: caso '{f.get('caso')}' debe ser S1–S8")
        try:
            if numero(f.get("minutos")) is None:
                err.append(f"sesiones fila {k}: falta minutos")
        except ValueError:
            err.append(f"sesiones fila {k}: minutos no es un número")
    return err


def analizar_sesiones(filas, rng):
    total = defaultdict(float)          # (analista, caso, condicion) -> minutos
    errores = defaultdict(float)
    incompletas = defaultdict(int)
    por_tarea = defaultdict(lambda: defaultdict(list))  # tarea -> condicion -> [min por caso]
    tarea_caso = defaultdict(float)
    orden = {}
    for f in filas:
        clave = (f["analista"], f["caso"], f["condicion"])
        m = numero(f["minutos"])
        total[clave] += m
        tarea_caso[(f["analista"], f["caso"], f["condicion"], f["tarea"])] += m
        errores[clave] += numero(f.get("errores", "")) or 0
        incompletas[clave] += int(f.get("completada", "1") == "0")
        orden[f["analista"]] = f.get("orden", "")
    for (an, caso, cond, tarea), m in tarea_caso.items():
        por_tarea[tarea][cond].append(m)

    pares = []  # (analista, par, manual, prototipo)
    for an in sorted({k[0] for k in total}):
        man = {PAR_DE_CASO[c]: v for (a, c, cond), v in total.items() if a == an and cond == "manual"}
        pro = {PAR_DE_CASO[c]: v for (a, c, cond), v in total.items() if a == an and cond == "prototipo"}
        for p in sorted(set(man) & set(pro)):
            pares.append((an, p, man[p], pro[p]))
    if not pares:
        return dict(etiqueta="PENDIENTE (no hay pares manual–prototipo)")
    m = np.array([x[2] for x in pares])
    p = np.array([x[3] for x in pares])
    red = 1 - p.mean() / m.mean()
    idx = rng.integers(0, len(pares), size=(N_BOOT, len(pares)))
    boot = 1 - p[idx].mean(1) / m[idx].mean(1)
    ic = [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)]
    dif = m - p
    prueba = wilcoxon(m, p, alternative="greater") if len(pares) >= 5 and np.any(dif != 0) else None

    tareas = {}
    for t, d in sorted(por_tarea.items()):
        mm, pp = np.mean(d.get("manual", [np.nan])), np.mean(d.get("prototipo", [np.nan]))
        tareas[t] = dict(nombre=FLUJO[t]["nombre"], to_be=FLUJO[t]["to_be"],
                         minutos_manual=round(float(mm), 2), minutos_prototipo=round(float(pp), 2),
                         reduccion=round(float(1 - pp / mm), 4) if mm and not np.isnan(mm) and not np.isnan(pp) else None,
                         n_manual=len(d.get("manual", [])), n_prototipo=len(d.get("prototipo", [])))
    err_cond = {c: [v for (a, cs, cd), v in errores.items() if cd == c] for c in ("manual", "prototipo")}
    inc_cond = {c: [v for (a, cs, cd), v in incompletas.items() if cd == c] for c in ("manual", "prototipo")}
    por_orden = defaultdict(list)
    for an, _, mm_, pp_ in pares:
        por_orden[orden.get(an, "")].append(1 - pp_ / mm_)
    return dict(
        analistas=len({x[0] for x in pares}), pares=len(pares),
        minutos_por_caso=dict(manual=dict(media=round(float(m.mean()), 2), de=round(float(m.std(ddof=1)), 2)),
                              prototipo=dict(media=round(float(p.mean()), 2), de=round(float(p.std(ddof=1)), 2))),
        reduccion_tareas_medidas=dict(valor=round(float(red), 4), ic95=ic,
                                      wilcoxon_p=round(float(prueba.pvalue), 5) if prueba else None,
                                      etiqueta=f"DATO VALIDADO (experimento controlado, {len(pares)} pares)",
                                      veredicto_meta_50=veredicto(float(red), ic, META_TIEMPO)),
        errores_por_caso={c: round(float(np.mean(v)), 3) if v else None for c, v in err_cond.items()},
        tareas_incompletas_por_caso={c: round(float(np.mean(v)), 3) if v else None for c, v in inc_cond.items()},
        reduccion_por_orden={o: round(float(np.mean(v)), 4) for o, v in por_orden.items()},
        por_tarea=tareas,
        _pares=pares, _por_tarea_crudo={t: {c: list(v) for c, v in d.items()} for t, d in por_tarea.items()},
    )


def reduccion_proceso_completo(lb: dict, ses: dict, rng) -> dict | None:
    """Reducción estimada sobre el esfuerzo total: Σ base_t × r_t / Σ base_t (r_t = 0 si no se midió)."""
    act = (lb or {}).get("esfuerzo", {}).get("actividades")
    minutos_caso = (lb or {}).get("esfuerzo", {}).get("minutos_por_caso")
    if not act or "por_tarea" not in ses:
        return None
    base = {t: v["minutos_media"] for t, v in act.items()}
    r = {t: max(-1.0, v["reduccion"]) for t, v in ses["por_tarea"].items() if v.get("reduccion") is not None}
    punto = sum(base[t] * r.get(t, 0.0) for t in base) / sum(base.values())
    # Incertidumbre: remuestrea los minutos por tarea de las sesiones (la base se toma como fija,
    # porque la bitácora resume casos reales; su variación se reporta en linea_base.json).
    crudo = ses["_por_tarea_crudo"]
    boots = []
    for _ in range(2000):
        rb = {}
        for t, d in crudo.items():
            mm = rng.choice(d["manual"], len(d["manual"])).mean() if d.get("manual") else None
            pp = rng.choice(d["prototipo"], len(d["prototipo"])).mean() if d.get("prototipo") else None
            if mm and pp is not None:
                rb[t] = max(-1.0, 1 - pp / mm)
        boots.append(sum(base[t] * rb.get(t, 0.0) for t in base) / sum(base.values()))
    ic = [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)]
    no_medidas = sorted(t for t in base if t not in r)
    return dict(valor=round(float(punto), 4), ic95=ic, veredicto_meta_50=veredicto(float(punto), ic, META_TIEMPO),
                tareas_sin_medicion_contadas_como_0=no_medidas, casos_base=len(minutos_caso or {}),
                etiqueta="ESTIMACIÓN (bitácora real × reducciones del experimento controlado)")


# ------------------------------------------------------------------ cuestionario (OE5)
def sus(f: dict) -> float:
    x = [numero(f[f"sus{i}"]) for i in range(1, 11)]
    return 2.5 * sum((v - 1) if i % 2 == 0 else (5 - v) for i, v in enumerate(x))


def validar_cuestionario(filas):
    err = []
    for k, f in enumerate(filas, 2):
        for c in [f"sus{i}" for i in range(1, 11)] + ["satisfaccion_general"]:
            try:
                v = numero(f.get(c, ""))
                if v is None or v not in (1, 2, 3, 4, 5):
                    err.append(f"cuestionario fila {k}: {c} debe ser un entero de 1 a 5")
            except ValueError:
                err.append(f"cuestionario fila {k}: {c} no es un número")
    return err


def analizar_cuestionario(filas, rng):
    salida = {}
    for perfil in ["todos"] + sorted({f["perfil"] for f in filas}):
        g = filas if perfil == "todos" else [f for f in filas if f["perfil"] == perfil]
        s = np.array([sus(f) for f in g])
        sat = [int(numero(f["satisfaccion_general"]) >= 4) for f in g]
        ic_sus = None
        if len(s) > 1:
            b = rng.choice(s, size=(N_BOOT, len(s))).mean(1)
            ic_sus = [round(float(np.percentile(b, 2.5)), 1), round(float(np.percentile(b, 97.5)), 1)]
        prop = sum(sat) / len(sat)
        ic_sat = wilson(sum(sat), len(sat))
        extra = {c: round(float(np.mean([numero(f[c]) for f in g if numero(f.get(c, "")) is not None])), 2)
                 for c in ("utilidad_respuestas", "confianza_respuestas", "recomendaria")
                 if any(numero(f.get(c, "")) is not None for f in g)}
        salida[perfil] = dict(
            n=len(g),
            sus=dict(media=round(float(s.mean()), 1), de=round(float(s.std(ddof=1)), 1) if len(s) > 1 else None,
                     ic95=ic_sus, sobre_68=round(float((s >= SUS_REFERENCIA).mean()), 3)),
            satisfechos=dict(proporcion=round(prop, 4), ic95=ic_sat, veredicto_meta_85=veredicto(prop, ic_sat, META_SATISFACCION)),
            otros_items_media=extra, etiqueta=f"DATO VALIDADO (cuestionario, n = {len(g)})")
    return salida


# ------------------------------------------------------------------ tareas de usabilidad
def analizar_tareas(filas, reevaluar: bool):
    ok = [int(f.get("exito") == "1") for f in filas]
    seg = [numero(f["segundos"]) for f in filas if numero(f.get("segundos", "")) is not None]
    por_esc = defaultdict(list)
    correcta = []
    for f in filas:
        por_esc[f["escenario"]].append(int(f.get("exito") == "1"))
        esp = ESCENARIOS.get(f["escenario"], {}).get("pasaje_esperado")
        if esp:
            if esp == "NINGUNO":
                correcta.append(int(f.get("accion_asistente", "").startswith("deriv")))
            else:
                correcta.append(int(f.get("accion_asistente", "").startswith("respond") and f.get("pasaje_mostrado") == esp))
    salida = dict(
        intentos=len(filas), participantes=len({f["participante"] for f in filas}),
        exito_tarea=dict(proporcion=round(sum(ok) / len(ok), 4), ic95=wilson(sum(ok), len(ok))),
        segundos=dict(mediana=float(np.median(seg)) if seg else None, p90=float(np.percentile(seg, 90)) if seg else None),
        ayuda=round(float(np.mean([f.get("ayuda") == "1" for f in filas])), 4),
        acierto_asistente_preguntas_reales=dict(proporcion=round(sum(correcta) / len(correcta), 4) if correcta else None,
                                                ic95=wilson(sum(correcta), len(correcta)), n=len(correcta)),
        exito_por_escenario={e: round(sum(v) / len(v), 3) for e, v in sorted(por_esc.items())},
        etiqueta=f"DATO VALIDADO (prueba de usabilidad, {len(filas)} intentos)")
    if reevaluar:
        from src.asistente import Asistente
        a = Asistente(modo="extractivo")
        bien = []
        for f in filas:
            esp = ESCENARIOS.get(f["escenario"], {}).get("pasaje_esperado")
            if not esp or not f.get("pregunta_escrita"):
                continue
            r = a.responder(f["pregunta_escrita"])
            fuente = (r.get("fuente") or "").rsplit("(", 1)[-1].rstrip(")")
            bien.append(int(r["accion"] != "responder") if esp == "NINGUNO" else int(r["accion"] == "responder" and fuente == esp))
        salida["reevaluacion_version_actual"] = dict(proporcion=round(sum(bien) / len(bien), 4) if bien else None,
                                                     ic95=wilson(sum(bien), len(bien)), n=len(bien),
                                                     nota="Mismas preguntas reales, respondidas por la versión actual del asistente.")
    return salida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ejemplo", action="store_true")
    ap.add_argument("--datos", default=None)
    ap.add_argument("--reevaluar", action="store_true", help="vuelve a pasar las preguntas reales por el asistente actual")
    a = ap.parse_args()
    datos = Path(a.datos) if a.datos else RAIZ / "data" / "reales" / ("ejemplo" if a.ejemplo else "")
    salida = RAIZ / "resultados" / "validacion_empirica" / ("ejemplo" if a.ejemplo else "")
    rng = np.random.default_rng(SEMILLA)
    leer = lambda n: leer_csv(datos / n) if (datos / n).exists() else []
    ses, cue, tar = leer("sesiones_analistas.csv"), leer("cuestionario_usuarios.csv"), leer("tareas_usabilidad.csv")
    err = validar_sesiones(ses) + validar_cuestionario(cue)
    if err:
        raise SystemExit("Corrija los datos antes de analizar:\n- " + "\n- ".join(err[:40]))

    inf = dict(AVISO="EJEMPLO SINTÉTICO: solo muestra el formato; no son resultados." if a.ejemplo else None,
               criterios=dict(meta_reduccion_tiempo=META_TIEMPO, meta_satisfaccion=META_SATISFACCION,
                              sus_referencia=SUS_REFERENCIA))
    inf["sesiones"] = analizar_sesiones(ses, rng) if ses else dict(etiqueta="PENDIENTE (no hay sesiones_analistas.csv)")
    lb_ruta = salida / "linea_base.json"
    lb = json.loads(lb_ruta.read_text(encoding="utf-8")) if lb_ruta.exists() else None
    if ses:
        inf["reduccion_proceso_completo"] = reduccion_proceso_completo(lb, inf["sesiones"], rng) or dict(
            etiqueta="PENDIENTE (falta linea_base.json con la bitácora de tiempos)")
    inf["cuestionario"] = analizar_cuestionario(cue, rng) if cue else dict(etiqueta="PENDIENTE (no hay cuestionario_usuarios.csv)")
    inf["usabilidad"] = analizar_tareas(tar, a.reevaluar) if tar else dict(etiqueta="PENDIENTE (no hay tareas_usabilidad.csv)")

    publico = json.loads(json.dumps(inf, default=str))
    publico.get("sesiones", {}).pop("_pares", None)
    publico.get("sesiones", {}).pop("_por_tarea_crudo", None)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "estudio_usuarios.json").write_text(json.dumps(publico, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = tabla_markdown(publico)
    (salida / "estudio_usuarios.md").write_text(md, encoding="utf-8")
    print(md)


def num(v, d=1):
    return "—" if v is None else f"{v:.{d}f}".replace(".", ",")


def pct(v):
    return "—" if v is None else f"{100 * v:.1f} %".replace(".", ",")


def tabla_markdown(inf):
    out = [f"> **{inf['AVISO']}**\n"] if inf.get("AVISO") else []
    out += ["| Indicador | Resultado | IC 95 % | Meta | Veredicto | Etiqueta |", "|---|---|---|---|---|---|"]
    s = inf.get("sesiones", {})
    if "reduccion_tareas_medidas" in s:
        r = s["reduccion_tareas_medidas"]
        out.append(f"| Reducción del tiempo en las tareas medidas (OE4) | {pct(r['valor'])} "
                   f"(manual {num(s['minutos_por_caso']['manual']['media'])} → prototipo {num(s['minutos_por_caso']['prototipo']['media'])} min/caso; "
                   f"Wilcoxon p = {num(r['wilcoxon_p'], 4)}) | {pct(r['ic95'][0])} a {pct(r['ic95'][1])} | ≥ 50 % | {r['veredicto_meta_50']} | {r['etiqueta']} |")
    rp = inf.get("reduccion_proceso_completo") or {}
    if "valor" in rp:
        out.append(f"| Reducción estimada sobre el proceso completo (OE4) | {pct(rp['valor'])} | {pct(rp['ic95'][0])} a "
                   f"{pct(rp['ic95'][1])} | ≥ 50 % | {rp['veredicto_meta_50']} | {rp['etiqueta']} |")
    for perfil, c in (inf.get("cuestionario") or {}).items():
        if isinstance(c, dict) and "sus" in c:
            out.append(f"| Satisfechos (≥ 4/5), {perfil} (OE5) | {pct(c['satisfechos']['proporcion'])} (n = {c['n']}) | "
                       f"{pct(c['satisfechos']['ic95'][0])} a {pct(c['satisfechos']['ic95'][1])} | ≥ 85 % | "
                       f"{c['satisfechos']['veredicto_meta_85']} | {c['etiqueta']} |")
            out.append(f"| SUS, {perfil} | {num(c['sus']['media'])} | "
                       f"{'—' if not c['sus']['ic95'] else num(c['sus']['ic95'][0]) + ' a ' + num(c['sus']['ic95'][1])}"
                       f" | ≥ 68 (referencia) | {'sobre la referencia' if c['sus']['media'] >= 68 else 'bajo la referencia'} | {c['etiqueta']} |")
    u = inf.get("usabilidad", {})
    if "exito_tarea" in u:
        out.append(f"| Éxito en las tareas de usabilidad | {pct(u['exito_tarea']['proporcion'])} ({u['intentos']} intentos) | "
                   f"{pct(u['exito_tarea']['ic95'][0])} a {pct(u['exito_tarea']['ic95'][1])} | — | — | {u['etiqueta']} |")
        ac = u["acierto_asistente_preguntas_reales"]
        if ac["proporcion"] is not None:
            out.append(f"| Acierto del asistente con preguntas escritas por usuarios | {pct(ac['proporcion'])} (n = {ac['n']}) | "
                       f"{pct(ac['ic95'][0])} a {pct(ac['ic95'][1])} | — | — | {u['etiqueta']} |")
    if "por_tarea" in s:
        out += ["\n| Tarea | TO-BE | Manual (min) | Prototipo (min) | Reducción |", "|---|---|---|---|---|"]
        for t, v in s["por_tarea"].items():
            out.append(f"| {t} {v['nombre']} | {v['to_be']} | {num(v['minutos_manual'])} | {num(v['minutos_prototipo'])} | {pct(v['reduccion'])} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
