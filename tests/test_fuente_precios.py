"""Enlace a la fuente de cada precio: la búsqueda exacta en Google Flights y en Google Hotels.

El enlace sale de la respuesta guardada del buscador (`search_metadata`); si falta, se construye con los aeropuertos y
las fechas. Solo se aceptan enlaces de `https://www.google.com/travel/...`: nunca uno que llegue del cliente.
"""
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, precios

V1 = "/api/v1"
MOAB = {"nombre": "Moab", "region": "Utah", "pais": "Estados Unidos", "lat": 38.57332, "lon": -109.54984}


def _metadatos(nombre: str) -> dict:
    return json.loads((config.DIR_RESPALDO / nombre).read_text())["search_metadata"]


def _q(url: str) -> str:
    return parse_qs(urlsplit(url).query)["q"][0]


# ---------- servicio ----------
@pytest.mark.parametrize("url", [
    "https://www.google.com/travel/flights?tfs=abc",
    "https://google.com/travel/search?q=Denver+hotels",
])
def test_la_lista_blanca_acepta_google_travel(url):
    assert precios.es_fuente_google(url)


@pytest.mark.parametrize("url", [
    "http://www.google.com/travel/flights?tfs=abc",            # sin cifrar
    "https://www.google.com.evil.example/travel/flights",       # otro dominio que empieza igual
    "https://evil.example/travel/flights?r=https://www.google.com/travel/",
    "https://usuario@www.google.com/travel/flights",            # con credenciales en el enlace
    "https://www.google.com:8443/travel/flights",
    "https://www.google.com/search?q=vuelos",                   # Google, pero no la parte de viajes
    "https://www.google.com/travelx/flights",
    "javascript:alert(1)", "", None, 42,
])
def test_la_lista_blanca_rechaza_lo_demas(url):
    assert not precios.es_fuente_google(url)


def test_el_enlace_de_vuelos_sale_de_la_respuesta_guardada(cliente):
    guardado = _metadatos("vuelos_MIA_LAS_2026-12-08_2026-12-11.json")["google_flights_url"]
    assert precios.enlace_vuelos("MIA", "LAS", "2026-12-08", "2026-12-11") == guardado
    # varios aeropuertos de destino: la misma búsqueda que se pagó
    moab = _metadatos("vuelos_MIA_CNY-GJT-SLC_2026-12-08_2026-12-11.json")["google_flights_url"]
    assert precios.enlace_vuelos(["MIA"], ["SLC", "CNY", "GJT"], "2026-12-08", "2026-12-11") == moab


@pytest.mark.parametrize("archivo, origen, destino, ida, regreso", [
    ("vuelos_ATL_ORD_2026-11-18_2026-11-21.json", ["ATL"], ["ORD"], "2026-11-18", "2026-11-21"),
    ("vuelos_MIA_CNY-GJT-SLC_2026-12-08_2026-12-11.json", ["MIA"], ["CNY", "GJT", "SLC"], "2026-12-08", "2026-12-11"),
])
def test_sin_metadatos_se_construye_la_misma_busqueda(archivo, origen, destino, ida, regreso):
    """Lo construido es idéntico a lo que entrega el buscador para esa ruta y esas fechas."""
    assert precios.construir_enlace_vuelos(origen, destino, ida, regreso) == _metadatos(archivo)["google_flights_url"]


def test_sin_respuesta_guardada_el_enlace_se_construye(cliente):
    url = precios.enlace_vuelos("BOG", "MDE,CLO", "2027-02-01", "2027-02-04")
    assert precios.es_fuente_google(url)
    assert url == precios.construir_enlace_vuelos(["BOG"], ["CLO", "MDE"], "2027-02-01", "2027-02-04")


def test_un_enlace_guardado_fuera_de_la_lista_blanca_no_se_usa(cliente):
    nombre = "vuelos_BOG_PEI_2027-03-01_2027-03-05.json"
    db.insertar("busquedas", clave=nombre, creado=db.ahora(), cuerpo=json.dumps(
        {"search_metadata": {"google_flights_url": "https://evil.example/travel/flights"}}))
    try:
        url = precios.enlace_vuelos("BOG", "PEI", "2027-03-01", "2027-03-05")
        assert url == precios.construir_enlace_vuelos(["BOG"], ["PEI"], "2027-03-01", "2027-03-05")
    finally:
        db.ejecutar("delete from busquedas where clave=:c", c=nombre)


