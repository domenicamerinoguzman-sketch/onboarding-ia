"""Etapa generativa del RAG en modo dual.

- GeneradorOllama: LLM local servido por Ollama (http://localhost:11434). Los datos no salen
  del equipo, lo que evita enviar información a un proveedor externo.
- GeneradorExtractivo: respaldo sin LLM. Devuelve las oraciones del pasaje más relevantes
  para la pregunta, con plantilla fija y cita. Es fiel por construcción (no redacta texto
  nuevo), pero menos natural.
- GeneradorDual: usa el LLM si está disponible; verifica su respuesta con las guardas de
  salida y, si no pasa la verificación, el LLM falla o no responde a tiempo, usa el respaldo.
"""
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .guardas import MENSAJE_DERIVACION, verificar_salida
from .preprocesamiento import tokenizar
from .sinonimos import expandir

RAIZ = Path(__file__).resolve().parent.parent


def cargar_prompt(ruta: str) -> str:
    lineas = (RAIZ / ruta).read_text(encoding="utf-8").splitlines()
    return "\n".join(l for l in lineas if not l.startswith("#")).strip()


def formatear_pasajes(pasajes: list[dict]) -> str:
    return "\n".join(f'<pasaje id="{p["id"]}" titulo="{p["documento"]} > {p["titulo"]}">\n{p["texto"]}\n</pasaje>'
                     for p in pasajes)


def dividir_oraciones(texto: str) -> list[str]:
    # Divide en ". " evitando cortar horas (08:30) o decimales.
    return [o.strip() for o in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ\"«])", texto) if o.strip()]


class GeneradorExtractivo:
    nombre = "extractivo"

    def __init__(self, max_oraciones: int = 2):
        self.max_oraciones = max_oraciones

    def generar(self, pregunta: str, pasajes: list[dict]) -> dict:
        t0 = time.perf_counter()
        top = pasajes[0]
        q = set(tokenizar(expandir(pregunta)))
        oraciones = dividir_oraciones(top["texto"])
        puntaje = [len(q & set(tokenizar(o))) for o in oraciones]
        orden = sorted(range(len(oraciones)), key=lambda i: (-puntaje[i], i))
        elegidas = sorted(i for i in orden[: self.max_oraciones] if puntaje[i] > 0) or [0]
        cuerpo = " ".join(oraciones[i] for i in elegidas)
        texto = f"Según la política «{top['documento']} > {top['titulo']}»: {cuerpo} [Fuente: {top['id']}]"
        return dict(texto=texto, modo=self.nombre, latencia_s=round(time.perf_counter() - t0, 4))


class GeneradorOllama:
    nombre = "llm_local"

    def __init__(self, modelo: str, url: str = "http://localhost:11434", prompt: str = "prompts/respuesta_rag_v2.txt",
                 temperatura: float = 0.0, max_tokens: int = 220, timeout_s: float = 60):
        self.modelo, self.url = modelo, url.rstrip("/")
        self.plantilla = cargar_prompt(prompt)
        self.temperatura, self.max_tokens, self.timeout_s = temperatura, max_tokens, timeout_s

    def disponible(self) -> bool:
        """True si Ollama responde y tiene descargado el modelo configurado."""
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=2) as r:
                modelos = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
            base = self.modelo.split(":")[0]
            return any(m == self.modelo or m.startswith(self.modelo) or
                       (":" not in self.modelo and m.split(":")[0] == base) for m in modelos)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return False

    def mensajes(self, pregunta: str, pasajes: list[dict]) -> list[dict]:
        sistema, usuario = self.plantilla.split("[USUARIO]")
        sistema = sistema.replace("[SISTEMA]", "").strip()
        usuario = usuario.replace("{pasajes}", formatear_pasajes(pasajes)).replace("{pregunta}", pregunta).strip()
        return [dict(role="system", content=sistema), dict(role="user", content=usuario)]

    def generar(self, pregunta: str, pasajes: list[dict]) -> dict:
        t0 = time.perf_counter()
        cuerpo = json.dumps(dict(model=self.modelo, messages=self.mensajes(pregunta, pasajes), stream=False,
                                 options=dict(temperature=self.temperatura, num_predict=self.max_tokens,
                                              seed=20260928))).encode("utf-8")
        req = urllib.request.Request(f"{self.url}/api/chat", data=cuerpo, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            datos = json.loads(r.read())
        texto = datos.get("message", {}).get("content", "").strip()
        return dict(texto=texto, modo=self.nombre, modelo=self.modelo, latencia_s=round(time.perf_counter() - t0, 3))


class GeneradorDual:
    """LLM local con verificación de fidelidad y respaldo extractivo."""

    def __init__(self, config: dict, forzar: str | None = None):
        g = config["generacion"]
        self.extractivo = GeneradorExtractivo()
        self.llm = GeneradorOllama(g["modelo_ollama"], g["url_ollama"], g["prompt"], g["temperatura"],
                                   g["max_tokens"], g["timeout_s"])
        self.forzar = forzar  # None (automático), "extractivo" o "llm_local"
        self._disponible = None

    def llm_disponible(self) -> bool:
        if self.forzar == "extractivo":
            return False
        if self._disponible is None:
            self._disponible = self.llm.disponible()
        return self._disponible

    def generar(self, pregunta: str, pasajes: list[dict]) -> dict:
        if not self.llm_disponible():
            if self.forzar == "llm_local":
                raise RuntimeError(f"Ollama no disponible en {self.llm.url} o falta el modelo {self.llm.modelo}. "
                                   f"Ejecute: ollama pull {self.llm.modelo}")
            r = self.extractivo.generar(pregunta, pasajes)
            r["verificacion"] = verificar_salida(r["texto"], pasajes)
            r["motivo_modo"] = "LLM no disponible: respaldo extractivo"
            return r
        try:
            r = self.llm.generar(pregunta, pasajes)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            r = self.extractivo.generar(pregunta, pasajes)
            r["verificacion"] = verificar_salida(r["texto"], pasajes)
            r["motivo_modo"] = f"error del LLM ({type(e).__name__}): respaldo extractivo"
            return r
        v = verificar_salida(r["texto"], pasajes)
        r["verificacion"] = v
        if v["fiel"]:
            r["motivo_modo"] = "respuesta del LLM verificada"
            if v.get("es_derivacion"):
                r["texto"] = MENSAJE_DERIVACION
            return r
        respaldo = self.extractivo.generar(pregunta, pasajes)
        respaldo["verificacion"] = verificar_salida(respaldo["texto"], pasajes)
        respaldo["motivo_modo"] = f"respuesta del LLM descartada ({v['motivo']}): respaldo extractivo"
        respaldo["respuesta_llm_descartada"] = r["texto"]
        respaldo["latencia_s"] = round(r["latencia_s"] + respaldo["latencia_s"], 3)
        return respaldo
