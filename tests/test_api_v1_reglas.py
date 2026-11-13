"""API v1, reglas y supuestos: el catálogo agrupado por ámbito y la edición de un valor, solo para administración.

La validación vive en `app/servicios/reglas.py` y es la misma para la pantalla de administración (`/reglas`) y la API:
una regla numérica sigue siendo numérica.
"""
from datetime import date

import pytest
from starlette.testclient import TestClient

from app import api_v1, db
from app.servicios import acceso

V1 = "/api/v1"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    assert r.headers["Cache-Control"] == "no-store"
    return cuerpo


def _editar(c: TestClient, rid: int, valor: str, cabeceras: dict | None = None):
    return c.post(f"{V1}/reglas/{rid}", json={"valor": valor}, headers=_csrf(c) if cabeceras is None else cabeceras)


def _regla(ambito: str, clave: str) -> dict:
    return db.uno("select * from reglas where ambito=:a and clave=:c order by id limit 1", a=ambito, c=clave)


@pytest.fixture(autouse=True)
def _sin_rastro():
    """Las reglas las usan otras pruebas: cada prueba deja los valores como estaban."""
    antes = {r["id"]: (r["valor"], r["verificado"]) for r in db.todos("select id, valor, verificado from reglas")}
    yield
    for rid, (valor, verificado) in antes.items():
        db.ejecutar("update reglas set valor=:v, verificado=:f where id=:i", v=valor, f=verificado, i=rid)


@pytest.fixture()
def numerica() -> dict:
    return _regla("supuesto", "tolerancia_presupuesto")


@pytest.fixture()
def de_texto() -> dict:
    regla = db.uno("select * from reglas where ambito='aerolinea' order by id limit 1")
    assert regla and not regla["valor"].replace(".", "").isdigit()
    return regla


# ---------- acceso ----------
def test_las_reglas_son_solo_de_administracion(anonimo, piloto, gestor, numerica):
    _error(anonimo.get(f"{V1}/reglas"), 401, "UNAUTHENTICATED")
    _error(anonimo.post(f"{V1}/reglas/{numerica['id']}", json={"valor": "1"}), 401, "UNAUTHENTICATED")
    for c in (piloto, gestor):
        _error(c.get(f"{V1}/reglas"), 403, "FORBIDDEN")
        _error(_editar(c, numerica["id"], "0.5"), 403, "FORBIDDEN")
    assert _regla("supuesto", "tolerancia_presupuesto")["valor"] == numerica["valor"]


def test_editar_exige_csrf_y_un_origen_permitido(cliente, numerica):
    _error(_editar(cliente, numerica["id"], "0.5", cabeceras={}), 403, "CSRF_INVALID")
    _error(_editar(cliente, numerica["id"], "0.5", cabeceras={**_csrf(cliente), "Origin": "https://sitio-ajeno.example"}),
           403, "ORIGIN_NOT_ALLOWED")
    assert _regla("supuesto", "tolerancia_presupuesto")["valor"] == numerica["valor"]


def test_una_regla_que_no_existe_responde_404(cliente):
    _error(_editar(cliente, 999_999, "1"), 404, "NOT_FOUND")


# ---------- catálogo ----------
def test_el_catalogo_va_agrupado_por_ambito(cliente):
    r = cliente.get(f"{V1}/reglas")
    assert r.status_code == 200, r.text
    assert r.headers["Cache-Control"] == "no-store"
    grupos = {g["clave"]: g for g in r.json()["grupos"]}
    assert {"aerolinea", "hotel", "supuesto", "kpi", "cuenta_contable", "bateria"} <= set(grupos)
    assert [g["clave"] for g in r.json()["grupos"]][:2] == ["aerolinea", "hotel"]
    assert all(g["titulo"] and g["reglas"] for g in grupos.values())
    # Las cuentas contables son supuestos con su propio grupo: no se repiten entre los supuestos
    assert all(x["clave"].startswith("cuenta_contable_") for x in grupos["cuenta_contable"]["reglas"])
    assert not any(x["clave"].startswith("cuenta_contable_") for x in grupos["supuesto"]["reglas"])
    total = sum(len(g["reglas"]) for g in grupos.values())
    assert total == db.uno("select count(*) n from reglas")["n"]


