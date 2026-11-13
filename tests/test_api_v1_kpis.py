"""API v1 de KPIs: tablero con meta, semáforo y tendencia, ficha por persona y exportación. Contrato en `contracts/api-v1.md`.

Solo administración, como la pantalla de hoy. Las cifras salen del mismo servicio que la pantalla (`servicios.kpis`).
"""
import csv
import io

from app import db
from app.servicios import kpis

V1 = "/api/v1/kpis"


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    return cuerpo["error"]


def _piloto_id() -> int:
    return db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]


# ---------- tablero ----------
def test_el_tablero_trae_los_indicadores_de_los_dos_retos_con_meta_y_semaforo(cliente, viaje_aprobado):
    r = cliente.get(V1)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    t = r.json()
    assert set(t) >= {"filtros", "retos", "proyectos", "kpis", "resumen", "tendencia", "cotizacion", "gastos", "personas", "por_cargo"}
    assert {k["nombre"] for k in t["kpis"]} == set(kpis.KPIS)
    assert {k["reto"] for k in t["kpis"]} == {1, 2}
    assert t["retos"] == [{"reto": 1, "nombre": kpis.RETOS[1]}, {"reto": 2, "nombre": kpis.RETOS[2]}]
    k = t["kpis"][0]
    assert set(k) == {"nombre", "titulo", "unidad", "para_que", "formula", "sentido", "meta", "alerta", "responsable", "reto",
                      "principal", "valor", "estado", "estado_texto"}
    assert all(x["estado"] in ("verde", "ambar", "rojo", "sin datos", "fuera de rango") for x in t["kpis"])
    # El resumen cuenta los cuatro estados aunque alguno esté en cero
    assert set(t["resumen"]) == {"verde", "ambar", "rojo", "sin_datos", "fuera_de_rango"}
    assert sum(t["resumen"].values()) == len(t["kpis"])


def test_el_tablero_usa_las_mismas_cifras_que_la_pantalla(cliente, viaje_aprobado):
    t = cliente.get(V1).json()
    pantalla = cliente.get("/api/kpis").json()
    assert [(k["nombre"], k["valor"], k["estado"]) for k in t["kpis"]] == \
           [(k["nombre"], k["valor"], k["estado"]) for k in pantalla["kpis"]]
    assert t["tendencia"]["semanas"] == pantalla["tendencia"]["semanas"]
    assert len(t["tendencia"]["filas"]) == len(pantalla["tendencia"]["filas"]) and len(t["tendencia"]["semanas"]) == 8
    assert [p["id"] for p in t["personas"]] == [p["id"] for p in pantalla["personas"]]


def test_los_desgloses_son_pares_con_nombre(cliente, viaje_aprobado):
    c = cliente.get(V1).json()["cotizacion"]
    for clave in ("cotizaciones_por_persona", "cotizaciones_por_ruta", "consultas_por_origen", "consultas_por_tipo",
                  "consultas_por_persona", "consultas_por_ruta"):
        assert all(set(p) == {"etiqueta", "valor"} for p in c[clave]), clave
    assert all(set(e) == {"momento", "tipo", "error"} for e in c["errores_buscador"])


def test_los_filtros_se_aplican_y_lo_invalido_se_ignora(cliente, viaje_aprobado):
    t = cliente.get(V1, params={"proyecto_id": 1, "desde": "2026-01-01", "hasta": "no-es-fecha"}).json()
    assert t["filtros"] == {"proyecto_id": 1, "desde": "2026-01-01", "hasta": None}
    assert any(p["id"] == 1 and p["nombre"] for p in t["proyectos"])
    # Un proyecto sin viajes deja sin datos lo que depende de viajes
    vacio = cliente.get(V1, params={"proyecto_id": 99999}).json()
    assert vacio["gastos"]["por_viaje"] == []


def test_el_tablero_es_solo_de_administracion(piloto, gestor, anonimo):
    _error(piloto.get(V1), 403, "FORBIDDEN")
    _error(gestor.get(V1), 403, "FORBIDDEN")
    _error(anonimo.get(V1), 401, "UNAUTHENTICATED")


# ---------- ficha por persona ----------
def test_la_ficha_de_una_persona_trae_su_linea_de_tiempo_y_deja_evento(cliente, viaje_aprobado):
    uid = _piloto_id()
    antes = db.uno("select coalesce(max(id), 0) m from eventos")["m"]
    r = cliente.get(f"{V1}/personas/{uid}")
    assert r.status_code == 200, r.text
    p = r.json()
    assert set(p) == {"usuario", "totales", "indicadores", "cotizaciones", "viajes", "gastos", "evidencias", "eventos",
                      "gastos_por_estado", "gastos_por_canal"}
    assert p["usuario"]["id"] == uid and p["usuario"]["codigo"] == f"P-{uid:04d}"
    assert "clave" not in p["usuario"] and "hash" not in str(p["usuario"])
    assert viaje_aprobado["id"] in {v["id"] for v in p["viajes"]}
    assert p["eventos"] and set(p["eventos"][0]) == {"momento", "entidad", "entidad_id", "paso", "detalle", "fuente", "quien"}
    assert {k["nombre"] for k in p["indicadores"]} == set(kpis.DE_PERSONA)
    nuevo = db.todos("select * from eventos where id>:a and entidad='kpis'", a=antes)
    assert any(e["paso"] == "ficha consultada" and e["entidad_id"] == uid for e in nuevo)


