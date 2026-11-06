"""Demo web del prototipo (solo biblioteca estándar de Python; sin dependencias nuevas).

    python -m app.servidor            # abre http://127.0.0.1:8000
    python -m app.servidor --puerto 8080 --modo extractivo

Páginas:
- /        Talento Humano: registrar nuevos ingresos, panel de seguimiento, revisión de
           documentos, plan de onboarding, tickets y mensajes. Pestañas adicionales: el
           asistente con trazabilidad y los casos de estudio de las sesiones (S1–S8).
- /portal  Portal del nuevo colaborador: inicia sesión con el usuario y el código temporal que
           le entrega Talento Humano; ve sus pendientes, envía documentos a revisión, consulta su
           primera semana y le pregunta al asistente.

Escucha solo en 127.0.0.1: es una demo local. El panel de Talento Humano no pide inicio de
sesión (en producción usaría el inicio de sesión corporativo); el portal sí.
"""
import argparse
import json
from datetime import date
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.asistente import Asistente
from src.flujos.orquestador import AGENDA, Orquestador, cargar_casos
from src.registro import RUTA_REGISTRO, ErrorRegistro, RegistroIngresos

RAIZ = Path(__file__).resolve().parent
ESTATICO = RAIZ / "static"
MAX_CUERPO = 4096
COOKIE = "portal_sesion"
PAGINAS = {"/": "index.html", "/index.html": "index.html", "/portal": "portal.html", "/portal/": "portal.html"}


class Aplicacion:
    def __init__(self, modo: str | None, ruta_casos: Path | None = None, ruta_registro: Path = RUTA_REGISTRO):
        self.asistentes = {"auto": Asistente(modo=None, registrar=True) if modo is None else Asistente(modo=modo, registrar=True),
                           "extractivo": Asistente(modo="extractivo", registrar=True)}
        self.orquestador = Orquestador()
        self.casos = {c.id: c for c in (cargar_casos(ruta_casos) if ruta_casos else cargar_casos())}
        self.registro = RegistroIngresos(ruta_registro, self.orquestador.calendario)

    def estado(self) -> dict:
        a = self.asistentes["auto"]
        return dict(version=a.config["version"], llm_disponible=a.generador.llm_disponible(),
                    modelo_llm=a.config["generacion"]["modelo_ollama"], umbral=a.umbral,
                    casos=[dict(id=c.id, nombre=c.nombre, cargo=c.cargo, area=c.area, fecha_ingreso=c.fecha_ingreso,
                                modalidad=c.modalidad) for c in self.casos.values()])

    def detalle(self, id_: str) -> dict:
        """Ingreso + resultado del orquestador recalculado con el estado actual de los documentos."""
        ing = self.registro.obtener(id_)
        flujo = self.orquestador.procesar(self.registro.caso(id_))
        for m in flujo["bandeja_salida"]:
            if m["plantilla"] == "bienvenida":
                m["texto"] += (f"\n\nAcceso a tu portal de ingreso: http://127.0.0.1:8000/portal\n"
                               f"Usuario: {ing['usuario_portal']}\n"
                               "El código temporal se te entrega por un canal separado (no viaja en este correo).")
        return dict(ingreso=ing, flujo=flujo)

    def portal(self, id_: str) -> dict:
        d = self.detalle(id_)
        ing, flujo = d["ingreso"], d["flujo"]
        cursos = [e for e in flujo["bitacora"] if e["operacion"] == "inscribir_curso"]
        hoy = date.today().isoformat()
        propios = [m for m in flujo["bandeja_salida"] if m["para"] == "colaborador"]
        return dict(nombre=ing["nombre"], cargo=ing["cargo"], area=ing["area"], fecha_ingreso=ing["fecha_ingreso"],
                    modalidad=ing["modalidad"], usuario=ing["usuario_portal"], documentos=ing["documentos"],
                    aprobados=ing["aprobados"], total_documentos=ing["total_documentos"], situacion=ing["situacion"],
                    agenda=AGENDA, cursos=[dict(curso=c["curso"], fecha_limite=c["fecha_limite"]) for c in cursos],
                    mensajes=[m for m in propios if m["fecha"] <= hoy],
                    programados=[dict(asunto=m["asunto"], fecha=m["fecha"]) for m in propios if m["fecha"] > hoy])