def test_cada_regla_trae_valor_nota_fuente_confianza_y_si_es_numerica(cliente, numerica, de_texto):
    reglas = {x["id"]: x for g in cliente.get(f"{V1}/reglas").json()["grupos"] for x in g["reglas"]}
    x = reglas[numerica["id"]]
    assert set(x) == {"id", "ambito", "entidad", "tarifa", "clave", "valor", "numerica", "nota", "fuente", "confianza", "verificado"}
    assert x["valor"] == numerica["valor"] and x["numerica"] is True and x["confianza"] == numerica["confianza"]
    assert reglas[de_texto["id"]]["numerica"] is False and reglas[de_texto["id"]]["fuente"] == de_texto["fuente"]


def test_las_membresias_van_en_solo_lectura_con_el_dato_de_ejemplo(cliente):
    membresias = cliente.get(f"{V1}/reglas").json()["membresias"]
    assert len(membresias) == db.uno("select count(*) n from membresias")["n"]
    assert set(membresias[0]) == {"id", "titular", "de_empresa", "programa", "entidad", "estatus", "ejemplo"}
    empresa = [m for m in membresias if m["de_empresa"]]
    assert empresa and all(m["titular"] == "Empresa" for m in empresa)
    assert any(m["ejemplo"] for m in membresias)


# ---------- edición ----------
def test_una_regla_numerica_acepta_coma_decimal_y_deja_el_evento(cliente, numerica):
    r = _editar(cliente, numerica["id"], " 0,25 ")
    assert r.status_code == 200, r.text
    assert r.json()["valor"] == "0.25" and r.json()["verificado"] == date.today().isoformat()
    assert _regla("supuesto", "tolerancia_presupuesto")["valor"] == "0.25"
    evento = db.uno("select * from eventos where entidad='regla' and entidad_id=:i order by id desc limit 1", i=numerica["id"])
    assert evento["paso"] == "regla editada" and evento["detalle"] == f"tolerancia_presupuesto: {numerica['valor']} → 0.25"
    assert evento["fuente"]


@pytest.mark.parametrize("valor", ["80 USD", "-1", "nan", "inf", ""])
def test_una_regla_numerica_sigue_siendo_numerica(cliente, numerica, valor):
    eventos = db.uno("select count(*) n from eventos where entidad='regla' and entidad_id=:i", i=numerica["id"])["n"]
    cuerpo = _error(_editar(cliente, numerica["id"], valor), 422, "VALIDATION_ERROR")
    assert "número" in cuerpo["error"]["fields"]["valor"]
    assert _regla("supuesto", "tolerancia_presupuesto")["valor"] == numerica["valor"]
    assert db.uno("select count(*) n from eventos where entidad='regla' and entidad_id=:i", i=numerica["id"])["n"] == eventos


def test_una_regla_de_texto_guarda_el_texto(cliente, de_texto):
    r = _editar(cliente, de_texto["id"], "  sí, en rutas nacionales  ")
    assert r.status_code == 200, r.text
    assert r.json()["valor"] == "sí, en rutas nacionales" and r.json()["numerica"] is False


def test_un_valor_demasiado_largo_se_rechaza(cliente, de_texto):
    _error(_editar(cliente, de_texto["id"], "x" * 501), 422, "VALIDATION_ERROR")


# ---------- la pantalla de administración usa la misma regla ----------
def test_la_pantalla_de_reglas_valida_igual_que_la_api(cliente, numerica):
    r = cliente.post(f"/reglas/{numerica['id']}", data={"valor": "nan"}, follow_redirects=False)
    assert r.status_code == 303 and "no%20es%20un%20n%C3%BAmero" in r.headers["location"]
    assert _regla("supuesto", "tolerancia_presupuesto")["valor"] == numerica["valor"]
    r = cliente.post(f"/reglas/{numerica['id']}", data={"valor": "0,3"}, follow_redirects=False)
    assert r.status_code == 303 and "Regla%20guardada" in r.headers["location"]
    assert _regla("supuesto", "tolerancia_presupuesto")["valor"] == "0.3"
    assert "tolerancia_presupuesto" in cliente.get("/reglas").text
