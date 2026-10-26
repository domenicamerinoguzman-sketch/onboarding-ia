"""Asistente de consultas de inducción: pipeline RAG completo (v1.0).

    pregunta -> guardas de entrada -> recuperación híbrida (BM25 + sinónimos + caracteres)
             -> decisión de derivación (umbral) -> generación dual (LLM local o extractiva)
             -> verificación de fidelidad -> respuesta con fuente y trazabilidad

Uso:
    python -m src.asistente "¿Cuándo me entregan la computadora?"
    python -m src.asistente --modo extractivo "¿Cuánto dura el período de prueba?"
    python -m src.asistente --modo llm_local "..."      (requiere Ollama con el modelo configurado)
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .corpus import cargar_corpus
from .generacion import GeneradorDual
from .guardas import MENSAJE_DERIVACION, revisar_entrada
from .recuperadores import construir
from .sinonimos import expansiones_aplicadas

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ / "config" / "modelo_final.json"
RUTA_REGISTRO = RAIZ / "logs" / "interacciones.jsonl"


def cargar_config(ruta: Path = RUTA_CONFIG) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


class Asistente:
    def __init__(self, config: dict | None = None, modo: str | None = None, registrar: bool = False):
        self.config = config or cargar_config()
        self.pasajes = cargar_corpus()
        self.modelo = construir(self.config["recuperador"], self.pasajes)
        self.umbral = self.config["umbral_derivacion"]
        self.k = self.config["pasajes_contexto"]
        self.generador = GeneradorDual(self.config, forzar=modo) if "generacion" in self.config else None
        self.registrar = registrar

    # --- etapa de recuperación (sin generación); usada también por la evaluación ---
    def recuperar(self, pregunta: str) -> dict:
        s = self.modelo.puntuar(pregunta)
        orden = np.argsort(-s, kind="stable")[: self.k]
        candidatos = [dict(id=self.pasajes[i].id, documento=self.pasajes[i].documento, titulo=self.pasajes[i].titulo,
                           texto=self.pasajes[i].texto, puntaje=round(float(s[i]), 3)) for i in orden]
        return dict(candidatos=candidatos, puntaje_top1=round(float(s[orden[0]]), 3),
                    deriva=bool(s[orden[0]] < self.umbral), indice_top1=int(orden[0]))

    def responder(self, pregunta: str) -> dict:
        t0 = time.perf_counter()
        entrada = revisar_entrada(pregunta)
        base = dict(version=self.config.get("version"), pregunta=entrada["pregunta_limpia"],
                    datos_personales_enmascarados=entrada["datos_personales"])
        if entrada["bloquear"]:
            r = dict(base, accion="derivar_talento_humano", respuesta=MENSAJE_DERIVACION,
                     motivo="posible inyección de instrucciones: la consulta no se envía al modelo",
                     guardas=dict(inyeccion=entrada["inyeccion"]))
            return self._cerrar(r, t0)

        rec = self.recuperar(entrada["pregunta_limpia"])
        top = rec["candidatos"][0]
        traza = dict(puntaje_top1=rec["puntaje_top1"], umbral=self.umbral,
                     expansiones=expansiones_aplicadas(entrada["pregunta_limpia"]),
                     terminos_top1={t: round(v, 3) for t, v in list(
                         self.modelo.contribuciones(entrada["pregunta_limpia"], rec["indice_top1"]).items())[:6]}
                     if hasattr(self.modelo, "contribuciones") else {},
                     candidatos=[{k: c[k] for k in ("id", "titulo", "puntaje")} for c in rec["candidatos"]])
        if rec["deriva"]:
            r = dict(base, accion="derivar_talento_humano", respuesta=MENSAJE_DERIVACION,
                     motivo="confianza de recuperación bajo el umbral", trazabilidad=traza)
            return self._cerrar(r, t0)

        if self.generador is None:  # configuración v0.2: solo recuperación
            r = dict(base, accion="responder", respuesta=top["texto"], fuente=f"{top['documento']} > {top['titulo']} ({top['id']})",
                     trazabilidad=traza)
            return self._cerrar(r, t0)

        g = self.generador.generar(entrada["pregunta_limpia"], rec["candidatos"])
        if g.get("verificacion", {}).get("es_derivacion"):
            accion, motivo = "derivar_talento_humano", "el modelo indicó que los pasajes no contienen la respuesta"
        else:
            accion, motivo = "responder", None
        citadas = g.get("verificacion", {}).get("citas") or [top["id"]]
        fuente = next((c for c in rec["candidatos"] if c["id"] == citadas[0]), top)
        r = dict(base, accion=accion, respuesta=g["texto"],
                 fuente=None if accion != "responder" else f"{fuente['documento']} > {fuente['titulo']} ({fuente['id']})",
                 generacion=dict(modo=g["modo"], motivo=g.get("motivo_modo"), latencia_s=g.get("latencia_s"),
                                 verificacion=g.get("verificacion"), modelo=g.get("modelo")),
                 trazabilidad=traza, revision_humana="respuesta informativa; la política vigente prevalece")
        if motivo:
            r["motivo"] = motivo
        if "respuesta_llm_descartada" in g:
            r["generacion"]["respuesta_llm_descartada"] = g["respuesta_llm_descartada"]
        return self._cerrar(r, t0)

    def _cerrar(self, r: dict, t0: float) -> dict:
        r["latencia_total_s"] = round(time.perf_counter() - t0, 4)
        if self.registrar:
            self._registrar(r)
        return r

    def _registrar(self, r: dict) -> None:
        """Registro mínimo para auditoría: sin la pregunta en claro (solo su huella) y sin el pasaje."""
        RUTA_REGISTRO.parent.mkdir(exist_ok=True)
        fila = dict(fecha=datetime.now(timezone.utc).isoformat(timespec="seconds"), version=r.get("version"),
                    huella_pregunta=hashlib.sha256(r["pregunta"].encode("utf-8")).hexdigest()[:16],
                    accion=r["accion"], fuente=r.get("fuente"), motivo=r.get("motivo"),
                    modo=r.get("generacion", {}).get("modo"), fiel=r.get("generacion", {}).get("verificacion", {}).get("fiel"),
                    pii=r.get("datos_personales_enmascarados"), latencia_s=r["latencia_total_s"])
        with RUTA_REGISTRO.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Asistente de inducción (RAG)")
    ap.add_argument("pregunta", nargs="*", default=["¿Cuándo me entregan la computadora?"])
    ap.add_argument("--modo", choices=["auto", "extractivo", "llm_local"], default="auto",
                    help="auto: LLM local si está disponible, si no extractivo")
    ap.add_argument("--registrar", action="store_true", help="guarda la interacción en logs/interacciones.jsonl")
    a = ap.parse_args()
    asistente = Asistente(modo=None if a.modo == "auto" else a.modo, registrar=a.registrar)
    print(json.dumps(asistente.responder(" ".join(a.pregunta)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
