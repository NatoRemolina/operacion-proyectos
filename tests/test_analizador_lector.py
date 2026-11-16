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
    assert d["vendedores"] == [{"vendedor": "American", "aerolinea": True, "tramo": None, "precio_desde": 619.0},
                               {"vendedor": "Expedia", "aerolinea": False, "tramo": None, "precio_desde": 612.4}]
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
    assert d["vendedores"] == [{"vendedor": "American", "aerolinea": True, "tramo": None, "precio_desde": 619.0}]
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


@pytest.mark.parametrize("url", ["https://www.google.com/travel/flights?tfs=abc", "https://google.com/travel/flights?tfs=x"])
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


def test_la_pestana_solo_navega_por_google_travel():
    assert lector.url_navegable("https://www.google.com/travel/flights/booking?tfs=x")
    assert lector.url_navegable("https://www.google.com/travel/search?q=hotels")
    for url in ("https://www.google.com/sorry/index", "https://consent.google.com/m", "https://www.google.com/search?q=x",
                "https://otro.example/travel/flights", "http://www.google.com/travel/flights", "chrome-error://chromewebdata/",
                "https://www.google.com:444/travel/flights", None):
        assert not lector.url_navegable(url), url


# ---------- ronda 1 · punto 12: el mismo criterio que los enlaces de la plataforma ----------
@pytest.mark.parametrize("url", [
    "https://www.google.com/travel/flightsX?tfs=abc",            # otra ruta que empieza igual
    "https://www.google.com/travel/flights/../search?q=x",       # sale de la ruta con ..
    "https://www.google.com/travel/flights/%2e%2e/search",       # .. codificado
    "https://www.google.com/travel/flights/%2E%2E/search",
    "https://www.google.com/travel/flights?tfs=a b",             # espacio
    "https://www.google.com/travel/flights?tfs=a\x00b",          # carácter de control
    "https://www.google.com/travel/flights\t",
])
def test_la_url_de_entrada_es_exactamente_google_flights(url):
    assert not lector.url_permitida(url)


def test_la_navegacion_tampoco_acepta_rutas_que_escapan():
    assert lector.url_permitida("https://www.google.com/travel/flights?hl=en&tfs=CBwQAh..x")   # «..» en el valor no es ruta
    for url in ("https://www.google.com/travel/../search", "https://www.google.com/travel/%2e%2e/search",
                "https://www.google.com/travel/flights/booking?x=\x07"):
        assert not lector.url_navegable(url), url


# ---------- pieza 5: lector ampliado (vuelo, aerolínea y hotel) ----------
def test_lee_el_detalle_de_cada_tramo_y_los_precios():
    d = _leer("vuelo_completo.html")
    ida, regreso = d["tramos"]
    assert (ida["avion"], ida["numeros"], ida["cabina"]) == ("Boeing 737MAX 8 Passenger", ["AA 1851"], "Economy")
    assert (ida["piernas"], ida["wifi"], ida["enchufes"]) == ("Average legroom (30 in)", "Wi-Fi for a fee", "In-seat power & USB outlets")
    assert ida["retrasos"] == "Often delayed by 30+ min" and ida["emisiones"] == "269 kg CO2e"
    assert ida["aeropuertos"] == ["9:48 AM · Miami International Airport (MIA)", "12:24 PM · Harry Reid International Airport (LAS)"]
    assert regreso["numeros"] == ["AA 2410", "AA 1597"] and regreso["avion"] == "Airbus A321"
    assert regreso["aviones"] == ["Airbus A321", "Boeing 737-800"]
    (escala,) = regreso["detalle_escalas"]
    assert "3 hr 5 min layover" in escala and regreso["nocturna"] is True and regreso["terminales"] == ["Terminal C"]
    assert ida["nocturna"] is False
    p = d["precios"]
    assert (p["actual"], p["nivel"], p["rango"]) == (619.0, "typical", [410.0, 870.0])
    assert p["historial"] == [{"cuando": "54 days ago", "precio": 612.0}, {"cuando": "40 days ago", "precio": 598.0},
                              {"cuando": "26 days ago", "precio": 530.0}, {"cuando": "12 days ago", "precio": 415.0},
                              {"cuando": "today", "precio": 619.0}]
    assert {(t["vendedor"], t["nombre"]) for t in d["tarifas"]} >= {("American", "Main Cabin"), ("Expedia", "Economy")}


