"""Demo web del prototipo (solo biblioteca estándar de Python; sin dependencias nuevas).

    python -m app.servidor            # abre http://127.0.0.1:8000
    python -m app.servidor --puerto 8080 --modo extractivo

Páginas:
- /        Talento Humano (requiere inicio de sesión; la primera cuenta se crea en pantalla):
           panel de seguimiento, registro de nuevos ingresos, revisión de documentos, tareas,
           correo de bienvenida redactado por IA con aprobación humana, indicadores, asistente
           con trazabilidad y casos de estudio de las sesiones (S1–S8).
- /portal  Portal del nuevo colaborador: inicia sesión con el usuario y el código temporal que
           le entrega Talento Humano; ve sus pendientes, envía documentos a revisión, consulta su
           primera semana, le pregunta al asistente y valora sus respuestas.

Escucha solo en 127.0.0.1: es una demo local.
"""
import argparse
import json
from datetime import date
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.asistente import Asistente
from src.bienvenida_ia import RedactorBienvenida
from src.cuentas import RUTA_CUENTAS, Cuentas, ErrorCuenta
from src.flujos.orquestador import AGENDA, Orquestador, cargar_casos
from src.guardas import revisar_entrada
from src.registro import RUTA_REGISTRO, ErrorRegistro, RegistroIngresos
from src import seguimiento

RAIZ = Path(__file__).resolve().parent
ESTATICO = RAIZ / "static"
MAX_CUERPO = 16384
COOKIE_PORTAL, COOKIE_TH = "portal_sesion", "th_sesion"
PAGINAS = {"/": "index.html", "/index.html": "index.html", "/portal": "portal.html", "/portal/": "portal.html"}


def _cookie(nombre: str, valor: str, borrar: bool = False) -> str:
    return f"{nombre}={valor}; HttpOnly; SameSite=Strict; Path=/" + ("; Max-Age=0" if borrar else "")


