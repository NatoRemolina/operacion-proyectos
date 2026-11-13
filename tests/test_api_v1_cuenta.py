"""API v1 de la cuenta propia: mis datos, cambiar mi contraseña y el estado de Telegram.

Contrato en `contracts/api-v1.md`, sección «Mi cuenta». Cada persona ve y cambia solo lo suyo: la cuenta sale de la sesión.
Las pruebas que cambian la contraseña usan cuentas propias, no las de demostración.
"""
import uuid

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.main import app
from app.servicios import acceso

V1 = "/api/v1"
DOMINIO = "cuenta-api.local"


@pytest.fixture(scope="module", autouse=True)
def _desactivar_lo_creado():
    yield
    db.ejecutar(f"update usuarios set activo=0 where correo like '%@{DOMINIO}'")


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    assert r.headers["cache-control"] == "no-store"
    return cuerpo["error"]


def _cuenta(clave: str = "clave-inicial-123") -> dict:
    correo = f"persona-{uuid.uuid4().hex[:8]}@{DOMINIO}"
    uid = acceso.crear_usuario(correo, "Persona de cuenta", "colaborador", clave)
    return {"id": uid, "correo": correo, "clave": clave}


def _sesion(correo: str, clave: str) -> TestClient:
    c = TestClient(app)
    assert c.post(f"{V1}/auth/login", json={"correo": correo, "clave": clave}).status_code == 200
    return c


def _pasos(uid: int) -> list[str]:
    return [e["paso"] for e in db.todos("select paso from eventos where entidad='usuario' and entidad_id=:i order by id", i=uid)]


def test_sin_sesion_responde_401(anonimo):
    _error(anonimo.get(f"{V1}/cuenta"), 401, "UNAUTHENTICATED")
    _error(anonimo.post(f"{V1}/cuenta/clave", json={"actual": "x", "nueva": "y"}), 401, "UNAUTHENTICATED")
    _error(anonimo.post(f"{V1}/cuenta/telegram/vinculo"), 401, "UNAUTHENTICATED")


def test_mis_datos_salen_de_la_sesion(piloto, gestor, cliente):
    r = piloto.get(f"{V1}/cuenta")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    cuenta = r.json()
    assert set(cuenta) == {"persona", "rol_texto", "telegram"}
    assert cuenta["persona"]["correo"] == "piloto@demo.local" and cuenta["persona"]["rol"] == "colaborador"
    assert cuenta["persona"]["codigo"].startswith("P-") and cuenta["persona"]["cargo"] == "Pilotaje de dron"
    assert cuenta["rol_texto"] == "colaborador"
    assert cuenta["telegram"] == {"vinculado": False, "usuario": None, "canal_activo": False}
    assert gestor.get(f"{V1}/cuenta").json()["rol_texto"] == "gestor de proyecto"
    assert cliente.get(f"{V1}/cuenta").json()["persona"]["correo"] == "admin@demo.local"
    assert "clave" not in r.text


def test_cambiar_mi_clave_exige_la_actual_y_renueva_la_sesion():
    c = _cuenta()
    sesion, otra = _sesion(c["correo"], c["clave"]), _sesion(c["correo"], c["clave"])
    error = _error(sesion.post(f"{V1}/cuenta/clave", json={"actual": "equivocada", "nueva": "clave-nueva-456789"}, headers=_csrf(sesion)),
                   422, "VALIDATION_ERROR")
    assert error["fields"] == {"actual": "La contraseña actual no coincide."}
    for nueva in ("corta", c["clave"]):
        error = _error(sesion.post(f"{V1}/cuenta/clave", json={"actual": c["clave"], "nueva": nueva}, headers=_csrf(sesion)),
                       422, "VALIDATION_ERROR")
        assert "nueva" in error["fields"]
    antes = _csrf(sesion)["X-CSRF-Token"]
    r = sesion.post(f"{V1}/cuenta/clave", json={"actual": c["clave"], "nueva": "clave-nueva-456789"}, headers=_csrf(sesion))
    assert r.status_code == 200, r.text
    assert "clave-nueva-456789" not in r.text and r.json()["mensaje"]
    nuevo = r.json()["csrf_token"]
    assert nuevo != antes and nuevo == api_v1.token_csrf(sesion.cookies.get(acceso.COOKIE))
    assert sesion.get(f"{V1}/auth/me").status_code == 200                 # esta sesión sigue, renovada
    assert otra.get(f"{V1}/auth/me").status_code == 401                   # las demás se cerraron
    assert TestClient(app).post(f"{V1}/auth/login", json={"correo": c["correo"], "clave": c["clave"]}).status_code == 401
    _sesion(c["correo"], "clave-nueva-456789")
    assert "contraseña cambiada por la persona" in _pasos(c["id"])


