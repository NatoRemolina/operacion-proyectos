"""El analizador con Chromium de verdad y sin red: las direcciones de Google las responde la página de ejemplo.

Corre dentro de la imagen del analizador (tiene Playwright):
    docker compose run --rm --no-deps analizador python -m pytest -q analizador/pruebas
"""
import base64
from pathlib import Path

import pytest

from analizador import lector, navegador

EJEMPLO = Path(__file__).resolve().parent.parent / "ejemplo"
URL = "https://www.google.com/travel/flights?hl=en&gl=us&curr=USD&tfs=prueba"


def _servir(paginas: dict[str, str], pedidos: list[str]):
    """Responde cada dirección de google.com con un archivo de ejemplo; cualquier otra petición se corta (sin red)."""
    def registrar(pagina):
        def atender(ruta):
            url = ruta.request.url
            pedidos.append(url)
            for inicio, archivo in paginas.items():
                if url.startswith(inicio):
                    return ruta.fulfill(status=200, content_type="text/html; charset=utf-8",
                                        body=(EJEMPLO / archivo).read_text(encoding="utf-8"))
            return ruta.abort()
        pagina.route("**/*", atender)
    return registrar


def test_lee_la_reserva_y_guarda_la_captura():
    pedidos = []
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/travel/flights": "reserva.html"}, pedidos))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["precio_total"] == 619 and r["datos"]["vendedores"][0]["vendedor"] == "American"
    assert [t["nombre"] for t in r["datos"]["tarifas"]][:2] == ["Basic Economy", "Main Cabin"]
    assert base64.b64decode(r["captura_png_b64"]).startswith(b"\x89PNG")
    assert r["agente"] == navegador.AGENTE and "AnalizadorDePrecios" in r["agente"] and r["duracion_ms"] > 0
    assert all(p.startswith("https://www.google.com/") for p in pedidos)


def test_en_la_lista_de_regresos_elige_el_mas_barato_y_llega_a_la_reserva():
    paginas = {"https://www.google.com/travel/flights/reserva": "reserva.html",
               "https://www.google.com/travel/flights?": "regresos.html"}
    r = navegador.analizar(URL, servir=_servir(paginas, []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["regreso_elegido"]["precio"] == 564 and r["datos"]["tarifas"]
    assert r["url_final"] == "https://www.google.com/travel/flights/reserva"


def test_tolera_que_la_pagina_cambie_de_direccion_mientras_carga():
    paginas = {"https://www.google.com/travel/flights/reserva": "reserva.html",
               "https://www.google.com/travel/flights?": "recarga.html"}
    r = navegador.analizar(URL, servir=_servir(paginas, []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["precio_total"] == 619


def test_si_no_aparecen_los_precios_falla_con_evidencia():
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/": "sin_precios.html"}, []), espera_ms=1500)
    assert (r["estado"], r["motivo"]) == ("fallido", "la página tardó demasiado en mostrar los precios")
    assert base64.b64decode(r["captura_png_b64"]).startswith(b"\x89PNG")
    assert r["extracto"].startswith("Something went wrong")


def test_una_verificacion_no_se_resuelve():
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/": "verificacion.html"}, []))
    assert (r["estado"], r["motivo"]) == ("fallido", lector.VERIFICACION) and r["captura_png_b64"] is None


@pytest.mark.parametrize("url", ["https://example.com/travel/flights", "https://www.google.com/search?q=vuelos"])
def test_no_abre_nada_fuera_de_google_flights(url):
    r = navegador.analizar(url)
    assert (r["estado"], r["motivo"]) == ("fallido", "el enlace no es de Google Flights")


def test_apagado_no_abre_nada(monkeypatch):
    monkeypatch.setenv("ANALIZADOR", "apagado")
    assert navegador.analizar(URL)["motivo"] == "el analizador está apagado"


def test_una_lectura_a_la_vez():
    navegador._turno.acquire()
    try:
        assert navegador.analizar(URL)["motivo"].startswith("el analizador está leyendo otra página")
    finally:
        navegador._turno.release()