class Aplicacion:
    def __init__(self, modo: str | None, ruta_casos: Path | None = None, ruta_registro: Path = RUTA_REGISTRO,
                 ruta_cuentas: Path | None = None):
        self.modo = modo
        self.asistentes = {"auto": Asistente(modo=None, registrar=True) if modo is None else Asistente(modo=modo, registrar=True),
                           "extractivo": Asistente(modo="extractivo", registrar=True)}
        self.orquestador = Orquestador()
        self.casos = {c.id: c for c in (cargar_casos(ruta_casos) if ruta_casos else cargar_casos())}
        self.registro = RegistroIngresos(ruta_registro, self.orquestador.calendario)
        self.cuentas = Cuentas(ruta_cuentas or (Path(ruta_registro).parent / RUTA_CUENTAS.name))
        a = self.asistentes["auto"]
        self.redactor = RedactorBienvenida(a.config, forzar=modo)
        self._borradores: dict[str, dict] = {}

    def llm_disponible(self) -> bool:
        return self.asistentes["auto"].generador.llm_disponible()

    def estado(self) -> dict:
        a = self.asistentes["auto"]
        return dict(version=a.config["version"], llm_disponible=self.llm_disponible(),
                    modelo_llm=a.config["generacion"]["modelo_ollama"], umbral=a.umbral,
                    casos=[dict(id=c.id, nombre=c.nombre, cargo=c.cargo, area=c.area, fecha_ingreso=c.fecha_ingreso,
                                modalidad=c.modalidad) for c in self.casos.values()])

    # ---------- Talento Humano ----------
    def detalle(self, id_: str, hoy: date | None = None) -> dict:
        """Ingreso + plan del orquestador + seguimiento (estado real de cada tarea, avance y pendientes)."""
        hoy = hoy or date.today()
        ing = self.registro.obtener(id_)
        flujo = self.orquestador.procesar(self.registro.caso(id_))
        tareas = seguimiento.estado_tareas(ing, flujo["plan"], hoy)
        bienvenida = ing.get("bienvenida")
        registro = ing["creado"][:10]
        for m in flujo["bandeja_salida"]:
            if m["fecha"] < registro:  # registro tardío: el mensaje sale el día del registro
                m["fecha"] = registro
            m["estado_envio"] = "programado" if m["fecha"] > hoy.isoformat() else "enviado (simulado)"
            if m["plantilla"] == "bienvenida":
                if bienvenida:
                    m["texto"], m["asunto"] = bienvenida["texto"], bienvenida["texto"].splitlines()[0].replace("Asunto: ", "")
                    m["origen"] = bienvenida["origen"]
                    m["aprobado_por"] = bienvenida["aprobado_por"]
                else:
                    m["origen"] = "plantilla"
                m["texto"] += (f"\n\nAcceso a tu portal de ingreso: http://127.0.0.1:8000/portal\n"
                               f"Usuario: {ing['usuario_portal']}\n"
                               "El código temporal se te entrega por un canal separado (no viaja en este correo).")
        av = seguimiento.avance(tareas)
        pend = seguimiento.pendientes(ing, tareas, hoy, flujo["escalamiento"])
        t02 = next((t for t in tareas if t["id"] == "T02"), None)
        if not bienvenida and t02 and t02["fecha"] <= (hoy.fromordinal(hoy.toordinal() + seguimiento.DIAS_AVISO)).isoformat():
            pend.append(dict(id=ing["id"], nombre=ing["nombre"], tipo="bienvenida", urgencia=1, fecha=t02["fecha"],
                             texto="Revisar el correo de bienvenida (si no se aprueba, "
                                   + ("hoy" if t02["fecha"] <= hoy.isoformat() else f"el {t02['fecha']}") + " sale la plantilla)"))
        ing["avance"] = av
        return dict(ingreso=ing, flujo=flujo, tareas=tareas, avance=av, pendientes=pend)

    def panel(self) -> dict:
        hoy = date.today()
        filas = []
        for i in self.registro.listar():
            d = self.detalle(i["id"], hoy)
            fila = d["ingreso"]
            fila.pop("historial", None)
            fila.update(avance=d["avance"], pendientes=d["pendientes"],
                        proxima=next((dict(fecha=t["fecha"], tarea=t["tarea"]) for t in d["tareas"]
                                      if t["estado_seguimiento"] in ("pendiente", "atrasada", "programada", "en_espera")), None))
            filas.append(fila)
        bandeja = sorted((p for f in filas for p in f["pendientes"]), key=lambda p: (p["urgencia"], p["fecha"]))
        return dict(hoy=hoy.isoformat(), resumen=seguimiento.resumen(filas, hoy), ingresos=filas, pendientes=bandeja)

    def indicadores(self) -> dict:
        filas = []
        for i in self.registro.listar():
            d = self.detalle(i["id"])
            filas.append(d["ingreso"])
        return seguimiento.indicadores(filas, self.registro.consultas())

    def borrador_bienvenida(self, id_: str) -> dict:
        ing = self.registro.obtener(id_)
        b = self.redactor.borrador(ing, self.orquestador.calendario, self.llm_disponible())
        self._borradores[id_] = b
        return b

    # ---------- portal ----------
    def portal(self, id_: str) -> dict:
        d = self.detalle(id_)
        ing, flujo = d["ingreso"], d["flujo"]
        hoy = date.today().isoformat()
        cursos = [e for e in flujo["bitacora"] if e["operacion"] == "inscribir_curso"]
        propios = [m for m in flujo["bandeja_salida"] if m["para"] == "colaborador"]
        return dict(nombre=ing["nombre"], cargo=ing["cargo"], area=ing["area"], fecha_ingreso=ing["fecha_ingreso"],
                    modalidad=ing["modalidad"], usuario=ing["usuario_portal"], documentos=ing["documentos"],
                    aprobados=ing["aprobados"], total_documentos=ing["total_documentos"], situacion=ing["situacion"],
                    agenda=AGENDA, cursos=[dict(curso=c["curso"], fecha_limite=c["fecha_limite"]) for c in cursos],
                    mensajes=[dict(asunto=m["asunto"], fecha=m["fecha"], texto=m["texto"]) for m in propios if m["fecha"] <= hoy],
                    programados=[dict(asunto=m["asunto"], fecha=m["fecha"]) for m in propios if m["fecha"] > hoy])

    def buscar(self, pregunta: str) -> dict:
        """Paso rápido (sin LLM): qué política se va a consultar. La respuesta llega después, ya verificada."""
        entrada = revisar_entrada(pregunta)
        if entrada["bloquear"]:
            return dict(encontrado=False)
        rec = self.asistentes["auto"].recuperar(entrada["pregunta_limpia"])
        top = rec["candidatos"][0]
        return dict(encontrado=not rec["deriva"], titulo=None if rec["deriva"] else f"{top['documento']} > {top['titulo']}")


