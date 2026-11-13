"""API v1 de proyectos: lista con previsto frente a real, alta y edición (administración) y tablero por proyecto.

Contrato en `contracts/api-v1.md`, sección «Proyectos». Los permisos son los de las pantallas actuales:
administración ve y edita todos; quien gestiona ve el tablero de los suyos; el resto no ve ninguno.
"""
import csv
import io
import re
import uuid
from decimal import Decimal

from starlette.testclient import TestClient

from app import api_v1, db
from app.servicios import acceso, viajes

V1 = "/api/v1"
DINERO = re.compile(r"^-?\d+\.\d{2}$")
CAMPOS = dict(nombre="Torre Sur (aéreo)", cliente="Constructora de prueba", ciudad="Denver", fecha_inicio="2026-12-15",
              fecha_fin="2026-12-18", moneda="usd")


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    assert r.headers["cache-control"] == "no-store"
    return cuerpo["error"]


def _nombre(base: str) -> str:
    return f"{base} {uuid.uuid4().hex[:6]}"


def _crear(cliente: TestClient, **cambios) -> dict:
    r = cliente.post(f"{V1}/proyectos", json={**CAMPOS, "nombre": _nombre("Torre"), **cambios}, headers=_csrf(cliente))
    assert r.status_code == 201, r.text
    return r.json()


# ---------- acceso ----------
def test_sin_sesion_responde_401(anonimo):
    for ruta in ("/proyectos", "/proyectos/1", "/proyectos/1/exportar.csv"):
        _error(anonimo.get(V1 + ruta), 401, "UNAUTHENTICATED")
    _error(anonimo.post(f"{V1}/proyectos", json=CAMPOS), 401, "UNAUTHENTICATED")


def test_la_lista_es_para_administracion_y_quien_gestiona(cliente, gestor, piloto):
    todos = {p["id"] for p in cliente.get(f"{V1}/proyectos", params={"limite": 100}).json()["items"]}
    assert {1, 2} <= todos
    r = gestor.get(f"{V1}/proyectos")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert {p["id"] for p in r.json()["items"]} == acceso.proyectos_de(db.uno("select id from usuarios where correo='gestor@demo.local'"))
    _error(piloto.get(f"{V1}/proyectos"), 403, "FORBIDDEN")


def test_el_tablero_solo_lo_ve_administracion_o_quien_gestiona_el_proyecto(cliente, gestor, piloto):
    assert cliente.get(f"{V1}/proyectos/2").status_code == 200
    assert gestor.get(f"{V1}/proyectos/1").status_code == 200
    _error(gestor.get(f"{V1}/proyectos/2"), 404, "NOT_FOUND")      # lo ajeno responde como si no existiera
    _error(piloto.get(f"{V1}/proyectos/1"), 404, "NOT_FOUND")
    _error(cliente.get(f"{V1}/proyectos/999999"), 404, "NOT_FOUND")
    _error(gestor.get(f"{V1}/proyectos/2/exportar.csv"), 404, "NOT_FOUND")
    _error(piloto.get(f"{V1}/proyectos/1/exportar.csv"), 404, "NOT_FOUND")


