"""«Ver desglose» lleva a la página oficial del vendedor: opciones de reserva del buscador → `booking_request` de un solo
uso, entregado al navegador en una página mínima que hace el envío. El `booking_request` nunca se guarda.

El buscador es un doble: nunca se sale a internet.
"""
import json
import re

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, cotizacion, precios

V1 = "/api/v1"
SECRETO_URL = "https://www.google.com/travel/clk/f?u=SECRETOURL123"
SECRETO_CUERPO = "u=SECRETOCUERPO456&adurl=SECRETOADURL789"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _vegas(c: TestClient) -> dict:
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    r = c.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def _opcion(vendedor: str, aerolinea: bool, precio: float, url: str = SECRETO_URL) -> dict:
    return {"together": {"book_with": vendedor, "airline": aerolinea, "price": precio, "option_title": "Main Cabin",
                         "extensions": ["Free change, possible fare difference"], "baggage_prices": ["1 free carry-on"],
                         "booking_request": {"url": url, "post_data": SECRETO_CUERPO}}}


@pytest.fixture
def buscador(monkeypatch, tmp_path):
    """Clave del buscador y un doble de la consulta: el regreso trae su `booking_token`; la reserva, sus vendedores."""
    llamadas = []
    respuestas = {"reserva": {"booking_options": [_opcion("Expedia", False, 450), _opcion("American", True, 458)]}}

    def consultar(parametros, entidad, entidad_id, que):
        llamadas.append(parametros)
        if "booking_token" in parametros:
            return json.loads(json.dumps(respuestas["reserva"]))
        sale = parametros["return_date"] + " 13:43"
        return {"best_flights": [{"price": 458, "booking_token": "TOKEN-RESERVA", "flights": [
            {"airline": "American", "flight_number": "AA 1851", "departure_airport": {"id": "LAS", "time": sale},
             "arrival_airport": {"id": "MIA", "time": parametros["return_date"] + " 21:29"}}]}]}

    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    monkeypatch.setattr(config, "DIR_RESPALDO_ESCRITURA", tmp_path)
    monkeypatch.setattr(precios, "_consultar", consultar)
    ultima = db.uno("select coalesce(max(id), 0) n from busquedas")["n"]
    yield llamadas, respuestas, tmp_path
    # lo que guardó el doble no debe servir de «respuesta guardada» a otras pruebas
    db.ejecutar("delete from busquedas where id>:n", n=ultima)
    precios._enlaces.clear()


def _abrir(c: TestClient, sid: int, vuelo: int, sitio: str | None = "same-origin"):
    return c.get(f"{V1}/cotizaciones/{sid}/vuelos/{vuelo}/vendedor", follow_redirects=False,
                 headers={"Sec-Fetch-Site": sitio} if sitio else {})


def _todo_lo_guardado(carpeta) -> str:
    """Todas las tablas de la base y los archivos de respaldo escritos, en un solo texto."""
    partes = []
    for t in db.meta.sorted_tables:
        partes.append(json.dumps(db.todos(f"select * from {t.name}"), default=str))
    partes += [p.read_text() for p in carpeta.rglob("*") if p.is_file()]
    return "\n".join(partes)


def test_lleva_a_la_pagina_oficial_de_la_aerolinea_sin_guardar_el_pedido(piloto, buscador, capsys):
    llamadas, _, carpeta = buscador
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    assert vuelo["vendedor_url"] == f"{V1}/cotizaciones/{c['id']}/vuelos/{vuelo['id']}/vendedor"
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["Cache-Control"] == "no-store" and r.headers["Referrer-Policy"] == "no-referrer"
    csp = r.headers["Content-Security-Policy"]
    # Chrome aplica form-action también a las redirecciones que siguen al envío: con solo google.com cortaría el salto de
    # Google a la aerolínea. El destino del envío ya lo valida el servidor (lista blanca) y el script va con nonce.
    assert re.search(r"form-action https:(;|$)", csp) and "default-src 'none'" in csp
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    pagina = r.text
    # el envío va a la dirección del vendedor oficial (la aerolínea, aunque una agencia sea más barata), con su cuerpo
    assert f'action="{SECRETO_URL}"' in pagina.replace("&amp;", "&") and 'method="post"' in pagina
    assert '<input type="hidden" name="u" value="SECRETOCUERPO456">' in pagina
    assert '<input type="hidden" name="adurl" value="SECRETOADURL789">' in pagina
    assert f'<script nonce="{nonce}">' in pagina and "American" in pagina
    assert any("booking_token" in p for p in llamadas)
    # el pedido de un solo uso no queda en ninguna parte: ni base, ni respaldo, ni registros
    guardado = _todo_lo_guardado(carpeta) + capsys.readouterr().out
    for secreto in ("SECRETOURL123", "SECRETOCUERPO456", "SECRETOADURL789", "booking_request"):
        assert secreto not in guardado, secreto
    # el clic queda: quién, opción, vendedor y dominio
    ev = db.uno("select * from eventos where entidad='solicitud' and entidad_id=:i and paso='página oficial abierta'", i=c["id"])
    assert ev["usuario_id"] == db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]
    assert ev["detalle"] == f"{' + '.join(vuelo['numeros'])} (opción {vuelo['id']}): American, aerolínea · www.google.com"


