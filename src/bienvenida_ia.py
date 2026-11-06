"""Borrador del correo de bienvenida redactado por el LLM local, con verificación y revisión humana.

Por qué usa IA: la plantilla fija dice lo mismo a todos. El LLM adapta el mensaje al cargo, al
área, a la modalidad y a los documentos que faltan, en un texto natural. Por qué no se envía solo:
un texto generado puede inventar datos, así que (1) la guarda determinista revisa el borrador y,
si falla o el LLM no está disponible, se usa la plantilla; y (2) Talento Humano lo edita y lo
aprueba antes de enviarlo. El sistema registra cuánto cambió el analista el borrador.
"""
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from .flujos.orquestador import AGENDA, NOMBRE_DOC, _render
from .generacion import cargar_prompt

PROMPT = "prompts/bienvenida_v1.txt"
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
# Indicaciones tomadas de las políticas sintéticas del corpus (trazabilidad: P01, P19, P37 y P38).
INDICACIONES = {
    "presencial": ["El primer día preséntate a las 08:30 en la recepción del edificio matriz, piso 2. (P01)",
                   "La computadora y los periféricos se entregan el día 4 de la inducción. (P19)"],
    "remota": ["El primer día preséntate a las 08:30 en la recepción del edificio matriz, piso 2. (P01)",
               "Para trabajar fuera de la oficina se usa solo la VPN institucional con doble factor de autenticación; "
               "tu jefe inmediato solicita el acceso y Tecnología lo habilita. (P37)",
               "Solo se puede trabajar remotamente con el equipo asignado por la institución. (P38)"],
}


