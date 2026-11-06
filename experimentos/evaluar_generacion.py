"""Evaluación de extremo a extremo del asistente (recuperación + generación + guardas).

    python -m experimentos.evaluar_generacion --modo extractivo          # siempre disponible
    python -m experimentos.evaluar_generacion --modo llm_local           # requiere Ollama
    python -m experimentos.evaluar_generacion --modo llm_local --modelo llama3.2:3b
    python -m experimentos.evaluar_generacion --modo llm_local --limite 10   # prueba rápida

En Windows, EVALUAR_LLM_WINDOWS.bat ejecuta todo (instala, descarga el modelo, evalúa y empaqueta).

Métricas (sobre el conjunto reservado y, por separado, el de desarrollo):
- exactitud_extremo_a_extremo: pregunta dentro del alcance -> responde citando el pasaje
  correcto; fuera del alcance -> deriva a Talento Humano.
- tasa_fidelidad_verificada: proporción de respuestas entregadas que pasan la guarda de salida
  (cita un pasaje recuperado y toda cifra está en el pasaje citado). Es una medida automática y
  parcial de groundedness: no detecta afirmaciones falsas sin cifras.
- respuestas_llm / tasa_descarte_llm: respuestas que produjo el LLM y proporción rechazada por la
  guarda (sustituida por el respaldo extractivo).
- errores_llm: consultas en que el LLM falló o superó el tiempo de espera (se usó el respaldo).
- derivaciones_del_llm: preguntas que el LLM derivó aunque la recuperación superó el umbral.
- latencia: media, mediana y percentil 95 (segundos por consulta), con el equipo registrado.

Guarda todas las respuestas en CSV y dos copias de una muestra de 30 respuestas para la revisión
humana independiente (rúbrica: docs/rubrica_revision_humana.md; análisis:
experimentos/analizar_revision_humana.py). Si la ejecución se interrumpe, al volver a lanzarla
continúa donde quedó (caché en resultados/v1/cache/).
"""
import argparse
import csv
import json
import os
import platform
import random
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.asistente import Asistente, cargar_config
from src.corpus import cargar_preguntas

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "resultados" / "v1"
CONJUNTOS = {"reservado": RAIZ / "data" / "prueba_reservada.csv", "desarrollo": RAIZ / "data" / "preguntas_evaluacion.csv"}
TAMANO_MUESTRA_HUMANA = 30
SEMILLA = 20260928


def fila_de(q: dict, r: dict) -> dict:
    gen = r.get("generacion") or {}
    ver = gen.get("verificacion") or {}
    fuente_id = (r.get("fuente") or "").rsplit("(", 1)[-1].rstrip(")") if r.get("fuente") else ""
    dentro = q["pasaje_correcto"] != "NINGUNO"
    correcta = (r["accion"] == "responder" and fuente_id == q["pasaje_correcto"]) if dentro else r["accion"] != "responder"
    motivo_gen = gen.get("motivo") or ""
    return dict(id=q["id"], tipo=q["tipo"], pasaje_correcto=q["pasaje_correcto"], accion=r["accion"],
                fuente=fuente_id, correcta=int(correcta), modo=gen.get("modo", ""),
                fiel="" if not ver else int(bool(ver.get("fiel"))),
                origen_respuesta=("llm_verificada" if "verificada" in motivo_gen else
                                  "llm_descartada" if "descartada" in motivo_gen else
                                  "llm_error" if "error del LLM" in motivo_gen else
                                  "extractivo" if gen else "sin_generacion"),
                motivo=r.get("motivo") or "", motivo_generacion=motivo_gen,
                llm_descartada=gen.get("respuesta_llm_descartada", ""),
                latencia_s=r["latencia_total_s"], pregunta=q["pregunta"], respuesta=r["respuesta"])


