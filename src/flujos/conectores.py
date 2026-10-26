"""Conectores SIMULADOS de los sistemas corporativos (HRIS, directorio, correo, mesa de servicios).

El proyecto no tiene acceso a los sistemas de la institución (alcance, sección 4.2). Cada
conector expone la misma interfaz que tendría una integración real por API REST y registra
cada operación en una bitácora común, para poder auditar qué hizo el flujo y en qué orden.
Sustituir un conector simulado por uno real no cambia el orquestador.
"""
import itertools
import unicodedata
from dataclasses import dataclass, field


def _slug(texto: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in t if ch.isalnum() or ch == " ").split()


@dataclass
class Bitacora:
    eventos: list = field(default_factory=list)

    def registrar(self, sistema: str, operacion: str, detalle: dict) -> None:
        self.eventos.append(dict(n=len(self.eventos) + 1, sistema=sistema, operacion=operacion, **detalle))


class HRISSimulado:
    def __init__(self, bitacora: Bitacora):
        self.bitacora, self.registros = bitacora, {}

    def registrar_colaborador(self, caso) -> str:
        self.registros[caso.id] = dict(nombre=caso.nombre, cargo=caso.cargo, area=caso.area, ingreso=caso.fecha_ingreso)
        self.bitacora.registrar("HRIS", "registrar_colaborador", dict(caso=caso.id))
        return caso.id

    def inscribir_cursos(self, caso, cursos: list[tuple[str, str]]) -> None:
        for curso, fecha in cursos:
            self.bitacora.registrar("HRIS", "inscribir_curso", dict(caso=caso.id, curso=curso, fecha_limite=fecha))


class MesaServiciosSimulada:
    def __init__(self, bitacora: Bitacora):
        self.bitacora, self.tickets = bitacora, []
        self._contador = itertools.count(1001)

    def crear_ticket(self, caso, tipo: str, fecha_objetivo: str, detalle: str = "") -> str:
        ticket = f"TCK-{next(self._contador)}"
        self.tickets.append(dict(ticket=ticket, caso=caso.id, tipo=tipo, fecha_objetivo=fecha_objetivo))
        self.bitacora.registrar("Mesa de Servicios", "crear_ticket",
                                dict(caso=caso.id, ticket=ticket, tipo=tipo, fecha_objetivo=fecha_objetivo, detalle=detalle))
        return ticket


class DirectorioSimulado:
    """Propone el nombre de usuario; la creación real la hace Tecnología al atender el ticket."""

    def __init__(self, bitacora: Bitacora):
        self.bitacora = bitacora

    def proponer_usuario(self, caso) -> str:
        partes = _slug(caso.nombre)
        usuario = (partes[0][0] + partes[-1]) if len(partes) > 1 else partes[0]
        self.bitacora.registrar("Directorio", "proponer_usuario", dict(caso=caso.id, usuario=usuario))
        return usuario


class CorreoSimulado:
    """Bandeja de salida: los mensajes se guardan, no se envían."""

    def __init__(self, bitacora: Bitacora):
        self.bitacora, self.bandeja = bitacora, []

    def enviar(self, caso, destinatario: str, plantilla: str, texto: str, fecha: str) -> None:
        asunto = texto.splitlines()[0].replace("Asunto: ", "") if texto else plantilla
        self.bandeja.append(dict(caso=caso.id, para=destinatario, plantilla=plantilla, asunto=asunto, fecha=fecha, texto=texto))
        self.bitacora.registrar("Correo", "encolar_mensaje", dict(caso=caso.id, para=destinatario, plantilla=plantilla, fecha=fecha))
