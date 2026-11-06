"""Pruebas del registro de ingresos, cuentas de Talento Humano, seguimiento, indicadores,
correo de bienvenida con IA (servidor Ollama simulado) y portal del colaborador."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

from src import seguimiento
from src.asistente import cargar_config
from src.bienvenida_ia import RedactorBienvenida, datos_borrador, verificar
from src.cuentas import Cuentas, ErrorCuenta
from src.flujos.orquestador import DOCUMENTOS, Orquestador
from src.registro import ErrorRegistro, RegistroIngresos
from tests.ollama_simulado import iniciar as iniciar_ollama

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
        self.assertNotIn(codigo, self.ruta.read_text(encoding="utf-8"))
        self.assertNotIn("hash", json.dumps(ing))
        ing2, _ = self.r.registrar(dict(DATOS, nombre="Víctor Andrade"))
        self.assertEqual(ing2["usuario_portal"], "vandrade2")

    def test_validaciones(self):
        for malo in (dict(DATOS, nombre=""), dict(DATOS, fecha_ingreso="2026-12-05"), dict(DATOS, modalidad="remoto")):
            with self.assertRaises(ErrorRegistro):
                self.r.registrar(malo)

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
            self.r.documento(ing["id"], "hoja_vida", "rechazado", "Ana", "")
        for d in DOCUMENTOS:
            self.r.documento(ing["id"], d, "entregado", "Ana")
        self.assertEqual(self.r.obtener(ing["id"])["situacion"], "expediente completo")
        self.assertIn("Solicitar usuario de red y correo", tipos())
        self.assertEqual(sum(h["tipo"] == "expediente_completo" for h in self.r.obtener(ing["id"])["historial"]), 1)
        otro = RegistroIngresos(self.ruta, self.o.calendario)  # persiste entre reinicios
        self.assertEqual(otro.obtener(ing["id"])["aprobados"], len(DOCUMENTOS))

    def test_tareas_manuales(self):
        ing, _ = self.r.registrar(DATOS)
        with self.assertRaises(ErrorRegistro):
            self.r.completar_tarea(ing["id"], "T10", "Ana", "")  # falta el nombre del guía
        with self.assertRaises(ErrorRegistro):
            self.r.completar_tarea(ing["id"], "T02", "Ana")  # automática: no se marca a mano
        self.r.completar_tarea(ing["id"], "T05", "Ana")
        self.assertIn("T05", self.r.obtener(ing["id"])["tareas"])


class TestSeguimiento(unittest.TestCase):
    """Fechas relativas a hoy, para que las pruebas no dependan del día en que se ejecutan."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.o = Orquestador()
        self.r = RegistroIngresos(Path(self.tmp.name) / "i.json", self.o.calendario)
        ingreso = self.o.calendario.sumar(date.today(), 25)  # día hábil, unas 5 semanas adelante
        ing, _ = self.r.registrar(dict(DATOS, fecha_ingreso=ingreso.isoformat()))
        self.id = ing["id"]
        self.plan = {p["id"]: date.fromisoformat(p["fecha"]) for p in self.o.procesar(self.r.caso(self.id))["plan"]}

    def tearDown(self):
        self.tmp.cleanup()

    def _tareas(self, hoy):
        ing = self.r.obtener(self.id)
        return ing, seguimiento.estado_tareas(ing, self.o.procesar(self.r.caso(self.id))["plan"], hoy)

    def test_programadas_atrasadas_y_completadas(self):
        _, t = self._tareas(date.today())
        est = {x["id"]: x["estado_seguimiento"] for x in t}
        self.assertEqual((est["T01"], est["T02"], est["T05"]), ("completada", "programada", "pendiente"))
        despues = self.plan["T05"] + timedelta(days=1)
        _, t = self._tareas(despues)
        est = {x["id"]: x["estado_seguimiento"] for x in t}
        self.assertEqual((est["T02"], est["T05"], est["T04"]), ("completada", "atrasada", "atrasada"))
        self.r.completar_tarea(self.id, "T05", "Ana")
        for d in DOCUMENTOS:
            self.r.documento(self.id, d, "entregado", "Ana")
        _, t = self._tareas(despues)
        est = {x["id"]: x["estado_seguimiento"] for x in t}
        self.assertEqual((est["T04"], est["T05"], est["T13"]), ("completada", "completada", "disponible"))

    def test_registro_tardio_mueve_las_fechas_vencidas_al_dia_del_registro(self):
        ingreso = self.o.calendario.sumar(date.today(), 2)
        ing, _ = self.r.registrar(dict(DATOS, nombre="Ana Tardía", fecha_ingreso=ingreso.isoformat()))
        plan = self.o.procesar(self.r.caso(ing["id"]))["plan"]
        t = {x["id"]: x for x in seguimiento.estado_tareas(self.r.obtener(ing["id"]), plan, date.today())}
        self.assertEqual(t["T02"]["fecha"], date.today().isoformat())
        self.assertEqual(t["T02"]["estado_seguimiento"], "completada")

    def test_pendientes_y_avance(self):
        self.r.documento(self.id, "hoja_vida", "en_revision", "colaborador")
        hoy = self.plan["T05"]
        ing, t = self._tareas(hoy)
        p = seguimiento.pendientes(ing, t, hoy, None)
        self.assertIn("documentos", [x["tipo"] for x in p])
        self.assertTrue(any(x.get("tarea") == "T05" for x in p))
        av = seguimiento.avance(t)
        self.assertGreater(av["total"], 0)
        self.assertFalse(av["terminado"])

    def test_indicadores_y_csv(self):
        self.r.documento(self.id, "hoja_vida", "en_revision", "colaborador")
        self.r.documento(self.id, "hoja_vida", "rechazado", "Ana", "ilegible")
        cid = self.r.registrar_consulta(self.id, dict(accion="responder", fuente="X", latencia_total_s=1.2))
        self.r.valorar_consulta(self.id, cid, True)
        ind = seguimiento.indicadores([self.r.obtener(self.id)], self.r.consultas())
        x = ind["por_ingreso"][0]
        self.assertEqual((x["documentos_rechazados"], x["revisiones_respondidas"], x["consultas_utiles"]), (1, 1, 1))
        self.assertEqual(ind["asistente"]["tasa_utilidad"], 1.0)
        csv = seguimiento.csv_indicadores(ind["por_ingreso"])
        self.assertTrue(csv.startswith("\ufeffid;cargo;"))
        self.assertNotIn("Valeria", csv)  # el CSV no lleva nombres


