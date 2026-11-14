"""Pieza 6: «Ir a…» lleva al enlace del vuelo, por tiquete, con el buscador primero.

La respuesta del buscador con billetes separados sigue la forma de su documentación («Example with separate tickets»):
cada opción trae `separate_tickets`, el total en `together` (sin pedido) y un tiquete por tramo en `departing` y
`returning`, cada uno con su `booking_request`. El buscador es un doble: nunca se sale a internet; los `post_data` son
inventados.
"""
import json

import pytest

from app import config, db
from app.servicios import precios

CLK = "https://www.google.com/travel/clk/f"


def tiquete(vendedor: str, precio: float, numeros: list[str], secreto: str, aerolinea: bool = True) -> dict:
    return {"book_with": vendedor, "airline": aerolinea, "marketed_as": numeros, "price": precio,
            "baggage_prices": ["1 free carry-on", "1st checked bag: 30"],
            "booking_request": {"url": CLK, "post_data": f"u={secreto}"}}


def separados(regreso_vendedor: str = "Avianca", regreso_precio: float = 323, regreso_aerolinea: bool = True) -> dict:
    return {"booking_options": [
        {"separate_tickets": True,
         "together": {"book_with": f"COPA, {regreso_vendedor}", "airline": True, "marketed_as": ["CM 687", "CM 240", "AV 9"],
                      "price": 334 + regreso_precio},
         "departing": tiquete("COPA", 334, ["CM 687", "CM 240"], "IDA-COPA-SECRETA"),
         "returning": tiquete(regreso_vendedor, regreso_precio, ["AV 9"], "REGRESO-SECRETA", regreso_aerolinea)},
    ]}


IDA = {"numeros": ["CM 687", "CM 240"], "hasta": "MIA"}


@pytest.fixture
def buscador(monkeypatch, tmp_path):
    respuesta = {"datos": separados()}
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    monkeypatch.setattr(config, "DIR_RESPALDO_ESCRITURA", tmp_path)
    monkeypatch.setattr(precios, "_consultar", lambda *a, **k: json.loads(json.dumps(respuesta["datos"])))
    ultima = db.uno("select coalesce(max(id), 0) n from busquedas")["n"]
    yield respuesta, tmp_path
    db.ejecutar("delete from busquedas where id>:n", n=ultima)


def _en_vivo():
    return precios.reserva_en_vivo(IDA, {"booking": "TOKEN"}, "MDE", "MIA", "2026-11-20", "2026-11-29")


# ---------- punto 1: el buscador devuelve también los billetes separados ----------
def test_los_billetes_separados_salen_por_tramo_con_su_pedido(buscador):
    opciones = _en_vivo()
    assert [(o["tramo"], o["vendedor"], o["precio"], o["aerolinea"]) for o in opciones] == [
        ("ida", "COPA", 334, True), ("regreso", "Avianca", 323, True)]
    ida, regreso = opciones
    assert (ida["url"], ida["post_data"]) == (CLK, "u=IDA-COPA-SECRETA")
    assert regreso["post_data"] == "u=REGRESO-SECRETA"
    assert ida["numeros"] == ["CM 687", "CM 240"] and regreso["numeros"] == ["AV 9"]
    assert ida["equipaje"] == ["1 free carry-on", "1st checked bag: 30"] and ida["tarifa"] == "Tarifa"


def test_lo_guardado_no_lleva_el_pedido(buscador):
    _, carpeta = buscador
    _en_vivo()
    guardado = json.dumps(db.todos("select * from busquedas"), default=str) + \
        "".join(p.read_text() for p in carpeta.rglob("*") if p.is_file())
    for secreto in ("IDA-COPA-SECRETA", "REGRESO-SECRETA", "booking_request"):
        assert secreto not in guardado, secreto


def test_una_opcion_junta_es_de_ambos_tramos(buscador):
    respuesta, _ = buscador
    respuesta["datos"] = {"booking_options": [{"together": {**tiquete("American", 458, ["AA 1851"], "JUNTA"),
                                                           "option_title": "Main Cabin"}}]}
    assert [(o["tramo"], o["vendedor"], o["tarifa"]) for o in _en_vivo()] == [("ambos", "American", "Main Cabin")]


@pytest.mark.parametrize("rara", [
    {"separate_tickets": True, "departing": "no es un objeto", "returning": None},
    {"separate_tickets": True, "departing": {"book_with": 7, "price": "caro"}},
    "una opción que no es un objeto",
])
def test_una_respuesta_rara_deja_la_opcion_fuera_sin_romper(buscador, rara):
    respuesta, _ = buscador
    respuesta["datos"] = {"booking_options": [rara, *separados()["booking_options"]]}
    assert [o["tramo"] for o in _en_vivo()] == ["ida", "regreso"]


def test_la_tarifa_de_billetes_separados_sin_total_suma_los_dos_tramos():
    opcion = separados()["booking_options"][0]
    del opcion["together"]
    t = precios._tarifa(opcion)
    assert (t["precio"], t["vende"]) == (657, "COPA, Avianca")


def test_las_opciones_guardadas_muestran_cada_tiquete(buscador):
    _en_vivo()
    tarifas, _ = precios.opciones_guardadas(IDA, "MDE", "MIA", "2026-11-20", "2026-11-29")
    assert [(t["vendedor"], t["nombre"], t["precio"], t["tramo"]) for t in tarifas] == [
        ("COPA", "ida", 334, "ida"), ("Avianca", "regreso", 323, "regreso")]