def test_crear_y_editar_son_solo_de_administracion(gestor, piloto):
    for c in (gestor, piloto):
        _error(c.post(f"{V1}/proyectos", json=CAMPOS, headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/proyectos/1", json=CAMPOS, headers=_csrf(c)), 403, "FORBIDDEN")
    assert not db.uno("select id from proyectos where nombre=:n", n=CAMPOS["nombre"])


def test_escribir_exige_token_csrf_y_origen(cliente):
    _error(cliente.post(f"{V1}/proyectos", json=CAMPOS), 403, "CSRF_INVALID")
    _error(cliente.post(f"{V1}/proyectos", json=CAMPOS, headers={"X-CSRF-Token": "otro"}), 403, "CSRF_INVALID")
    ajeno = {**_csrf(cliente), "Origin": "https://sitio-ajeno.example", "Sec-Fetch-Site": "cross-site"}
    _error(cliente.post(f"{V1}/proyectos", json=CAMPOS, headers=ajeno), 403, "ORIGIN_NOT_ALLOWED")
    _error(cliente.post(f"{V1}/proyectos/1", json=CAMPOS), 403, "CSRF_INVALID")
    assert not db.uno("select id from proyectos where nombre=:n", n=CAMPOS["nombre"])


# ---------- alta y edición ----------
def test_administracion_crea_un_proyecto_y_queda_el_evento(cliente):
    nombre = _nombre("Torre Sur")
    p = _crear(cliente, nombre=nombre)
    assert p["nombre"] == nombre and p["moneda"] == "USD" and p["ciudad"] == "Denver"
    assert p["fecha_inicio"] == "2026-12-15" and p["fecha_fin"] == "2026-12-18"
    assert p["viajes"] == 0 and p["gastos"] == 0
    assert p["previsto_usd"] == "0.00" and p["real_usd"] == "0.00" and p["diferencia_usd"] == "0.00"
    fila = db.uno("select * from proyectos where id=:i", i=p["id"])
    assert fila["nombre"] == nombre and fila["cliente"] == "Constructora de prueba"
    evento = db.uno("select * from eventos where entidad='proyecto' and entidad_id=:i", i=p["id"])
    assert evento["paso"] == "proyecto creado" and evento["fuente"] == "Administración (demo)"


def test_administracion_edita_un_proyecto(cliente):
    p = _crear(cliente)
    r = cliente.post(f"{V1}/proyectos/{p['id']}", json={**CAMPOS, "nombre": p["nombre"], "ciudad": "Boulder", "cliente": ""},
                     headers=_csrf(cliente))
    assert r.status_code == 200, r.text
    assert r.json()["ciudad"] == "Boulder" and r.json()["cliente"] is None
    assert db.uno("select ciudad from proyectos where id=:i", i=p["id"])["ciudad"] == "Boulder"
    acciones = [e["paso"] for e in db.todos("select paso from eventos where entidad='proyecto' and entidad_id=:i order by id", i=p["id"])]
    assert acciones == ["proyecto creado", "proyecto editado"]
    _error(cliente.post(f"{V1}/proyectos/999999", json=CAMPOS, headers=_csrf(cliente)), 404, "NOT_FOUND")


def test_datos_invalidos_responden_422_con_el_campo_y_no_se_guardan(cliente):
    casos = {"nombre": {"nombre": "ab"}, "fecha_fin": {"fecha_fin": "2026-12-01"}, "fecha_inicio": {"fecha_inicio": "15/12/2026"},
             "moneda": {"moneda": "dólar"}}
    for campo, cambio in casos.items():
        nombre = _nombre("Inválido")
        datos = {**CAMPOS, "nombre": nombre, **cambio}
        error = _error(cliente.post(f"{V1}/proyectos", json=datos, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
        assert campo in error["fields"], (campo, error)
        assert not db.uno("select id from proyectos where nombre=:n", n=datos["nombre"])
    p = _crear(cliente)
    error = _error(cliente.post(f"{V1}/proyectos/{p['id']}", json={**CAMPOS, "fecha_fin": "2026-12-01"}, headers=_csrf(cliente)),
                   422, "VALIDATION_ERROR")
    assert "fecha_fin" in error["fields"]
    assert db.uno("select fecha_fin from proyectos where id=:i", i=p["id"])["fecha_fin"] == "2026-12-18"


def test_campos_de_mas_no_se_aceptan(cliente):
    error = _error(cliente.post(f"{V1}/proyectos", json={**CAMPOS, "id": 1}, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
    assert error["fields"]


def test_la_pantalla_actual_sigue_validando_igual(cliente):
    """La ruta de las pantallas llama al mismo servicio: el mismo mensaje y nada se guarda."""
    nombre = _nombre("Jinja")
    r = cliente.post("/admin/proyectos", data={**CAMPOS, "nombre": nombre, "fecha_fin": "2026-12-01"}, follow_redirects=False)
    assert "anterior%20a%20la%20inicial" in r.headers["location"]
    assert not db.uno("select id from proyectos where nombre=:n", n=nombre)


# ---------- tablero ----------
def test_el_tablero_trae_previsto_real_diferencia_viajes_y_gastos(cliente, viaje_aprobado):
    r = cliente.get(f"{V1}/proyectos/1")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    t = r.json()
    assert set(t) == {"proyecto", "categorias", "previsto_usd", "real_usd", "diferencia_usd", "en_revision", "faltantes",
                      "viajes", "gastos", "periodo_contable"}
    assert t["proyecto"]["id"] == 1
    for campo in ("previsto_usd", "real_usd", "diferencia_usd"):
        assert DINERO.match(t[campo])
    assert Decimal(t["diferencia_usd"]) == Decimal(t["real_usd"]) - Decimal(t["previsto_usd"])
    # El previsto es el presupuesto de los viajes del proyecto que no se rechazaron (la misma cifra de la pantalla actual)
    del_proyecto = viajes.lista("v.proyecto_id=1 and v.estado<>'rechazado'")
    assert Decimal(t["previsto_usd"]) == Decimal(str(round(sum(v["presupuesto_usd"] or 0 for v in del_proyecto), 2))).quantize(Decimal("0.01"))
    assert {v["id"] for v in t["viajes"]} == {v["id"] for v in del_proyecto}
    assert viaje_aprobado["id"] in {v["id"] for v in t["viajes"]}
    for c in t["categorias"]:
        assert set(c) == {"clave", "nombre", "previsto_usd", "real_usd", "diferencia_usd"}
        assert Decimal(c["diferencia_usd"]) == Decimal(c["real_usd"]) - Decimal(c["previsto_usd"])
    assert sum(Decimal(c["previsto_usd"]) for c in t["categorias"]) == Decimal(t["previsto_usd"])
    gastos = db.todos("select id from gastos where proyecto_id=1")
    assert {g["id"] for g in t["gastos"]} == {g["id"] for g in gastos}
    assert t["en_revision"] == db.uno("select count(*) n from gastos where proyecto_id=1 and estado='revision'")["n"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", t["periodo_contable"]["desde"]) and re.match(r"^\d{4}-\d{2}-\d{2}$", t["periodo_contable"]["hasta"])


def test_la_lista_y_el_tablero_dan_las_mismas_cifras(cliente, viaje_aprobado):
    lista = {p["id"]: p for p in cliente.get(f"{V1}/proyectos", params={"limite": 100}).json()["items"]}
    t = cliente.get(f"{V1}/proyectos/1").json()
    for campo in ("previsto_usd", "real_usd", "diferencia_usd"):
        assert lista[1][campo] == t[campo]
    assert lista[1]["viajes"] == db.uno("select count(*) n from viajes where proyecto_id=1")["n"]
    assert lista[1]["gastos"] == db.uno("select count(*) n from gastos where proyecto_id=1")["n"]


def test_el_gestor_ve_el_mismo_tablero_que_administracion(cliente, gestor, viaje_aprobado):
    assert gestor.get(f"{V1}/proyectos/1").json() == cliente.get(f"{V1}/proyectos/1").json()


def test_la_lista_pagina_por_cursor(cliente):
    for _ in range(2):
        _crear(cliente)
    primera = cliente.get(f"{V1}/proyectos", params={"limite": 1}).json()
    assert len(primera["items"]) == 1 and primera["siguiente"]
    segunda = cliente.get(f"{V1}/proyectos", params={"limite": 1, "cursor": primera["siguiente"]}).json()
    assert segunda["items"][0]["id"] < primera["items"][0]["id"]


# ---------- exportar ----------
def test_el_csv_del_proyecto_es_el_de_la_pantalla_actual(cliente, gestor, viaje_aprobado):
    r = gestor.get(f"{V1}/proyectos/1/exportar.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="gastos_proyecto_1.csv"' in r.headers["content-disposition"]
    assert r.text == cliente.get("/proyectos/1/exportar.csv").text
    filas = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    assert filas[0][:4] == ["id", "fecha", "comercio", "categoria"]
    assert len(filas) - 1 == db.uno("select count(*) n from gastos where proyecto_id=1")["n"]


# ---------- ronda de arreglos menores ----------
def test_el_csv_de_la_pantalla_actual_no_se_guarda_en_cache(cliente):
    assert cliente.get("/proyectos/1/exportar.csv").headers.get("cache-control") == "no-store"


def test_la_lista_no_hace_consultas_por_cada_proyecto(cliente):
    from sqlalchemy import event
    for _ in range(6):
        _crear(cliente)
    consultas: list[str] = []

    def contar(conn, cursor, sql, *a):
        consultas.append(sql)

    event.listen(db.motor, "before_cursor_execute", contar)
    try:
        cliente.get(f"{V1}/proyectos", params={"limite": 1})
        una = len(consultas)
        consultas.clear()
        cliente.get(f"{V1}/proyectos", params={"limite": 7})
        siete = len(consultas)
    finally:
        event.remove(db.motor, "before_cursor_execute", contar)
    assert siete <= una + 1, (una, siete)
