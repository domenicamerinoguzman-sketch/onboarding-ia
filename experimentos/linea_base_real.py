"""Contrasta la línea base de la propuesta con datos reales de la institución.

Fuentes (archivos anonimizados que el grupo coloca en data/reales/; NO se suben a GitHub):
- hris_extraccion.csv: una fila por incorporación, exportada del HRIS (volumen y tiempos de ciclo).
- bitacora_tiempos.csv: minutos que cada analista dedica a cada actividad de cada incorporación,
  registrados durante el período de medición (esfuerzo en horas-hombre).

El HRIS registra fechas, no esfuerzo: valida el volumen mensual y los tiempos de ciclo, pero las
«4 horas por incorporación» solo se pueden contrastar con la bitácora de tiempos.

    python -m experimentos.linea_base_real                 # datos reales en data/reales/
    python -m experimentos.linea_base_real --ejemplo       # datos de ejemplo SINTÉTICOS (formato)

Salida: resultados/validacion_empirica/linea_base.json y linea_base.md (tablas para el documento).
Cada cifra lleva su etiqueta: DATO PROPORCIONADO (propuesta), DATO VALIDADO (HRIS o bitácora,
con su n) o ESTIMACIÓN (derivada de datos validados).
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.lectura import leer_csv, numero

RAIZ = Path(__file__).resolve().parent.parent
FLUJO = json.loads((RAIZ / "config" / "flujo_onboarding.json").read_text(encoding="utf-8"))
ACTIVIDADES = {t["id"]: t for t in FLUJO["tareas"]}
ACTIVIDADES["T99"] = dict(id="T99", nombre="Otra actividad del onboarding", to_be="manual")
SEMILLA, N_BOOT = 20260928, 5000

PROPUESTA = dict(  # DATO PROPORCIONADO: propuesta del proyecto (sección 2)
    horas_por_incorporacion=4.0, incorporaciones_mes=[30, 36], incorporaciones_analista_mes=[10, 12],
    analistas=3, horas_hombre_mes=132, horas_hombre_anio=1584)
HITOS = {"dias_solicitud_a_ingreso": "Aprobación de la vacante → ingreso",
         "dias_documentos_completos": "Expediente completo (respecto al ingreso)",
         "dias_contrato_firmado": "Contrato firmado (respecto al ingreso)",
         "dias_usuario_red": "Usuario de red creado (respecto al ingreso)",
         "dias_correo": "Correo creado (respecto al ingreso)",
         "dias_equipo_entregado": "Equipo entregado (respecto al ingreso)"}
N_MINIMO = 10  # por debajo, la cifra se reporta pero se marca como insuficiente


def ic_media(x: np.ndarray, rng) -> list[float] | None:
    if len(x) < 2:
        return None
    b = rng.choice(x, size=(N_BOOT, len(x)), replace=True).mean(axis=1)
    return [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)]


def etiqueta(n: int, fuente: str) -> str:
    return f"DATO VALIDADO ({fuente}, n = {n})" if n >= N_MINIMO else f"DATO VALIDADO CON n INSUFICIENTE ({fuente}, n = {n})"


def en_rango(v: float, rango: list[float]) -> str:
    return "dentro del rango de la propuesta" if rango[0] <= v <= rango[1] else (
        "por debajo de la propuesta" if v < rango[0] else "por encima de la propuesta")


def validar_hris(filas: list[dict]) -> list[str]:
    errores = []
    for k, f in enumerate(filas, 2):
        if not f.get("id_caso"):
            errores.append(f"hris fila {k}: falta id_caso")
        mes = f.get("mes_ingreso", "")
        if len(mes) != 7 or mes[4] != "-":
            errores.append(f"hris fila {k}: mes_ingreso debe ser AAAA-MM (recibido '{mes}')")
        for c in list(HITOS) + ["documentos_rechazados"]:
            try:
                numero(f.get(c, ""))
            except ValueError:
                errores.append(f"hris fila {k}: {c} no es un número ('{f.get(c)}')")
    return errores


def validar_bitacora(filas: list[dict]) -> list[str]:
    errores = []
    for k, f in enumerate(filas, 2):
        if f.get("actividad") not in ACTIVIDADES:
            errores.append(f"bitácora fila {k}: actividad '{f.get('actividad')}' no existe (use T01–T13 o T99)")
        try:
            m = numero(f.get("minutos", ""))
            if m is None or m < 0 or m > 600:
                errores.append(f"bitácora fila {k}: minutos fuera de rango ('{f.get('minutos')}')")
        except ValueError:
            errores.append(f"bitácora fila {k}: minutos no es un número ('{f.get('minutos')}')")
    return errores


def analizar_hris(filas: list[dict], rng) -> dict:
    por_mes = defaultdict(int)
    por_analista_mes = defaultdict(int)
    for f in filas:
        por_mes[f["mes_ingreso"]] += 1
        if f.get("analista"):
            por_analista_mes[(f["analista"], f["mes_ingreso"])] += 1
    meses = sorted(por_mes)
    v = np.array([por_mes[m] for m in meses], float)
    analistas = sorted({a for a, _ in por_analista_mes})
    va = np.array(list(por_analista_mes.values()), float)
    volumen = dict(
        meses=len(meses), periodo=[meses[0], meses[-1]] if meses else None, incorporaciones=len(filas),
        por_mes=dict(media=round(float(v.mean()), 2), minimo=int(v.min()), maximo=int(v.max()), ic95_media=ic_media(v, rng),
                     etiqueta=etiqueta(len(filas), "HRIS"),
                     contraste=en_rango(float(v.mean()), PROPUESTA["incorporaciones_mes"])),
        analistas_distintos=len(analistas),
        por_analista_mes=dict(media=round(float(va.mean()), 2) if len(va) else None,
                              minimo=int(va.min()) if len(va) else None, maximo=int(va.max()) if len(va) else None,
                              contraste=en_rango(float(va.mean()), PROPUESTA["incorporaciones_analista_mes"]) if len(va) else None),
        serie_mensual={m: por_mes[m] for m in meses},
    )
    hitos = {}
    for c, nombre in HITOS.items():
        x = np.array([numero(f.get(c, "")) for f in filas if numero(f.get(c, "")) is not None], float)
        if not len(x):
            hitos[c] = dict(nombre=nombre, n=0, etiqueta="PENDIENTE DE VALIDACIÓN (sin registros en el HRIS)")
            continue
        hitos[c] = dict(nombre=nombre, n=len(x), cobertura=round(len(x) / len(filas), 3),
                        mediana=float(np.median(x)), p25=float(np.percentile(x, 25)), p75=float(np.percentile(x, 75)),
                        p90=float(np.percentile(x, 90)), etiqueta=etiqueta(len(x), "HRIS"))
    tarde = {}
    for c, limite, texto in (("dias_usuario_red", 0, "usuario de red creado después del ingreso"),
                             ("dias_equipo_entregado", 4, "equipo entregado después del día 4"),
                             ("dias_documentos_completos", -3, "expediente completo después del plazo (−3 días)")):
        x = [numero(f.get(c, "")) for f in filas if numero(f.get(c, "")) is not None]
        if x:
            tarde[c] = dict(descripcion=texto, n=len(x), proporcion=round(sum(v > limite for v in x) / len(x), 3))
    rech = [numero(f.get("documentos_rechazados", "")) for f in filas if numero(f.get("documentos_rechazados", "")) is not None]
    reprog = [f.get("reprogramado", "") for f in filas if f.get("reprogramado", "") in ("0", "1")]
    calidad = dict(
        casos_con_rechazo=dict(n=len(rech), proporcion=round(sum(r > 0 for r in rech) / len(rech), 3) if rech else None),
        reprogramados=dict(n=len(reprog), proporcion=round(reprog.count("1") / len(reprog), 3) if reprog else None))
    return dict(volumen=volumen, tiempos_de_ciclo=hitos, retrasos=tarde, calidad=calidad)


def analizar_bitacora(filas: list[dict], rng) -> dict:
    por_caso = defaultdict(lambda: defaultdict(float))
    completos, analista_de = set(), {}
    for f in filas:
        por_caso[f["id_caso"]][f["actividad"]] += numero(f["minutos"])
        analista_de[f["id_caso"]] = f.get("analista", "")
        if f.get("registro_completo") == "1":
            completos.add(f["id_caso"])
    casos = sorted(completos)
    excluidos = sorted(set(por_caso) - completos)
    if not casos:
        return dict(casos_completos=0, casos_excluidos=len(excluidos),
                    etiqueta="PENDIENTE DE VALIDACIÓN (ningún caso con registro_completo = 1)")
    horas = np.array([sum(por_caso[c].values()) / 60 for c in casos])
    act = {}
    total_min = sum(sum(por_caso[c].values()) for c in casos)
    for a in sorted(ACTIVIDADES):
        m = np.array([por_caso[c].get(a, 0.0) for c in casos])
        if m.sum() == 0:
            continue
        act[a] = dict(nombre=ACTIVIDADES[a]["nombre"], to_be=ACTIVIDADES[a]["to_be"],
                      minutos_media=round(float(m.mean()), 2), participacion=round(float(m.sum() / total_min), 4),
                      casos_con_actividad=int((m > 0).sum()))
    automatizable = sum(v["participacion"] for v in act.values() if v["to_be"] in ("automatica", "ia"))
    media = float(horas.mean())
    ic = ic_media(horas, rng)
    return dict(
        casos_completos=len(casos), casos_excluidos=len(excluidos), analistas=len({analista_de[c] for c in casos}),
        horas_por_incorporacion=dict(media=round(media, 3), mediana=round(float(np.median(horas)), 3),
                                     de=round(float(horas.std(ddof=1)), 3) if len(horas) > 1 else None,
                                     minimo=round(float(horas.min()), 3), maximo=round(float(horas.max()), 3),
                                     ic95_media=ic, etiqueta=etiqueta(len(casos), "bitácora de tiempos"),
                                     contraste_con_4_horas=("4 h dentro del IC 95 %" if ic and ic[0] <= 4 <= ic[1]
                                                            else "4 h fuera del IC 95 %" if ic else "sin IC (n < 2)")),
        actividades=act,
        participacion_tareas_automatizables_o_ia=round(automatizable, 4),
        minutos_por_caso={c: round(sum(por_caso[c].values()), 1) for c in casos},
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ejemplo", action="store_true", help="usar data/reales/ejemplo (SINTÉTICO)")
    ap.add_argument("--datos", default=None)
    a = ap.parse_args()
    datos = Path(a.datos) if a.datos else RAIZ / "data" / "reales" / ("ejemplo" if a.ejemplo else "")
    salida = RAIZ / "resultados" / "validacion_empirica" / ("ejemplo" if a.ejemplo else "")
    rng = np.random.default_rng(SEMILLA)
    informe = dict(fuente_datos=str(datos.relative_to(RAIZ)) if datos.is_relative_to(RAIZ) else str(datos),
                   AVISO="EJEMPLO SINTÉTICO: solo muestra el formato; no son resultados." if a.ejemplo else None,
                   propuesta=dict(PROPUESTA, etiqueta="DATO PROPORCIONADO (propuesta del proyecto)"))
    errores = []
    hris_ruta, bit_ruta = datos / "hris_extraccion.csv", datos / "bitacora_tiempos.csv"
    hris = leer_csv(hris_ruta) if hris_ruta.exists() else []
    bit = leer_csv(bit_ruta) if bit_ruta.exists() else []
    errores += validar_hris(hris) + validar_bitacora(bit)
    if errores:
        raise SystemExit("Corrija los datos antes de analizar:\n- " + "\n- ".join(errores[:40]))
    informe["hris"] = analizar_hris(hris, rng) if hris else dict(etiqueta="PENDIENTE DE VALIDACIÓN (no hay hris_extraccion.csv)")
    informe["esfuerzo"] = analizar_bitacora(bit, rng) if bit else dict(etiqueta="PENDIENTE DE VALIDACIÓN (no hay bitacora_tiempos.csv)")

    if hris and bit and informe["esfuerzo"].get("casos_completos"):
        h = informe["esfuerzo"]["horas_por_incorporacion"]["media"]
        vol = informe["hris"]["volumen"]["por_mes"]["media"]
        informe["horas_hombre_estimadas"] = dict(
            mensuales=round(h * vol, 1), anuales=round(h * vol * 12, 1),
            etiqueta="ESTIMACIÓN (horas por incorporación de la bitácora × volumen mensual del HRIS)",
            propuesta=dict(mensuales=PROPUESTA["horas_hombre_mes"], anuales=PROPUESTA["horas_hombre_anio"]))

    salida.mkdir(parents=True, exist_ok=True)
    (salida / "linea_base.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (salida / "linea_base.md").write_text(tabla_markdown(informe), encoding="utf-8")
    print(tabla_markdown(informe))


def fmt(v, dec=1):
    return "—" if v is None else f"{v:.{dec}f}".replace(".", ",")


def tabla_markdown(inf: dict) -> str:
    p = inf["propuesta"]
    out = []
    if inf.get("AVISO"):
        out.append(f"> **{inf['AVISO']}**\n")
    out.append("| Indicador | Propuesta (DATO PROPORCIONADO) | Dato real | Etiqueta | Contraste |")
    out.append("|---|---|---|---|---|")
    vol = inf.get("hris", {}).get("volumen")
    if vol:
        pm = vol["por_mes"]
        out.append(f"| Incorporaciones por mes | 30–36 | {fmt(pm['media'])} (mín. {pm['minimo']}, máx. {pm['maximo']}; "
                   f"{vol['meses']} meses) | {pm['etiqueta']} | {pm['contraste']} |")
        pa = vol["por_analista_mes"]
        out.append(f"| Incorporaciones por analista y mes | 10–12 | {fmt(pa['media'])} | {pm['etiqueta']} | {pa['contraste']} |")
        out.append(f"| Analistas que gestionan ingresos | 3 | {vol['analistas_distintos']} | {pm['etiqueta']} | — |")
    else:
        out.append("| Incorporaciones por mes | 30–36 | — | PENDIENTE DE VALIDACIÓN | — |")
    esf = inf.get("esfuerzo", {}).get("horas_por_incorporacion")
    if esf:
        ic = esf["ic95_media"]
        out.append(f"| Horas por incorporación | 4 | {fmt(esf['media'], 2)} (IC 95 %: {fmt(ic[0], 2) if ic else '—'} a "
                   f"{fmt(ic[1], 2) if ic else '—'}) | {esf['etiqueta']} | {esf['contraste_con_4_horas']} |")
        out.append(f"| Participación de tareas automatizables o con IA | — | "
                   f"{fmt(100 * inf['esfuerzo']['participacion_tareas_automatizables_o_ia'])} % del tiempo | "
                   f"{esf['etiqueta']} | — |")
    else:
        out.append("| Horas por incorporación | 4 | — | PENDIENTE DE VALIDACIÓN | — |")
    hh = inf.get("horas_hombre_estimadas")
    if hh:
        out.append(f"| Horas-hombre mensuales | {p['horas_hombre_mes']} | {fmt(hh['mensuales'])} | {hh['etiqueta']} | — |")
        out.append(f"| Horas-hombre anuales | 1.584 | {fmt(hh['anuales'])} | {hh['etiqueta']} | — |")
    tc = inf.get("hris", {}).get("tiempos_de_ciclo")
    if tc:
        out.append("\n| Hito (días) | n | Mediana | P25–P75 | P90 | Etiqueta |")
        out.append("|---|---|---|---|---|---|")
        for v in tc.values():
            if v.get("n"):
                out.append(f"| {v['nombre']} | {v['n']} | {fmt(v['mediana'])} | {fmt(v['p25'])} a {fmt(v['p75'])} | "
                           f"{fmt(v['p90'])} | {v['etiqueta']} |")
            else:
                out.append(f"| {v['nombre']} | 0 | — | — | — | {v['etiqueta']} |")
    act = inf.get("esfuerzo", {}).get("actividades")
    if act:
        out.append("\n| Actividad | TO-BE | Minutos por caso (media) | % del tiempo |")
        out.append("|---|---|---|---|")
        for k, v in sorted(act.items(), key=lambda kv: -kv[1]["participacion"]):
            out.append(f"| {k} {v['nombre']} | {v['to_be']} | {fmt(v['minutos_media'])} | {fmt(100 * v['participacion'])} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
