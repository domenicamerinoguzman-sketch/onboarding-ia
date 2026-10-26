"""Guardas de seguridad del asistente (controles deterministas, sin IA).

Entrada (antes de recuperar o generar):
- detecta intentos de inyección de prompts (OWASP LLM01) y los deriva sin llamar al LLM;
- detecta datos personales (cédula, correo, teléfono, tarjeta) y los enmascara, para que
  no lleguen al modelo ni al registro (minimización, LOPDP).

Salida (después de generar):
- exige que la respuesta cite un pasaje que efectivamente se recuperó;
- exige que toda cifra de la respuesta (plazos, montos, horas, porcentajes) aparezca en
  los pasajes entregados; si no, la respuesta se considera no fiel y se descarta.
"""
import re
import unicodedata

PATRONES_INYECCION = [
    r"ignora\w*\s+(las|tus|todas|cualquier)?\s*(instrucciones|reglas|indicaciones)",
    r"olvida\w*\s+(las|tus|todas)?\s*(instrucciones|reglas)",
    r"(nuevas|otras)\s+instrucciones",
    r"(act[uú]a|comp[oó]rtate|finge|haz de cuenta)\s+(como|que eres)",
    r"(eres|ahora eres)\s+(un|una)\s+(nuevo|nueva|otro|otra)?\s*(asistente|modelo|ia|hacker|administrador)",
    r"(muestra|revela|imprime|dime|repite)\w*\s+(tu|el|las|los)?\s*(prompt|instrucciones|sistema|system|configuraci[oó]n)",
    r"\b(system prompt|jailbreak|dan mode|developer mode|modo desarrollador)\b",
    r"ignore\s+(all|previous|the)?\s*(previous\s+)?instructions",
    r"\[\s*(sistema|system)\s*\]|<\s*/?\s*(system|sistema|pasaje)\b",
]
_RE_INYECCION = [re.compile(p, re.IGNORECASE) for p in PATRONES_INYECCION]

# Datos personales. Orden importante: tarjeta antes que cédula y teléfono.
PATRONES_PII = [
    ("TARJETA", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("CORREO", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("CEDULA", re.compile(r"\b\d{10}\b")),
    ("TELEFONO", re.compile(r"(?:\+593[\s-]?|\b0)9\d(?:[\s-]?\d){7}\b")),
]

MENSAJE_DERIVACION = "No encuentro esa información en las políticas de inducción. Te derivo a Talento Humano."


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def detectar_inyeccion(texto: str) -> list[str]:
    """Patrones de inyección encontrados (lista vacía si no hay)."""
    t = _sin_tildes(texto)
    return [p.pattern for p in _RE_INYECCION if p.search(t) or p.search(texto)]


def enmascarar_pii(texto: str) -> tuple[str, list[str]]:
    """Reemplaza datos personales por [TIPO] y devuelve los tipos encontrados."""
    encontrados = []
    for etiqueta, patron in PATRONES_PII:
        if patron.search(texto):
            encontrados.append(etiqueta)
            texto = patron.sub(f"[{etiqueta}]", texto)
    return texto, encontrados


def revisar_entrada(pregunta: str, max_caracteres: int = 500) -> dict:
    """Aplica las guardas de entrada. bloquear=True significa: no consultar al LLM."""
    limpia, pii = enmascarar_pii(pregunta.strip()[:max_caracteres])
    inyeccion = detectar_inyeccion(limpia)
    return dict(pregunta_limpia=limpia, datos_personales=pii, inyeccion=inyeccion,
                bloquear=bool(inyeccion), truncada=len(pregunta.strip()) > max_caracteres)


_RE_NUM = re.compile(r"\d+(?:[.,:]\d+)?")
_NUMEROS_PALABRA = {"dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
                    "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10", "quince": "15",
                    "treinta": "30", "cuarenta": "40", "cincuenta": "50", "sesenta": "60", "noventa": "90"}


def cifras(texto: str) -> set[str]:
    """Cifras normalizadas de un texto ("08:30" -> "8:30", "dos" -> "2")."""
    t = _sin_tildes(texto.lower())
    salida = {re.sub(r"^0+(?=\d)", "", n.replace(",", ".")) for n in _RE_NUM.findall(t)}
    for palabra, num in _NUMEROS_PALABRA.items():
        if re.search(rf"\b{palabra}\b", t):
            salida.add(num)
    return salida


_RE_CITA = re.compile(r"\[?\s*fuente\s*:?\s*(P\d{2})(?:\s*[,y]\s*(P\d{2}))*\s*\]?", re.IGNORECASE)


def citas(texto: str) -> list[str]:
    return [p.upper() for p in re.findall(r"\bP\d{2}\b", texto, re.IGNORECASE)]


def verificar_salida(respuesta: str, pasajes: list[dict]) -> dict:
    """Verificación determinista de fidelidad de una respuesta generada.

    pasajes: [{"id": "P19", "texto": "..."}] entregados como contexto.
    Devuelve fiel=True solo si la respuesta deriva con el mensaje estándar, o si cita un pasaje
    entregado y todas sus cifras aparecen en los pasajes citados.
    """
    ids = {p["id"] for p in pasajes}
    texto_resp = respuesta.strip()
    if not texto_resp:
        return dict(fiel=False, motivo="respuesta vacía", es_derivacion=False)
    es_derivacion = _sin_tildes(MENSAJE_DERIVACION.lower())[:40] in _sin_tildes(texto_resp.lower())
    if es_derivacion:
        return dict(fiel=True, motivo="derivación explícita del modelo", es_derivacion=True, citas=[])
    citadas = [c for c in citas(texto_resp) if c in ids]
    ajenas = [c for c in citas(texto_resp) if c not in ids]
    if not citadas:
        return dict(fiel=False, motivo="sin cita a un pasaje recuperado", es_derivacion=False, citas=ajenas)
    contexto = " ".join(p["texto"] for p in pasajes if p["id"] in citadas)
    sin_cita = _RE_CITA.sub(" ", texto_resp)
    sin_cita = re.sub(r"\bP\d{2}\b", " ", sin_cita)
    no_respaldadas = sorted(cifras(sin_cita) - cifras(contexto))
    if no_respaldadas:
        return dict(fiel=False, motivo=f"cifras no respaldadas: {', '.join(no_respaldadas)}",
                    es_derivacion=False, citas=citadas)
    if ajenas:
        return dict(fiel=False, motivo=f"cita pasajes no entregados: {', '.join(ajenas)}",
                    es_derivacion=False, citas=citadas)
    return dict(fiel=True, motivo="cita válida y cifras respaldadas", es_derivacion=False, citas=citadas)
