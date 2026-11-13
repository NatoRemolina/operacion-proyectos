"""API v1 de Monitoreo: cada pestaña con sus cifras, tablas y descargas, y la exportación CSV. Contrato en `contracts/api-v1.md`.

Solo administración, como `/admin/monitoreo`. Las cifras salen de `metricas`, la misma definición de la pantalla.
"""
import csv
import io

import pytest

from app import db
from app.servicios import metricas, tablero

V1 = "/api/v1/monitoreo"
PESTANAS = ["viajes", "gastos", "busquedas", "modelo", "cupos", "auditoria", "calidad"]


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    return cuerpo["error"]


def _cifra(p: dict, etiqueta: str) -> dict:
    return next(c for c in p["cifras"] if c["etiqueta"] == etiqueta)


def _tabla(p: dict, titulo: str) -> dict:
    return next(t for t in p["tablas"] if t["titulo"] == titulo)


@pytest.mark.parametrize("pestana", PESTANAS)
def test_cada_pestana_tiene_la_forma_del_contrato(cliente, viaje_aprobado, pestana):
    r = cliente.get(V1, params={"pestana": pestana})
    assert r.status_code == 200, r.text
    p = r.json()
    assert set(p) == {"pestana", "titulo", "nota", "pestanas", "filtros", "proyectos", "cifras", "tablas", "exportar"}
    assert p["pestana"] == pestana and p["titulo"] == tablero.PESTANAS[pestana]
    assert [x["clave"] for x in p["pestanas"]] == PESTANAS
    for c in p["cifras"]:
        assert set(c) == {"etiqueta", "valor", "unidad", "pie"}
    for t in p["tablas"]:
        assert set(t) == {"titulo", "columnas", "filas", "vacio", "nota", "barras"}
        assert all(len(f) == len(t["columnas"]) for f in t["filas"]), t["titulo"]
    assert all(e["vista"] in tablero.FECHA_DE_VISTA for e in p["exportar"])


def test_sin_pestana_es_gastos_y_una_desconocida_es_422(cliente):
    assert cliente.get(V1).json()["pestana"] == "gastos"
    _error(cliente.get(V1, params={"pestana": "secretos"}), 422, "VALIDATION_ERROR")


def test_las_cifras_son_las_mismas_de_las_metricas(cliente, viaje_aprobado):
    g = cliente.get(V1, params={"pestana": "gastos"}).json()
    m = metricas.gastos(tablero.filtros())
    assert _cifra(g, "Esperando revisión")["valor"] == m["pendientes"]
    assert _cifra(g, "Gasto real aprobado")["valor"] == m["real_total"] and _cifra(g, "Gasto real aprobado")["unidad"] == "USD"
    v = cliente.get(V1, params={"pestana": "viajes"}).json()
    assert _cifra(v, "Presupuestos por aprobar")["valor"] == metricas.viajes({})["pendientes"]
    detalle = _tabla(v, "Presupuesto frente a gasto, por viaje")
    assert viaje_aprobado["id"] in {int(f[0]["href"].rsplit("/", 1)[1]) for f in detalle["filas"]}
    assert detalle["filas"][0][0]["href"].startswith("/viajes/")


def test_el_modelo_separa_el_costo_del_asesor_con_su_tope(cliente):
    db.insertar("llamadas_modelo", momento=db.ahora(), uso="asesor", modelo="asesor-prueba", tokens_entrada=0, tokens_salida=0,
                latencia_ms=900, estado_http=200, error=None, costo_usd="0.25")
    p = cliente.get(V1, params={"pestana": "modelo"}).json()
    asesor = _cifra(p, "Costo del asesor")
    assert asesor["unidad"] == "USD" and asesor["valor"] >= 0.25
    assert "tope" in asesor["pie"]
    usos = [f[0] for f in _tabla(p, "Por uso")["filas"]]
    assert "asesor" in usos


def test_auditoria_y_calidad_traen_bitacora_comprobaciones_y_catalogo(cliente, viaje_aprobado):
    a = cliente.get(V1, params={"pestana": "auditoria"}).json()
    assert _tabla(a, "Qué se hizo")["filas"]
    assert _tabla(a, "Últimos hechos")["columnas"][0]["texto"] == "Momento (UTC)"
    c = cliente.get(V1, params={"pestana": "calidad"}).json()
    assert len(_tabla(c, "Comprobaciones de los datos")["filas"]) == len(metricas.calidad_de_datos())
    assert {f[1] for f in _tabla(c, "Catálogo de métricas")["filas"]} == set(metricas.CATALOGO)


def test_los_filtros_se_aplican(cliente, viaje_aprobado):
    p = cliente.get(V1, params={"pestana": "viajes", "proyecto_id": 99999, "desde": "2026-01-01", "hasta": "x"}).json()
    assert p["filtros"] == {"proyecto_id": 99999, "desde": "2026-01-01", "hasta": None}
    assert _tabla(p, "Presupuesto frente a gasto, por viaje")["filas"] == []


def test_monitoreo_es_solo_de_administracion(piloto, gestor, anonimo):
    _error(piloto.get(V1), 403, "FORBIDDEN")
    _error(gestor.get(V1, params={"pestana": "auditoria"}), 403, "FORBIDDEN")
    _error(anonimo.get(V1), 401, "UNAUTHENTICATED")


# ---------- exportación ----------
def test_exporta_una_vista_con_los_filtros_y_deja_evento(cliente, viaje_aprobado):
    antes = db.uno("select coalesce(max(id), 0) m from eventos")["m"]
    r = cliente.get(f"{V1}/exportar.csv", params={"vista": "v_h_viaje"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv") and r.headers["cache-control"] == "no-store"
    assert 'filename="v_h_viaje.csv"' in r.headers["content-disposition"]
    filas = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    assert viaje_aprobado["id"] in {int(f["id"]) for f in filas}
    assert any(e["paso"] == "exportación" for e in db.todos("select * from eventos where id>:a and entidad='monitoreo'", a=antes))
    assert r.text == cliente.get("/admin/monitoreo/exportar.csv", params={"vista": "v_h_viaje"}).text


def test_solo_exporta_las_vistas_de_la_capa_analitica(cliente):
    _error(cliente.get(f"{V1}/exportar.csv", params={"vista": "usuarios"}), 422, "VALIDATION_ERROR")
    _error(cliente.get(f"{V1}/exportar.csv", params={"vista": "sesiones"}), 422, "VALIDATION_ERROR")


def test_la_exportacion_es_solo_de_administracion(piloto, anonimo):
    _error(piloto.get(f"{V1}/exportar.csv", params={"vista": "v_h_gasto"}), 403, "FORBIDDEN")
    _error(anonimo.get(f"{V1}/exportar.csv", params={"vista": "v_h_gasto"}), 401, "UNAUTHENTICATED")
