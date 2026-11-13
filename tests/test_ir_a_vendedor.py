"""«Ir a…» (pieza 3b): la tarifa elegida, en la página del vendedor. Tres caminos: página, buscador y Google Flights.
El analizador y el buscador son dobles: nunca se sale a internet."""
import base64
import json
import re

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, analizador, precios

V1 = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"captura previa"
CLK = "https://www.google.com/travel/clk/f?pf=1"
SECRETO = "u=UNSOLOUSO-SECRETO-777&adurl="


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _vegas(c: TestClient) -> dict:
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    r = c.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def _ir(c: TestClient, sid: int, vuelo: int, vendedor="American", tarifa="Main Cabin", cabeceras=None):
    return c.post(f"{V1}/cotizaciones/{sid}/vuelos/{vuelo}/ir", json={"vendedor": vendedor, "tarifa": tarifa},
                  headers=_csrf(c) if cabeceras is None else cabeceras)


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """El analizador como servicio (doble) y el buscador sin clave; cada prueba ajusta lo suyo."""
    pedidos = []
    respuesta = {"estado": "listo", "url": CLK, "cuerpo": SECRETO, "vendedor": "American", "tarifa": "Main Cabin",
                 "captura_previa_png_b64": base64.b64encode(PNG).decode(), "duracion_ms": 6000}
    monkeypatch.setenv("ANALIZADOR_URL", "http://analizador:8090")
    monkeypatch.delenv("ANALIZADOR", raising=False)
    monkeypatch.setattr(analizador, "_invocar", lambda p: pedidos.append(p) or dict(respuesta))
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    monkeypatch.setattr(config, "DIR_RESPALDO_ESCRITURA", tmp_path)
    db.ejecutar("delete from analisis_vuelo")
    ultima = db.uno("select coalesce(max(id), 0) n from busquedas")["n"]
    yield pedidos, respuesta, tmp_path
    db.ejecutar("delete from analisis_vuelo")
    db.ejecutar("delete from busquedas where id>:n", n=ultima)


def _guardado(carpeta) -> str:
    partes = [json.dumps(db.todos(f"select * from {t.name}"), default=str) for t in db.meta.sorted_tables]
    return "\n".join(partes + [p.read_text() for p in carpeta.rglob("*") if p.is_file()])


def test_por_la_pagina_devuelve_el_envio_de_esa_tarifa_y_no_lo_guarda(piloto, entorno, capsys):
    pedidos, _, carpeta = entorno
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    r = _ir(piloto, c["id"], vuelo["id"])
    assert r.status_code == 200, r.text
    assert r.headers["Cache-Control"] == "no-store"
    e = r.json()
    assert (e["camino"], e["url"], e["vendedor"], e["tarifa"], e["motivo"]) == ("pagina", CLK, "American", "Main Cabin", None)
    assert e["campos"] == [["u", "UNSOLOUSO-SECRETO-777"], ["adurl", ""]]
    (p,) = pedidos
    assert (p["accion"], p["vendedor"], p["tarifa"]) == ("ir_a", "American", "Main Cabin")
    assert p["url"].startswith("https://www.google.com/travel/flights?")
    assert "UNSOLOUSO-SECRETO-777" not in _guardado(carpeta) + capsys.readouterr().out
    fila = db.uno("select * from analisis_vuelo where accion='ir_a'")
    assert (fila["estado"], fila["camino"], fila["vendedor"], fila["tarifa"]) == ("listo", "pagina", "American", "Main Cabin")
    assert fila["captura"]                                          # la captura previa al clic queda como evidencia
    ev = db.uno("select detalle from eventos where entidad_id=:i and paso='ir a vendedor'", i=c["id"])["detalle"]
    assert re.match(rf"^{re.escape(' + '.join(vuelo['numeros']))} \(opción {vuelo['id']}\): American · Main Cabin · camino pagina · "
                    r"www\.google\.com · \d+ ms$", ev), ev