def test_lee_la_pagina_de_la_aerolinea_con_impuestos():
    texto, _ = lector.desde_html((EJEMPLO / "aerolinea.html").read_text(encoding="utf-8"))
    a = lector.aerolinea(texto)
    assert (a["total"], a["tarifa_base"], a["impuestos"]) == (748.80, 669.50, 79.30)
    assert a["cabinas"] == ["Main"] and a["numeros"] == ["AA 1851", "AA 1597"]
    assert a["ruta"] == "Miami, United States to Las Vegas, United States"


def test_lee_la_ficha_del_hotel():
    texto, _ = lector.desde_html((EJEMPLO / "hotel.html").read_text(encoding="utf-8"))
    h = lector.hotel(texto)
    assert (h["nombre"], h["calificacion"], h["resenas"]) == ("Flamingo Las Vegas Hotel & Casino", 4.1, 52318)
    assert h["ubicacion"] == "3555 S Las Vegas Blvd, Las Vegas, NV 89109" and h["clase"] == "3-star hotel"
    assert h["vendedores"] == [
        {"vendedor": "Booking.com", "por_noche": 204.0, "total": 612.0, "incluye": ["Free cancellation until Dec 6"], "oficial": False},
        {"vendedor": "Expedia.com", "por_noche": 209.0, "total": 627.0, "incluye": ["Breakfast included"], "oficial": False},
        {"vendedor": "Flamingo Las Vegas", "por_noche": 199.0, "total": 597.0, "incluye": ["Non-refundable"], "oficial": True}]
    assert h["habitaciones"] == [{"tipo": "Standard Room, 2 Queen Beds", "precio": 199.0, "incluye": ["Free cancellation"]},
                                 {"tipo": "Go Room, 1 King Bed", "precio": 239.0, "incluye": ["Breakfast included"]}]
    assert h["servicios"] == ["Free Wi-Fi", "Pool", "Fitness center", "Paid parking", "Restaurant", "Air conditioning"]


def test_el_hotel_solo_abre_google_hotels():
    assert lector.url_permitida_hotel("https://www.google.com/travel/search?q=Flamingo%20from%202026-12-08&hl=en")
    assert lector.url_permitida_hotel("https://www.google.com/travel/hotels/entity/ChkIabc?hl=en")
    for malo in ("https://www.google.com/travel/flights?tfs=x", "https://www.google.com/search?q=hotel",
                 "http://www.google.com/travel/search?q=x", "https://www.booking.com/hotel/us/flamingo.html"):
        assert not lector.url_permitida_hotel(malo), malo


# ---------- producción, cotización 12: billetes separados («Separate tickets»), texto real de la prueba 11 ----------
def _real() -> dict:
    return lector.leer((EJEMPLO / "billetes_separados_texto_real.txt").read_text(encoding="utf-8"), [])


@pytest.mark.parametrize("leer", [_real, lambda: _leer("billetes_separados.html")])
def test_billetes_separados_son_una_opcion_y_la_reserva_por_telefono_no_es_tarifa(leer):
    d = leer()
    assert d["billetes_separados"] is True
    assert d["tarifas"] == []                                       # ninguna tarifa inventada
    assert d["vendedores"] == []
    (op,) = d["opciones_separadas"]
    assert (op["vendedores"], op["precio"]) == (["COPA", "Avianca"], 657.0)
    assert op["tramos"] == [{"tramo": "ida", "vendedor": "COPA"}, {"tramo": "regreso", "vendedor": "Avianca"}]
    assert op["notas"] == ["Separate ticketsThe 2 tickets in your itinerary must be booked individually"]
    (tel,) = d["por_telefono"]
    assert (tel["vendedor"], tel["precio"], tel["telefono"]) == ("COPA", 3134.0, "1 (786) 840-2672")
    assert tel["notas"] == ["Price includes an estimated airline phone service fee of $25"]
    # los avisos de Google van a notas; avisos dice solo lo que no se encontró
    assert "Separate ticketsThe 2 tickets in your itinerary must be booked individually" in d["notas"]
    assert not any("vendedor" in a for a in d["avisos"])