def test_el_enlace_de_hoteles_lleva_la_busqueda_guardada_y_las_fechas(cliente):
    guardado = _metadatos("hoteles_las-vegas_2026-12-08_2026-12-11.json")["google_hotels_url"]
    url = precios.enlace_hoteles("Las Vegas", "2026-12-08", "2026-12-11")
    assert precios.es_fuente_google(url) and urlsplit(url).path == urlsplit(guardado).path
    # el buscador no pone las fechas en su enlace: van en el texto de la búsqueda, que Google sí respeta
    assert _q(url) == f"{_q(guardado)} from 2026-12-08 to 2026-12-11"
    # un hotel: la misma búsqueda con su nombre, para verlo primero
    uno = precios.enlace_hoteles("Las Vegas", "2026-12-08", "2026-12-11", hotel="Hotel & Casino \"Ejemplo\"")
    assert _q(uno) == "Hotel & Casino \"Ejemplo\", Las Vegas from 2026-12-08 to 2026-12-11"


def test_sin_respuesta_de_hoteles_el_enlace_se_construye(cliente):
    url = precios.enlace_hoteles("Pueblo Sin Guardar", "2027-02-01", "2027-02-04")
    assert url.startswith("https://www.google.com/travel/search?")
    assert _q(url) == "Pueblo Sin Guardar hotels from 2027-02-01 to 2027-02-04"


# ---------- API v1 ----------
def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _vegas(c: TestClient) -> dict:
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    r = c.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def test_la_cotizacion_trae_sus_enlaces_a_la_fuente(piloto):
    c = _vegas(piloto)
    assert c["fuente_url"] == _metadatos("vuelos_MIA_LAS_2026-12-08_2026-12-11.json")["google_flights_url"]
    assert precios.es_fuente_google(c["fuente_hoteles_url"]) and "Las Vegas" in _q(c["fuente_hoteles_url"])
    assert c["hoteles"]
    for h in c["hoteles"] + c["hoteles_descartados"]:
        assert precios.es_fuente_google(h["fuente_url"]) and _q(h["fuente_url"]).startswith(h["nombre"])


def test_abrir_la_fuente_deja_rastro_de_quien_cuando_y_adonde(piloto):
    c = _vegas(piloto)
    ruta = f"{V1}/cotizaciones/{c['id']}/fuente"
    r = piloto.post(ruta, json={"destino": "vuelos"}, headers=_csrf(piloto))
    assert r.status_code == 200, r.text
    assert r.json() == {"destino": "vuelos", "url": c["fuente_url"]}
    hotel = c["hoteles"][0]
    r = piloto.post(ruta, json={"destino": "hoteles", "hotel_id": hotel["id"]}, headers=_csrf(piloto))
    assert r.json() == {"destino": "hoteles", "url": hotel["fuente_url"]}
    assert piloto.post(ruta, json={"destino": "hoteles"}, headers=_csrf(piloto)).json()["url"] == c["fuente_hoteles_url"]
    yo = db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]
    eventos = db.todos("select * from eventos where entidad='solicitud' and entidad_id=:i and paso='fuente abierta' order by id",
                       i=c["id"])
    assert [e["usuario_id"] for e in eventos] == [yo] * 3
    assert eventos[0]["detalle"] == f"Google Flights: {c['fuente_url']}"[:500]
    assert eventos[1]["detalle"].startswith(f"Google Hotels ({hotel['nombre']}): https://www.google.com/travel/")
    assert all(e["fuente"] == "api v1 · Andrés Molina" for e in eventos)


def test_abrir_la_fuente_respeta_sesion_csrf_y_alcance(piloto, piloto2, gestor, anonimo):
    c = _vegas(piloto)
    ruta = f"{V1}/cotizaciones/{c['id']}/fuente"
    assert anonimo.post(ruta, json={"destino": "vuelos"}).status_code == 401
    assert piloto.post(ruta, json={"destino": "vuelos"}).status_code == 403                     # sin CSRF
    assert piloto2.post(ruta, json={"destino": "vuelos"}, headers=_csrf(piloto2)).status_code == 404   # ajena
    assert gestor.post(ruta, json={"destino": "vuelos"}, headers=_csrf(gestor)).status_code == 200    # la ve: puede verificar
    # la URL nunca viene del cliente; un destino o un hotel que no son de esta cotización no se aceptan
    assert piloto.post(ruta, json={"destino": "vuelos", "url": "https://evil.example"}, headers=_csrf(piloto)).status_code == 422
    assert piloto.post(ruta, json={"destino": "otro"}, headers=_csrf(piloto)).status_code == 422
    vuelo = c["vuelos"][0]["id"]
    r = piloto.post(ruta, json={"destino": "hoteles", "hotel_id": vuelo}, headers=_csrf(piloto))
    assert r.status_code == 422 and r.json()["error"]["fields"] == {"hotel_id": "Ese hotel no es de esta cotización."}
