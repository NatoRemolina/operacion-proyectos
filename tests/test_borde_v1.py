"""Borde de la API v1: categoría propia de acceso, errores en JSON, token CSRF y origen permitido.

Aún no hay endpoints de negocio en v1 (los añade su frente). Estas pruebas fijan el comportamiento común
con rutas inexistentes y con un endpoint de prueba que se registra solo durante la prueba.
"""
import pytest
from fastapi import APIRouter, Depends

from app import api_v1, config
from app.main import app
from app.servicios import acceso


def _contrato(r, estado, codigo):
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and "fields" in cuerpo["error"]
    assert cuerpo["request_id"] and cuerpo["request_id"] == r.headers["X-Peticion"]
    assert r.headers["Cache-Control"] == "no-store"
    return cuerpo


@pytest.fixture(scope="module")
def eco():
    """Endpoints de prueba: uno de lectura y uno de escritura, montados solo en este módulo."""
    router = APIRouter()

    @router.get("/api/v1/_prueba/yo")
    def yo(p: dict = Depends(api_v1.persona)):
        return {"id": p["id"], "rol": p["rol"]}

    @router.post("/api/v1/_prueba/escribir")
    def escribir(p: dict = Depends(api_v1.escritura)):
        return {"ok": True}

    @router.get("/api/v1/_prueba/numero/{n}")
    def numero(n: int, p: dict = Depends(api_v1.persona)):
        return {"n": n}

    antes = len(app.router.routes)
    app.include_router(router)
    yield
    del app.router.routes[antes:]


def test_la_api_v1_tiene_su_propia_categoria():
    assert acceso.nivel("/api/v1/gastos") == "api" and acceso.nivel("/api/v1") == "api"
    assert acceso.nivel("/api/v1/auth/login") == "publica"
    assert acceso.nivel("/api/gastos") == "admin" and acceso.nivel("/api/v1x") == "admin"   # lo de antes no cambia


def test_sin_sesion_responde_401_en_json(anonimo, eco):
    _contrato(anonimo.get("/api/v1/_prueba/yo"), 401, "UNAUTHENTICATED")
    _contrato(anonimo.get("/api/v1/no-existe"), 401, "UNAUTHENTICATED")   # sin sesión no se revela qué existe


def test_con_sesion_los_errores_del_marco_salen_en_json(piloto, eco):
    assert piloto.get("/api/v1/_prueba/yo").json()["rol"] == "piloto"     # un piloto entra: no es solo administración
    _contrato(piloto.get("/api/v1/no-existe"), 404, "NOT_FOUND")
    cuerpo = _contrato(piloto.get("/api/v1/_prueba/numero/abc"), 422, "VALIDATION_ERROR")
    assert cuerpo["error"]["fields"]


def test_escribir_exige_token_csrf_y_origen(piloto, eco):
    _contrato(piloto.post("/api/v1/_prueba/escribir"), 403, "CSRF_INVALID")
    token = api_v1.token_csrf(piloto.cookies.get(acceso.COOKIE))
    assert piloto.post("/api/v1/_prueba/escribir", headers={"X-CSRF-Token": "otro"}).status_code == 403
    assert piloto.post("/api/v1/_prueba/escribir", headers={"X-CSRF-Token": token}).json() == {"ok": True}
    ajeno = {"X-CSRF-Token": token, "Origin": "https://sitio-ajeno.example", "Sec-Fetch-Site": "cross-site"}
    _contrato(piloto.post("/api/v1/_prueba/escribir", headers=ajeno), 403, "ORIGIN_NOT_ALLOWED")


def test_un_origen_declarado_puede_escribir(piloto, eco, monkeypatch):
    monkeypatch.setattr(config, "ORIGENES_WEB", ["http://localhost:8080"])
    token = api_v1.token_csrf(piloto.cookies.get(acceso.COOKIE))
    cabeceras = {"X-CSRF-Token": token, "Origin": "http://localhost:8080", "Sec-Fetch-Site": "same-site"}
    assert piloto.post("/api/v1/_prueba/escribir", headers=cabeceras).status_code == 200


def test_el_token_csrf_no_es_la_huella_guardada(piloto):
    token = piloto.cookies.get(acceso.COOKIE)
    assert api_v1.token_csrf(token) != acceso.huella(token) and len(api_v1.token_csrf(token)) == 64


def test_las_pantallas_siguen_con_paginas_y_no_con_json(piloto, cliente):
    r = piloto.get("/ruta-que-no-existe")
    assert r.status_code == 404 and "Volver al inicio" in r.text
    r = cliente.get("/viaje/abc")
    assert r.status_code == 422 and "Volver al inicio" in r.text
    assert piloto.get("/api/gastos").status_code == 403            # la API anterior sigue siendo solo de administración