def crear_manejador(app: Aplicacion):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "OnboardingIA/1.0"

        def log_message(self, fmt, *args):  # sin registrar preguntas en la consola
            pass

        def _json(self, datos, codigo=HTTPStatus.OK, cookie: str | None = None):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(cuerpo)

        def _error(self, texto: str, codigo=HTTPStatus.BAD_REQUEST):
            return self._json(dict(error=texto), codigo)

        def _leer(self) -> dict:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_CUERPO:
                raise ValueError("solicitud demasiado grande")
            datos = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(datos, dict):
                raise ValueError("se esperaba un objeto JSON")
            return datos

        def _token(self) -> str | None:
            c = SimpleCookie(self.headers.get("Cookie", ""))
            return c[COOKIE].value if COOKIE in c else None

        def _colaborador(self) -> str | None:
            return app.registro.sesion(self._token())

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if ruta in PAGINAS:
                cuerpo = (ESTATICO / PAGINAS[ruta]).read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                self.wfile.write(cuerpo)
            elif ruta == "/api/estado":
                self._json(app.estado())
            elif ruta == "/api/ingresos":
                self._json(dict(ingresos=app.registro.listar()))
            elif ruta == "/api/portal/yo":
                id_ = self._colaborador()
                if not id_:
                    return self._error("sesión no iniciada", HTTPStatus.UNAUTHORIZED)
                self._json(app.portal(id_))
            else:
                self._error("no encontrado", HTTPStatus.NOT_FOUND)

        def do_POST(self):
            try:
                datos = self._leer()
            except (ValueError, json.JSONDecodeError) as e:
                return self._error(str(e))
            try:
                return self._post(self.path.split("?")[0], datos)
            except ErrorRegistro as e:
                return self._error(str(e), HTTPStatus.NOT_FOUND if "no encontrado" in str(e) else HTTPStatus.BAD_REQUEST)

        def _post(self, ruta: str, datos: dict):
            # ----- asistente y casos de estudio (sin cambios) -----
            if ruta in ("/api/preguntar", "/api/portal/preguntar"):
                if ruta == "/api/portal/preguntar" and not self._colaborador():
                    return self._error("sesión no iniciada", HTTPStatus.UNAUTHORIZED)
                pregunta = str(datos.get("pregunta", "")).strip()
                if not pregunta:
                    return self._error("pregunta vacía")
                modo = "extractivo" if datos.get("modo") == "extractivo" else "auto"
                return self._json(app.asistentes[modo].responder(pregunta))
            if ruta == "/api/flujo":
                caso = app.casos.get(str(datos.get("id", "")))
                if caso is None:
                    return self._error("caso no encontrado", HTTPStatus.NOT_FOUND)
                return self._json(app.orquestador.procesar(caso))
            # ----- Talento Humano -----
            if ruta == "/api/ingresos":
                ing, codigo = app.registro.registrar(datos)
                return self._json(dict(ingreso=ing, codigo_temporal=codigo), HTTPStatus.CREATED)
            id_ = str(datos.get("id", ""))
            if ruta == "/api/ingreso":
                return self._json(app.detalle(id_))
            if ruta == "/api/ingreso/documento":
                app.registro.documento(id_, str(datos.get("documento", "")), str(datos.get("estado", "")),
                                       "Talento Humano", str(datos.get("motivo", "")))
                return self._json(app.detalle(id_))
            if ruta == "/api/ingreso/codigo":
                return self._json(dict(codigo_temporal=app.registro.regenerar_codigo(id_),
                                       usuario=app.registro.obtener(id_)["usuario_portal"]))
            if ruta == "/api/ingreso/eliminar":
                app.registro.eliminar(id_)
                return self._json(dict(ok=True))
            # ----- portal del colaborador -----
            if ruta == "/api/portal/entrar":
                token = app.registro.autenticar(str(datos.get("usuario", "")), str(datos.get("codigo", "")))
                if not token:
                    return self._error("usuario o código incorrectos", HTTPStatus.UNAUTHORIZED)
                return self._json(dict(ok=True), cookie=f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/")
            if ruta == "/api/portal/salir":
                app.registro.cerrar_sesion(self._token())
                return self._json(dict(ok=True), cookie=f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
            if ruta == "/api/portal/documento":
                yo = self._colaborador()
                if not yo:
                    return self._error("sesión no iniciada", HTTPStatus.UNAUTHORIZED)
                app.registro.documento(yo, str(datos.get("documento", "")), "en_revision", "colaborador")
                return self._json(app.portal(yo))
            return self._error("no encontrado", HTTPStatus.NOT_FOUND)

    return Manejador


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--modo", choices=["auto", "extractivo", "llm_local"], default="auto")
    ap.add_argument("--casos", default=None, help="archivo de casos (p. ej. data/casos_estudio.json para las sesiones)")
    ap.add_argument("--registro", default=str(RUTA_REGISTRO), help="archivo local de ingresos registrados")
    a = ap.parse_args()
    app = Aplicacion(None if a.modo == "auto" else a.modo, Path(a.casos) if a.casos else None, Path(a.registro))
    servidor = ThreadingHTTPServer(("127.0.0.1", a.puerto), crear_manejador(app))
    e = app.estado()
    print(f"Demo v{e['version']} en http://127.0.0.1:{a.puerto}  |  LLM local: "
          f"{'disponible (' + e['modelo_llm'] + ')' if e['llm_disponible'] else 'no disponible -> modo extractivo'}")
    print(f"  Talento Humano:        http://127.0.0.1:{a.puerto}/")
    print(f"  Portal del colaborador: http://127.0.0.1:{a.puerto}/portal")
    print("  Para cerrar: Ctrl + C")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        servidor.server_close()


if __name__ == "__main__":
    main()
