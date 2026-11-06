"""Registro local de nuevos ingresos y acceso al portal del colaborador (automatización, sin IA).

Es la entrada del proceso TO-BE: Talento Humano registra a la persona que ingresa y, desde ese
momento, el orquestador arma su plan, los tickets y los mensajes, y el colaborador puede entrar a
su portal con un usuario y un código temporal.

Decisiones de diseño (prototipo local, datos ficticios):
- Persistencia en un archivo JSON local (data/registro_local/ingresos.json), excluido del
  repositorio. En producción sería la base de datos del sistema o el HRIS.
- El código temporal del portal se muestra una sola vez; solo se guarda su derivación PBKDF2
  con sal. Las sesiones viven en memoria y expiran.
- Los documentos no se cargan como archivos: el colaborador marca el documento como enviado y
  Talento Humano lo aprueba o lo rechaza. Así el prototipo no almacena documentos personales.
"""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

from .flujos.orquestador import DOCUMENTOS, NOMBRE_DOC, CasoIncorporacion

RAIZ = Path(__file__).resolve().parent.parent
RUTA_REGISTRO = RAIZ / "data" / "registro_local" / "ingresos.json"
ESTADOS_DOC = {"pendiente", "en_revision", "entregado", "rechazado"}
MODALIDADES = {"presencial", "remota"}
DURACION_SESION_S = 8 * 3600
ITERACIONES = 120_000
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para evitar confusiones


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _derivar(codigo: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", codigo.strip().upper().encode(), bytes.fromhex(sal), ITERACIONES).hex()


def _base_usuario(nombre: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", nombre.lower()) if unicodedata.category(c) != "Mn")
    partes = re.sub(r"[^a-z ]", "", t).split()
    return (partes[0][0] + partes[-1]) if len(partes) > 1 else (partes[0] if partes else "colaborador")


class ErrorRegistro(ValueError):
    pass


class RegistroIngresos:
    def __init__(self, ruta: Path = RUTA_REGISTRO, calendario=None):
        self.ruta = Path(ruta)
        self.calendario = calendario
        self._lock = threading.Lock()
        self._sesiones: dict[str, tuple[str, float]] = {}
        self._datos = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta.exists() else {"ingresos": []}

    # ---------- persistencia ----------
    def _guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._datos, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.ruta)

    def _buscar(self, id_: str) -> dict:
        for i in self._datos["ingresos"]:
            if i["id"] == id_:
                return i
        raise ErrorRegistro("ingreso no encontrado")

    @staticmethod
    def _evento(ing: dict, actor: str, texto: str) -> None:
        ing["historial"].append(dict(fecha=_ahora(), actor=actor, evento=texto))

    # ---------- Talento Humano ----------
    def registrar(self, datos: dict, actor: str = "Talento Humano") -> tuple[dict, str]:
        """Devuelve (ingreso público, código temporal en claro: se muestra una sola vez)."""
        campos = {k: str(datos.get(k, "")).strip() for k in ("nombre", "cargo", "area", "fecha_ingreso", "modalidad")}
        faltan = [k for k, v in campos.items() if not v]
        if faltan:
            raise ErrorRegistro("faltan datos: " + ", ".join(faltan))
        if any(len(v) > 80 for v in campos.values()):
            raise ErrorRegistro("algún dato supera los 80 caracteres")
        if campos["modalidad"] not in MODALIDADES:
            raise ErrorRegistro("modalidad no válida (presencial o remota)")
        try:
            ingreso = date.fromisoformat(campos["fecha_ingreso"])
        except ValueError:
            raise ErrorRegistro("fecha de ingreso no válida")
        if self.calendario and not self.calendario.es_habil(ingreso):
            raise ErrorRegistro("la fecha de ingreso no es día hábil (fin de semana o feriado)")
        with self._lock:
            n = len(self._datos["ingresos"]) + 1
            id_ = f"I-{n:04d}"
            while any(i["id"] == id_ for i in self._datos["ingresos"]):
                n += 1
                id_ = f"I-{n:04d}"
            base, usuario, k = _base_usuario(campos["nombre"]), None, 1
            usados = {i["portal"]["usuario"] for i in self._datos["ingresos"]}
            usuario = base
            while usuario in usados:
                k += 1
                usuario = f"{base}{k}"
            codigo, portal = self._nuevo_codigo(usuario)
            ing = dict(id=id_, **campos, aprobacion_especial=bool(datos.get("aprobacion_especial")),
                       documentos={d: dict(estado="pendiente", motivo="") for d in DOCUMENTOS},
                       portal=portal, creado=_ahora(), historial=[])
            self._evento(ing, actor, "registró el ingreso y se generó el acceso al portal")
            self._datos["ingresos"].append(ing)
            self._guardar()
        return self.publico(ing), codigo

    @staticmethod
    def _nuevo_codigo(usuario: str) -> tuple[str, dict]:
        crudo = "".join(secrets.choice(ALFABETO) for _ in range(8))
        codigo = f"{crudo[:4]}-{crudo[4:]}"
        sal = secrets.token_hex(16)
        return codigo, dict(usuario=usuario, sal=sal, hash=_derivar(codigo, sal), ultimo_acceso=None)

    def regenerar_codigo(self, id_: str, actor: str = "Talento Humano") -> str:
        with self._lock:
            ing = self._buscar(id_)
            codigo, portal = self._nuevo_codigo(ing["portal"]["usuario"])
            ing["portal"].update(sal=portal["sal"], hash=portal["hash"])
            self._sesiones = {t: s for t, s in self._sesiones.items() if s[0] != id_}
            self._evento(ing, actor, "generó un nuevo código de acceso al portal")
            self._guardar()
        return codigo

    def eliminar(self, id_: str) -> None:
        with self._lock:
            self._buscar(id_)
            self._datos["ingresos"] = [i for i in self._datos["ingresos"] if i["id"] != id_]
            self._sesiones = {t: s for t, s in self._sesiones.items() if s[0] != id_}
            self._guardar()

    def documento(self, id_: str, doc: str, estado: str, actor: str, motivo: str = "") -> dict:
        if doc not in DOCUMENTOS or estado not in ESTADOS_DOC:
            raise ErrorRegistro("documento o estado no válido")
        if actor == "colaborador" and estado != "en_revision":
            raise ErrorRegistro("el colaborador solo puede enviar documentos a revisión")
        if estado == "rechazado" and not motivo.strip():
            raise ErrorRegistro("indique el motivo del rechazo")
        with self._lock:
            ing = self._buscar(id_)
            if actor == "colaborador" and ing["documentos"][doc]["estado"] == "entregado":
                raise ErrorRegistro("ese documento ya fue aprobado")
            ing["documentos"][doc] = dict(estado=estado, motivo=motivo.strip()[:200] if estado == "rechazado" else "")
            verbo = {"en_revision": "envió a revisión", "entregado": "aprobó", "rechazado": "rechazó", "pendiente": "marcó como pendiente"}[estado]
            self._evento(ing, actor, f"{verbo}: {NOMBRE_DOC[doc]}" + (f" (motivo: {motivo.strip()[:200]})" if estado == "rechazado" else ""))
            self._guardar()
            return self.publico(ing)

    # ---------- portal del colaborador ----------
    def autenticar(self, usuario: str, codigo: str) -> str | None:
        with self._lock:
            for ing in self._datos["ingresos"]:
                p = ing["portal"]
                if p["usuario"] == usuario.strip().lower():
                    if hmac.compare_digest(p["hash"], _derivar(codigo, p["sal"])):
                        token = secrets.token_urlsafe(32)
                        self._sesiones[token] = (ing["id"], time.time() + DURACION_SESION_S)
                        p["ultimo_acceso"] = _ahora()
                        self._evento(ing, "colaborador", "ingresó al portal")
                        self._guardar()
                        return token
                    return None
            _derivar(codigo, "00" * 16)  # tiempo similar si el usuario no existe
            return None

    def sesion(self, token: str | None) -> str | None:
        s = self._sesiones.get(token or "")
        if not s or s[1] < time.time():
            self._sesiones.pop(token or "", None)
            return None
        return s[0]

    def cerrar_sesion(self, token: str | None) -> None:
        self._sesiones.pop(token or "", None)

    # ---------- vistas ----------
    def listar(self) -> list[dict]:
        return [self.publico(i) for i in self._datos["ingresos"]]

    def obtener(self, id_: str) -> dict:
        return self.publico(self._buscar(id_))

    def caso(self, id_: str) -> CasoIncorporacion:
        i = self._buscar(id_)
        return CasoIncorporacion(id=i["id"], nombre=i["nombre"], cargo=i["cargo"], area=i["area"],
                                 fecha_ingreso=i["fecha_ingreso"], modalidad=i["modalidad"],
                                 documentos={d: v["estado"] for d, v in i["documentos"].items()},
                                 aprobacion_especial=i.get("aprobacion_especial", False))

    @staticmethod
    def publico(i: dict) -> dict:
        """Vista sin secretos (sin sal ni hash del código)."""
        estados = [v["estado"] for v in i["documentos"].values()]
        aprobados = estados.count("entregado")
        if aprobados == len(DOCUMENTOS):
            situacion = "expediente completo"
        elif "rechazado" in estados:
            situacion = "documento rechazado"
        elif "en_revision" in estados:
            situacion = "documentos por revisar"
        else:
            situacion = "esperando documentos"
        return dict(id=i["id"], nombre=i["nombre"], cargo=i["cargo"], area=i["area"], fecha_ingreso=i["fecha_ingreso"],
                    modalidad=i["modalidad"], aprobacion_especial=i.get("aprobacion_especial", False),
                    documentos=[dict(id=d, nombre=NOMBRE_DOC[d], **i["documentos"][d]) for d in DOCUMENTOS],
                    aprobados=aprobados, total_documentos=len(DOCUMENTOS),
                    por_revisar=estados.count("en_revision"), situacion=situacion,
                    usuario_portal=i["portal"]["usuario"], ultimo_acceso_portal=i["portal"]["ultimo_acceso"],
                    creado=i["creado"], historial=i["historial"])
