"""Pieza 5: captura completa con Chromium de verdad y sin red (las páginas de ejemplo responden por Google y la
aerolínea). Corre en la etapa `pruebas` de la imagen del analizador, como test_navegador.py."""
import base64
from pathlib import Path

import pytest

from analizador import navegador
from analizador.pruebas.test_navegador import URL, _servir

EJEMPLO = Path(__file__).resolve().parent.parent / "ejemplo"
COMPLETO = {"https://www.google.com/travel/flights/reserva": "vuelo_completo.html",
            "https://www.google.com/travel/flights?": "regresos.html"}
CLK = "https://www.google.com/travel/clk/f?pf=1"
AA = "https://www.aa.com/airfare-sales/ui/passenger-ui/"


def _png(b64: str) -> bool:
    return base64.b64decode(b64).startswith(b"\x89PNG")


def test_captura_del_vuelo_con_detalles_texto_imagen_y_envio():
    pedidos = []
    r = navegador.captura_vuelo(URL, "American", "Main Cabin", servir=_servir(dict(COMPLETO), pedidos))
    assert r["estado"] == "listo", r["motivo"]
    ida = r["datos"]["tramos"][0]
    assert (ida["avion"], ida["piernas"], ida["wifi"]) == ("Boeing 737MAX 8 Passenger", "Average legroom (30 in)", "Wi-Fi for a fee")
    assert r["datos"]["precios"]["rango"] == [410.0, 870.0]
    assert "Booking options" in r["texto"] and "Often delayed" in r["texto"]
    assert len(r["capturas_png_b64"]) == 1 and _png(r["capturas_png_b64"][0])
    assert r["envio"]["url"].startswith("https://www.google.com/travel/clk/f") and r["envio"]["cuerpo"].startswith("u=AA-MAIN")
    assert not any("/travel/clk" in p for p in pedidos)          # el envío no salió del navegador del servidor


def test_sin_la_tarifa_la_captura_de_google_vale_igual():
    r = navegador.captura_vuelo(URL, "American", "First", servir=_servir(dict(COMPLETO), []))
    assert r["estado"] == "listo" and r["envio"] is None and r["motivo_envio"] == navegador.SIN_TARIFA
    assert r["datos"]["tramos"] and r["capturas_png_b64"]


def _servir_aerolinea(enviados: list, destino: str = AA, pagina_aerolinea: str = "aerolinea.html"):
    """Google recibe el POST y manda a la aerolínea (con una navegación de la página, que Playwright sí intercepta)."""
    def registrar(pagina):
        def atender(ruta):
            pedido = ruta.request
            if pedido.url.startswith(CLK):
                enviados.append((pedido.method, pedido.post_data))
                return ruta.fulfill(status=200, content_type="text/html",
                                    body=f"<script>location.href = {destino!r};</script>")
            if pedido.url.startswith(AA):
                return ruta.fulfill(status=200, content_type="text/html; charset=utf-8",
                                    body=(EJEMPLO / pagina_aerolinea).read_text(encoding="utf-8"))
            return ruta.fallback() if pedido.is_navigation_request() else ruta.abort()
        pagina.route("**/*", atender)
    return registrar


def test_captura_de_la_aerolinea_con_impuestos_sin_tocar_el_formulario():
    enviados = []
    r = navegador.captura_aerolinea(CLK, "u=AA-MAIN-UNSOLOUSO&adurl=", servir=_servir_aerolinea(enviados))
    assert r["estado"] == "listo", r["motivo"]
    assert enviados == [("POST", "u=AA-MAIN-UNSOLOUSO&adurl=")]          # el envío se hizo una vez
    d = r["datos"]
    assert (d["total"], d["impuestos"], d["tarifa_base"]) == (748.80, 79.30, 669.50)   # el clic desplegó los impuestos
    assert d["numeros"] == ["AA 1851", "AA 1597"] and d["pagina"] == AA
    assert d["titulo"] != "ENVIADO" and "Taxes and carrier-imposed fees" in r["texto"]  # el formulario no se envió
    assert _png(r["capturas_png_b64"][0])


@pytest.mark.parametrize("pagina", ["aerolinea_bloqueo.html", "aerolinea_verificacion.html"])
def test_la_pagina_de_bloqueo_de_la_aerolinea_no_es_una_captura_lista(pagina):
    """Pieza 6: COPA respondió «Access is temporarily restricted» (prueba 13) y un deslizador «Verificación requerida»
    (Chrome real). Nunca se resuelve: la captura queda fallida, sin precios y sin fotografiar la verificación."""
    r = navegador.captura_aerolinea(CLK, "u=1", servir=_servir_aerolinea([], pagina_aerolinea=pagina))
    assert (r["estado"], r["motivo"]) == ("fallido", "la aerolínea pidió verificación")
    assert not r.get("capturas_png_b64") and not r.get("datos")
    assert r["duracion_ms"] < 10_000   # no espera los precios que nunca llegan


def test_la_aerolinea_solo_acepta_un_envio_de_google():
    assert navegador.captura_aerolinea("https://www.aa.com/x", "u=1")["estado"] == "fallido"
    assert navegador.captura_aerolinea(CLK, "x" * 20_000)["estado"] == "fallido"


def test_captura_del_hotel():
    url = "https://www.google.com/travel/search?q=Flamingo%2C%20Las%20Vegas%20from%202026-12-08%20to%202026-12-11"
    r = navegador.captura_hotel(url, "Flamingo Las Vegas",
                                servir=_servir({"https://www.google.com/travel/search?": "hotel.html"}, []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["calificacion"] == 4.1 and len(r["datos"]["vendedores"]) == 3
    assert "Amenities" in r["texto"] and _png(r["capturas_png_b64"][0])


def test_el_hotel_solo_abre_google_hotels():
    assert navegador.captura_hotel(URL, "Flamingo")["estado"] == "fallido"
    assert navegador.captura_hotel("https://www.booking.com/hotel/us/x.html", "Flamingo")["estado"] == "fallido"


def test_el_servidor_atiende_las_capturas(monkeypatch):
    from analizador import servidor
    llamadas = []
    for nombre in ("captura_vuelo", "captura_aerolinea", "captura_hotel"):
        monkeypatch.setattr(navegador, nombre, lambda *a, _n=nombre, **k: llamadas.append(_n) or {"estado": "listo"})
    servidor.atender({"accion": "captura_vuelo", "url": URL, "vendedor": "American", "tarifa": "Main Cabin"})
    servidor.atender({"accion": "captura_aerolinea", "url": CLK, "cuerpo": "u=1"})
    servidor.atender({"accion": "captura_hotel", "url": "https://www.google.com/travel/search?q=x", "hotel": "X"})
    assert llamadas == ["captura_vuelo", "captura_aerolinea", "captura_hotel"]
