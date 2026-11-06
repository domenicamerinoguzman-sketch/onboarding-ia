"""Cuentas del personal de Talento Humano para el panel del sistema (autenticación local).

- La primera cuenta se crea desde la pantalla de inicio cuando todavía no existe ninguna.
- Contraseñas con PBKDF2-SHA256 y sal propia; nunca se guardan en claro.
- Sesiones en memoria con vencimiento; bloqueo temporal tras 5 intentos fallidos.
- Rol único en el prototipo: "talento_humano". En producción se reemplaza por el inicio de
  sesión corporativo (directorio de la institución), sin cambiar el resto del sistema.
"""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CUENTAS = RAIZ / "data" / "registro_local" / "cuentas.json"
ITERACIONES = 200_000
DURACION_SESION_S = 10 * 3600
MAX_INTENTOS, BLOQUEO_S = 5, 300
ROLES = {"talento_humano"}


class ErrorCuenta(ValueError):
    pass


def _hash(clave: str, sal: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), ITERACIONES).hex()


class Cuentas:
    def __init__(self, ruta: Path = RUTA_CUENTAS):
        self.ruta = Path(ruta)
        self._lock = threading.Lock()
        self._sesiones: dict[str, tuple[dict, float]] = {}
        self._fallos: dict[str, list[float]] = {}
        self._datos = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta.exists() else {"cuentas": []}

    def _guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._datos, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.ruta)

    def hay_cuentas(self) -> bool:
        return bool(self._datos["cuentas"])

    def crear(self, nombre: str, usuario: str, clave: str, rol: str = "talento_humano") -> dict:
        nombre, usuario = nombre.strip(), usuario.strip().lower()
        if not nombre or len(nombre) > 60:
            raise ErrorCuenta("indique un nombre (máximo 60 caracteres)")
        if not re.fullmatch(r"[a-z0-9._-]{3,30}", usuario):
            raise ErrorCuenta("el usuario debe tener de 3 a 30 letras, números, punto, guion o guion bajo")
        if len(clave) < 8:
            raise ErrorCuenta("la contraseña debe tener al menos 8 caracteres")
        if rol not in ROLES:
            raise ErrorCuenta("rol no válido")
        with self._lock:
            if any(c["usuario"] == usuario for c in self._datos["cuentas"]):
                raise ErrorCuenta("ese usuario ya existe")
            sal = secrets.token_hex(16)
            cuenta = dict(usuario=usuario, nombre=nombre, rol=rol, sal=sal, hash=_hash(clave, sal),
                          creada=datetime.now().isoformat(timespec="seconds"))
            self._datos["cuentas"].append(cuenta)
            self._guardar()
        return self.publica(cuenta)

    @staticmethod
    def publica(c: dict) -> dict:
        return dict(usuario=c["usuario"], nombre=c["nombre"], rol=c["rol"])

    def listar(self) -> list[dict]:
        return [self.publica(c) for c in self._datos["cuentas"]]

    def autenticar(self, usuario: str, clave: str) -> str | None:
        usuario = usuario.strip().lower()
        ahora = time.time()
        with self._lock:
            recientes = [t for t in self._fallos.get(usuario, []) if ahora - t < BLOQUEO_S]
            if len(recientes) >= MAX_INTENTOS:
                raise ErrorCuenta("demasiados intentos fallidos; espere 5 minutos")
            cuenta = next((c for c in self._datos["cuentas"] if c["usuario"] == usuario), None)
            ok = cuenta is not None and hmac.compare_digest(cuenta["hash"], _hash(clave, cuenta["sal"]))
            if cuenta is None:
                _hash(clave, "00" * 16)  # tiempo similar si el usuario no existe
            if not ok:
                self._fallos[usuario] = recientes + [ahora]
                return None
            self._fallos.pop(usuario, None)
            token = secrets.token_urlsafe(32)
            self._sesiones[token] = (self.publica(cuenta), ahora + DURACION_SESION_S)
            return token

    def sesion(self, token: str | None) -> dict | None:
        s = self._sesiones.get(token or "")
        if not s or s[1] < time.time():
            self._sesiones.pop(token or "", None)
            return None
        return s[0]

    def cerrar(self, token: str | None) -> None:
        self._sesiones.pop(token or "", None)