class TestCuentas(unittest.TestCase):
    def test_crear_autenticar_y_bloqueo(self):
        with tempfile.TemporaryDirectory() as d:
            c = Cuentas(Path(d) / "c.json")
            self.assertFalse(c.hay_cuentas())
            with self.assertRaises(ErrorCuenta):
                c.crear("Ana", "ana", "corta")
            c.crear("Ana Pérez", "ana", "clave-segura-1")
            self.assertNotIn("clave-segura-1", (Path(d) / "c.json").read_text(encoding="utf-8"))
            self.assertEqual(c.sesion(c.autenticar("ANA", "clave-segura-1"))["nombre"], "Ana Pérez")
            for _ in range(5):
                self.assertIsNone(c.autenticar("ana", "mala-clave"))
            with self.assertRaises(ErrorCuenta):
                c.autenticar("ana", "clave-segura-1")  # bloqueo temporal


class TestBienvenidaIA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ollama = iniciar_ollama(0)
        cls.config = cargar_config()
        cls.config["generacion"]["url_ollama"] = f"http://127.0.0.1:{cls.ollama.server_port}"
        cls.cal = Orquestador().calendario
        cls.ing = dict(DATOS, documentos=[dict(id=d, estado="pendiente" if d == "hoja_vida" else "entregado") for d in DOCUMENTOS])

    @classmethod
    def tearDownClass(cls):
        cls.ollama.shutdown()

    def test_borrador_verificado(self):
        b = RedactorBienvenida(self.config).borrador(self.ing, self.cal, True)
        self.assertEqual(b["origen"], "llm_local")
        self.assertTrue(b["verificacion"]["fiel"])
        self.assertIn("Valeria", b["texto"])

    def test_cifra_inventada_se_descarta_y_usa_plantilla(self):
        b = RedactorBienvenida(self.config).borrador(dict(self.ing, cargo="INVENTA"), self.cal, True)
        self.assertEqual(b["origen"], "plantilla")
        self.assertIn("999", b["motivo"])

    def test_sin_llm_usa_plantilla(self):
        b = RedactorBienvenida(self.config).borrador(self.ing, self.cal, False)
        self.assertEqual(b["origen"], "plantilla")

    def test_verificador(self):
        d = datos_borrador(self.ing, self.cal)
        malo = "Asunto: Hola\n\nHola, Valeria: visita https://x.com el 7 de diciembre. " + "texto " * 60
        v = verificar(malo, d)
        self.assertFalse(v["fiel"])
        self.assertTrue(any("enlaces" in m for m in v["motivos"]))
        self.assertTrue(any("plazo" in m for m in v["motivos"]))


