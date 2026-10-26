"""Orquestador del flujo TO-BE de onboarding (automatización tradicional, sin IA).

Para cada caso de incorporación:
1. calcula el plan de tareas con fechas en días hábiles respecto a la fecha de ingreso;
2. ejecuta las tareas automáticas sobre los conectores simulados (HRIS, mesa de servicios,
   directorio, correo), respetando sus condiciones (p. ej. VPN solo en modalidad remota);
3. aplica las reglas de escalamiento y, si hay motivos, encola una alerta para Talento Humano;
4. devuelve el plan, la bitácora de operaciones y el conteo de actividades manuales AS-IS
   frente a TO-BE (indicador de diseño, no medición de tiempo).

    python -m src.flujos.orquestador                     # procesa data/casos_demo.json
    python -m src.flujos.orquestador --caso C-DEMO-02
"""
import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from string import Template

from ..reglas_escalamiento import evaluar_caso
from .conectores import Bitacora, CorreoSimulado, DirectorioSimulado, HRISSimulado, MesaServiciosSimulada

RAIZ = Path(__file__).resolve().parents[2]
RUTA_FLUJO = RAIZ / "config" / "flujo_onboarding.json"
RUTA_CASOS = RAIZ / "data" / "casos_demo.json"
DOCUMENTOS = ["cedula_votacion", "hoja_vida", "titulos_senescyt", "certificado_bancario", "referencias", "antecedentes"]
NOMBRE_DOC = {"cedula_votacion": "cédula y certificado de votación", "hoja_vida": "hoja de vida",
              "titulos_senescyt": "títulos registrados", "certificado_bancario": "certificado bancario",
              "referencias": "referencias laborales", "antecedentes": "certificado de antecedentes penales"}
AGENDA = ["Día 1: bienvenida y firma de documentos", "Día 2: seguridad de la información y cumplimiento",
          "Día 3: inducción al área", "Día 4: herramientas y sistemas (entrega de equipo)",
          "Día 5: evaluación de la inducción y reunión con el jefe inmediato"]


@dataclass
class CasoIncorporacion:
    id: str
    nombre: str            # seudónimo: el prototipo no usa nombres reales
    cargo: str
    area: str
    fecha_ingreso: str     # AAAA-MM-DD
    modalidad: str = "presencial"
    documentos: dict = field(default_factory=dict)  # documento -> "entregado" | "pendiente" | "rechazado"
    equipo_pendiente: bool = False
    choque_agenda: bool = False
    aprobacion_especial: bool = False
    acceso_remoto_pendiente: bool = False

    @property
    def documentos_pendientes(self) -> list[str]:
        return [d for d in DOCUMENTOS if self.documentos.get(d, "pendiente") != "entregado"]


class Calendario:
    def __init__(self, flujo: dict):
        self.habiles = set(flujo["dias_habiles"])
        self.feriados = {date.fromisoformat(f) for f in flujo["feriados"]}

    def es_habil(self, d: date) -> bool:
        return d.weekday() in self.habiles and d not in self.feriados

    def sumar(self, inicio: date, dias: int) -> date:
        """Desplaza `dias` días hábiles (negativo = hacia atrás). 0 = la fecha de ingreso."""
        d, paso, restantes = inicio, (1 if dias >= 0 else -1), abs(dias)
        while restantes:
            d += timedelta(days=paso)
            if self.es_habil(d):
                restantes -= 1
        return d


def _render(plantilla: str, **valores) -> str:
    return Template((RAIZ / "plantillas" / f"{plantilla}.txt").read_text(encoding="utf-8")).safe_substitute(**valores)


