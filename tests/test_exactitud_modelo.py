"""Exactitud del precio esperado como indicador: lo que el modelo esperaba al decidir frente al precio del buscador en ese
momento y, cuando exista, frente a lo pagado. Proyecto propio para que nada de otras pruebas cambie las cifras."""
import json

from sqlalchemy import inspect

from app import db
from app.servicios import kpis, metricas, modelo

PROYECTO = 903


def _eleccion(precio, rasgos, origen="ZEA", destino="ZEB", creado="2027-01-15 10:00:00", elegida=1) -> int:
    if not db.uno("select id from proyectos where id=:i", i=PROYECTO):
        db.insertar("proyectos", id=PROYECTO, nombre="Proyecto de exactitud", moneda="USD")
    sid = db.insertar("solicitudes", proyecto_id=PROYECTO, origen=origen, destino=destino, ida="2027-02-01", regreso="2027-02-04",
                      estado="decidido", creado=creado)
    db.insertar("elecciones", solicitud_id=sid, tipo="vuelo", posicion=1, elegida=elegida, precio=precio,
                rasgos=json.dumps(rasgos), creado=creado)
    return sid


def test_sin_datos_todavia():
    vacio = modelo.exactitud({"proyecto_id": 10 ** 6})
    assert vacio["mae"] is None and vacio["mensaje"] == "sin datos todavía"


def test_mae_y_mape_por_ruta_y_mes():
    _eleccion(330, {"frente_esperado": 10})                  # esperado 300: el modelo se quedó corto en 30
    _eleccion(180, {"esperado": 200})                        # esperado 200: se pasó en 20
    _eleccion(500, {"tarifa": "Basic"})                      # sin precio esperado: no cuenta
    _eleccion(120, {"esperado": 100}, origen="ZEC", destino="ZED", creado="2027-02-03 09:00:00")
    e = modelo.exactitud({"proyecto_id": PROYECTO})
    assert e["filas"] == 3 and e["mae"] == 23.33 and e["mape"] == 12.3 and e["mensaje"] is None
    rutas = {r["ruta"]: r for r in e["por_ruta"]}
    assert rutas["ZEA → ZEB"] == {"ruta": "ZEA → ZEB", "filas": 2, "mae": 25.0, "mape": 10.1}
    assert {m["mes"]: m["filas"] for m in e["por_mes"]} == {"2027-01": 2, "2027-02": 1}
    assert modelo.exactitud({"proyecto_id": PROYECTO, "desde": "2027-02-01"})["filas"] == 1


def test_es_un_indicador_con_meta_y_semaforo():
    k = {x["nombre"]: x for x in kpis.evaluar({"proyecto_id": PROYECTO})}["exactitud_modelo"]
    assert k["valor"] == modelo.exactitud({"proyecto_id": PROYECTO})["mape"]
    assert k["sentido"] == "menor" and k["estado"] in ("verde", "ambar", "rojo")
    assert metricas.valor("exactitud_modelo", {"proyecto_id": 10 ** 6})["valor"] is None
    assert "exactitud_modelo" not in kpis.DE_PERSONA


def test_frente_a_lo_pagado_cuando_hay_compras():
    propia = not inspect(db.motor).has_table("compras")
    if propia:   # en esta rama la tabla aún no existe; con la del otro frente se usa la suya tal cual
        db.ejecutar("create table compras (id integer primary key, viaje_id integer, precio_pagado float)")
    sid = _eleccion(400, {"esperado": 380}, origen="ZEE", destino="ZEF")
    did = db.insertar("decisiones", solicitud_id=sid, proyecto_id=PROYECTO, total=400, creado=db.ahora())
    db.ejecutar("update elecciones set decision_id=:d where solicitud_id=:s", d=did, s=sid)
    vid = db.insertar("viajes", solicitud_id=sid, decision_id=did, proyecto_id=PROYECTO, usuario_id=1, estado="aprobado",
                      presupuesto_usd=400, creado=db.ahora())
    if propia:
        db.ejecutar("insert into compras (id, viaje_id, precio_pagado) values (:i, :v, 418)",
                    i=(db.uno("select max(id) i from compras")["i"] or 0) + 1, v=vid)
        pagado = modelo.exactitud({"proyecto_id": PROYECTO})["contra_pagado"]
        assert pagado["filas"] == 1 and pagado["mae"] == 38.0
        db.ejecutar("drop table compras")
