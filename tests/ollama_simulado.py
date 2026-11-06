"""Servidor que imita la API de Ollama, para probar la ruta del LLM sin descargar un modelo.

Responde con la primera oración del primer pasaje que recibe y su cita, salvo que la pregunta
pida una cifra inventada (contiene "INVENTA"). NO evalúa la calidad de un LLM: solo comprueba
que el pipeline de evaluación funciona de punta a punta.

    python -m tests.ollama_simulado --puerto 11434
"""
import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path == "/api/version":
            return self._json({"version": "simulado"})
        self._json({"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2:3b"}]})

    def do_POST(self):
        datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path == "/api/show":
            return self._json({"details": {"family": "simulado", "parameter_size": "0", "quantization_level": "-"}})
        usuario = datos["messages"][-1]["content"]
        m = re.search(r'<pasaje id="(P\d{2})"[^\n]*\n(.+?)\n</pasaje>', usuario, re.S)
        if not m:
            return self._json({"message": {"content": "No encuentro esa información en las políticas de inducción. "
                                                      "Te derivo a Talento Humano."}})
        pid, texto = m.groups()
        oracion = re.split(r"(?<=\.)\s", texto.strip())[0]
        if "INVENTA" in usuario:
            oracion = "El plazo es de 999 días."
        self._json({"message": {"role": "assistant", "content": f"{oracion} [Fuente: {pid}]"}})


def iniciar(puerto: int = 0) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=11434)
    srv = ThreadingHTTPServer(("127.0.0.1", ap.parse_args().puerto), Manejador)
    srv.serve_forever()
