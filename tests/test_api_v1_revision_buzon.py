"""API v1, buzón de correo simulado: administración lee los correos (.eml) y las confirmaciones en HTML de la carpeta
de ejemplos como si llegaran a un buzón de gastos. Es una simulación: no hay ningún correo real detrás.

Las lecturas salen de las lecturas guardadas de `datos/ejemplos` (sin modelo de lenguaje en las pruebas).
"""
import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso

V1 = "/api/v1"
CORREOS = sorted(p.name for p in config.DIR_EJEMPLOS.iterdir() if p.suffix in (".eml", ".html"))


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    assert r.headers["Cache-Control"] == "no-store"
    return cuerpo


def _leer(c: TestClient, cabeceras: dict | None = None, **cuerpo):
    return c.post(f"{V1}/buzon/lectura", json=cuerpo, headers=_csrf(c) if cabeceras is None else cabeceras)


@pytest.fixture(autouse=True, scope="module")
def _sin_rastro():
    """Los correos leídos aquí no deben volver «duplicados» los que leen otras pruebas después."""
    antes = db.uno("select coalesce(max(id), 0) n from gastos")["n"]
    documentos = db.uno("select coalesce(max(id), 0) n from documentos")["n"]
    yield
    db.ejecutar("delete from eventos where entidad='gasto' and entidad_id>:n", n=antes)
    db.ejecutar("delete from gastos where id>:n", n=antes)
    db.ejecutar("delete from documentos where id>:n", n=documentos)


# ---------- acceso ----------
def test_el_buzon_es_solo_de_administracion(anonimo, piloto, gestor):
    _error(anonimo.get(f"{V1}/buzon"), 401, "UNAUTHENTICATED")
    _error(anonimo.post(f"{V1}/buzon/lectura", json={"nombres": CORREOS[:1]}), 401, "UNAUTHENTICATED")
    for c in (piloto, gestor):
        _error(c.get(f"{V1}/buzon"), 403, "FORBIDDEN")
        _error(_leer(c, nombres=CORREOS[:1]), 403, "FORBIDDEN")


def test_leer_exige_csrf_y_un_origen_permitido(cliente):
    _error(_leer(cliente, cabeceras={}, nombres=CORREOS[:1]), 403, "CSRF_INVALID")
    _error(_leer(cliente, cabeceras={**_csrf(cliente), "Origin": "https://sitio-ajeno.example"}, nombres=CORREOS[:1]),
           403, "ORIGIN_NOT_ALLOWED")


# ---------- lo que hay en el buzón ----------
def test_el_buzon_dice_que_es_simulado_y_lista_los_correos_de_ejemplo(cliente, viaje_aprobado):
    r = cliente.get(f"{V1}/buzon")
    assert r.status_code == 200, r.text
    assert r.headers["Cache-Control"] == "no-store"
    buzon = r.json()
    assert buzon["simulado"] is True and "simulado" in buzon["aviso"].lower()
    assert [m["nombre"] for m in buzon["mensajes"]] == CORREOS
    eml = next(m for m in buzon["mensajes"] if m["nombre"].endswith(".eml"))
    assert eml["formato"] == "correo" and eml["remitente"] and eml["asunto"]
    html = next(m for m in buzon["mensajes"] if m["nombre"].endswith(".html"))
    assert html["formato"] == "html" and html["remitente"] is None
    assert viaje_aprobado["id"] in {v["id"] for v in buzon["viajes"]}


# ---------- leer ----------
def test_leer_carga_los_correos_al_viaje_por_el_canal_correo(cliente, viaje_aprobado):
    r = _leer(cliente, nombres=["reserva_hotel.eml", "confirmacion_hotel.html"], viaje_id=viaje_aprobado["id"])
    assert r.status_code == 200, r.text
    resultado = r.json()
    assert resultado["errores"] == [] and len(resultado["leidos"]) == 2
    for g in resultado["leidos"]:
        assert g["estado"] in ("aprobado_auto", "revision") and g["viaje"]["id"] == viaje_aprobado["id"]
        detalle = cliente.get(f"{V1}/gastos/{g['id']}").json()
        assert detalle["canal"] == "correo" and detalle["propio"] is False   # es del viaje del piloto: administración lo revisa
    eml = cliente.get(f"{V1}/gastos/{resultado['leidos'][0]['id']}").json()
    assert eml["correo"]["remitente"]


def test_lo_que_no_esta_en_el_buzon_no_se_lee(cliente):
    antes = db.uno("select coalesce(max(id), 0) n from gastos")["n"]
    r = _leer(cliente, nombres=["../../app/config.py", "recibo_lisboa.png", "no_existe.eml"])
    assert r.status_code == 200, r.text
    assert r.json()["leidos"] == [] and len(r.json()["errores"]) == 3
    assert all(e["mensaje"] for e in r.json()["errores"])
    assert db.uno("select coalesce(max(id), 0) n from gastos")["n"] == antes


def test_datos_invalidos_responden_422(cliente):
    _error(_leer(cliente, nombres=[]), 422, "VALIDATION_ERROR")
    cuerpo = _error(_leer(cliente, nombres=CORREOS[:1], viaje_id=999_999), 422, "VALIDATION_ERROR")
    assert "viaje_id" in cuerpo["error"]["fields"]
