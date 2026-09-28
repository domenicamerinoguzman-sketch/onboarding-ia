"""Componente de automatización tradicional (sin IA): reglas de escalamiento a Talento Humano.

v0.1 solo revisaba documentos, equipo y choque de agenda y omitió el caso C075
(aprobación especial). v0.2 incorpora acceso remoto pendiente y aprobación especial,
y registra el motivo de cada alerta para trazabilidad.
"""
SENALES = {
    "documentos_pendientes": "Documentos del expediente pendientes",
    "equipo_pendiente": "Equipo de trabajo pendiente",
    "choque_agenda": "Choque de agenda declarado",
    "acceso_remoto_pendiente": "Acceso remoto (VPN) pendiente",
    "aprobacion_especial": "Aprobación especial pendiente",
}


def evaluar_caso(caso: dict) -> dict:
    motivos = [texto for campo, texto in SENALES.items() if int(caso.get(campo, 0))]
    return {"id": caso.get("id"), "requiere_intervencion": bool(motivos), "motivos": motivos}