def fecha_larga(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def _limpio(v: str) -> str:
    return re.sub(r"[<>{}\[\]]", "", str(v)).strip()[:80]


def datos_borrador(ingreso: dict, calendario) -> dict:
    ingreso_d = date.fromisoformat(ingreso["fecha_ingreso"])
    limite = calendario.sumar(ingreso_d, -3).isoformat()
    pendientes = [NOMBRE_DOC[d["id"]] for d in ingreso["documentos"] if d["estado"] != "entregado"]
    return dict(nombre=_limpio(ingreso["nombre"]), cargo=_limpio(ingreso["cargo"]), area=_limpio(ingreso["area"]),
                modalidad=ingreso["modalidad"], fecha_ingreso=fecha_larga(ingreso["fecha_ingreso"]),
                fecha_limite_documentos=fecha_larga(limite), documentos_pendientes=pendientes,
                indicaciones=INDICACIONES[ingreso["modalidad"]],
                primera_semana=[a.split(": ", 1)[1] for a in AGENDA])


def texto_datos(d: dict) -> str:
    return "\n".join([
        f"nombre: {d['nombre']}", f"cargo: {d['cargo']}", f"área: {d['area']}", f"modalidad: {d['modalidad']}",
        f"fecha de ingreso: {d['fecha_ingreso']}",
        "documentos pendientes: " + ("; ".join(d["documentos_pendientes"]) or "ninguno (expediente completo)"),
        f"plazo para documentos: {d['fecha_limite_documentos']}" if d["documentos_pendientes"] else "plazo para documentos: no aplica",
        "indicaciones de la modalidad: " + " ".join(re.sub(r" \(P\d+\)$", "", i) for i in d["indicaciones"]),
        "primera semana: " + "; ".join(f"día {i}: {a}" for i, a in enumerate(d["primera_semana"], 1)),
    ])


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def verificar(texto: str, d: dict) -> dict:
    """Guarda determinista del borrador. Devuelve fiel=True solo si pasa todos los controles."""
    motivos = []
    fuente = texto_datos(d)
    cifras_fuente = set(re.findall(r"\d+(?::\d+)?", fuente))
    ajenas = sorted({c for c in re.findall(r"\d+(?::\d+)?", texto) if c not in cifras_fuente})
    if ajenas:
        motivos.append("cifras que no están en los datos: " + ", ".join(ajenas))
    if re.search(r"https?://|www\.|\b[\w.+-]+@[\w-]+\.\w", texto):
        motivos.append("contiene enlaces o correos")
    if re.search(r"[\[{]|<[a-z]", texto, re.I):
        motivos.append("contiene marcadores sin reemplazar")
    primer_nombre = _norm(d["nombre"].split()[0])
    if primer_nombre not in _norm(texto):
        motivos.append("no saluda a la persona por su nombre")
    dia_mes = _norm(" ".join(d["fecha_ingreso"].split()[1:4]))  # "7 de diciembre"
    if dia_mes not in _norm(texto):
        motivos.append("no menciona la fecha de ingreso tal como está en los datos")
    if d["documentos_pendientes"] and _norm(" ".join(d["fecha_limite_documentos"].split()[1:4])) not in _norm(texto):
        motivos.append("no menciona el plazo de los documentos")
    palabras = len(texto.split())
    if not 50 <= palabras <= 320:
        motivos.append(f"longitud fuera de rango ({palabras} palabras)")
    if not texto.lstrip().lower().startswith("asunto:"):
        motivos.append("falta la línea de asunto")
    return dict(fiel=not motivos, motivos=motivos, palabras=palabras)


def plantilla(ingreso: dict, d: dict) -> str:
    return _render("bienvenida", nombre=d["nombre"], area=d["area"], cargo=d["cargo"],
                   fecha_ingreso=ingreso["fecha_ingreso"], fecha_limite_documentos=d["fecha_limite_documentos"])


class RedactorBienvenida:
    def __init__(self, config: dict, forzar: str | None = None):
        g = config["generacion"]
        self.modelo, self.url = g["modelo_ollama"], g["url_ollama"].rstrip("/")
        self.temperatura, self.timeout_s = g["temperatura"], max(g["timeout_s"], 120)
        self.prompt = cargar_prompt(PROMPT)
        self.forzar = forzar

    def _llamar(self, datos: str) -> str:
        sistema, usuario = self.prompt.split("[USUARIO]")
        mensajes = [dict(role="system", content=sistema.replace("[SISTEMA]", "").strip()),
                    dict(role="user", content=usuario.replace("{datos}", datos).strip())]
        cuerpo = json.dumps(dict(model=self.modelo, messages=mensajes, stream=False,
                                 options=dict(temperature=self.temperatura, num_predict=500, seed=20260928))).encode()
        req = urllib.request.Request(f"{self.url}/api/chat", data=cuerpo, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            return json.loads(r.read()).get("message", {}).get("content", "").strip()

    def borrador(self, ingreso: dict, calendario, llm_disponible: bool) -> dict:
        d = datos_borrador(ingreso, calendario)
        base = dict(prompt=PROMPT, modelo=self.modelo, datos=texto_datos(d))
        if self.forzar == "extractivo" or not llm_disponible:
            return dict(base, texto=plantilla(ingreso, d), origen="plantilla", modelo=None,
                        motivo="LLM local no disponible: se usa la plantilla", verificacion=None, latencia_s=0)
        t0 = time.perf_counter()
        try:
            texto = self._llamar(texto_datos(d))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
            return dict(base, texto=plantilla(ingreso, d), origen="plantilla", modelo=None,
                        motivo=f"error del LLM ({type(e).__name__}): se usa la plantilla", verificacion=None,
                        latencia_s=round(time.perf_counter() - t0, 2))
        v = verificar(texto, d)
        lat = round(time.perf_counter() - t0, 2)
        if not v["fiel"]:
            return dict(base, texto=plantilla(ingreso, d), origen="plantilla", modelo=None, verificacion=v,
                        borrador_descartado=texto, latencia_s=lat,
                        motivo="borrador de la IA descartado por la verificación: " + "; ".join(v["motivos"]))
        return dict(base, texto=texto, origen="llm_local", verificacion=v, latencia_s=lat,
                    motivo="borrador de la IA verificado; requiere revisión y aprobación de Talento Humano")
