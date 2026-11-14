"""Lo comprado cuenta en el gasto del viaje: registrar la compra crea el gasto del tiquete (categoría vuelo, enlazado en
`compras.gasto_id`), que suma en «gastado» y entra al Excel contable. Si después llega el recibo de ese mismo tiquete,
se enlaza a ese gasto y no se cuenta dos veces. El modelo de lectura es un doble.

Con la decisión de la responsable («Aprobado si cuadra»): el gasto del tiquete queda aprobado si lo pagado no supera lo
cotizado al decidir en más de la regla `tolerancia_tiquete_pct` (10 %); si lo supera, o no hay precio cotizado, va a
revisión y lo aprueba otra persona de administración. Cancelar el tiquete comprado devuelve su gasto a revisión. Un
recibo que llegó antes de la compra se enlaza en vez de duplicarse, y uno que llega después solo se une si el importe
coincide.
"""
import io
import json
import uuid
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, compras, contable, gastos, llm, revision, tiempo, viajes

V1 = "/api/v1"
PEDIDO = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
          "ida": "2026-12-08", "regreso": "2026-12-11"}


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


@pytest.fixture(scope="module")
def otra_admin() -> dict:
    """Otra persona de administración, para aprobar lo que registró la primera."""
    correo = f"admin-dos-{uuid.uuid4().hex[:6]}@demo.local"
    acceso.crear_usuario(correo, "Otra administración", "admin", "clave-de-otra-admin-2026")
    return db.uno("select * from usuarios where correo=:c", c=correo)


@pytest.fixture()
def tolerancia():
    """Fija la regla `tolerancia_tiquete_pct` durante la prueba y deja la de antes al final."""
    fila = db.uno("select id, valor from reglas where ambito='supuesto' and clave=:c", c=compras.TOLERANCIA_TIQUETE)

    def fijar(valor: str):
        db.actualizar("reglas", fila["id"], valor=valor)

    yield fijar
    db.actualizar("reglas", fila["id"], valor=fila["valor"])


def _decidir(piloto: TestClient, cot: dict | None = None, vuelo_id: int | None = None) -> tuple[dict, dict]:
    cot = cot or piloto.post(f"{V1}/cotizaciones", json=PEDIDO, headers=_csrf(piloto)).json()
    cuerpo = {"vuelo_id": vuelo_id or cot["recomendada_id"]}
    if vuelo_id:
        cuerpo["motivo"] = "Sale a una hora que le sirve más al rodaje"
    r = piloto.post(f"{V1}/cotizaciones/{cot['id']}/decision", json=cuerpo, headers=_csrf(piloto))
    assert r.status_code in (200, 201), r.text
    return cot, r.json()["viaje"]


def _por_comprar(viaje_id: int) -> dict:
    """La compra activa del viaje, aprobado, en «Se va a comprar»."""
    assert viajes.cambiar_estado(viaje_id, "aprobar", "", _admin(), confirmar_precio=True)[0]
    c = db.uno("select * from compras where viaje_id=:v and activa=1", v=viaje_id)
    return compras.cambiar_estado(c["id"], "se_comprara", c["version"], "Se compra hoy", _admin())


def _registrar(c: dict, precio: Decimal | str, localizador: str | None = None) -> dict:
    localizador = localizador or "Q" + uuid.uuid4().hex[:5].upper()
    c = compras.registrar_compra(c["id"], c["version"], localizador, Decimal(str(precio)), "American", _admin())
    return {"viaje": viajes.uno(c["viaje_id"]), "compra": db.uno("select * from compras where id=:i", i=c["id"]),
            "localizador": localizador}


def _gasto(gid: int) -> dict:
    g = db.uno("select * from gastos where id=:i", i=gid)
    return {**g, "alertas": db.de_json(g["alertas"], []), "motivos": db.de_json(g["motivos"], [])}


def _vuelos_aprobados(viaje_id: int) -> list[dict]:
    return db.todos("select id, total_usd from gastos where viaje_id=:v and categoria='vuelo' and estado in ('aprobado','aprobado_auto')",
                    v=viaje_id)


@pytest.fixture()
def comprada(piloto) -> dict:
    """Un viaje del piloto aprobado, con el tiquete comprado por lo cotizado al decidir (localizador único)."""
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    return _registrar(c, Decimal(str(c["precio_cotizado"])))


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
    pagado = c["precio_pagado"]
    assert (g["categoria"], g["total"], g["moneda"], g["total_usd"], g["estado"], g["viaje_id"]) == \
        ("vuelo", pagado, "USD", pagado, "aprobado", v["id"])
    assert g["viajero_id"] == v["viajero_id"] and g["proyecto_id"] == v["proyecto_id"]
    assert viajes.gastado(v["id"]) == pytest.approx(pagado)                       # suma en «gastado»
    hoy = tiempo.hoy()
    hoja = load_workbook(io.BytesIO(contable.libro(_admin(), hoy, hoy)))["Gastos"]
    filas = list(hoja.iter_rows(values_only=True))
    assert c["gasto_id"] in {dict(zip(filas[0], f, strict=True))["N.º gasto"] for f in filas[1:]}   # y en el Excel contable