def resumir(filas: list[dict]) -> dict:
    entregadas = [f for f in filas if f["accion"] == "responder"]
    origen = [f["origen_respuesta"] for f in filas]
    llm = [f for f in filas if f["origen_respuesta"] in ("llm_verificada", "llm_descartada")]
    lat = np.array([f["latencia_s"] for f in filas], float)
    lat_llm = np.array([f["latencia_s"] for f in llm], float)
    tipos = sorted({f["tipo"] for f in filas})
    media = lambda xs: float(np.mean(xs)) if len(xs) else None
    return dict(
        preguntas=len(filas),
        exactitud_extremo_a_extremo=media([f["correcta"] for f in filas]),
        exactitud_por_tipo={t: media([f["correcta"] for f in filas if f["tipo"] == t]) for t in tipos},
        respuestas_entregadas=len(entregadas),
        respuestas_erroneas=sum(1 for f in entregadas if not f["correcta"]),
        tasa_respuesta_erronea=len([f for f in entregadas if not f["correcta"]]) / len(filas) if filas else None,
        tasa_fidelidad_verificada=media([f["fiel"] == 1 for f in entregadas]),
        respuestas_llm=len(llm),
        tasa_descarte_llm=(origen.count("llm_descartada") / len(llm)) if llm else None,
        errores_llm=origen.count("llm_error"),
        derivaciones_del_llm=sum(1 for f in filas if "pasajes no contienen" in f["motivo"]),
        latencia_s=dict(media=float(lat.mean()), mediana=float(np.median(lat)), p95=float(np.percentile(lat, 95))),
        latencia_llm_s=(dict(media=float(lat_llm.mean()), mediana=float(np.median(lat_llm)),
                             p95=float(np.percentile(lat_llm, 95))) if len(lat_llm) else None),
    )