def test_el_detalle_real_de_cada_tramo_con_palabras_pegadas():
    ida, regreso = _real()["tramos"]
    assert (ida["aerolinea"], ida["sale"], ida["llega"], ida["cabina"]) == ("COPA", "12:40 PM", "7:06 PM", "Economy")
    assert (ida["numeros"], ida["aviones"]) == (["CM 687", "CM 240"], ["Boeing 737", "Boeing 737"])
    assert ida["piernas"] == "Average legroom (31 in)" and ida["enchufes"] == "In-seat USB outlet"
    assert ida["emisiones"] == "234 kg CO2e" and ida["detalle_escalas"] == ["1 hr 49 min layoverPanama City (PTY)"]
    assert ida["equipaje"] == ["1 free carry-on", "1st checked bag available for a fee"]
    assert (regreso["aerolinea"], regreso["sale"], regreso["numeros"]) == ("Avianca", "1:35 AM", ["AV 9", "AV 9332"])
    assert regreso["nocturna"] is True and regreso["avion"] == "Airbus A320"
    assert regreso["equipaje"][:2] == ["1 free carry-on", "First checked bag costs 95 US dollars"]


def test_una_tarifa_comun_no_lleva_tramo_ni_opciones_especiales():
    d = _leer("reserva_completa.html")
    assert d["billetes_separados"] is False and all(t["tramo"] is None for t in d["tarifas"])
    assert d["opciones_separadas"] == [] and d["por_telefono"] == []


# ---------- prueba 12: el diálogo «Purchase separate tickets» trae un tiquete por tramo, cada uno con su «Continue» ----------
def test_los_tiquetes_del_dialogo_son_tarifas_de_su_aerolinea_por_tramo():
    d = lector.leer((EJEMPLO / "billetes_separados_dialogo_texto_real.txt").read_text(encoding="utf-8"), [])
    assert [(t["vendedor"], t["nombre"], t["precio"], t["tramo"]) for t in d["tarifas"]] == [
        ("COPA", "ida", 334.0, "ida"), ("Avianca", "regreso", 323.0, "regreso")]
    assert [(v["vendedor"], v["aerolinea"], v["tramo"]) for v in d["vendedores"]] == [("COPA", True, "ida"), ("Avianca", True, "regreso")]
    (op,) = d["opciones_separadas"]
    assert op["tiquetes"] == [{"tramo": "ida", "vendedor": "COPA", "precio": 334.0},
                              {"tramo": "regreso", "vendedor": "Avianca", "precio": 323.0}]
    assert op["precio"] == 657.0                                    # el total, no una tarifa
    assert d["por_telefono"][0]["precio"] == 3134.0 and len(d["tarifas"]) == 2
    assert "Confirm the price on each booking website" in d["notas"]


def test_en_la_aerolinea_solo_cuentan_las_senales_fuertes():
    """Pieza 6, ronda 1: «captcha» o «recaptcha» sueltos no son un bloqueo en la página de la aerolínea (el pie «This site
    is protected by reCAPTCHA» sale en páginas buenas); «Access is temporarily restricted», «unusual activity» y
    «Verificación requerida» sí."""
    url = "https://shopping.copaair.com/"
    pie = "Your trip total\n$748.80\nThis site is protected by reCAPTCHA and the Google Privacy Policy apply. captcha"
    assert lector.bloqueo(url, pie, aerolinea=True) is None
    for senal in ("Access is temporarily restricted", "We've detected unusual activity", "Verificación requerida"):
        assert lector.bloqueo(url, senal, aerolinea=True) == lector.VERIFICACION_AEROLINEA, senal
    assert lector.bloqueo(url, "x" * 4000 + "Access is temporarily restricted", aerolinea=True) is None


def test_la_espera_en_la_aerolinea_usa_el_mismo_tope_de_4000_caracteres():
    assert lector.precio_o_bloqueo_aerolinea("Your trip total\n$748.80")
    assert lector.precio_o_bloqueo_aerolinea("Access is temporarily restricted")
    assert not lector.precio_o_bloqueo_aerolinea("Loading… This site is protected by reCAPTCHA")
    assert not lector.precio_o_bloqueo_aerolinea("x" * 4000 + "unusual activity")