def test_sin_vendedor_oficial_usa_el_primero_y_sin_reserva_va_a_google_flights(piloto, buscador):
    _, respuestas, _ = buscador
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    respuestas["reserva"] = {"booking_options": [_opcion("Expedia", False, 450), _opcion("Priceline", False, 455)]}
    assert "Expedia" in _abrir(piloto, c["id"], vuelo["id"]).text
    respuestas["reserva"] = {"booking_options": []}
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 303 and r.headers["location"] == vuelo["fuente_url"]


def test_nunca_envia_a_un_dominio_fuera_de_la_lista_blanca(piloto, buscador):
    _, respuestas, _ = buscador
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    respuestas["reserva"] = {"booking_options": [_opcion("American", True, 458, url="https://evil.example/clk?u=1")]}
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 303 and r.headers["location"] == vuelo["fuente_url"]


def test_sin_clave_del_buscador_va_a_google_flights(piloto, monkeypatch):
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 303 and r.headers["location"] == vuelo["fuente_url"]
    assert db.uno("select id from eventos where entidad_id=:i and paso='página oficial abierta'", i=c["id"])


def test_tope_por_persona_y_dia_y_reutiliza_la_ultima_hora(piloto, buscador):
    llamadas, _, _ = buscador
    c = _vegas(piloto)
    uno, dos = c["vuelos"][0]["id"], c["vuelos"][1]["id"]
    cotizacion.asegurar_reglas_vendedor()
    db.ejecutar("delete from consultas_buscador where tipo='vendedor'")   # las pruebas anteriores abrieron otros
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='enlace_vendedor_persona_dia'")
    try:
        assert _abrir(piloto, c["id"], uno).status_code == 200
        # el mismo itinerario dentro de la hora: el buscador lo sirve de su caché sin cobrar; no cuenta para el tope
        assert _abrir(piloto, c["id"], uno).status_code == 200
        r = _abrir(piloto, c["id"], dos)   # otro itinerario: tope alcanzado, va a Google Flights
        assert r.status_code == 303 and r.headers["location"] == c["vuelos"][1]["fuente_url"]
        assert sum("booking_token" in p for p in llamadas) == 2
    finally:
        db.ejecutar("update reglas set valor='10' where ambito='supuesto' and clave='enlace_vendedor_persona_dia'")


def test_permisos_todas_las_personas_que_ven_la_cotizacion(piloto, piloto2, gestor, anonimo, buscador):
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]["id"]
    assert _abrir(anonimo, c["id"], vuelo).status_code == 401
    assert _abrir(piloto2, c["id"], vuelo).status_code == 404                 # cotización ajena
    assert _abrir(gestor, c["id"], vuelo).status_code == 200                  # la ve: también va a la página oficial
    assert _abrir(piloto, c["id"], vuelo, sitio="cross-site").status_code == 403   # otro sitio no gasta el cupo de nadie
    assert _abrir(piloto, c["id"], vuelo, sitio=None).status_code == 200      # navegador sin la cabecera
    otra = _vegas(piloto2)
    assert _abrir(piloto, c["id"], otra["vuelos"][0]["id"]).status_code == 404


def test_las_reglas_del_tope_se_crean_con_la_migracion():
    db.ejecutar("delete from reglas where clave='enlace_vendedor_persona_dia'")
    assert cotizacion.asegurar_reglas_vendedor() == 1 and cotizacion.asegurar_reglas_vendedor() == 0


# ---------- ronda 1 · punto 17: una respuesta rara del buscador manda a Google Flights ----------
@pytest.mark.parametrize("respuesta", [
    {"booking_options": [{"together": "texto"}]},
    {"booking_options": ["texto", 7, None]},
    {"booking_options": [{"together": {"book_with": 123, "airline": True, "price": 458,
                                       "booking_request": dict(url=SECRETO_URL, post_data={"u": "dict"})}}]},
    {"booking_options": [{"together": {"book_with": "American", "booking_request": "texto"}}]},
    ["no", "es", "un", "objeto"],
    "texto",
])
def test_una_respuesta_rara_del_buscador_va_a_google_flights(piloto, buscador, respuesta):
    _, respuestas, _ = buscador
    respuestas["reserva"] = respuesta
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 303 and r.headers["location"] == vuelo["fuente_url"], r.text


def test_un_fallo_inesperado_va_a_google_flights_con_nota(piloto, buscador, monkeypatch):
    def roto(*a, **k):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(precios, "vuelo_regreso", roto)
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 303 and r.headers["location"] == vuelo["fuente_url"]
    ev = db.uno("select detalle from eventos where entidad_id=:i and paso='página oficial abierta' order by id desc", i=c["id"])
    assert ev["detalle"].endswith("error al preparar el enlace (RuntimeError) · Google Flights")


def test_un_envio_a_google_fuera_de_travel_clk_no_se_usa(piloto, buscador):
    _, respuestas, _ = buscador
    respuestas["reserva"] = {"booking_options": [_opcion("American", True, 458, url="https://www.google.com/url?q=https://evil.example")]}
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 303 and r.headers["location"] == vuelo["fuente_url"]


# ---------- ronda 1 · punto 19: billetes separados ----------
def test_con_billetes_separados_va_a_google_flights(piloto, buscador):
    _, respuestas, _ = buscador
    ida = _opcion("Spirit", False, 120)["together"]
    respuestas["reserva"] = {"booking_options": [{"separate_tickets": True, "departing": ida, "returning": dict(ida)}]}
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    r = _abrir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 303 and r.headers["location"] == vuelo["fuente_url"]   # nunca solo la ida