class Orquestador:
    def __init__(self, ruta_flujo: Path = RUTA_FLUJO):
        self.flujo = json.loads(Path(ruta_flujo).read_text(encoding="utf-8"))
        self.calendario = Calendario(self.flujo)

    def condicion(self, nombre: str | None, caso: CasoIncorporacion) -> bool:
        if not nombre:
            return True
        return {"documentos_pendientes": bool(caso.documentos_pendientes),
                "expediente_completo": not caso.documentos_pendientes,
                "modalidad_remota": caso.modalidad == "remota"}[nombre]

    def procesar(self, caso: CasoIncorporacion, fecha_corte: str | None = None) -> dict:
        """fecha_corte: fecha en que se evalúan los pendientes (por defecto, el plazo de documentos)."""
        bitacora = Bitacora()
        hris, mesa = HRISSimulado(bitacora), MesaServiciosSimulada(bitacora)
        directorio, correo = DirectorioSimulado(bitacora), CorreoSimulado(bitacora)
        ingreso = date.fromisoformat(caso.fecha_ingreso)
        if not self.calendario.es_habil(ingreso):
            raise ValueError(f"{caso.id}: la fecha de ingreso {caso.fecha_ingreso} no es día hábil")
        fecha = lambda t: self.calendario.sumar(ingreso, t["dias"]).isoformat()
        limite_docs = self.calendario.sumar(ingreso, -3).isoformat()
        valores = dict(nombre=caso.nombre, area=caso.area, cargo=caso.cargo, fecha_ingreso=caso.fecha_ingreso,
                       fecha_limite_documentos=limite_docs, id_caso=caso.id,
                       documentos_pendientes=", ".join(NOMBRE_DOC[d] for d in caso.documentos_pendientes) or "ninguno",
                       agenda="\n".join(f"- {a}" for a in AGENDA))
        plan = []
        for t in self.flujo["tareas"]:
            aplica = self.condicion(t.get("condicion"), caso)
            estado = "no_aplica"
            if aplica and t["to_be"] == "automatica":
                estado = "ejecutada"
                c = t.get("conector")
                if c == "hris" and t["id"] == "T01":
                    hris.registrar_colaborador(caso)
                elif c == "hris":
                    hris.inscribir_cursos(caso, [("Seguridad de la información", self.calendario.sumar(ingreso, 10).isoformat()),
                                                 ("Prevención de lavado de activos", self.calendario.sumar(ingreso, 30).isoformat())])
                elif c == "correo":
                    correo.enviar(caso, "colaborador", t["plantilla"], _render(t["plantilla"], **valores), fecha(t))
                elif c == "mesa_servicios":
                    detalle = f"usuario propuesto: {directorio.proponer_usuario(caso)}" if t["id"] == "T06" else ""
                    mesa.crear_ticket(caso, t["nombre"], fecha(t), detalle)
            elif aplica and t["to_be"] in ("manual", "asistida"):
                estado = "pendiente_humano"
            elif aplica and t["to_be"] == "ia":
                estado = "asistente_disponible"
            elif not aplica and t.get("condicion") == "expediente_completo":
                estado = "en_espera"  # se dispara cuando se complete el expediente
            plan.append(dict(id=t["id"], tarea=t["nombre"], responsable=t["responsable"], fecha=fecha(t),
                             as_is=t["as_is"], to_be=t["to_be"], estado=estado))

        senales = dict(id=caso.id, documentos_pendientes=int(bool(caso.documentos_pendientes)),
                       equipo_pendiente=int(caso.equipo_pendiente), choque_agenda=int(caso.choque_agenda),
                       acceso_remoto_pendiente=int(caso.acceso_remoto_pendiente or
                                                   (caso.modalidad == "remota" and bool(caso.documentos_pendientes))),
                       aprobacion_especial=int(caso.aprobacion_especial))
        escalamiento = evaluar_caso(senales)
        if escalamiento["requiere_intervencion"]:
            correo.enviar(caso, "talento_humano", "alerta_escalamiento",
                          _render("alerta_escalamiento", motivos="\n".join(f"- {m}" for m in escalamiento["motivos"]), **valores),
                          fecha_corte or limite_docs)

        plan.sort(key=lambda p: (p["fecha"], p["id"]))
        aplicables = [p for p in plan if p["estado"] != "no_aplica"]
        indicador = dict(
            actividades_aplicables=len(aplicables),
            manuales_as_is=sum(p["as_is"] == "manual" for p in aplicables),
            manuales_to_be=sum(p["to_be"] in ("manual", "asistida") for p in aplicables),
            automatizadas_to_be=sum(p["to_be"] == "automatica" for p in aplicables),
            asistidas_por_ia=sum(p["to_be"] == "ia" for p in aplicables),
            nota="Conteo sobre el modelo AS-IS preliminar (pendiente de validación). No mide tiempo.")
        return dict(caso=asdict(caso), plan=plan, escalamiento=escalamiento, bitacora=bitacora.eventos,
                    bandeja_salida=correo.bandeja, tickets=mesa.tickets, indicador_actividades=indicador)


def cargar_casos(ruta: Path = RUTA_CASOS) -> list[CasoIncorporacion]:
    return [CasoIncorporacion(**c) for c in json.loads(Path(ruta).read_text(encoding="utf-8"))["casos"]]


def main():
    ap = argparse.ArgumentParser(description="Flujo de onboarding con conectores simulados")
    ap.add_argument("--caso", help="id del caso (por defecto, todos)")
    ap.add_argument("--completo", action="store_true", help="incluye bitácora y textos de los mensajes")
    a = ap.parse_args()
    o = Orquestador()
    for caso in cargar_casos():
        if a.caso and caso.id != a.caso:
            continue
        r = o.procesar(caso)
        if not a.completo:
            r = dict(caso=r["caso"]["id"], escalamiento=r["escalamiento"], indicador=r["indicador_actividades"],
                     tickets=[t["tipo"] for t in r["tickets"]], mensajes=[m["asunto"] for m in r["bandeja_salida"]],
                     plan=[f"{p['fecha']} {p['id']} {p['tarea']} [{p['estado']}]" for p in r["plan"]])
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
