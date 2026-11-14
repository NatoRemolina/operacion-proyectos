"""Defensa del ingreso: límite de intentos por dirección y por correo (tabla y ventana, 429), y en la nube solo entra lo
que llega por CloudFront con la cabecera secreta `X-Origen-CloudFront` (lo demás, 403)."""
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from app import config, db
from app.main import app
from app.servicios import acceso, intentos

V1 = "/api/v1"
SECRETO = "s" * 48


def _cliente(direccion: str | None = None) -> TestClient:
    return TestClient(app, client=(direccion or f"198.51.100.{uuid.uuid4().int % 250 + 1}", 50000))


def _cuenta() -> tuple[str, str]:
    correo, clave = f"ingreso-{uuid.uuid4().hex[:8]}@demo.local", "clave-de-ingreso-2026"
    acceso.crear_usuario(correo, "Iginio Zipaquirá", "colaborador", clave)
    return correo, clave


def _login(c: TestClient, correo: str, clave: str, **cabeceras):
    return c.post(f"{V1}/auth/login", json={"correo": correo, "clave": clave}, headers=cabeceras)


@pytest.fixture(autouse=True)
def _ventana_limpia():
    db.ejecutar("delete from intentos_ingreso")
    yield
    db.ejecutar("delete from intentos_ingreso")


# ---------- límite de intentos ----------
def test_demasiados_fallos_con_un_correo_responden_429_aunque_no_exista_la_cuenta():
    """El bloqueo de cada cuenta no cubre los correos que no existen; este límite sí."""
    correo = f"no-existe-{uuid.uuid4().hex[:8]}@demo.local"
    for _ in range(intentos.MAX_POR_CORREO):
        assert _login(_cliente(), correo, "equivocada-123").status_code == 401   # desde direcciones distintas
    r = _login(_cliente(), correo, "equivocada-123")
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS", r.text
    assert r.json()["error"]["message"] == intentos.DEMASIADOS


def test_con_el_correo_limitado_ni_la_clave_buena_entra_y_no_se_mira():
    correo, clave = _cuenta()
    for i in range(intentos.MAX_POR_CORREO):
        intentos.anotar_fallo(f"198.51.100.{i}", correo)
    r = _login(_cliente(), correo, clave)
    assert r.status_code == 429 and r.json()["error"]["message"] == intentos.DEMASIADOS
    assert db.uno("select fallos from usuarios where correo=:c", c=correo)["fallos"] in (0, None)   # no se verificó la clave
    otro, clave_otro = _cuenta()
    assert _login(_cliente(), otro, clave_otro).status_code == 200   # otra cuenta no queda limitada


def test_demasiados_fallos_desde_una_direccion_responden_429_para_cualquier_correo():
    c = _cliente("203.0.113.40")
    for i in range(intentos.MAX_POR_DIRECCION):
        assert _login(c, f"no-existe-{i}@demo.local", "equivocada-123").status_code == 401
    correo, clave = _cuenta()
    assert _login(c, correo, clave).status_code == 429
    assert _login(_cliente("203.0.113.41"), correo, clave).status_code == 200   # desde otra dirección, sí


def test_los_fallos_viejos_salen_de_la_ventana():
    correo, clave = _cuenta()
    viejo = (datetime.now(UTC) - intentos.VENTANA - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    for _ in range(intentos.MAX_POR_CORREO):
        db.insertar("intentos_ingreso", clave=intentos.clave_correo(correo), momento=viejo)
    assert _login(_cliente(), correo, clave).status_code == 200


def test_un_ingreso_bueno_borra_los_fallos_de_su_correo():
    correo, clave = _cuenta()
    for i in range(intentos.MAX_POR_CORREO - 1):
        intentos.anotar_fallo(f"198.51.100.{i}", correo)
    assert _login(_cliente(), correo, clave).status_code == 200
    assert db.uno("select count(*) n from intentos_ingreso where clave=:c", c=intentos.clave_correo(correo))["n"] == 0


def test_el_formulario_de_ingreso_tambien_limita():
    correo, clave = _cuenta()
    c = _cliente()
    for _ in range(intentos.MAX_POR_DIRECCION):
        c.post("/entrar", data={"correo": f"no-existe-{uuid.uuid4().hex[:6]}@demo.local", "clave": "x"}, follow_redirects=False)
    r = c.post("/entrar", data={"correo": correo, "clave": clave}, follow_redirects=False)
    assert r.status_code == 429 and "intentos" in r.text


def test_la_tabla_no_guarda_ni_el_correo_ni_la_direccion():
    _login(_cliente("203.0.113.77"), "alguien@demo.local", "equivocada-123")
    filas = db.todos("select clave from intentos_ingreso")
    assert len(filas) == 2 and all("alguien" not in f["clave"] and "203.0.113" not in f["clave"] for f in filas)


# ---------- la cabecera secreta de CloudFront ----------
@pytest.fixture()
def en_la_nube(monkeypatch):
    monkeypatch.setattr(config, "LOCAL", False)
    monkeypatch.setattr(config, "ORIGEN_SECRETO", SECRETO)


def test_en_la_nube_lo_que_llega_directo_a_la_funcion_se_rechaza(en_la_nube):
    c = TestClient(app)
    for ruta in ("/salud", "/entrar", f"{V1}/auth/me"):
        assert c.get(ruta).status_code == 403, ruta
        assert c.get(ruta, headers={"X-Origen-CloudFront": "otra-cosa"}).status_code == 403, ruta
    r = c.get(f"{V1}/auth/me")
    assert r.json()["error"]["code"] == "FORBIDDEN"   # la API responde con su contrato
    assert c.get("/salud", headers={"X-Origen-CloudFront": SECRETO}).status_code == 200


def test_en_la_nube_el_webhook_de_telegram_entra_directo_con_su_propio_secreto(en_la_nube, monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", "secreto-de-pruebas")
    r = TestClient(app).post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "otro"})
    assert r.status_code == 403   # lo rechaza su propio secreto, no la cabecera de CloudFront
    assert r.text != TestClient(app).get("/salud").text


def test_detras_de_cloudfront_la_direccion_es_la_del_visitante(en_la_nube):
    """La dirección que cuenta es la que pone CloudFront; la de la conexión es la de CloudFront."""
    c = TestClient(app, client=("10.0.0.1", 1))
    cabeceras = {"X-Origen-CloudFront": SECRETO, "CloudFront-Viewer-Address": "192.0.2.10:443"}
    for i in range(intentos.MAX_POR_DIRECCION):
        _login(c, f"nadie-{i}@demo.local", "equivocada-123", **cabeceras)
    assert _login(c, "nadie@demo.local", "equivocada-123", **{**cabeceras, "CloudFront-Viewer-Address": "192.0.2.11:443"}).status_code == 401
    assert _login(c, "nadie@demo.local", "equivocada-123", **cabeceras).status_code == 429


def test_en_local_no_hace_falta_la_cabecera():
    assert TestClient(app).get("/salud").status_code == 200


def test_en_la_nube_sin_el_secreto_queda_como_problema_de_configuracion():
    entorno = {**os.environ, "ENTORNO": "nube", "DATABASE_URL": "postgresql://db.invalid:5432/x", "SUPABASE_URL": "https://x.invalid",
               "SUPABASE_SERVICE_KEY": "k", "ORIGEN_SECRETO": "", "SECRETO_ARN": ""}
    salida = subprocess.run([sys.executable, "-c", "from app import config; print(config.PROBLEMAS)"], env=entorno,  # noqa: S603  orden fija
                            capture_output=True, text=True, cwd=config.RAIZ, check=True).stdout
    assert "ORIGEN_SECRETO" in salida