# ---------- «Aprobado si cuadra» ----------
def test_dentro_de_la_tolerancia_queda_aprobado_sin_revisor_y_con_su_origen(piloto):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    tope = (Decimal(str(c["precio_cotizado"])) * Decimal("1.10")).quantize(Decimal("0.01"))
    hecho = _registrar(c, tope)                                                     # justo el 10 % encima: cuadra
    g = _gasto(hecho["compra"]["gasto_id"])
    assert (g["estado"], g["revisado_por"], g["origen_dato"], g["motivos"]) == ("aprobado", None, compras.ORIGEN_COMPRA, [])


def test_por_encima_de_lo_cotizado_va_a_revision_y_la_aprueba_otra_persona(piloto, otra_admin):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    cotizado = Decimal(str(c["precio_cotizado"]))
    pagado = (cotizado * Decimal("1.10")).quantize(Decimal("0.01")) + Decimal("0.01")
    hecho = _registrar(c, pagado)
    g = _gasto(hecho["compra"]["gasto_id"])
    assert g["estado"] == "revision" and g["revisado_por"] is None
    assert g["motivos"] == [compras.SOBRE_COTIZADO]
    assert g["alertas"] == [f"Tiquete por encima de lo cotizado ({pagado:.2f} USD frente a {cotizado:.2f} USD)"]
    assert viajes.gastado(v["id"]) == 0                                             # en revisión no suma
    with pytest.raises(revision.RevisionImpedida):                                  # quien registró la compra no lo aprueba
        revision.guardar(g["id"], _admin(), g["version"], "aprobar")
    hecho = revision.guardar(g["id"], otra_admin, _gasto(g["id"])["version"], "excepcion",
                             motivo="Se confirmó el precio con la aerolínea")
    assert hecho["estado"] == "aprobado" and _gasto(g["id"])["revisado_por"] == otra_admin["id"]


def test_sin_precio_cotizado_va_a_revision(piloto):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    db.ejecutar("update compras set precio_cotizado=null where id=:i", i=c["id"])
    hecho = _registrar(c, "300.00")
    g = _gasto(hecho["compra"]["gasto_id"])
    assert g["estado"] == "revision" and g["motivos"] == [compras.SOBRE_COTIZADO]
    assert "sin precio cotizado" in g["alertas"][0]


def test_la_tolerancia_es_una_regla_editable(piloto, tolerancia):
    assert db.uno("select valor from reglas where ambito='supuesto' and clave=:c", c=compras.TOLERANCIA_TIQUETE)["valor"] == "10"
    tolerancia("100")
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    hecho = _registrar(c, (Decimal(str(c["precio_cotizado"])) * Decimal("1.9")).quantize(Decimal("0.01")))
    assert _gasto(hecho["compra"]["gasto_id"])["estado"] == "aprobado"


# ---------- cancelar lo comprado ----------
def test_cancelar_lo_comprado_y_volver_a_comprar_deja_un_solo_vuelo_aprobado(piloto, tolerancia):
    tolerancia("500")   # los dos tiquetes quedan aprobados al comprarlos: así se ve que cancelar quita el primero
    cot, v = _decidir(piloto)
    primera = _registrar(_por_comprar(v["id"]), "461.30")
    assert len(_vuelos_aprobados(v["id"])) == 1
    c = compras.uno(primera["compra"]["id"])
    compras.cambiar_estado(c["id"], "cancelada", c["version"], "La aerolínea movió el vuelo", _admin())
    g = _gasto(primera["compra"]["gasto_id"])
    assert g["estado"] == "revision" and compras.COMPRA_CANCELADA in g["motivos"]
    assert "Compra cancelada: revisar reembolso" in g["alertas"]
    assert _vuelos_aprobados(v["id"]) == []
    assert db.uno("select id from eventos where entidad='gasto' and entidad_id=:i and paso='compra cancelada: revisar reembolso'",
                  i=g["id"])
    gastos.asignar_viaje(g["id"], viajes.uno(v["id"]))                             # volver a validarlo no quita el motivo
    g = _gasto(g["id"])
    assert g["estado"] == "revision" and g["motivos"][0] == compras.COMPRA_CANCELADA
    assert viajes.cambiar_estado(v["id"], "reabrir", "", _admin())[0]
    otro = next(x["id"] for x in cot["vuelos"] if x["id"] != cot["recomendada_id"])
    _decidir(piloto, cot, otro)
    segunda = _registrar(_por_comprar(v["id"]), "470.00")
    assert segunda["compra"]["id"] != primera["compra"]["id"]
    assert [f["id"] for f in _vuelos_aprobados(v["id"])] == [segunda["compra"]["gasto_id"]]
    assert viajes.gastado(v["id"]) == pytest.approx(470.00)


