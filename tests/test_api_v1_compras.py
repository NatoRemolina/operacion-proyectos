"""Pieza 4: la solicitud de compra nace al decidir y la lleva administración (nunca sobre su propio viaje).

Estados: solicitada → en_analisis → se_comprara | no_se_comprara → comprada | cancelada. Versión esperada en cada
cambio. El buscador y el analizador no salen a internet: se usan las respuestas guardadas o un doble.
"""
from datetime import date

import pytest
from starlette.testclient import TestClient

from app import api_v1, db
from app.servicios import acceso, analizador, compras

V1 = "/api/v1"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _decidir(c: TestClient, viajero_id: int | None = None) -> dict:
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    if viajero_id:
        pedido["viajero_id"] = viajero_id
    r = c.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(c))
    assert r.status_code == 201, r.text
    cot = r.json()
    r = c.post(f"{V1}/cotizaciones/{cot['id']}/decision", json={"vuelo_id": cot["recomendada_id"]}, headers=_csrf(c))
    assert r.status_code == 200, r.text
    return r.json()


def _compra(cot: dict) -> dict:
    return db.uno("select * from compras where viaje_id=:v and activa=1", v=cot["viaje"]["id"])


def _estado(c: TestClient, cid: int, accion: str, version: int, motivo: str = ""):
    return c.post(f"{V1}/compras/{cid}/estado", json={"accion": accion, "version": version, "motivo": motivo}, headers=_csrf(c))


def _aprobar_viaje(admin: TestClient, viaje_id: int):
    r = admin.post(f"{V1}/viajes/{viaje_id}/estado", json={"accion": "aprobar", "confirmar_precio": True}, headers=_csrf(admin))
    assert r.status_code == 200, r.text


def test_al_decidir_nace_la_solicitud_de_compra(piloto):
    cot = _decidir(piloto)
    assert cot["compra"]["estado"] == "solicitada" and cot["compra"]["estado_texto"] == "Solicitud de compra enviada"
    c = _compra(cot)
    yo = db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]
    assert (c["estado"], c["solicitada_por"], c["version"]) == ("solicitada", yo, 1)
    d = db.de_json(db.uno("select desglose from decisiones where id=:i", i=cot["decision"]["id"])["desglose"])
    assert c["precio_cotizado"] == pytest.approx(d["precio_tarifa"])     # el precio del buscador al decidir
    # cambiar la decisión no duplica la compra activa del viaje
    otro = next(v for v in cot["vuelos"] if v["id"] != cot["recomendada_id"])
    r = piloto.post(f"{V1}/cotizaciones/{cot['id']}/decision", json={"vuelo_id": otro["id"], "motivo": "Mejor horario"},
                    headers=_csrf(piloto))
    assert r.status_code == 200, r.text
    assert db.uno("select count(*) n from compras where viaje_id=:v and activa=1", v=cot["viaje"]["id"])["n"] == 1


def test_fuera_de_administracion_toda_la_api_de_compras_es_403(piloto, gestor, anonimo):
    cot = _decidir(piloto)
    cid = _compra(cot)["id"]
    for c in (piloto, gestor):
        assert c.get(f"{V1}/compras").status_code == 403
        assert c.get(f"{V1}/compras/{cid}").status_code == 403
        assert _estado(c, cid, "en_analisis", 1).status_code == 403
        assert c.post(f"{V1}/compras/{cid}/registro", json={"version": 1, "localizador": "ABC123", "precio_pagado": "458.00",
                                                           "vendedor": "American"}, headers=_csrf(c)).status_code == 403
        assert c.post(f"{V1}/compras/{cid}/analisis", headers=_csrf(c)).status_code == 403
    assert anonimo.get(f"{V1}/compras").status_code == 401
    assert _compra(cot)["estado"] == "solicitada"


def test_los_estados_respetan_la_version_y_se_comprara_exige_el_viaje_aprobado(piloto, cliente):
    cot = _decidir(piloto)
    c = _compra(cot)
    lista = cliente.get(f"{V1}/compras").json()
    assert any(x["id"] == c["id"] and x["estado"] == "solicitada" for x in lista["items"])
    r = _estado(cliente, c["id"], "en_analisis", 1)
    assert r.status_code == 200, r.text
    assert (r.json()["estado"], r.json()["version"]) == ("en_analisis", 2)
    assert _estado(cliente, c["id"], "en_analisis", 1).status_code == 409                     # versión vieja
    assert _estado(cliente, c["id"], "se_comprara", 2).json()["error"]["code"] == "INVALID_STATE"   # viaje sin aprobar
    r = _estado(cliente, c["id"], "no_se_comprara", 2, motivo="no")
    assert r.status_code == 422 and "motivo" in r.json()["error"]["fields"]
    _aprobar_viaje(cliente, cot["viaje"]["id"])
    r = _estado(cliente, c["id"], "se_comprara", 2, motivo="Aprobado y con el precio del buscador")
    assert r.status_code == 200 and r.json()["estado"] == "se_comprara"
    aviso = db.uno("""select detalle from eventos where entidad='viaje' and entidad_id=:v and paso='aviso al viajero'
                      order by id desc""", v=cot["viaje"]["id"])
    assert aviso and "se va a comprar" in aviso["detalle"]
    # el detalle tiene el vuelo, el enlace oficial y los clics
    d = cliente.get(f"{V1}/compras/{c['id']}").json()
    assert d["vuelo"]["numeros"] and d["vuelo"]["vendedor_url"].endswith("/vendedor") and d["viaje"]["estado"] == "aprobado"
    assert isinstance(d["clics"], list)


