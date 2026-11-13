"""Leer la página del vuelo en Google Flights al abrir su desglose: API v1 y servicio, con un doble del analizador.

El doble responde con lo que el lector saca de la página de ejemplo (`analizador/ejemplo/reserva.html`): sin red.
"""
import base64
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from analizador import lector
from app import api_v1, db
from app.servicios import acceso, analizador, cotizacion, precios

V1 = "/api/v1"
MOAB = {"nombre": "Moab", "region": "Utah", "pais": "Estados Unidos", "lat": 38.57332, "lon": -109.54984}
PNG = b"\x89PNG\r\n\x1a\n" + b"captura de prueba"
EJEMPLO = Path(__file__).resolve().parent.parent / "analizador" / "ejemplo" / "reserva.html"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _cotizar(c: TestClient) -> dict:
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"},
              "destino": {"texto": "Moab", "aeropuertos": ["CNY", "GJT", "SLC"], "lugar": MOAB},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    r = c.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def doble(monkeypatch):
    """El analizador como servicio local, reemplazado por una función que cuenta sus llamadas."""
    llamadas = []
    respuesta = {"estado": "listo", "motivo": None, "duracion_ms": 4200,
                 "datos": lector.leer(*lector.desde_html(EJEMPLO.read_text(encoding="utf-8"))),
                 "captura_png_b64": base64.b64encode(PNG).decode()}
    monkeypatch.setenv("ANALIZADOR_URL", "http://analizador:8090")
    monkeypatch.delenv("ANALIZADOR", raising=False)
    monkeypatch.setattr(analizador, "_llamar", lambda url: llamadas.append(url) or dict(respuesta))
    db.ejecutar("delete from analisis_vuelo")
    yield llamadas, respuesta
    db.ejecutar("delete from analisis_vuelo")


def _pedir(c: TestClient, sid: int, opcion: int):
    return c.post(f"{V1}/cotizaciones/{sid}/vuelos/{opcion}/analisis", headers=_csrf(c))


def test_lee_la_pagina_del_vuelo_y_la_reutiliza_una_hora(piloto, doble):
    llamadas, _ = doble
    c = _cotizar(piloto)
    vuelo = c["vuelos"][0]
    r = _pedir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["estado"] == "listo" and a["reutilizado"] is False and a["motivo"] is None
    assert a["datos"]["precio_total"] == 619 and a["datos"]["tarifas"][0]["nombre"] == "Basic Economy"
    assert a["datos"]["vendedores"][1] == {"vendedor": "Expedia", "aerolinea": False, "precio_desde": 612.4}
    assert a["leido"] and a["duracion_ms"] == 4200 and a["precio_buscador_usd"] == vuelo["precio_usd"]
    # la página abierta es la de este vuelo: la búsqueda de la cotización con la ida elegida
    assert llamadas == [a["url"]] and precios.es_fuente_google(a["url"]) and a["url"].startswith("https://www.google.com/travel/flights?")
    # lo leído no reemplaza el precio del buscador: si difiere, se avisa
    assert a["aviso_precio"] == (f"Google Flights muestra 619 USD y el buscador dio {float(vuelo['precio_usd']):,.0f} USD. "
                                 "La comparación sigue usando el precio del buscador.")
    assert piloto.get(f"{V1}/cotizaciones/{c['id']}").json()["vuelos"][0]["precio_usd"] == vuelo["precio_usd"]
    captura = piloto.get(a["captura_url"])
    assert captura.status_code == 200 and captura.content == PNG and captura.headers["content-type"] == "image/png"
    # la segunda vez, dentro de la hora, no se vuelve a abrir la página
    otra = _pedir(piloto, c["id"], vuelo["id"]).json()
    assert otra["reutilizado"] is True and otra["id"] == a["id"] and len(llamadas) == 1
    assert piloto.get(f"{V1}/cotizaciones/{c['id']}/vuelos/{vuelo['id']}/analisis").json()["id"] == a["id"]
    pasos = [e["paso"] for e in db.todos("select paso from eventos where entidad='solicitud' and entidad_id=:i", i=c["id"])]
    assert "lectura de Google Flights pedida" in pasos and "página del vuelo leída" in pasos
    # pasada la hora, se lee de nuevo
    db.ejecutar("update analisis_vuelo set creado='2026-01-01 00:00:00'")
    assert _pedir(piloto, c["id"], vuelo["id"]).json()["reutilizado"] is False and len(llamadas) == 2


def test_una_verificacion_queda_como_lectura_fallida(piloto, doble, monkeypatch):
    llamadas, _ = doble
    monkeypatch.setattr(analizador, "_llamar", lambda url: llamadas.append(url) or
                        {"estado": "fallido", "motivo": lector.VERIFICACION, "duracion_ms": 900})
    c = _cotizar(piloto)
    a = _pedir(piloto, c["id"], c["vuelos"][0]["id"]).json()
    assert (a["estado"], a["motivo"], a["datos"], a["captura_url"]) == ("fallido", "la página pidió verificación", None, None)
    assert _pedir(piloto, c["id"], c["vuelos"][0]["id"]).json()["reutilizado"] is False   # lo fallido no se reutiliza