def test_cambiar_mi_clave_exige_token_csrf():
    c = _cuenta()
    sesion = _sesion(c["correo"], c["clave"])
    _error(sesion.post(f"{V1}/cuenta/clave", json={"actual": c["clave"], "nueva": "clave-nueva-456789"}), 403, "CSRF_INVALID")
    _sesion(c["correo"], c["clave"])                                      # no cambió


def test_vincular_telegram_con_el_canal_apagado_lo_dice(piloto):
    error = _error(piloto.post(f"{V1}/cuenta/telegram/vinculo", headers=_csrf(piloto)), 409, "INVALID_STATE")
    assert "Telegram no está configurado" in error["message"]


def test_vincular_telegram_da_un_codigo_de_un_solo_uso(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "token-de-prueba")
    monkeypatch.setattr(config, "TELEGRAM_BOT_NOMBRE", "bot_de_prueba")
    c = _cuenta()
    sesion = _sesion(c["correo"], c["clave"])
    assert sesion.get(f"{V1}/cuenta").json()["telegram"]["canal_activo"] is True
    _error(sesion.post(f"{V1}/cuenta/telegram/vinculo"), 403, "CSRF_INVALID")
    r = sesion.post(f"{V1}/cuenta/telegram/vinculo", headers=_csrf(sesion))
    assert r.status_code == 200, r.text
    vinculo = r.json()
    assert vinculo["enlace"] == f"https://t.me/bot_de_prueba?start={vinculo['codigo']}" and vinculo["minutos"] == 15
    guardado = db.uno("select huella from vinculos_telegram where usuario_id=:u", u=c["id"])
    assert guardado["huella"] == acceso.huella(vinculo["codigo"]) and guardado["huella"] != vinculo["codigo"]


def test_desvincular_telegram(cliente):
    c = _cuenta()
    db.actualizar("usuarios", c["id"], telegram_chat_id=88001, telegram_usuario="persona_cuenta")
    sesion = _sesion(c["correo"], c["clave"])
    assert sesion.get(f"{V1}/cuenta").json()["telegram"]["vinculado"] is True
    r = sesion.post(f"{V1}/cuenta/telegram/desvincular", headers=_csrf(sesion))
    assert r.status_code == 200, r.text
    assert r.json()["telegram"] == {"vinculado": False, "usuario": None, "canal_activo": False}
    assert db.uno("select telegram_chat_id from usuarios where id=:i", i=c["id"])["telegram_chat_id"] is None
    assert "Telegram desvinculado" in _pasos(c["id"])


def test_la_pantalla_actual_sigue_igual(anonimo):
    c = _cuenta()
    anonimo.post("/entrar", data={"correo": c["correo"], "clave": c["clave"]})
    r = anonimo.post("/mi-cuenta/clave", data={"actual": "otra", "nueva": "clave-nueva-123"}, follow_redirects=False)
    assert r.headers["location"] == "/mi-cuenta?aviso=La+contrase%C3%B1a+actual+no+coincide."
