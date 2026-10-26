"""Ejecuta todo el pipeline en orden y regenera los resultados (≈ 1 minuto, sin LLM).

    python -m experimentos.reproducir_todo
"""
import runpy
import sys
import time
import unittest

PASOS = [
    ("1/8 Validación cruzada v0.2 (A0–A5)", "experimentos.validacion_cruzada"),
    ("2/8 Validación cruzada v1.0 (A4, B1–B5)", "experimentos.validacion_v1"),
    ("3/8 Umbral del modelo final -> config/modelo_final.json", "experimentos.ajustar_modelo_final"),
    ("4/8 Prueba final en el conjunto reservado", "experimentos.prueba_final"),
    ("5/8 Robustez y seguridad", "experimentos.robustez"),
    ("6/8 Evaluación de extremo a extremo (modo extractivo)", "experimentos.evaluar_generacion"),
    ("7/8 Figuras", None),
]


def main():
    t0 = time.time()
    for titulo, modulo in PASOS:
        print(f"\n=== {titulo} ===", flush=True)
        if modulo is None:
            runpy.run_module("experimentos.graficos", run_name="__main__")
            runpy.run_module("experimentos.graficos_v1", run_name="__main__")
            continue
        sys.argv = [modulo]
        runpy.run_module(modulo, run_name="__main__")
    print("\n=== 8/8 Pruebas unitarias ===", flush=True)
    r = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests", top_level_dir="."))
    print(f"\nListo en {time.time() - t0:.0f} s. Resultados en resultados/ y resultados/v1/.")
    sys.exit(0 if r.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