def test_la_ficha_de_alguien_que_no_existe_responde_404(cliente):
    _error(cliente.get(f"{V1}/personas/999999"), 404, "NOT_FOUND")


def test_la_ficha_es_solo_de_administracion(piloto, gestor, anonimo):
    uid = _piloto_id()
    # Ni siquiera la propia: la ficha es una herramienta de administración, como hoy
    _error(piloto.get(f"{V1}/personas/{uid}"), 403, "FORBIDDEN")
    _error(gestor.get(f"{V1}/personas/{uid}"), 403, "FORBIDDEN")
    _error(anonimo.get(f"{V1}/personas/{uid}"), 401, "UNAUTHENTICATED")


# ---------- exportación ----------
def test_exporta_los_indicadores_en_csv_con_los_filtros(cliente, viaje_aprobado):
    antes = db.uno("select coalesce(max(id), 0) m from eventos")["m"]
    r = cliente.get(f"{V1}/exportar.csv", params={"que": "kpis", "proyecto_id": 1})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="kpis_kpis.csv"' in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    filas = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    assert {f["nombre"] for f in filas} == set(kpis.KPIS)
    assert any(e["paso"] == "exportación" for e in db.todos("select * from eventos where id>:a and entidad='kpis'", a=antes))


def test_exporta_personas_y_consultas_y_rechaza_lo_desconocido(cliente, viaje_aprobado):
    assert cliente.get(f"{V1}/exportar.csv", params={"que": "personas"}).status_code == 200
    assert cliente.get(f"{V1}/exportar.csv", params={"que": "consultas"}).status_code == 200
    _error(cliente.get(f"{V1}/exportar.csv", params={"que": "usuarios"}), 422, "VALIDATION_ERROR")


def test_la_exportacion_es_solo_de_administracion(piloto, anonimo):
    _error(piloto.get(f"{V1}/exportar.csv", params={"que": "kpis"}), 403, "FORBIDDEN")
    _error(anonimo.get(f"{V1}/exportar.csv", params={"que": "kpis"}), 401, "UNAUTHENTICATED")


def test_la_pantalla_y_la_api_exportan_lo_mismo(cliente, viaje_aprobado):
    jinja = cliente.get("/admin/kpis/exportar.csv", params={"que": "personas"}).text
    v1 = cliente.get(f"{V1}/exportar.csv", params={"que": "personas"}).text
    assert jinja == v1


# ---------- valores imposibles (hallazgo M-20 del QA) ----------
def test_un_valor_negativo_donde_no_tiene_sentido_queda_fuera_de_rango():
    # −28 días del recibo a la carga (un recibo con fecha futura) no está «en meta» aunque sea menor que la meta
    assert kpis.estado(-28, "menor", 3, 10, kpis.RANGOS["dias_recibo_a_carga"]) == "fuera de rango"
    assert kpis.estado(-5, "mayor", 21, 7, kpis.RANGOS["anticipacion_compra"]) == "fuera de rango"
    # Una proporción no pasa de 100 %
    assert kpis.estado(130, "mayor", 60, 30, kpis.RANGOS["tasa_reutilizacion"]) == "fuera de rango"
    # El ahorro sí puede ser negativo: elegir algo más caro que lo más barato que sirve
    assert kpis.estado(-40, "mayor", 100, 0, kpis.RANGOS["ahorro_capturado"]) == "rojo"
    assert kpis.estado(2, "menor", 3, 10, kpis.RANGOS["dias_recibo_a_carga"]) == "verde"
    assert kpis.estado(None, "menor", 3, 10, kpis.RANGOS["dias_recibo_a_carga"]) == "sin datos"
    assert kpis.ESTADOS["fuera de rango"] == "Fuera de rango"


def test_el_tablero_y_la_tendencia_marcan_fuera_de_rango(cliente, monkeypatch):
    from app.servicios import metricas
    original = metricas.CATALOGO["dias_recibo_a_carga"]
    monkeypatch.setitem(metricas.CATALOGO, "dias_recibo_a_carga", (*original[:3], lambda f: -28))
    t = cliente.get(V1).json()
    k = next(x for x in t["kpis"] if x["nombre"] == "dias_recibo_a_carga")
    assert k["valor"] == -28 and k["estado"] == "fuera de rango" and k["estado_texto"] == "Fuera de rango"
    assert t["resumen"]["fuera_de_rango"] >= 1 and sum(t["resumen"].values()) == len(t["kpis"])
    fila = next(f for f in t["tendencia"]["filas"] if f["nombre"] == "dias_recibo_a_carga")
    assert all(p["estado"] == "fuera de rango" for p in fila["puntos"])
