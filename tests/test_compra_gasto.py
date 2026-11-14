"""Lo comprado cuenta en el gasto del viaje: registrar la compra crea el gasto del tiquete (categoría vuelo, enlazado en
`compras.gasto_id`), que suma en «gastado» y entra al Excel contable. Si después llega el recibo de ese mismo tiquete,
se enlaza a ese gasto y no se cuenta dos veces. El modelo de lectura es un doble.
"""
import io
import json
import uuid
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, compras, contable, llm, tiempo, viajes

V1 = "/api/v1"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


@pytest.fixture()
def comprada(piloto) -> dict:
    """Un viaje del piloto aprobado, con el tiquete comprado por 461,30 USD (localizador único)."""
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    cot = piloto.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(piloto)).json()
    v = piloto.post(f"{V1}/cotizaciones/{cot['id']}/decision", json={"vuelo_id": cot["recomendada_id"]},
                    headers=_csrf(piloto)).json()["viaje"]
    assert viajes.cambiar_estado(v["id"], "aprobar", "", _admin(), confirmar_precio=True)[0]
    c = db.uno("select * from compras where viaje_id=:v and activa=1", v=v["id"])
    c = compras.cambiar_estado(c["id"], "se_comprara", c["version"], "Se compra hoy", _admin())
    localizador = "Q" + uuid.uuid4().hex[:5].upper()
    c = compras.registrar_compra(c["id"], c["version"], localizador, Decimal("461.30"), "American", _admin())
    return {"viaje": viajes.uno(v["id"]), "compra": db.uno("select * from compras where id=:i", i=c["id"]), "localizador": localizador}


@pytest.fixture()
def modelo(monkeypatch):
    for nombre, valor in (("MODELO_API_URL", "http://modelo.test"), ("MODELO_API_KEY", "clave-de-prueba"),
                          ("MODELO_NOMBRE", "modelo-de-prueba"), ("MODELO_FORMATO", "gemini")):
        monkeypatch.setattr(config, nombre, valor)
    doble = {"respuesta": {}}

    def generar(contenidos, **opciones):
        lectura = {"comercio": "American Airlines", "fecha": tiempo.hoy().isoformat(), "categoria": "vuelo", "total": 461.30,
                   "moneda": "USD", "confianza": 0.99, "dudas": [], **doble["respuesta"]}
        return {"content": {"parts": [{"text": json.dumps(lectura)}]}, "finishReason": "STOP"}

    monkeypatch.setattr(llm, "generar", generar)
    return doble


def _subir(c: TestClient, viaje_id: int):
    png = b"\x89PNG\r\n\x1a\n" + uuid.uuid4().bytes
    return c.post(f"{V1}/gastos", files={"archivo": ("tiquete.png", png, "image/png")}, data={"viaje_id": str(viaje_id)},
                  headers=_csrf(c))


def test_registrar_la_compra_crea_el_gasto_del_tiquete(comprada):
    c, v = comprada["compra"], comprada["viaje"]
    assert c["gasto_id"]
    g = db.uno("select * from gastos where id=:i", i=c["gasto_id"])
    assert (g["categoria"], g["total"], g["moneda"], g["total_usd"], g["estado"], g["viaje_id"]) == \
        ("vuelo", 461.30, "USD", 461.30, "aprobado", v["id"])
    assert g["viajero_id"] == v["viajero_id"] and g["proyecto_id"] == v["proyecto_id"]
    assert viajes.gastado(v["id"]) == pytest.approx(461.30)                       # suma en «gastado»
    hoy = tiempo.hoy()
    hoja = load_workbook(io.BytesIO(contable.libro(_admin(), hoy, hoy)))["Gastos"]
    filas = list(hoja.iter_rows(values_only=True))
    assert c["gasto_id"] in {dict(zip(filas[0], f, strict=True))["N.º gasto"] for f in filas[1:]}   # y en el Excel contable


def test_el_recibo_del_mismo_tiquete_se_enlaza_y_no_se_duplica(comprada, modelo, piloto):
    c, v = comprada["compra"], comprada["viaje"]
    modelo["respuesta"] = {"numero_factura": comprada["localizador"]}
    antes = db.uno("select count(*) n from gastos where viaje_id=:v", v=v["id"])["n"]
    r = _subir(piloto, v["id"])
    assert r.status_code in (200, 201), r.text
    assert r.json()["id"] == c["gasto_id"]                                          # el gasto de la compra
    assert db.uno("select count(*) n from gastos where viaje_id=:v", v=v["id"])["n"] == antes
    g = db.uno("select * from gastos where id=:i", i=c["gasto_id"])
    assert g["documento_id"] and g["estado"] == "aprobado"
    assert viajes.gastado(v["id"]) == pytest.approx(461.30)                       # una sola vez
    assert db.uno("select id from eventos where entidad='gasto' and entidad_id=:i and paso='recibo del tiquete enlazado'",
                  i=c["gasto_id"])


def test_el_recibo_de_otro_gasto_del_viaje_no_se_enlaza(comprada, modelo, piloto):
    c, v = comprada["compra"], comprada["viaje"]
    modelo["respuesta"] = {"categoria": "comida", "comercio": "Diner", "total": 23.10}
    r = _subir(piloto, v["id"])
    assert r.status_code == 201 and r.json()["id"] != c["gasto_id"]
    assert db.uno("select documento_id from gastos where id=:i", i=c["gasto_id"])["documento_id"] is None
