"""Pruebas de los scripts de validación empírica (LLM real, revisión humana, línea base, usuarios)."""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experimentos import analizar_estudio_usuarios as ae
from experimentos import linea_base_real as lb
from src.lectura import leer_csv, numero
from tests import ollama_simulado

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLO = RAIZ / "data" / "reales" / "ejemplo"
V1 = RAIZ / "resultados" / "v1"


class TestLectura(unittest.TestCase):
    def test_excel_en_espanol(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.csv"
            p.write_bytes("id;minutos;comentario\nC1;12,5;revisión\n;;\n".encode("cp1252"))
            filas = leer_csv(p)
            self.assertEqual(len(filas), 1)
            self.assertEqual(numero(filas[0]["minutos"]), 12.5)
            self.assertEqual(filas[0]["comentario"], "revisión")


class TestEvaluacionLLMConServidorSimulado(unittest.TestCase):
    etiqueta = "llm_local_qwen2.5_3b_prueba5"

    @classmethod
    def setUpClass(cls):
        cls.srv = ollama_simulado.iniciar(0)
        url = f"http://127.0.0.1:{cls.srv.server_port}"
        cls.salida = subprocess.run([sys.executable, "-m", "experimentos.evaluar_generacion", "--modo", "llm_local",
                                     "--url", url, "--limite", "5", "--conjuntos", "reservado", "--sin-cache"],
                                    cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        for f in list(V1.glob(f"*{cls.etiqueta}*")) + list((V1 / "cache").glob(f"*{cls.etiqueta}*")):
            f.unlink()

    def test_evaluacion_y_revision_humana(self):
        self.assertEqual(self.salida.returncode, 0, self.salida.stderr)
        inf = json.loads((V1 / f"generacion_{self.etiqueta}.json").read_text(encoding="utf-8"))
        r = inf["conjuntos"]["reservado"]
        self.assertEqual(r["preguntas"], 5)
        self.assertGreater(r["respuestas_llm"], 0)
        self.assertIn("ollama_version", inf["entorno"])
        # dos revisores que discrepan en una fila
        for k, revisor in enumerate(("revisor1", "revisor2")):
            ruta = V1 / f"revision_humana_{self.etiqueta}_{revisor}.csv"
            filas = leer_csv(ruta)
            for i, f in enumerate(filas):
                respondio = f["accion"] == "responder"
                f.update(revision_correcta="1" if i or not k else "0", revision_fiel="1" if respondio else "NA",
                         revision_util="4" if respondio else "")
            with ruta.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=filas[0].keys(), delimiter=";")
                w.writeheader()
                w.writerows(filas)
        res = subprocess.run([sys.executable, "-m", "experimentos.analizar_revision_humana", "--etiqueta", self.etiqueta],
                             cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        a = json.loads((V1 / f"revision_humana_{self.etiqueta}_analisis.json").read_text(encoding="utf-8"))
        self.assertEqual(a["acuerdo_entre_revisores"]["revision_correcta"]["porcentaje"], 0.8)
        self.assertEqual(len(a["desacuerdos_pendientes"]), 1)
        self.assertEqual(a["tasa_alucinacion_humana"]["valor"], 0.0)


class TestLineaBase(unittest.TestCase):
    def test_ejemplo(self):
        rng = np.random.default_rng(1)
        h = lb.analizar_hris(leer_csv(EJEMPLO / "hris_extraccion.csv"), rng)
        self.assertEqual(h["volumen"]["meses"], 12)
        self.assertIn("DATO VALIDADO", h["volumen"]["por_mes"]["etiqueta"])
        b = lb.analizar_bitacora(leer_csv(EJEMPLO / "bitacora_tiempos.csv"), rng)
        self.assertEqual(b["casos_completos"], 15)
        self.assertAlmostEqual(sum(v["participacion"] for v in b["actividades"].values()), 1.0, places=3)

    def test_errores_de_formato(self):
        e = lb.validar_hris([dict(id_caso="C1", mes_ingreso="11/2026")]) + \
            lb.validar_bitacora([dict(actividad="X1", minutos="abc")])
        self.assertEqual(len(e), 3)

    def test_n_insuficiente_se_marca(self):
        self.assertIn("INSUFICIENTE", lb.etiqueta(4, "bitácora"))


class TestEstudioUsuarios(unittest.TestCase):
    def test_sus(self):
        mejor = {f"sus{i}": ("5" if i % 2 else "1") for i in range(1, 11)}
        peor = {f"sus{i}": ("1" if i % 2 else "5") for i in range(1, 11)}
        self.assertEqual(ae.sus(mejor), 100)
        self.assertEqual(ae.sus(peor), 0)

    def test_sesiones_ejemplo(self):
        s = ae.analizar_sesiones(leer_csv(EJEMPLO / "sesiones_analistas.csv"), np.random.default_rng(1))
        self.assertEqual(s["pares"], 12)
        r = s["reduccion_tareas_medidas"]
        self.assertLess(r["ic95"][0], r["valor"])
        self.assertLess(r["valor"], r["ic95"][1])

    def test_reduccion_total_acotada_por_tareas_no_automatizables(self):
        rng = np.random.default_rng(1)
        base = dict(esfuerzo=lb.analizar_bitacora(leer_csv(EJEMPLO / "bitacora_tiempos.csv"), rng))
        s = ae.analizar_sesiones(leer_csv(EJEMPLO / "sesiones_analistas.csv"), rng)
        total = ae.reduccion_proceso_completo(base, s, rng)
        self.assertLess(total["valor"], s["reduccion_tareas_medidas"]["valor"])
        self.assertLessEqual(total["valor"], base["esfuerzo"]["participacion_tareas_automatizables_o_ia"])

    def test_veredictos(self):
        self.assertTrue(ae.veredicto(0.6, [0.55, 0.65], 0.5).startswith("cumple con holgura"))
        self.assertTrue(ae.veredicto(0.6, [0.4, 0.7], 0.5).startswith("cumple (estimación puntual)"))
        self.assertEqual(ae.veredicto(0.4, [0.3, 0.5], 0.5), "no cumple")

    def test_validacion_cuestionario(self):
        self.assertTrue(ae.validar_cuestionario([{**{f"sus{i}": "3" for i in range(1, 11)}, "satisfaccion_general": "7"}]))


if __name__ == "__main__":
    unittest.main()