def test_el_registro_guarda_el_localizador_y_lo_compara_con_el_presupuesto(piloto, cliente):
    cot = _decidir(piloto)
    c = _compra(cot)
    _aprobar_viaje(cliente, cot["viaje"]["id"])
    assert _estado(cliente, c["id"], "en_analisis", 1).status_code == 200
    assert _estado(cliente, c["id"], "se_comprara", 2, motivo="Se compra hoy").status_code == 200
    registro = {"version": 3, "localizador": "QX7Z2P", "precio_pagado": "461.30", "vendedor": "American"}
    mal = cliente.post(f"{V1}/compras/{c['id']}/registro", json={**registro, "localizador": "x"}, headers=_csrf(cliente))
    assert mal.status_code == 422
    r = cliente.post(f"{V1}/compras/{c['id']}/registro", json=registro, headers=_csrf(cliente))
    assert r.status_code == 200, r.text
    hecha = r.json()
    assert (hecha["estado"], hecha["localizador"], hecha["precio_pagado_usd"], hecha["vendedor"]) == \
        ("comprada", "QX7Z2P", "461.30", "American")
    assert hecha["frente_presupuesto"]["presupuesto_usd"] and hecha["frente_presupuesto"]["diferencia_usd"]
    fila = _compra(cot)
    assert fila["localizador"] == "QX7Z2P" and fila["comprada_por"]
    assert fila["anticipacion_dias"] == (date(2026, 12, 8) - date.fromisoformat(fila["comprada"][:10])).days
    assert _estado(cliente, c["id"], "cancelada", 4, motivo="La grabación se movió").json()["estado"] == "cancelada"


def test_administracion_no_decide_la_compra_de_su_propio_viaje(piloto, cliente):
    admin = db.uno("select * from usuarios where correo='admin@demo.local'")
    cot = _decidir(piloto)
    # administración es la titular del viaje mientras dura la prueba (otras pruebas cuentan con que no tiene viajes)
    titular = db.uno("select usuario_id from viajes where id=:v", v=cot["viaje"]["id"])["usuario_id"]
    db.ejecutar("update viajes set usuario_id=:u where id=:v", u=admin["id"], v=cot["viaje"]["id"])
    try:
        c = _compra(cot)
        r = _estado(cliente, c["id"], "en_analisis", 1)
        assert r.status_code == 403 and r.json()["error"]["code"] == "SELF_APPROVAL"
        assert db.uno("select id from eventos where entidad='compra' and entidad_id=:i and paso='autoaprobación impedida'",
                      i=c["id"])
        assert _compra(cot)["estado"] == "solicitada"
    finally:
        db.ejecutar("update viajes set usuario_id=:u where id=:v", u=titular, v=cot["viaje"]["id"])


def test_analisis_desde_la_bandeja(piloto, cliente, monkeypatch):
    monkeypatch.setenv("ANALIZADOR_URL", "http://analizador:8090")
    monkeypatch.delenv("ANALIZADOR", raising=False)
    monkeypatch.setattr(analizador, "_llamar", lambda url, *a: {"estado": "fallido", "motivo": "la página pidió verificación"})
    db.ejecutar("delete from analisis_vuelo")
    cot = _decidir(piloto)
    c = _compra(cot)
    r = cliente.post(f"{V1}/compras/{c['id']}/analisis", headers=_csrf(cliente))
    assert r.status_code == 200 and r.json()["estado"] == "fallido", r.text
    assert cliente.get(f"{V1}/compras/{c['id']}").json()["analisis"]["estado"] == "fallido"
    db.ejecutar("delete from analisis_vuelo")


def test_cada_clic_a_una_fuente_queda_en_clics_fuente(piloto, cliente):
    cot = _decidir(piloto)
    vuelo = cot["decision"]["vuelo_id"]
    piloto.post(f"{V1}/cotizaciones/{cot['id']}/fuente", json={"destino": "vuelos", "vuelo_id": vuelo}, headers=_csrf(piloto))
    piloto.get(f"{V1}/cotizaciones/{cot['id']}/vuelos/{vuelo}/vendedor", follow_redirects=False)
    filas = db.todos("select * from clics_fuente where viaje_id=:v order by id", v=cot["viaje"]["id"])
    assert [f["destino"] for f in filas] == ["google_flights", "google_flights"]   # sin clave del buscador: a Google Flights
    assert all(f["dominio"] == "www.google.com" and f["usuario_id"] and f["opcion_id"] == vuelo for f in filas)
    assert len(cliente.get(f"{V1}/compras/{_compra(cot)['id']}").json()["clics"]) == 2


def test_las_elecciones_guardan_el_precio_esperado_y_el_del_buscador(piloto):
    cot = _decidir(piloto)
    for e in db.todos("select rasgos, precio from elecciones where decision_id=:d and tipo='vuelo'", d=cot["decision"]["id"]):
        rasgos = db.de_json(e["rasgos"], {})
        assert {"esperado", "frente_esperado", "precio_buscador"} <= set(rasgos)
        assert rasgos["precio_buscador"] == e["precio"]


def test_las_tablas_tienen_su_migracion():
    assert {"compras", "clics_fuente"} <= set(db.TABLAS)
    assert compras.TRANSICIONES["en_analisis"] == ("solicitada",)
