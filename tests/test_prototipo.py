"""Pruebas mínimas del prototipo. Ejecutar: python -m unittest discover -s tests -v"""
import csv
import unittest
from pathlib import Path

from src.asistente import Asistente
from src.corpus import cargar_corpus, cargar_preguntas
from src.preprocesamiento import tokenizar
from src.reglas_escalamiento import evaluar_caso

RAIZ = Path(__file__).resolve().parent.parent


class TestCorpus(unittest.TestCase):
    def test_corpus_y_preguntas_consistentes(self):
        ids = {p.id for p in cargar_corpus()}
        self.assertEqual(len(ids), 46)
        for q in cargar_preguntas():
            self.assertTrue(q["pasaje_correcto"] in ids or q["pasaje_correcto"] == "NINGUNO", q["id"])

    def test_normalizacion(self):
        self.assertEqual(tokenizar("Contraseñas y Credenciales", stemming=False), ["contrasenas", "credenciales"])


class TestAsistente(unittest.TestCase):
    def test_respuesta_con_fuente(self):
        r = Asistente().responder("¿Cuándo me entregan la computadora y el equipo?")
        self.assertEqual(r["accion"], "responder")
        self.assertIn("P19", r["fuente"])

    def test_estructura_derivacion(self):
        r = Asistente().responder("xyz qwerty")
        self.assertEqual(r["accion"], "derivar_talento_humano")


class TestReglas(unittest.TestCase):
    def test_caso_c075_ahora_escala(self):
        r = evaluar_caso({"id": "C075", "aprobacion_especial": 1})
        self.assertTrue(r["requiere_intervencion"])
        self.assertIn("Aprobación especial pendiente", r["motivos"])

    def test_reglas_cubren_casos_sinteticos(self):
        with (RAIZ / "v0_reglas" / "casos_sinteticos.csv").open(encoding="utf-8") as f:
            for c in csv.DictReader(f):
                self.assertEqual(evaluar_caso(c)["requiere_intervencion"], c["requiere_intervencion"] == "1")


if __name__ == "__main__":
    unittest.main()
