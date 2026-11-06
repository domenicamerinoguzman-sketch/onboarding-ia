"""Pruebas del registro de nuevos ingresos y del portal del colaborador (demo web)."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from src.flujos.orquestador import DOCUMENTOS, Orquestador
from src.registro import ErrorRegistro, RegistroIngresos

DATOS = dict(nombre="Valeria Ríos Andrade", cargo="Analista de crédito", area="Negocios",
             fecha_ingreso="2026-12-07", modalidad="remota")


class TestRegistro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "ingresos.json"
        self.o = Orquestador()
        self.r = RegistroIngresos(self.ruta, self.o.calendario)

    def tearDown(self):
        self.tmp.cleanup()

    def test_registrar_genera_usuario_y_codigo_sin_guardarlo_en_claro(self):
        ing, codigo = self.r.registrar(DATOS)
        self.assertEqual(ing["usuario_portal"], "vandrade")
        self.assertRegex(codigo, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        texto = self.ruta.read_text(encoding="utf-8")
        self.assertNotIn(codigo, texto)
        self.assertNotIn("hash", json.dumps(ing))
        ing2, _ = self.r.registrar(dict(DATOS, nombre="Víctor Andrade"))
        self.assertEqual(ing2["usuario_portal"], "vandrade2")

    def test_validaciones(self):
        with self.assertRaises(ErrorRegistro):
            self.r.registrar(dict(DATOS, nombre=""))
        with self.assertRaises(ErrorRegistro):
            self.r.registrar(dict(DATOS, fecha_ingreso="2026-12-05"))  # sábado
        with self.assertRaises(ErrorRegistro):
            self.r.registrar(dict(DATOS, modalidad="remoto"))

    def test_autenticacion_y_nuevo_codigo(self):
        ing, codigo = self.r.registrar(DATOS)
        self.assertIsNone(self.r.autenticar("vandrade", "AAAA-AAAA"))
        token = self.r.autenticar("VANDRADE", codigo.lower())
        self.assertEqual(self.r.sesion(token), ing["id"])
        nuevo = self.r.regenerar_codigo(ing["id"])
        self.assertIsNone(self.r.sesion(token))
        self.assertIsNone(self.r.autenticar("vandrade", codigo))
        self.assertIsNotNone(self.r.autenticar("vandrade", nuevo))

    def test_expediente_completo_dispara_solicitud_de_usuario(self):
        ing, _ = self.r.registrar(DATOS)
        tipos = lambda: [t["tipo"] for t in self.o.procesar(self.r.caso(ing["id"]))["tickets"]]
        self.assertNotIn("Solicitar usuario de red y correo", tipos())
        with self.assertRaises(ErrorRegistro):
            self.r.documento(ing["id"], "hoja_vida", "entregado", "colaborador")
        self.r.documento(ing["id"], "hoja_vida", "en_revision", "colaborador")
        with self.assertRaises(ErrorRegistro):
            self.r.documento(ing["id"], "hoja_vida", "rechazado", "Talento Humano", "")
        for d in DOCUMENTOS:
            self.r.documento(ing["id"], d, "entregado", "Talento Humano")
        self.assertEqual(self.r.obtener(ing["id"])["situacion"], "expediente completo")
        self.assertIn("Solicitar usuario de red y correo", tipos())
        # persiste entre reinicios
        otro = RegistroIngresos(self.ruta, self.o.calendario)
        self.assertEqual(otro.obtener(ing["id"])["aprobados"], len(DOCUMENTOS))


class TestPortalWeb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.servidor import Aplicacion, crear_manejador
        cls.tmp = tempfile.TemporaryDirectory()
        app = Aplicacion("extractivo", ruta_registro=Path(cls.tmp.name) / "ingresos.json")
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), crear_manejador(app))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def _req(self, ruta, datos=None, cookie=None):
        h = {"Content-Type": "application/json"}
        if cookie:
            h["Cookie"] = cookie
        req = urllib.request.Request(self.url + ruta, data=json.dumps(datos).encode() if datos is not None else None, headers=h)
        try:
            r = urllib.request.urlopen(req, timeout=10)
            return r.status, json.loads(r.read()), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), None

    def test_recorrido_completo(self):
        st, j, _ = self._req("/api/ingresos", DATOS)
        self.assertEqual(st, 201)
        id_, usuario, codigo = j["ingreso"]["id"], j["ingreso"]["usuario_portal"], j["codigo_temporal"]
        self.assertEqual(self._req("/api/portal/yo")[0], 401)
        self.assertEqual(self._req("/api/portal/preguntar", {"pregunta": "¿Cuándo me pagan?"})[0], 401)
        self.assertEqual(self._req("/api/portal/entrar", {"usuario": usuario, "codigo": "MAL0-MAL0"})[0], 401)
        st, _, set_cookie = self._req("/api/portal/entrar", {"usuario": usuario, "codigo": codigo})
        self.assertEqual(st, 200)
        self.assertIn("HttpOnly", set_cookie)
        cookie = set_cookie.split(";")[0]
        st, yo, _ = self._req("/api/portal/yo", cookie=cookie)
        self.assertEqual(yo["nombre"], DATOS["nombre"])
        self.assertTrue(any("Bienvenida" in m["asunto"] for m in yo["mensajes"] + yo["programados"]))
        st, yo, _ = self._req("/api/portal/documento", {"documento": "hoja_vida"}, cookie)
        self.assertEqual(next(d for d in yo["documentos"] if d["id"] == "hoja_vida")["estado"], "en_revision")
        st, det, _ = self._req("/api/ingreso/documento", {"id": id_, "documento": "hoja_vida", "estado": "rechazado", "motivo": "falta firma"})
        self.assertEqual(st, 200)
        self.assertIn("plan", det["flujo"])
        st, r, _ = self._req("/api/portal/preguntar", {"pregunta": "¿Qué día me entregan la laptop?"}, cookie)
        self.assertEqual(r["accion"], "responder")
        self.assertEqual(self._req("/api/ingresos", dict(DATOS, fecha_ingreso="2026-12-06"))[0], 400)
        html = urllib.request.urlopen(self.url + "/portal", timeout=10).read().decode()
        self.assertIn("Portal de ingreso", html)


if __name__ == "__main__":
    unittest.main()
