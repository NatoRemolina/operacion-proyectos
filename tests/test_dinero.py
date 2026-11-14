"""Dinero: los importes se comparan a centavos (Decimal), no con igualdad de coma flotante.

- Un duplicado exacto se reconoce aunque la base guarde 0.30000000000000004 y el recibo diga 0.3.
- La exactitud frente a lo pagado solo cuenta compras `comprada` y activas, y compara lo pagado con lo cotizado.
"""
import json
import uuid

import pytest

from app import db
from app.servicios import modelo, validacion

PROYECTO = 904


def _gasto(comercio: str, total: float, fecha: str = "2031-05-05", moneda: str = "USD") -> int:
    return db.insertar("gastos", comercio=comercio, fecha=fecha, total=total, moneda=moneda, estado="revision", creado=db.ahora())


@pytest.mark.parametrize("guardado, leido", [(0.1 + 0.2, 0.3), (19.99, 19.990000001), (100.0, 100.004)])
def test_un_duplicado_exacto_se_reconoce_a_centavos(guardado, leido):
    comercio = f"Comercio {uuid.uuid4().hex[:8]}"
    gid = _gasto(comercio, guardado)
    try:
        r = validacion.revisar({"comercio": comercio, "fecha": "2031-05-05", "total": leido, "moneda": "USD",
                                "categoria": "comida", "confianza": 0.99, "dudas": []}, None, 0, None)
        assert "duplicado" in r["motivos"], r["motivos"]
    finally:
        db.ejecutar("delete from gastos where id=:i", i=gid)


def test_un_centavo_de_diferencia_no_es_duplicado_exacto():
    comercio = f"Comercio {uuid.uuid4().hex[:8]}"
    gid = _gasto(comercio, 19.99)
    try:
        r = validacion.revisar({"comercio": comercio, "fecha": "2031-05-05", "total": 20.00, "moneda": "USD",
                                "categoria": "comida", "confianza": 0.99, "dudas": []}, None, 0, None)
        assert "duplicado" not in r["motivos"] and "duplicado_aproximado" in r["motivos"]
    finally:
        db.ejecutar("delete from gastos where id=:i", i=gid)


def _viaje_con_compra(rasgos: dict | None = None, **compra) -> None:
    if not db.uno("select id from proyectos where id=:i", i=PROYECTO):
        db.insertar("proyectos", id=PROYECTO, nombre="Proyecto de lo pagado", moneda="USD", fecha_inicio="2020-01-01", fecha_fin="2035-12-31")
    sid = db.insertar("solicitudes", proyecto_id=PROYECTO, origen="ZPA", destino="ZPB", ida="2031-06-01", regreso="2031-06-04",
                      estado="decidido", creado="2031-05-01 10:00:00")
    did = db.insertar("decisiones", solicitud_id=sid, proyecto_id=PROYECTO, total=400, creado="2031-05-01 10:00:00")
    db.insertar("elecciones", decision_id=did, solicitud_id=sid, tipo="vuelo", posicion=1, elegida=1, precio=400,
                rasgos=json.dumps({"esperado": 380} if rasgos is None else rasgos), creado="2031-05-01 10:00:00")
    vid = db.insertar("viajes", solicitud_id=sid, decision_id=did, proyecto_id=PROYECTO, usuario_id=1, estado="aprobado",
                      presupuesto_usd=400, creado="2031-05-01 10:00:00")
    db.insertar("compras", viaje_id=vid, solicitud_id=sid, decision_id=did, version=0, creado="2031-05-02 10:00:00", **compra)


def test_lo_pagado_solo_cuenta_compras_compradas_y_activas_frente_a_lo_cotizado():
    _viaje_con_compra(activa=1, estado="comprada", precio_pagado=440.0, precio_cotizado=400.0)    # cuenta: 40 sobre lo cotizado
    _viaje_con_compra(activa=0, estado="comprada", precio_pagado=999.0, precio_cotizado=400.0)    # inactiva: no cuenta
    _viaje_con_compra(activa=1, estado="cancelada", precio_pagado=999.0, precio_cotizado=400.0)   # cancelada: no cuenta
    _viaje_con_compra(activa=1, estado="comprada", precio_pagado=405.0, precio_cotizado=405.0, rasgos={})   # sin precio esperado: cuenta
    pagado = modelo.exactitud({"proyecto_id": PROYECTO})["contra_pagado"]
    assert pagado == {"filas": 2, "mae": 20.0, "mape": 4.5}
