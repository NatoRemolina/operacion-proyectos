"""Compras frente al viaje: lo que le pasa a la compra del tiquete cuando el viaje cambia de estado.

- La vuelta a análisis se hace al cambiar el estado del viaje, no al leer la compra: un GET no cambia datos ni versión.
- Con el viaje cerrado, la compra que iba a comprarse tiene salida.
- Rechazar o reabrir con el tiquete comprado deja un evento y un aviso en Compras.
- Volver a aprobar con el tiquete comprado no consulta el buscador: el presupuesto usa lo pagado.
"""
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from app import api_v1, db
from app.servicios import acceso, compras, precios, viajes

V1 = "/api/v1"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


def _viaje_con_compra(piloto: TestClient, hasta: str) -> tuple[dict, dict]:
    """Un viaje del piloto, aprobado, con su compra llevada hasta `hasta` (se_comprara o comprada)."""
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    cot = piloto.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(piloto)).json()
    decidida = piloto.post(f"{V1}/cotizaciones/{cot['id']}/decision", json={"vuelo_id": cot["recomendada_id"]},
                           headers=_csrf(piloto)).json()
    v = decidida["viaje"]
    assert viajes.cambiar_estado(v["id"], "aprobar", "", _admin(), confirmar_precio=True)[0]
    c = db.uno("select * from compras where viaje_id=:v and activa=1", v=v["id"])
    c = compras.cambiar_estado(c["id"], "se_comprara", c["version"], "Se compra hoy", _admin())
    if hasta == "comprada":
        c = compras.registrar_compra(c["id"], c["version"], "QX7Z2P", Decimal("461.30"), "American", _admin())
    return viajes.uno(v["id"]), c


def _fila(cid: int) -> dict:
    return db.uno("select estado, version from compras where id=:i", i=cid)


def test_leer_la_compra_no_la_cambia(piloto, cliente):
    v, c = _viaje_con_compra(piloto, "se_comprara")
    db.actualizar("viajes", v["id"], estado="pendiente_aprobacion")   # un viaje que salió de aprobado por otra vía
    antes = _fila(c["id"])
    assert cliente.get(f"{V1}/compras/{c['id']}").status_code == 200
    assert cliente.get(f"{V1}/compras").status_code == 200
    assert _fila(c["id"]) == antes == {"estado": "se_comprara", "version": c["version"]}


def test_reabrir_el_viaje_devuelve_la_compra_a_analisis_en_ese_momento(piloto):
    v, c = _viaje_con_compra(piloto, "se_comprara")
    assert viajes.cambiar_estado(v["id"], "reabrir", "", _admin())[0]
    assert _fila(c["id"]) == {"estado": "en_analisis", "version": c["version"] + 1}   # sin que nadie la lea
    assert db.uno("select id from eventos where entidad='compra' and entidad_id=:i and paso='compra: vuelve a análisis'", i=c["id"])


def test_con_el_viaje_cerrado_la_compra_que_iba_a_comprarse_tiene_salida(piloto):
    v, c = _viaje_con_compra(piloto, "se_comprara")
    assert viajes.cambiar_estado(v["id"], "cerrar", "", _admin())[0]
    fila = _fila(c["id"])
    assert fila["estado"] == "en_analisis"
    hecho = compras.cambiar_estado(c["id"], "no_se_comprara", fila["version"], "El viaje se cerró sin comprar", _admin())
    assert hecho["estado"] == "no_se_comprara"


def test_una_compra_que_quedo_en_se_comprara_con_el_viaje_cerrado_se_puede_cancelar(piloto):
    v, c = _viaje_con_compra(piloto, "se_comprara")
    db.actualizar("viajes", v["id"], estado="cerrado")   # dato de antes: el viaje se cerró sin pasar por la compra
    hecho = compras.cambiar_estado(c["id"], "cancelada", c["version"], "El viaje ya se cerró", _admin())
    assert hecho["estado"] == "cancelada"


@pytest.mark.parametrize("acciones, paso", [(["reabrir"], "viaje reabierto con el tiquete comprado"),
                                            (["reabrir", "rechazar"], "viaje rechazado con el tiquete comprado")])
def test_rechazar_o_reabrir_con_el_tiquete_comprado_deja_evento_y_aviso_en_compras(piloto, cliente, acciones, paso):
    v, c = _viaje_con_compra(piloto, "comprada")
    for accion in acciones:
        assert viajes.cambiar_estado(v["id"], accion, "No se graba esa semana", _admin())[0]
    assert db.uno("select id from eventos where entidad='compra' and entidad_id=:i and paso=:p", i=c["id"], p=paso)
    detalle = cliente.get(f"{V1}/compras/{c['id']}").json()
    assert detalle["estado"] == "comprada" and "tiquete ya está comprado" in detalle["aviso"]
    assert any(x["id"] == c["id"] and x["aviso"] for x in cliente.get(f"{V1}/compras").json()["items"])


def test_volver_a_aprobar_con_el_tiquete_comprado_no_consulta_el_buscador_y_usa_lo_pagado(piloto, monkeypatch):
    v, c = _viaje_con_compra(piloto, "comprada")
    assert viajes.cambiar_estado(v["id"], "reabrir", "", _admin())[0]
    monkeypatch.setattr(precios, "reconfirmar", lambda *a, **k: pytest.fail("no se consulta el buscador"))
    hecho, mensaje = viajes.cambiar_estado(v["id"], "aprobar", "", _admin())
    assert hecho and "461.30" in mensaje
    aprobado = viajes.uno(v["id"])
    lineas = db.de_json(aprobado["presupuesto_detalle"], [])
    tiquete = next(l for l in lineas if l["grupo"] == "vuelo" and l["concepto"].startswith("Precio"))
    assert tiquete["valor"] == 461.30 and "pagado" in tiquete["concepto"]
    assert aprobado["presupuesto_usd"] == pytest.approx(sum(l["valor"] for l in lineas))
    assert compras.de_viaje(v["id"])["aviso"] is None   # aprobado otra vez, ya no hay nada que mirar


def test_el_presupuesto_con_lo_pagado_se_suma_con_decimal(piloto):
    """Con coma flotante, 300 + 100,005 = 400,00499…, que redondeaba a 400,00; a centavos y medio hacia arriba es 400,01."""
    v, _ = _viaje_con_compra(piloto, "comprada")
    lineas = [{"grupo": "vuelo", "concepto": "Precio del vuelo", "valor": 279.0},
              {"grupo": "hotel", "concepto": "Hotel", "valor": 100.005}]
    db.actualizar("viajes", v["id"], presupuesto_detalle=lineas, presupuesto_usd=379.01)
    texto = viajes._presupuesto_con_lo_pagado(viajes.uno(v["id"]), {"precio_pagado": 300.0}, _admin())
    assert "300.00 USD" in texto
    guardado = viajes.uno(v["id"])
    assert guardado["presupuesto_usd"] == 400.01
    assert db.de_json(guardado["presupuesto_detalle"], [])[0]["valor"] == 300.0


def test_aprobar_con_la_compra_en_se_comprara_lo_avisa(piloto):
    v, c = _viaje_con_compra(piloto, "se_comprara")
    db.actualizar("viajes", v["id"], estado="pendiente_aprobacion")   # dato de antes, con la compra sin devolver a análisis
    hecho, mensaje = viajes.cambiar_estado(v["id"], "aprobar", "", _admin(), confirmar_precio=True)
    assert hecho and "Se va a comprar" in mensaje