# ---------- el recibo que llega antes de la compra ----------
def test_el_recibo_que_llego_antes_se_enlaza_al_registrar_la_compra(piloto, modelo):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    localizador = "R" + uuid.uuid4().hex[:5].upper()
    pagado = Decimal(str(c["precio_cotizado"]))
    modelo["respuesta"] = {"numero_factura": localizador, "total": float(pagado)}
    recibo = _subir(piloto, v["id"])
    assert recibo.status_code == 201, recibo.text
    antes = db.uno("select count(*) n from gastos where viaje_id=:v", v=v["id"])["n"]
    hecho = _registrar(c, pagado, localizador)
    assert hecho["compra"]["gasto_id"] == recibo.json()["id"]                       # el del recibo, no uno nuevo
    assert db.uno("select count(*) n from gastos where viaje_id=:v", v=v["id"])["n"] == antes
    assert db.uno("select id from eventos where entidad='gasto' and entidad_id=:i and paso='recibo ya cargado enlazado a la compra'",
                  i=recibo.json()["id"])


def test_el_recibo_anterior_del_mismo_comercio_e_importe_parecido_tambien_se_enlaza(piloto, modelo):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    modelo["respuesta"] = {"comercio": "American", "total": float(pagado + Decimal("0.50")), "numero_factura": None}
    recibo = _subir(piloto, v["id"]).json()
    assert _registrar(c, pagado)["compra"]["gasto_id"] == recibo["id"]


def test_un_recibo_anterior_de_otro_importe_no_se_enlaza(piloto, modelo):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    localizador = "E" + uuid.uuid4().hex[:5].upper()
    modelo["respuesta"] = {"numero_factura": localizador, "total": 45.00, "comercio": "American"}   # el equipaje
    recibo = _subir(piloto, v["id"]).json()
    hecho = _registrar(c, Decimal(str(c["precio_cotizado"])), localizador)
    assert hecho["compra"]["gasto_id"] != recibo["id"]


# ---------- el recibo que llega después ----------
def test_el_recibo_del_mismo_tiquete_se_enlaza_y_no_se_duplica(comprada, modelo, piloto):
    c, v = comprada["compra"], comprada["viaje"]
    modelo["respuesta"] = {"numero_factura": comprada["localizador"], "total": c["precio_pagado"]}
    antes = db.uno("select count(*) n from gastos where viaje_id=:v", v=v["id"])["n"]
    r = _subir(piloto, v["id"])
    assert r.status_code in (200, 201), r.text
    assert r.json()["id"] == c["gasto_id"]                                          # el gasto de la compra
    assert db.uno("select count(*) n from gastos where viaje_id=:v", v=v["id"])["n"] == antes
    g = db.uno("select * from gastos where id=:i", i=c["gasto_id"])
    assert g["documento_id"] and g["estado"] == "aprobado"
    assert viajes.gastado(v["id"]) == pytest.approx(c["precio_pagado"])           # una sola vez
    assert db.uno("select id from eventos where entidad='gasto' and entidad_id=:i and paso='recibo del tiquete enlazado'",
                  i=c["gasto_id"])


@pytest.mark.parametrize("diferencia", [Decimal("0.99"), Decimal("-0.99")])
def test_el_recibo_se_une_con_una_diferencia_de_hasta_un_dolar(comprada, modelo, piloto, diferencia):
    c, v = comprada["compra"], comprada["viaje"]
    modelo["respuesta"] = {"numero_factura": comprada["localizador"], "total": float(Decimal(str(c["precio_pagado"])) + diferencia)}
    assert _subir(piloto, v["id"]).json()["id"] == c["gasto_id"]


def test_el_recibo_con_el_localizador_y_otro_importe_queda_aparte_en_revision(comprada, modelo, piloto):
    c, v = comprada["compra"], comprada["viaje"]
    modelo["respuesta"] = {"numero_factura": comprada["localizador"], "total": 45.00}   # el recibo del equipaje
    r = _subir(piloto, v["id"])
    assert r.status_code == 201 and r.json()["id"] != c["gasto_id"]
    g = _gasto(r.json()["id"])
    assert g["estado"] == "revision" and compras.IMPORTE_DISTINTO in g["motivos"]
    assert "Mismo localizador que el tiquete, importe distinto" in g["alertas"]
    assert db.uno("select documento_id from gastos where id=:i", i=c["gasto_id"])["documento_id"] is None


def test_el_recibo_de_otro_gasto_del_viaje_no_se_enlaza(comprada, modelo, piloto):
    c, v = comprada["compra"], comprada["viaje"]
    modelo["respuesta"] = {"categoria": "comida", "comercio": "Diner", "total": 23.10}
    r = _subir(piloto, v["id"])
    assert r.status_code == 201 and r.json()["id"] != c["gasto_id"]
    assert db.uno("select documento_id from gastos where id=:i", i=c["gasto_id"])["documento_id"] is None