def info_entorno(config: dict, modo: str) -> dict:
    info = dict(fecha_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"), sistema=platform.platform(),
                procesador=platform.processor() or platform.machine(), nucleos=os.cpu_count(),
                python=platform.python_version())
    try:
        import ctypes  # memoria total en Windows
        if sys.platform == "win32":
            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("c", ctypes.c_ulong), ("t", ctypes.c_ulonglong)] + \
                           [(f"x{i}", ctypes.c_ulonglong) for i in range(6)]
            m = M(); m.l = ctypes.sizeof(M)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            info["ram_gb"] = round(m.t / 2**30, 1)
        elif hasattr(os, "sysconf"):
            info["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except Exception:
        pass
    if modo == "llm_local":
        url = config["generacion"]["url_ollama"].rstrip("/")
        try:
            with urllib.request.urlopen(f"{url}/api/version", timeout=5) as r:
                info["ollama_version"] = json.loads(r.read()).get("version")
            req = urllib.request.Request(f"{url}/api/show", data=json.dumps(
                {"model": config["generacion"]["modelo_ollama"]}).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read()).get("details", {})
            info["modelo_detalles"] = {k: d.get(k) for k in ("family", "parameter_size", "quantization_level", "format")}
        except Exception as e:  # el servidor simulado de las pruebas no implementa todo
            info["ollama_info_error"] = type(e).__name__
    return info


def calentar(asistente: Asistente) -> float | None:
    """Primera consulta para cargar el modelo en memoria (no se cuenta en la latencia)."""
    t0 = time.perf_counter()
    try:
        asistente.responder("¿Qué día me entregan la computadora?")
        return round(time.perf_counter() - t0, 1)
    except Exception:
        return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=["extractivo", "llm_local"], default="extractivo")
    ap.add_argument("--modelo", default=None, help="modelo de Ollama (por defecto, el de config/modelo_final.json)")
    ap.add_argument("--url", default=None, help="dirección de Ollama (por defecto, http://localhost:11434)")
    ap.add_argument("--timeout", type=float, default=None, help="segundos de espera por respuesta del LLM")
    ap.add_argument("--conjuntos", default="reservado,desarrollo", help="reservado, desarrollo o ambos")
    ap.add_argument("--limite", type=int, default=None, help="solo las primeras N preguntas (prueba rápida)")
    ap.add_argument("--sin-cache", action="store_true", help="no reutilizar respuestas de una ejecución anterior")
    a = ap.parse_args()

    config = cargar_config()
    if a.modelo:
        config["generacion"]["modelo_ollama"] = a.modelo
    if a.timeout:
        config["generacion"]["timeout_s"] = a.timeout
    if a.url:
        config["generacion"]["url_ollama"] = a.url
    asistente = Asistente(config=config, modo=a.modo)
    modelo = config["generacion"]["modelo_ollama"]
    etiqueta = a.modo if a.modo == "extractivo" else f"llm_local_{modelo.replace(':', '_').replace('/', '_')}"
    if a.limite:
        etiqueta += f"_prueba{a.limite}"
    SALIDA.mkdir(parents=True, exist_ok=True)

    informe = dict(modo=a.modo, modelo=modelo if a.modo == "llm_local" else None, version=config["version"],
                   umbral=config["umbral_derivacion"], prompt=config["generacion"]["prompt"],
                   temperatura=config["generacion"]["temperatura"], timeout_s=config["generacion"]["timeout_s"],
                   entorno=info_entorno(config, a.modo), conjuntos={})
    if a.modo == "llm_local":
        informe["calentamiento_s"] = calentar(asistente)
        print(f"Modelo {modelo} cargado (calentamiento: {informe['calentamiento_s']} s)", flush=True)

    cache_ruta = SALIDA / "cache" / f"{etiqueta}.jsonl"
    cache = {}
    if a.modo == "llm_local" and not a.sin_cache and cache_ruta.exists():
        for linea in cache_ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                d = json.loads(linea)
                cache[(d["conjunto"], d["id"])] = d["fila"]
        print(f"Reanudando: {len(cache)} respuestas ya calculadas", flush=True)
    cache_ruta.parent.mkdir(exist_ok=True)

    for nombre in [c.strip() for c in a.conjuntos.split(",") if c.strip()]:
        preguntas = cargar_preguntas(CONJUNTOS[nombre])[: a.limite] if a.limite else cargar_preguntas(CONJUNTOS[nombre])
        filas, t0 = [], time.time()
        for i, q in enumerate(preguntas, 1):
            if (nombre, q["id"]) in cache:
                filas.append(cache[(nombre, q["id"])])
                continue
            f = fila_de(q, asistente.responder(q["pregunta"]))
            filas.append(f)
            if a.modo == "llm_local":
                with cache_ruta.open("a", encoding="utf-8") as c:
                    c.write(json.dumps(dict(conjunto=nombre, id=q["id"], fila=f), ensure_ascii=False) + "\n")
            if i % 10 == 0 or i == len(preguntas):
                print(f"  {nombre}: {i}/{len(preguntas)} preguntas ({time.time() - t0:.0f} s)", flush=True)
        m = resumir(filas)
        informe["conjuntos"][nombre] = m
        with (SALIDA / f"generacion_{etiqueta}_{nombre}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=filas[0].keys())
            w.writeheader()
            w.writerows(filas)
        if nombre == "reservado":
            muestra = random.Random(SEMILLA).sample(filas, min(TAMANO_MUESTRA_HUMANA, len(filas)))
            campos = ["id", "pregunta", "respuesta", "fuente", "pasaje_correcto", "accion",
                      "revision_correcta", "revision_fiel", "revision_util", "revision_comentario"]
            for revisor in ("revisor1", "revisor2"):
                with (SALIDA / f"revision_humana_{etiqueta}_{revisor}.csv").open("w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=campos)
                    w.writeheader()
                    w.writerows({k: x.get(k, "") for k in campos} for x in muestra)
        print(nombre, json.dumps({k: m[k] for k in ("exactitud_extremo_a_extremo", "tasa_fidelidad_verificada",
                                                    "respuestas_llm", "tasa_descarte_llm", "errores_llm")},
                                 ensure_ascii=False), flush=True)
    (SALIDA / f"generacion_{etiqueta}.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n",
                                                        encoding="utf-8")
    print(f"Resultados: resultados/v1/generacion_{etiqueta}.json")


if __name__ == "__main__":
    main()