def test_si_la_pagina_falla_usa_el_buscador_con_esa_tarifa(piloto, entorno, monkeypatch, capsys):
    pedidos, respuesta, carpeta = entorno
    respuesta.update(estado="fallido", motivo="no se encontró la tarifa", url=None, cuerpo=None)
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    monkeypatch.setattr(precios, "vuelo_regreso", lambda *a, **k: {"booking": "TOKEN"})

    def opcion(vendedor, tarifa, u):
        return {"together": {"book_with": vendedor, "option_title": tarifa, "price": 500, "airline": vendedor == "American",
                             "booking_request": dict(url=CLK, post_data=f"u={u}")}}

    monkeypatch.setattr(precios, "_consultar", lambda *a, **k: {"booking_options": [
        opcion("American", "Basic Economy", "BASICA-SECRETA"), opcion("American", "Main Cabin", "MAIN-SECRETA")]})
    c = _vegas(piloto)
    r = _ir(piloto, c["id"], c["vuelos"][0]["id"])
    assert r.status_code == 200, r.text
    e = r.json()
    assert (e["camino"], e["campos"], e["motivo"]) == ("buscador", [["u", "MAIN-SECRETA"]], "no se encontró la tarifa")
    assert "MAIN-SECRETA" not in _guardado(carpeta) + capsys.readouterr().out


def test_sin_pagina_ni_buscador_va_a_google_flights(piloto, entorno):
    _, respuesta, _ = entorno
    respuesta.update(estado="fallido", motivo="la página pidió verificación", url=None, cuerpo=None)
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    e = _ir(piloto, c["id"], vuelo["id"]).json()
    assert (e["camino"], e["url"], e["campos"]) == ("google", vuelo["fuente_url"], [])


def test_un_envio_fuera_de_la_lista_blanca_no_se_entrega(piloto, entorno):
    _, respuesta, _ = entorno
    respuesta.update(url="https://otro.example/clk")
    c = _vegas(piloto)
    assert _ir(piloto, c["id"], c["vuelos"][0]["id"]).json()["camino"] == "google"


def test_tope_por_persona_y_dia(piloto, entorno):
    pedidos, _, _ = entorno
    analizador.asegurar_reglas()
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='ir_a_persona_dia'")
    try:
        c = _vegas(piloto)
        assert _ir(piloto, c["id"], c["vuelos"][0]["id"]).json()["camino"] == "pagina"
        e = _ir(piloto, c["id"], c["vuelos"][1]["id"]).json()
        assert (e["camino"], e["motivo"]) == ("google", analizador.TOPE_IR_A_TEXTO) and len(pedidos) == 1
    finally:
        db.ejecutar("update reglas set valor='20' where ambito='supuesto' and clave='ir_a_persona_dia'")


def test_permisos_y_entrada(piloto, piloto2, anonimo, entorno):
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]["id"]
    assert _ir(anonimo, c["id"], vuelo, cabeceras={}).status_code == 401
    assert _ir(piloto, c["id"], vuelo, cabeceras={}).status_code == 403               # sin CSRF
    assert _ir(piloto2, c["id"], vuelo).status_code == 404                            # ajena
    otra = _vegas(piloto2)
    assert _ir(piloto, c["id"], otra["vuelos"][0]["id"]).status_code == 404          # vuelo de otra cotización
    assert _ir(piloto, c["id"], vuelo, vendedor="<script>").status_code == 422
    r = piloto.post(f"{V1}/cotizaciones/{c['id']}/vuelos/{vuelo}/ir", headers=_csrf(piloto),
                    json={"vendedor": "American", "tarifa": "Main Cabin", "url": "https://otro.example"})
    assert r.status_code == 422                                                       # la URL nunca viene del cliente


def test_la_pagina_de_envio_prepara_el_enlace_con_la_sesion(piloto, piloto2, entorno):
    c = _vegas(piloto)
    vuelo = c["vuelos"][0]
    ruta = f"{V1}/cotizaciones/{c['id']}/vuelos/{vuelo['id']}/ir"
    r = piloto.get(ruta, params={"vendedor": "American", "tarifa": "Main Cabin"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    csp = r.headers["Content-Security-Policy"]
    assert "form-action https:" in csp and "connect-src 'self'" in csp and "default-src 'none'" in csp
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    assert f'<script nonce="{nonce}">' in r.text and "Preparando tu enlace a American · Main Cabin…" in r.text
    assert api_v1.token_csrf(piloto.cookies.get(acceso.COOKIE)) in r.text
    assert vuelo["fuente_url"].replace("&", "&amp;") in r.text                         # la alternativa: Google Flights
    assert r.headers["Cache-Control"] == "no-store"
    assert piloto.get(ruta, params={"vendedor": "American", "tarifa": "Main Cabin"},
                      headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert piloto2.get(ruta, params={"vendedor": "American", "tarifa": "Main Cabin"}).status_code == 404
    assert piloto.get(ruta, params={"vendedor": "<b>", "tarifa": "x"}).status_code == 422
    assert db.uno("select count(*) n from analisis_vuelo")["n"] == 0                  # abrir la página no gasta el tope