def crear_manejador(app: Aplicacion):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "OnboardingIA/1.3"

        def log_message(self, fmt, *args):  # sin registrar preguntas en la consola
            pass

        def _enviar(self, cuerpo: bytes, tipo: str, codigo=HTTPStatus.OK, cookie: str | None = None, extra: dict | None = None):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(cuerpo)

        def _json(self, datos, codigo=HTTPStatus.OK, cookie: str | None = None):
            self._enviar(json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", codigo, cookie)

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

        def _galleta(self, nombre: str) -> str | None:
            c = SimpleCookie(self.headers.get("Cookie", ""))
            return c[nombre].value if nombre in c else None

        def _colaborador(self) -> str | None:
            return app.registro.sesion(self._galleta(COOKIE_PORTAL))

        def _analista(self) -> dict | None:
            return app.cuentas.sesion(self._galleta(COOKIE_TH))

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if ruta in PAGINAS:
                return self._enviar((ESTATICO / PAGINAS[ruta]).read_bytes(), "text/html; charset=utf-8", extra={
                    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
                    "X-Frame-Options": "DENY"})
            if ruta == "/api/th/sesion":
                return self._json(dict(hay_cuentas=app.cuentas.hay_cuentas(), analista=self._analista()))
            if ruta == "/api/portal/yo":
                id_ = self._colaborador()
                return self._json(app.portal(id_)) if id_ else self._error("sesión no iniciada", HTTPStatus.UNAUTHORIZED)
            if not ruta.startswith("/api/"):
                return self._error("no encontrado", HTTPStatus.NOT_FOUND)
            # ----- rutas de Talento Humano: requieren sesión -----
            if not self._analista():
                return self._error("inicie sesión como Talento Humano", HTTPStatus.UNAUTHORIZED)
            if ruta == "/api/estado":
                return self._json(app.estado())
            if ruta in ("/api/ingresos", "/api/panel"):
                return self._json(app.panel())
            if ruta == "/api/indicadores":
                return self._json(app.indicadores())
            if ruta == "/api/indicadores.csv":
                cuerpo = seguimiento.csv_indicadores(app.indicadores()["por_ingreso"]).encode("utf-8")
                return self._enviar(cuerpo, "text/csv; charset=utf-8", extra={
                    "Content-Disposition": f'attachment; filename="indicadores_onboarding_{date.today().isoformat()}.csv"'})
            if ruta == "/api/th/cuentas":
                return self._json(dict(cuentas=app.cuentas.listar()))
            return self._error("no encontrado", HTTPStatus.NOT_FOUND)

        def do_POST(self):
            try:
                datos = self._leer()
            except (ValueError, json.JSONDecodeError) as e:
                return self._error(str(e))
            try:
                return self._post(self.path.split("?")[0], datos)
            except (ErrorRegistro, ErrorCuenta) as e:
                return self._error(str(e), HTTPStatus.NOT_FOUND if "no encontrad" in str(e) else HTTPStatus.BAD_REQUEST)

        def _post(self, ruta: str, datos: dict):
            # ----- acceso de Talento Humano -----
            if ruta == "/api/th/primera-cuenta":
                if app.cuentas.hay_cuentas():
                    return self._error("ya existe una cuenta; inicie sesión", HTTPStatus.FORBIDDEN)
                app.cuentas.crear(str(datos.get("nombre", "")), str(datos.get("usuario", "")), str(datos.get("clave", "")))
                ruta, datos = "/api/th/entrar", datos
            if ruta == "/api/th/entrar":
                token = app.cuentas.autenticar(str(datos.get("usuario", "")), str(datos.get("clave", "")))
                if not token:
                    return self._error("usuario o contraseña incorrectos", HTTPStatus.UNAUTHORIZED)
                return self._json(dict(ok=True, analista=app.cuentas.sesion(token)), cookie=_cookie(COOKIE_TH, token))
            if ruta == "/api/th/salir":
                app.cuentas.cerrar(self._galleta(COOKIE_TH))
                return self._json(dict(ok=True), cookie=_cookie(COOKIE_TH, "", borrar=True))
            # ----- portal del colaborador -----
            if ruta.startswith("/api/portal/"):
                return self._portal(ruta, datos)
            # ----- todo lo demás es de Talento Humano -----
            analista = self._analista()
            if not analista:
                return self._error("inicie sesión como Talento Humano", HTTPStatus.UNAUTHORIZED)
            actor = analista["nombre"]
            if ruta == "/api/th/cuentas":
                return self._json(app.cuentas.crear(str(datos.get("nombre", "")), str(datos.get("usuario", "")),
                                                    str(datos.get("clave", ""))), HTTPStatus.CREATED)
            if ruta == "/api/preguntar":
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
            if ruta == "/api/ingresos":
                ing, codigo = app.registro.registrar(datos, actor)
                return self._json(dict(ingreso=ing, codigo_temporal=codigo), HTTPStatus.CREATED)
            id_ = str(datos.get("id", ""))
            if ruta == "/api/ingreso":
                return self._json(app.detalle(id_))
            if ruta == "/api/ingreso/documento":
                app.registro.documento(id_, str(datos.get("documento", "")), str(datos.get("estado", "")), actor,
                                       str(datos.get("motivo", "")))
                return self._json(app.detalle(id_))
            if ruta == "/api/ingreso/tarea":
                app.registro.completar_tarea(id_, str(datos.get("tarea", "")), actor, str(datos.get("nota", "")))
                return self._json(app.detalle(id_))
            if ruta == "/api/ingreso/bienvenida/borrador":
                app.registro.obtener(id_)
                return self._json(app.borrador_bienvenida(id_))
            if ruta == "/api/ingreso/bienvenida/aprobar":
                app.registro.aprobar_bienvenida(id_, actor, str(datos.get("texto", "")), app._borradores.pop(id_, None))
                return self._json(app.detalle(id_))
            if ruta == "/api/ingreso/codigo":
                return self._json(dict(codigo_temporal=app.registro.regenerar_codigo(id_, actor),
                                       usuario=app.registro.obtener(id_)["usuario_portal"]))
            if ruta == "/api/ingreso/eliminar":
                app.registro.eliminar(id_)
                return self._json(dict(ok=True))
            return self._error("no encontrado", HTTPStatus.NOT_FOUND)

        def _portal(self, ruta: str, datos: dict):
            if ruta == "/api/portal/entrar":
                token = app.registro.autenticar(str(datos.get("usuario", "")), str(datos.get("codigo", "")))
                if not token:
                    return self._error("usuario o código incorrectos", HTTPStatus.UNAUTHORIZED)
                return self._json(dict(ok=True), cookie=_cookie(COOKIE_PORTAL, token))
            if ruta == "/api/portal/salir":
                app.registro.cerrar_sesion(self._galleta(COOKIE_PORTAL))
                return self._json(dict(ok=True), cookie=_cookie(COOKIE_PORTAL, "", borrar=True))
            yo = self._colaborador()
            if not yo:
                return self._error("sesión no iniciada", HTTPStatus.UNAUTHORIZED)
            if ruta == "/api/portal/documento":
                app.registro.documento(yo, str(datos.get("documento", "")), "en_revision", "colaborador")
                return self._json(app.portal(yo))
            if ruta in ("/api/portal/buscar", "/api/portal/preguntar"):
                pregunta = str(datos.get("pregunta", "")).strip()[:500]
                if not pregunta:
                    return self._error("pregunta vacía")
                if ruta == "/api/portal/buscar":
                    return self._json(app.buscar(pregunta))
                r = app.asistentes["auto"].responder(pregunta)
                return self._json(dict(respuesta=r["respuesta"], fuente=r.get("fuente"), accion=r["accion"],
                                       consulta=app.registro.registrar_consulta(yo, r)))
            if ruta == "/api/portal/valorar":
                app.registro.valorar_consulta(yo, str(datos.get("consulta", "")), bool(datos.get("util")))
                return self._json(dict(ok=True))
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
    print(f"  Talento Humano:         http://127.0.0.1:{a.puerto}/")
    print(f"  Portal del colaborador: http://127.0.0.1:{a.puerto}/portal")
    if not app.cuentas.hay_cuentas():
        print("  Primera vez: al abrir la página se crea la cuenta de Talento Humano.")
    print("  Para cerrar: Ctrl + C")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        servidor.server_close()


if __name__ == "__main__":
    main()
