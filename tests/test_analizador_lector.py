"""El lector del analizador con las páginas de ejemplo de `analizador/ejemplo/` (forma de Google Flights): sin red."""
from pathlib import Path

import pytest

from analizador import lector

EJEMPLO = Path(__file__).resolve().parent.parent / "analizador" / "ejemplo"


def _leer(nombre: str) -> dict:
    return lector.leer(*lector.desde_html((EJEMPLO / nombre).read_text(encoding="utf-8")))


def test_lee_tarifas_equipaje_cambios_reembolso_escalas_y_vendedores():
    d = _leer("reserva.html")
    assert d["precio_total"] == 619 and d["avisos"] == []
    ida, vuelta = d["tramos"]
    assert (ida["fecha"], ida["sale"], ida["llega"], ida["aerolinea"], ida["duracion"], ida["ruta"], ida["escalas"]) == \
        ("Tue, Dec 8", "9:48 AM", "12:24 PM", "American", "5 hr 36 min", "MIA–LAS", "Nonstop")
    assert (vuelta["ruta"], vuelta["escalas"], vuelta["detalle_escalas"]) == ("LAS–MIA", "1 stop", ["1 hr 10 min DFW"])
    assert d["escalas"][1] == {"ruta": "LAS–MIA", "escalas": "1 stop", "detalle": ["1 hr 10 min DFW"]}
    assert d["vendedores"] == [{"vendedor": "American", "aerolinea": True, "precio_desde": 619.0},
                               {"vendedor": "Expedia", "aerolinea": False, "precio_desde": 612.4}]
    basica, main_cabin, select, expedia = d["tarifas"]
    assert (basica["nombre"], basica["precio"], basica["vendedor"]) == ("Basic Economy", 619.0, "American")
    assert basica["equipaje"] == ["1 free carry-on", "1st checked bag: $110"]   # sin la frase repetida para lectores
    assert basica["cambios"] == ["No ticket changes"] and basica["reembolso"] == ["No refunds"]
    assert "Seat selection for a fee" in basica["otras"]
    assert (main_cabin["precio"], main_cabin["cambios"]) == (1014.0, ["Free change, possible fare difference"])
    assert select["reembolso"] == ["Full refunds"]
    assert (expedia["nombre"], expedia["precio"], expedia["vendedor"]) == ("Tarifa", 612.4, "Expedia")
    assert "Full refunds" in d["reembolso"] and "No ticket changes" in d["cambios"]
    assert any(n.startswith("Fare and baggage fees") for n in d["notas"])


def test_lee_el_texto_real_de_la_pagina():
    """`innerText` de la página real (13 nov 2026): el vendedor y su marca llegan pegados en una línea."""
    d = lector.leer((EJEMPLO / "reserva_texto_real.txt").read_text(encoding="utf-8"), [])
    assert d["precio_total"] == 619 and d["avisos"] == []
    assert d["vendedores"] == [{"vendedor": "American", "aerolinea": True, "precio_desde": 619.0}]
    assert [(t["nombre"], t["precio"]) for t in d["tarifas"]] == [("Basic Economy", 619), ("Main Cabin", 1014),
                                                                  ("Main Plus", 1226), ("Main Select", 1284)]
    assert d["tarifas"][2]["equipaje"] == ["1 free carry-on", "1st checked bag free"]
    assert [t["ruta"] for t in d["tramos"]] == ["MIA–LAS", "LAS–MIA"] and d["tramos"][0]["llega"] == "12:24 PM"


def test_en_la_lista_de_regresos_lee_cada_opcion_de_su_etiqueta():
    d = _leer("regresos.html")
    assert d["avisos"] == ["La página no mostró opciones de reserva."] and d["tarifas"] == []
    primero, segundo = d["itinerarios"]
    assert (primero["precio"], primero["escalas"], primero["aerolinea"], primero["sale"], primero["llega"]) == \
        (564.0, "Nonstop", "American", "11:06 PM", "6:43 AM")
    assert primero["desde"] == "Harry Reid International Airport" and primero["duracion"] == "4 hr 37 min"
    assert primero["equipaje"] == ["1 carry-on bag included", "0 checked bags included"]
    assert segundo["precio"] == 619.0


@pytest.mark.parametrize("url", ["https://www.google.com/travel/flights?tfs=abc", "https://google.com/travel/flights/booking"])
def test_solo_abre_google_flights(url):
    assert lector.url_permitida(url)


@pytest.mark.parametrize("url", ["http://www.google.com/travel/flights", "https://www.google.com/travel/search?q=x",
                                 "https://www.google.com.evil.example/travel/flights", "https://a@www.google.com/travel/flights",
                                 "file:///etc/passwd", "", None])
def test_no_abre_nada_mas(url):
    assert not lector.url_permitida(url)


def test_reconoce_cuando_la_pagina_pide_verificacion_o_condiciones():
    assert lector.bloqueo("https://www.google.com/sorry/index?continue=x", "") == lector.VERIFICACION
    assert lector.bloqueo("https://www.google.com/travel/flights", "Our systems have detected unusual traffic") == lector.VERIFICACION
    assert lector.bloqueo("https://consent.google.com/m?continue=x", "Before you continue to Google") == lector.CONSENTIMIENTO
    assert lector.bloqueo("https://www.google.com/travel/flights?tfs=x", "Booking options") is None


def test_reconoce_las_horas_con_el_espacio_fino_de_chromium():
    etiqueta = ("From 564 US dollars round trip total. Nonstop flight with American. Leaves Harry Reid International "
                "Airport at 6:00\u202fAM on Friday, December 11 and arrives at Miami International Airport at 1:43\u202fPM on "
                "Friday, December 11. Total duration 4 hr 43 min.   1 carry-on bag included. 0 checked bags included.  Select flight")
    (o,) = lector.itinerarios([etiqueta])
    assert (o["precio"], o["sale"], o["llega"]) == (564, "6:00 AM", "1:43 PM") and o["etiqueta"] == etiqueta
    d = lector.leer("Selected flights\nTue, Dec 8\n9:48\u202fAM\n – \n12:24\u202fPM\nAmerican\nBooking options\n", [])
    assert (d["tramos"][0]["sale"], d["tramos"][0]["llega"], d["tramos"][0]["aerolinea"]) == ("9:48 AM", "12:24 PM", "American")
