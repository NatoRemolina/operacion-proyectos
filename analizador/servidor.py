"""El analizador como servicio interno para el entorno local (`docker compose`): un único endpoint.

    POST /analizar   {"url": "https://www.google.com/travel/flights?...", "regreso": {"sale", "aerolinea"}}  →  `navegador.analizar`
                     {"accion": "ir_a", "url", "vendedor", "tarifa", "regreso"}                         →  `navegador.ir_a`
    GET  /salud

No publica puerto hacia fuera: solo lo alcanza la API dentro de la red de Docker. En AWS lo mismo corre como función
Lambda (`lambda_handler.py`).
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import navegador

TOPE_CUERPO = 4096


def atender(pedido: dict) -> dict:
    """La misma entrada para el servidor local y para Lambda."""
    regreso = pedido.get("regreso") if isinstance(pedido.get("regreso"), dict) else None
    if pedido.get("accion") == "ir_a":
        return navegador.ir_a(pedido.get("url"), pedido.get("vendedor"), pedido.get("tarifa"), regreso=regreso)
    return navegador.analizar(pedido.get("url"), elegir_regreso=pedido.get("elegir_regreso") is not False, regreso=regreso)


class Manejador(BaseHTTPRequestHandler):
    def _responder(self, estado: int, cuerpo: dict):
        datos = json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):  # noqa: N802 (nombre que exige http.server)
        if self.path == "/salud":
            return self._responder(200, {"ok": True})
        return self._responder(404, {"error": "no existe"})

    def do_POST(self):  # noqa: N802
        if self.path != "/analizar":
            return self._responder(404, {"error": "no existe"})
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > TOPE_CUERPO:
            return self._responder(413, {"error": "pedido demasiado grande"})
        try:
            pedido = json.loads(self.rfile.read(largo) or b"{}")
        except ValueError:
            return self._responder(400, {"error": "JSON no válido"})
        if not isinstance(pedido, dict):
            return self._responder(400, {"error": "JSON no válido"})
        return self._responder(200, atender(pedido))

    def log_message(self, formato, *args):
        print(f"analizador {self.address_string()} {formato % args}", flush=True)


def main():
    puerto = int(os.environ.get("PUERTO", "8090"))
    ThreadingHTTPServer(("0.0.0.0", puerto), Manejador).serve_forever()   # noqa: S104 (solo en la red interna de Docker)


if __name__ == "__main__":
    main()
