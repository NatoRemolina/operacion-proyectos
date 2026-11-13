"""Escrituras detrás de CloudFront (infra/lib/web-stack.ts, H-69).

La política de solicitud al origen de `/api/v1/*` y de administración es AllViewerExceptHostHeader: a la función
llegan la cookie de sesión, Origin, Sec-Fetch-Site, X-CSRF-Token e Idempotency-Key tal como los mandó el
navegador, y Host pasa a ser el de la dirección de función. Estas pruebas fijan con `app/servicios/acceso.py` que
así una escritura pasa, y que si la política dejara fuera esas cabeceras daría 403.
"""
import pytest
from starlette.testclient import TestClient

from app import config
from app.main import app

WEB = "https://software.nataliaremolinarodriguez.com"
ADMIN = "https://admin.software.nataliaremolinarodriguez.com"
# Lo que pone CloudFront: Host de la dirección de función y sus propias cabeceras de paso
CLOUDFRONT = {"host": "abcdefghijklmnopqrstuvwxyz234567.lambda-url.us-east-1.on.aws",
              "via": "2.0 d111111abcdef8.cloudfront.net (CloudFront)", "x-amz-cf-id": "prueba", "x-forwarded-for": "203.0.113.7"}


def _navegador(origen: str) -> dict:
    """Lo que manda un navegador actual cuando la página escribe en su mismo origen."""
    return {"origin": origen, "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors"}


@pytest.fixture()
def sesion_web():
    """Una sesión propia abierta desde la web nueva a través de CloudFront (salir no toca las de los demás)."""
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"correo": "piloto@demo.local", "clave": "demo-piloto-2026"},
               headers={**CLOUDFRONT, **_navegador(WEB)})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def _salir(c: TestClient, cabeceras: dict):
    return c.post("/api/v1/auth/logout", headers={**CLOUDFRONT, **cabeceras})


def test_una_escritura_con_lo_que_reenvia_cloudfront_pasa(sesion_web):
    c, csrf = sesion_web
    assert _salir(c, {**_navegador(WEB), "x-csrf-token": csrf}).status_code == 204


def test_sin_sec_fetch_site_ni_origenes_web_da_403(sesion_web, monkeypatch):
    # Host ya no es el de la web: sin Sec-Fetch-Site el Origin no coincide con nada conocido
    monkeypatch.setattr(config, "ORIGENES_WEB", [])
    c, csrf = sesion_web
    r = _salir(c, {"origin": WEB, "x-csrf-token": csrf})
    assert r.status_code == 403 and r.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_con_origenes_web_basta_el_origin(sesion_web, monkeypatch):
    # Por eso ORIGENES_WEB lleva el dominio de la web: cubre a los navegadores que no mandan Sec-Fetch-Site
    monkeypatch.setattr(config, "ORIGENES_WEB", [WEB])
    c, csrf = sesion_web
    assert _salir(c, {"origin": WEB, "x-csrf-token": csrf}).status_code == 204


def test_sin_el_token_csrf_da_403(sesion_web):
    c, _ = sesion_web
    r = _salir(c, _navegador(WEB))
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_INVALID"


def test_sin_la_cookie_no_hay_sesion(sesion_web):
    c, csrf = sesion_web
    c.cookies.clear()
    assert _salir(c, {**_navegador(WEB), "x-csrf-token": csrf}).status_code == 401


def _entrar_en_administracion(cabeceras: dict):
    datos = {"correo": "admin@demo.local", "clave": "demo-admin-2026"}
    return TestClient(app).post("/entrar", data=datos, headers={**CLOUDFRONT, **cabeceras}, follow_redirects=False)


def test_un_formulario_de_administracion_con_sec_fetch_site_pasa():
    r = _entrar_en_administracion({"origin": ADMIN, "sec-fetch-site": "same-origin"})
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_un_formulario_de_administracion_sin_sec_fetch_site_da_403():
    # Las pantallas comparan Origin con Host, y detrás de CloudFront Host es el de la función
    assert _entrar_en_administracion({"origin": ADMIN}).status_code == 403