def test_sin_analizador_apagado_u_ocupado_no_lee_nada(piloto, doble, monkeypatch):
    llamadas, _ = doble
    c = _cotizar(piloto)
    vuelo = c["vuelos"][0]["id"]
    monkeypatch.setenv("ANALIZADOR", "apagado")
    assert _pedir(piloto, c["id"], vuelo).json() == {**_pedir(piloto, c["id"], vuelo).json(), "estado": "no_disponible",
                                                      "motivo": analizador.APAGADO}
    monkeypatch.delenv("ANALIZADOR")
    monkeypatch.delenv("ANALIZADOR_URL")
    assert _pedir(piloto, c["id"], vuelo).json()["motivo"] == analizador.SIN_ANALIZADOR
    monkeypatch.setenv("ANALIZADOR_URL", "http://analizador:8090")
    # otra lectura en curso (de cualquier vuelo): una a la vez
    db.insertar("analisis_vuelo", opcion_id=c["vuelos"][1]["id"], solicitud_id=c["id"], clave="x", url="https://www.google.com/travel/flights",
                estado="pendiente", creado=db.ahora())
    assert _pedir(piloto, c["id"], vuelo).json()["motivo"] == analizador.OCUPADO
    assert llamadas == [] and db.uno("select count(*) n from analisis_vuelo")["n"] == 1


def test_los_topes_del_dia_son_editables(piloto, piloto2, doble):
    llamadas, _ = doble
    analizador.asegurar_reglas()
    regla = lambda clave, valor: db.ejecutar("update reglas set valor=:v where ambito='supuesto' and clave=:c", v=valor, c=clave)  # noqa: E731
    c = _cotizar(piloto)
    try:
        regla("analisis_persona_dia", "1")
        assert _pedir(piloto, c["id"], c["vuelos"][0]["id"]).json()["estado"] == "listo"
        assert _pedir(piloto, c["id"], c["vuelos"][1]["id"]).json()["motivo"] == analizador.TOPE_PERSONA_TEXTO
        regla("analisis_persona_dia", "10")
        regla("analisis_vuelo_dia", "1")
        otra = _cotizar(piloto2)
        assert _pedir(piloto2, otra["id"], otra["vuelos"][0]["id"]).json()["motivo"] == analizador.TOPE_TOTAL_TEXTO
        assert len(llamadas) == 1
    finally:
        regla("analisis_persona_dia", "10")
        regla("analisis_vuelo_dia", "40")


def test_las_reglas_de_los_topes_se_crean_una_vez():
    db.ejecutar("delete from reglas where clave in ('analisis_persona_dia', 'analisis_vuelo_dia')")
    assert analizador.asegurar_reglas() == 2 and analizador.asegurar_reglas() == 0
    assert analizador.topes() == (10, 40)


def test_permisos_y_lo_ajeno(piloto, piloto2, gestor, anonimo, doble):
    c = _cotizar(piloto)
    ruta = f"{V1}/cotizaciones/{c['id']}/vuelos/{c['vuelos'][0]['id']}/analisis"
    assert anonimo.post(ruta).status_code == 401
    assert piloto.post(ruta).status_code == 403                                  # sin CSRF
    assert piloto2.post(ruta, headers=_csrf(piloto2)).status_code == 404          # cotización ajena
    assert piloto2.get(ruta).status_code == 404
    otra = _cotizar(piloto2)                                                      # un vuelo de otra cotización
    assert _pedir(piloto, c["id"], otra["vuelos"][0]["id"]).status_code == 404
    a = gestor.post(ruta, headers=_csrf(gestor)).json()                           # el gestor del proyecto la ve
    assert a["estado"] == "listo"
    assert piloto2.get(a["captura_url"]).status_code == 404
    assert piloto.get(f"{V1}/cotizaciones/{otra['id']}/analisis/{a['id']}/captura").status_code == 404


def test_al_decidir_el_detalle_vigente_se_copia_a_la_decision(piloto, doble):
    c = _cotizar(piloto)
    vuelo = c["recomendada_id"]
    a = _pedir(piloto, c["id"], vuelo).json()
    r = piloto.post(f"{V1}/cotizaciones/{c['id']}/decision", json={"vuelo_id": vuelo}, headers=_csrf(piloto))
    assert r.status_code == 200, r.text
    d = db.de_json(db.uno("select desglose from decisiones where solicitud_id=:s", s=c["id"])["desglose"])
    copia = d["analisis_google"]
    assert copia["id"] == a["id"] and copia["url"] == a["url"] and copia["datos"]["precio_total"] == 619
    # sin lectura vigente, la decisión no lleva detalle
    assert cotizacion.analizador.para_decision(c["vuelos"][-1]["id"]) is None


def test_cada_vuelo_enlaza_a_su_pagina_y_el_clic_queda_con_el_vuelo(piloto):
    c = _cotizar(piloto)
    vuelo = c["vuelos"][0]
    assert vuelo["fuente_url"] != c["fuente_url"] and precios.es_fuente_google(vuelo["fuente_url"])
    assert vuelo["fuente_url"] == analizador.enlace_itinerario(db.uno("select * from solicitudes where id=:i", i=c["id"]),
                                                               db.de_json(db.uno("select datos from opciones where id=:o", o=vuelo["id"])["datos"]))
    ruta = f"{V1}/cotizaciones/{c['id']}/fuente"
    r = piloto.post(ruta, json={"destino": "vuelos", "vuelo_id": vuelo["id"]}, headers=_csrf(piloto))
    assert r.json() == {"destino": "vuelos", "url": vuelo["fuente_url"]}
    detalle = db.uno("select detalle from eventos where entidad_id=:i and paso='fuente abierta' order by id desc", i=c["id"])["detalle"]
    assert detalle.startswith(f"Google Flights ({' + '.join(vuelo['numeros'])}): https://www.google.com/travel/flights?")
    otra = piloto.post(ruta, json={"destino": "vuelos", "vuelo_id": c["hoteles"][0]["id"] if c["hoteles"] else 999999},
                       headers=_csrf(piloto))
    assert otra.status_code == 422 and otra.json()["error"]["fields"] == {"vuelo_id": "Ese vuelo no es de esta cotización."}
