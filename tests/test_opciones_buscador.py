"""Capa inmediata del desglose: las opciones de reserva del buscador que ya trajo el enlace a la página oficial.
Se leen de lo guardado (sin el pedido de un solo uso); nunca se paga una búsqueda para mostrarlas."""
import json

import pytest
from starlette.testclient import TestClient

from app import api_v1, config
from app.servicios import acceso, precios

V1 = "/api/v1"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _vegas(c: TestClient) -> dict:
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    r = c.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def sin_red(monkeypatch):
    llamadas = []
    monkeypatch.setattr(precios, "_consultar", lambda *a, **k: llamadas.append(a) or {})
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    return llamadas


def test_muestra_las_opciones_guardadas_del_itinerario_sin_consultar(piloto, sin_red):
    c = _vegas(piloto)
    aa = next(v for v in c["vuelos"] + c["descartados"] if v["numeros"] == ["AA 1851"])
    r = piloto.get(f"{V1}/cotizaciones/{c['id']}/vuelos/{aa['id']}/reserva")
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["estado"] == "listo" and sin_red == []                   # lo guardado: ninguna búsqueda
    basica = o["tarifas"][0]
    assert (basica["vendedor"], basica["nombre"], basica["precio"]) == ("American", "Basic Economy", 458)
    assert basica["equipaje"] == ["1 free carry-on", "1st checked bag: 110"]
    assert basica["cambios"] == ["No ticket changes"] and basica["reembolso"] == ["No refunds"]
    assert "Seat selection for a fee" in basica["otras"]
    assert [v["vendedor"] for v in o["vendedores"]][0] == "American" and o["vendedores"][0]["aerolinea"] is True
    assert "booking_request" not in json.dumps(o)


def test_sin_opciones_guardadas_lo_dice(piloto, sin_red):
    c = _vegas(piloto)
    otro = next(v for v in c["vuelos"] + c["descartados"] if v["numeros"] != ["AA 1851"])
    o = piloto.get(f"{V1}/cotizaciones/{c['id']}/vuelos/{otro['id']}/reserva").json()
    assert (o["estado"], o["tarifas"], o["vendedores"]) == ("sin_datos", [], []) and sin_red == []


def test_permisos(piloto, piloto2, anonimo):
    c = _vegas(piloto)
    ruta = f"{V1}/cotizaciones/{c['id']}/vuelos/{c['vuelos'][0]['id']}/reserva"
    assert anonimo.get(ruta).status_code == 401
    assert piloto2.get(ruta).status_code == 404
    otra = _vegas(piloto2)
    assert piloto.get(f"{V1}/cotizaciones/{c['id']}/vuelos/{otra['vuelos'][0]['id']}/reserva").status_code == 404


# ---------- ronda 2 · punto 13: datos raros guardados no dan 500 ----------
def test_opciones_guardadas_raras_no_rompen(piloto, sin_red):
    import json

    from app import db
    from app.servicios import precios as p
    c = _vegas(piloto)
    otro = next(v for v in c["vuelos"] + c["descartados"] if v["numeros"] != ["AA 1851"])
    sol = db.uno("select * from solicitudes where id=:i", i=c["id"])
    vuelo = db.de_json(db.uno("select datos from opciones where id=:o", o=otro["id"])["datos"])
    _, _, n_o, n_d = p.ruta(p.codigos(sol["origen_aeropuertos"] or sol["origen"]), p.codigos(sol["destino_aeropuertos"] or sol["destino"]))
    clave = f"reserva_{n_o}_{n_d}_{sol['ida']}_{sol['regreso']}_{''.join(n.replace(' ', '') for n in vuelo['numeros'])}.json"
    raro = {"booking_options": ["texto", {"together": "x"}, {"together": {"book_with": 123, "option_title": ["lista"], "price": 500,
            "extensions": "no es lista", "baggage_prices": {"a": 1}}}]}
    db.insertar("busquedas", clave=clave, cuerpo=json.dumps(raro), creado=db.ahora())
    try:
        r = piloto.get(f"/api/v1/cotizaciones/{c['id']}/vuelos/{otro['id']}/reserva")
        assert r.status_code == 200, r.text
        (t,) = r.json()["tarifas"]
        assert (t["vendedor"], t["nombre"], t["equipaje"], t["cambios"]) == ("123", "['lista']", [], [])
    finally:
        db.ejecutar("delete from busquedas where clave=:c", c=clave)
