"""Seguimiento del onboarding para Talento Humano y medición automática del proceso (sin IA).

- estado_tareas: combina el plan del orquestador con lo que ya ocurrió (documentos aprobados,
  tareas manuales marcadas, fecha de hoy) para decir qué está completado, programado,
  pendiente o atrasado.
- pendientes: bandeja de lo que requiere acción de Talento Humano, de todas las personas.
- indicadores: tiempos de ciclo observados en el sistema (a partir del historial con fecha y
  hora) y uso del asistente del portal. Son DATOS DEL SISTEMA: miden cuándo ocurrió cada
  hito, no el esfuerzo del analista; el esfuerzo se mide en las sesiones cronometradas.
"""
import csv
import io
from datetime import date, datetime, timedelta

EXCLUIDAS_DEL_AVANCE = {"T13"}  # el asistente está disponible todo el proceso; no es una tarea que se cierre
DIAS_AVISO = 2


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _horas(a: str | None, b: str | None) -> float | None:
    return round((_dt(b) - _dt(a)).total_seconds() / 3600, 2) if a and b else None


def estado_tareas(ingreso: dict, plan: list[dict], hoy: date) -> list[dict]:
    completo = ingreso["aprobados"] == ingreso["total_documentos"]
    momento_completo = next((h["fecha"] for h in ingreso["historial"] if h.get("tipo") == "expediente_completo"), None)
    tareas = ingreso.get("tareas", {})
    registro = date.fromisoformat(ingreso["creado"][:10])
    salida = []
    for p in plan:
        t = dict(p)
        f = date.fromisoformat(p["fecha"])
        if f < registro:  # registro tardío: lo que debía ocurrir antes del registro vence el día del registro
            f = registro
            t.update(fecha=f.isoformat(), fecha_plan=p["fecha"])
        marca = None
        if p["estado"] == "no_aplica":
            estado = "no_aplica"
        elif p["id"] == "T01":  # el registro en el HRIS ocurre al registrar el ingreso
            estado, marca = "completada", ingreso["creado"]
        elif p["id"] in EXCLUIDAS_DEL_AVANCE:
            estado = "disponible"
        elif p["id"] == "T04":
            estado, marca = ("completada", momento_completo) if completo else ("pendiente", None)
        elif p["id"] in tareas:
            estado, marca = "completada", tareas[p["id"]]["fecha"]
            t["nota"] = tareas[p["id"]].get("nota", "")
        elif p["estado"] == "ejecutada":
            estado = "completada" if f <= hoy else "programada"
        elif p["estado"] == "en_espera":
            estado = "en_espera"
        else:
            estado = "pendiente"
        if estado in ("pendiente", "en_espera") and f < hoy:
            estado = "atrasada"
        t.update(estado_seguimiento=estado, completada_en=marca,
                 accion_manual=p["id"] in ("T05", "T10") and estado in ("pendiente", "atrasada"))
        salida.append(t)
    return salida


def avance(tareas: list[dict]) -> dict:
    cuentan = [t for t in tareas if t["estado_seguimiento"] not in ("no_aplica", "disponible")]
    hechas = sum(t["estado_seguimiento"] == "completada" for t in cuentan)
    return dict(completadas=hechas, total=len(cuentan), atrasadas=sum(t["estado_seguimiento"] == "atrasada" for t in cuentan),
                porcentaje=round(100 * hechas / len(cuentan)) if cuentan else 0, terminado=bool(cuentan) and hechas == len(cuentan))


def pendientes(ingreso: dict, tareas: list[dict], hoy: date, alerta: dict | None) -> list[dict]:
    """Acciones de Talento Humano para esta persona, ordenadas por urgencia."""
    p = []
    base = dict(id=ingreso["id"], nombre=ingreso["nombre"])
    if ingreso["por_revisar"]:
        p.append(dict(base, tipo="documentos", urgencia=0, fecha=hoy.isoformat(),
                      texto=f"Revisar {ingreso['por_revisar']} documento(s) enviado(s)"))
    limite = hoy + timedelta(days=DIAS_AVISO)
    for t in tareas:
        if t["estado_seguimiento"] in ("pendiente", "atrasada") and date.fromisoformat(t["fecha"]) <= limite \
                and t["responsable"] in ("Talento Humano", "Jefe inmediato") and t["id"] != "T04":
            p.append(dict(base, tipo="tarea", tarea=t["id"], urgencia=0 if t["estado_seguimiento"] == "atrasada" else 1,
                          fecha=t["fecha"], atrasada=t["estado_seguimiento"] == "atrasada",
                          texto=t["tarea"] + ("" if t["responsable"] == "Talento Humano" else f" (coordinar con {t['responsable'].lower()})")))
    t04 = next((t for t in tareas if t["id"] == "T04"), None)
    if t04 and t04["estado_seguimiento"] == "atrasada":
        p.append(dict(base, tipo="expediente", urgencia=0, fecha=t04["fecha"], atrasada=True,
                      texto=f"Expediente incompleto: {ingreso['aprobados']}/{ingreso['total_documentos']} documentos aprobados"))
    if alerta and alerta.get("requiere_intervencion") and date.fromisoformat(t04["fecha"] if t04 else hoy.isoformat()) <= limite:
        p.append(dict(base, tipo="alerta", urgencia=1, fecha=hoy.isoformat(), texto="Alerta: " + " · ".join(alerta["motivos"])))
    return sorted(p, key=lambda x: (x["urgencia"], x["fecha"]))