class TestEvaluacionBienvenida(unittest.TestCase):
    def test_casos_cubren_ambas_variantes(self):
        from experimentos.evaluar_bienvenida import casos
        c = casos()
        self.assertEqual(len(c), 22)
        self.assertTrue(all(any(d["estado"] != "entregado" for d in x["documentos"]) for x in c if x["id"].endswith("pendientes")))


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
            cuerpo = r.read()
            return r.status, (json.loads(cuerpo) if r.headers.get_content_type() == "application/json" else cuerpo.decode()), r.headers.get("Set-Cookie")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read()), None

    def test_recorrido_completo(self):
        # Talento Humano: primera cuenta, y ya no se puede crear otra "primera"
        self.assertFalse(self._req("/api/th/sesion")[1]["hay_cuentas"])
        self.assertEqual(self._req("/api/ingresos", DATOS)[0], 401)
        st, _, c = self._req("/api/th/primera-cuenta", dict(nombre="Ana Pérez", usuario="ana", clave="clave-segura-1"))
        self.assertEqual(st, 200)
        th = c.split(";")[0]
        self.assertEqual(self._req("/api/th/primera-cuenta", dict(nombre="X", usuario="x", clave="clave-segura-2"))[0], 403)
        st, j, _ = self._req("/api/ingresos", DATOS, th)
        self.assertEqual(st, 201)
        id_, usuario, codigo = j["ingreso"]["id"], j["ingreso"]["usuario_portal"], j["codigo_temporal"]
        self.assertEqual(j["ingreso"]["historial"][0]["actor"], "Ana Pérez")
        # Portal
        self.assertEqual(self._req("/api/portal/yo")[0], 401)
        self.assertEqual(self._req("/api/portal/entrar", {"usuario": usuario, "codigo": "MAL0-MAL0"})[0], 401)
        st, _, set_cookie = self._req("/api/portal/entrar", {"usuario": usuario, "codigo": codigo})
        self.assertIn("HttpOnly", set_cookie)
        pc = set_cookie.split(";")[0]
        st, yo, _ = self._req("/api/portal/yo", cookie=pc)
        self.assertEqual(yo["nombre"], DATOS["nombre"])
        self.assertTrue(any("Bienvenida" in m["asunto"] for m in yo["mensajes"] + yo["programados"]))
        st, yo, _ = self._req("/api/portal/documento", {"documento": "hoja_vida"}, pc)
        self.assertEqual(next(d for d in yo["documentos"] if d["id"] == "hoja_vida")["estado"], "en_revision")
        st, b, _ = self._req("/api/portal/buscar", {"pregunta": "¿Qué día me entregan la laptop?"}, pc)
        self.assertTrue(b["encontrado"])
        st, r, _ = self._req("/api/portal/preguntar", {"pregunta": "¿Qué día me entregan la laptop?"}, pc)
        self.assertEqual(r["accion"], "responder")
        self.assertEqual(self._req("/api/portal/valorar", {"consulta": r["consulta"], "util": True}, pc)[0], 200)
        # Talento Humano: panel, revisión, tareas, bienvenida e indicadores
        st, p, _ = self._req("/api/panel", cookie=th)
        self.assertEqual(p["resumen"]["por_revisar"], 1)
        self.assertEqual(p["pendientes"][0]["tipo"], "documentos")
        st, det, _ = self._req("/api/ingreso/documento", {"id": id_, "documento": "hoja_vida", "estado": "rechazado", "motivo": "falta firma"}, th)
        self.assertIn("tareas", det)
        st, det, _ = self._req("/api/ingreso/tarea", {"id": id_, "tarea": "T05"}, th)
        self.assertEqual(next(t for t in det["tareas"] if t["id"] == "T05")["estado_seguimiento"], "completada")
        st, borrador, _ = self._req("/api/ingreso/bienvenida/borrador", {"id": id_}, th)
        self.assertEqual(borrador["origen"], "plantilla")  # modo extractivo: sin LLM
        st, det, _ = self._req("/api/ingreso/bienvenida/aprobar", {"id": id_, "texto": borrador["texto"] + "\nUn saludo."}, th)
        self.assertEqual(det["ingreso"]["bienvenida"]["aprobado_por"], "Ana Pérez")
        self.assertGreater(det["ingreso"]["bienvenida"]["proporcion_cambio"], 0)
        st, ind, _ = self._req("/api/indicadores", cookie=th)
        self.assertEqual(ind["asistente"]["utiles"], 1)
        st, csv, _ = self._req("/api/indicadores.csv", cookie=th)
        self.assertIn("horas_registro_a_expediente", csv)
        self.assertEqual(self._req("/api/ingresos", dict(DATOS, fecha_ingreso="2026-12-06"), th)[0], 400)
        self.assertIn("Portal de ingreso", urllib.request.urlopen(self.url + "/portal", timeout=10).read().decode())


if __name__ == "__main__":
    unittest.main()
