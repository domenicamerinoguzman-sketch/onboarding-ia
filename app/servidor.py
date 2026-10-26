"""Demo web del prototipo (solo biblioteca estándar de Python; sin dependencias nuevas).

    python -m app.servidor            # abre http://127.0.0.1:8000
    python -m app.servidor --puerto 8080 --modo extractivo

Pestañas:
- Asistente: consulta en lenguaje natural; muestra la respuesta, la fuente, el modo de
  generación, la verificación de fidelidad y la trazabilidad (términos y candidatos).
- Flujos: procesa un caso sintético de incorporación y muestra el plan, los tickets, los
  mensajes encolados y las alertas de escalamiento.

Escucha solo en 127.0.0.1: es una demo local, sin autenticación.
"""
import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.asistente import Asistente
from src.flujos.orquestador import Orquestador, cargar_casos

RAIZ = Path(__file__).resolve().parent
ESTATICO = RAIZ / "static"
MAX_CUERPO = 4096


class Aplicacion:
    def __init__(self, modo: str | None):
        self.asistentes = {"auto": Asistente(modo=None, registrar=True) if modo is None else Asistente(modo=modo, registrar=True),
                           "extractivo": Asistente(modo="extractivo", registrar=True)}
        self.orquestador = Orquestador()
        self.casos = {c.id: c for c in cargar_casos()}

    def estado(self) -> dict:
        a = self.asistentes["auto"]
        return dict(version=a.config["version"], llm_disponible=a.generador.llm_disponible(),
                    modelo_llm=a.config["generacion"]["modelo_ollama"], umbral=a.umbral,
                    casos=[dict(id=c.id, nombre=c.nombre, cargo=c.cargo, area=c.area, fecha_ingreso=c.fecha_ingreso,
                                modalidad=c.modalidad) for c in self.casos.values()])


def crear_manejador(app: Aplicacion):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "OnboardingIA/1.0"

        def log_message(self, fmt, *args):  # sin registrar preguntas en la consola
            pass

        def _json(self, datos, codigo=HTTPStatus.OK):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(cuerpo)

        def _leer(self) -> dict:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_CUERPO:
                raise ValueError("solicitud demasiado grande")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                cuerpo = (ESTATICO / "index.html").read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
                self.end_headers()
                self.wfile.write(cuerpo)
            elif self.path == "/api/estado":
                self._json(app.estado())
            else:
                self._json(dict(error="no encontrado"), HTTPStatus.NOT_FOUND)

        def do_POST(self):
            try:
                datos = self._leer()
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(dict(error=str(e)), HTTPStatus.BAD_REQUEST)
            if self.path == "/api/preguntar":
                pregunta = str(datos.get("pregunta", "")).strip()
                if not pregunta:
                    return self._json(dict(error="pregunta vacía"), HTTPStatus.BAD_REQUEST)
                modo = "extractivo" if datos.get("modo") == "extractivo" else "auto"
                return self._json(app.asistentes[modo].responder(pregunta))
            if self.path == "/api/flujo":
                caso = app.casos.get(str(datos.get("id", "")))
                if caso is None:
                    return self._json(dict(error="caso no encontrado"), HTTPStatus.NOT_FOUND)
                return self._json(app.orquestador.procesar(caso))
            self._json(dict(error="no encontrado"), HTTPStatus.NOT_FOUND)

    return Manejador


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--modo", choices=["auto", "extractivo", "llm_local"], default="auto")
    a = ap.parse_args()
    app = Aplicacion(None if a.modo == "auto" else a.modo)
    servidor = ThreadingHTTPServer(("127.0.0.1", a.puerto), crear_manejador(app))
    e = app.estado()
    print(f"Demo v{e['version']} en http://127.0.0.1:{a.puerto}  |  LLM local: "
          f"{'disponible (' + e['modelo_llm'] + ')' if e['llm_disponible'] else 'no disponible -> modo extractivo'}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        servidor.server_close()


if __name__ == "__main__":
    main()