def resumen(filas: list[dict], hoy: date) -> dict:
    """filas: ingresos públicos con 'avance' y 'pendientes' calculados."""
    activos = [f for f in filas if not f["avance"]["terminado"]]
    return dict(activos=len(activos), terminados=len(filas) - len(activos),
                por_revisar=sum(f["por_revisar"] for f in filas),
                atrasadas=sum(f["avance"]["atrasadas"] for f in filas),
                ingresan_7_dias=sum(0 <= (date.fromisoformat(f["fecha_ingreso"]) - hoy).days <= 7 for f in activos),
                pendientes_hoy=sum(len(f["pendientes"]) for f in filas))


def indicadores_ingreso(ing: dict, consultas: list[dict]) -> dict:
    h = ing["historial"]
    primero = lambda tipo, **k: next((e["fecha"] for e in h if e.get("tipo") == tipo and all(e.get(a) == b for a, b in k.items())), None)
    registro, completo = primero("registro"), primero("expediente_completo")
    acceso = primero("acceso_portal")
    # tiempo de respuesta de Talento Humano: envío del colaborador -> aprobación o rechazo del mismo documento
    esperas, pendiente = [], {}
    for e in h:
        if e.get("tipo") != "documento":
            continue
        if e["estado"] == "en_revision":
            pendiente[e["documento"]] = e["fecha"]
        elif e["estado"] in ("entregado", "rechazado") and e["documento"] in pendiente:
            esperas.append(_horas(pendiente.pop(e["documento"]), e["fecha"]))
    propias = [c for c in consultas if c["ingreso"] == ing["id"]]
    valoradas = [c for c in propias if c["util"] is not None]
    bienvenida = ing.get("bienvenida") or {}
    return dict(
        id=ing["id"], cargo=ing["cargo"], area=ing["area"], modalidad=ing["modalidad"], fecha_ingreso=ing["fecha_ingreso"],
        registrado=registro, expediente_completo=completo, horas_registro_a_expediente=_horas(registro, completo),
        horas_registro_a_primer_acceso=_horas(registro, acceso),
        documentos_rechazados=sum(1 for e in h if e.get("tipo") == "documento" and e["estado"] == "rechazado"),
        revisiones_respondidas=len(esperas),
        horas_promedio_respuesta_th=round(sum(esperas) / len(esperas), 2) if esperas else None,
        acciones_talento_humano=sum(1 for e in h if e["actor"] not in ("colaborador", "sistema")),
        acciones_colaborador=sum(1 for e in h if e["actor"] == "colaborador" and e.get("tipo") != "acceso_portal"),
        consultas_asistente=len(propias), consultas_derivadas=sum(c["accion"] != "responder" for c in propias),
        consultas_utiles=sum(c["util"] is True for c in valoradas), consultas_no_utiles=sum(c["util"] is False for c in valoradas),
        bienvenida_origen=bienvenida.get("origen"), bienvenida_proporcion_cambio=bienvenida.get("proporcion_cambio"),
        avance_porcentaje=ing.get("avance", {}).get("porcentaje"))


def indicadores(filas: list[dict], consultas: list[dict]) -> dict:
    por_ingreso = [indicadores_ingreso(f, consultas) for f in filas]
    vals = lambda k: [x[k] for x in por_ingreso if x[k] is not None]
    media = lambda v: round(sum(v) / len(v), 2) if v else None
    valoradas = [c for c in consultas if c["util"] is not None]
    respondidas = [c for c in consultas if c["accion"] == "responder"]
    lat = sorted(c["latencia_s"] for c in consultas if c.get("latencia_s") is not None)
    ia = [x for x in por_ingreso if x["bienvenida_origen"] == "llm_local"]
    return dict(
        nota=("Datos observados en el sistema (fecha y hora de cada hito). Miden tiempos de ciclo y uso, "
              "no el esfuerzo del analista; en la demo reflejan pruebas, no operación real."),
        ingresos=len(por_ingreso),
        proceso=dict(expedientes_completos=len(vals("horas_registro_a_expediente")),
                     horas_promedio_registro_a_expediente=media(vals("horas_registro_a_expediente")),
                     horas_promedio_respuesta_th=media(vals("horas_promedio_respuesta_th")),
                     rechazos_por_ingreso=media([x["documentos_rechazados"] for x in por_ingreso]),
                     acciones_th_por_ingreso=media([x["acciones_talento_humano"] for x in por_ingreso])),
        asistente=dict(consultas=len(consultas), respondidas=len(respondidas),
                       derivadas=len(consultas) - len(respondidas), valoradas=len(valoradas),
                       utiles=sum(c["util"] for c in valoradas),
                       tasa_utilidad=round(sum(c["util"] for c in valoradas) / len(valoradas), 3) if valoradas else None,
                       latencia_mediana_s=lat[len(lat) // 2] if lat else None),
        bienvenida_ia=dict(aprobadas_redactadas_por_ia=len(ia),
                           proporcion_cambio_promedio=media([x["bienvenida_proporcion_cambio"] for x in ia
                                                             if x["bienvenida_proporcion_cambio"] is not None])),
        por_ingreso=por_ingreso)


def csv_indicadores(por_ingreso: list[dict]) -> str:
    buf = io.StringIO()
    if por_ingreso:
        w = csv.DictWriter(buf, fieldnames=list(por_ingreso[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(por_ingreso)
    return "﻿" + buf.getvalue()  # BOM: Excel en español abre bien tildes y punto y coma
