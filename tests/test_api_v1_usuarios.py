"""API v1 de usuarios y cargos: solo administración. Contrato en `contracts/api-v1.md`, sección «Usuarios y cargos».

Las mismas protecciones y eventos que la pantalla actual (`/admin/usuarios`): nadie se quita su propio rol de
administración ni desactiva su cuenta, la contraseña inicial nunca se devuelve y cada cambio queda en la bitácora.
Las cuentas que crean estas pruebas son propias y se desactivan al final: no cambian a las de demostración.
"""
import uuid

import pytest
from starlette.testclient import TestClient

from app import api_v1, db
from app.main import app
from app.servicios import acceso

V1 = "/api/v1"
DOMINIO = "usuarios-api.local"


@pytest.fixture(scope="module", autouse=True)
def _desactivar_lo_creado():
    """Las cuentas de estas pruebas no deben quedar activas (en especial, una administración de más)."""
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


def _correo() -> str:
    return f"persona-{uuid.uuid4().hex[:8]}@{DOMINIO}"


def _crear(cliente: TestClient, **cambios) -> dict:
    datos = {"correo": _correo(), "nombre": "Persona de prueba", "rol": "colaborador", "clave": "clave-inicial-123", "cargo_id": None,
             **cambios}
    r = cliente.post(f"{V1}/usuarios", json=datos, headers=_csrf(cliente))
    assert r.status_code == 201, r.text
    return {**r.json()["usuario"], "clave": datos["clave"]}


def _sesion(correo: str, clave: str) -> TestClient:
    c = TestClient(app)
    assert c.post(f"{V1}/auth/login", json={"correo": correo, "clave": clave}).status_code == 200
    return c


def _cargo(nombre: str) -> int:
    return db.uno("select id from cargos where nombre=:n", n=nombre)["id"]


def _admin_id() -> int:
    return db.uno("select id from usuarios where correo='admin@demo.local'")["id"]


def _pasos(uid: int) -> list[str]:
    return [e["paso"] for e in db.todos("select paso from eventos where entidad='usuario' and entidad_id=:i order by id", i=uid)]


# ---------- acceso ----------
def test_sin_sesion_responde_401(anonimo):
    for ruta in ("/usuarios", "/cargos"):
        _error(anonimo.get(V1 + ruta), 401, "UNAUTHENTICATED")
    _error(anonimo.post(f"{V1}/usuarios", json={}), 401, "UNAUTHENTICATED")


def test_todo_es_solo_de_administracion(gestor, piloto):
    for c in (gestor, piloto):
        _error(c.get(f"{V1}/usuarios"), 403, "FORBIDDEN")
        _error(c.get(f"{V1}/cargos"), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/usuarios", json={"correo": _correo(), "nombre": "X", "rol": "admin", "clave": "clave-inicial-123"},
                      headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/usuarios/1/rol", json={"rol": "admin"}, headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/usuarios/1/estado", json={"activo": False}, headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/usuarios/1/clave", json={"clave": "otra-clave-12345"}, headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/usuarios/1/cargo", json={"cargo_id": None}, headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/usuarios/1/proyectos", json={"proyectos_ids": [1, 2]}, headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/cargos", json={"nombre": "Cargo del gestor"}, headers=_csrf(c)), 403, "FORBIDDEN")
        _error(c.post(f"{V1}/cargos/1", json={"activo": False}, headers=_csrf(c)), 403, "FORBIDDEN")
    gestor_id = db.uno("select id from usuarios where correo='gestor@demo.local'")["id"]
    assert db.uno("select rol from usuarios where id=:i", i=gestor_id)["rol"] == "gestor"
    assert not db.uno("select id from cargos where nombre='Cargo del gestor'")


def test_escribir_exige_token_csrf_y_origen(cliente):
    correo = _correo()
    datos = {"correo": correo, "nombre": "Sin token", "rol": "colaborador", "clave": "clave-inicial-123"}
    _error(cliente.post(f"{V1}/usuarios", json=datos), 403, "CSRF_INVALID")
    ajeno = {**_csrf(cliente), "Origin": "https://sitio-ajeno.example", "Sec-Fetch-Site": "cross-site"}
    _error(cliente.post(f"{V1}/usuarios", json=datos, headers=ajeno), 403, "ORIGIN_NOT_ALLOWED")
    assert not db.uno("select id from usuarios where correo=:c", c=correo)
    u = _crear(cliente)
    _error(cliente.post(f"{V1}/usuarios/{u['id']}/estado", json={"activo": False}), 403, "CSRF_INVALID")
    _error(cliente.post(f"{V1}/cargos", json={"nombre": "Cargo sin token"}), 403, "CSRF_INVALID")
    assert db.uno("select activo from usuarios where id=:i", i=u["id"])["activo"] == 1


# ---------- lista ----------
def test_la_lista_trae_codigo_rol_cargo_proyectos_estado_y_telegram(cliente):
    r = cliente.get(f"{V1}/usuarios", params={"limite": 100})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    por_correo = {u["correo"]: u for u in r.json()["items"]}
    gestor = por_correo["gestor@demo.local"]
    assert set(gestor) == {"id", "codigo", "correo", "nombre", "rol", "rol_texto", "cargo", "proyectos", "activo", "telegram",
                           "ultima_sesion", "creado"}
    assert gestor["rol"] == "gestor" and gestor["rol_texto"] == "gestor de proyecto" and gestor["activo"] is True
    assert gestor["codigo"].startswith("P-") and gestor["cargo"]["nombre"] == "Producción"
    assert [p["id"] for p in gestor["proyectos"]] == [1] and gestor["proyectos"][0]["nombre"]
    assert gestor["telegram"] == {"vinculado": False, "usuario": None}
    assert "clave_hash" not in r.text and "clave" not in gestor


def test_la_lista_dice_si_telegram_esta_vinculado(cliente):
    u = _crear(cliente)
    db.actualizar("usuarios", u["id"], telegram_chat_id=99001, telegram_usuario="persona_prueba")
    fila = next(x for x in cliente.get(f"{V1}/usuarios", params={"limite": 100}).json()["items"] if x["id"] == u["id"])
    assert fila["telegram"] == {"vinculado": True, "usuario": "persona_prueba"}


# ---------- crear ----------
def test_administracion_crea_una_cuenta_y_la_clave_nunca_vuelve(cliente):
    correo = _correo()
    r = cliente.post(f"{V1}/usuarios", headers=_csrf(cliente), json={
        "correo": f"  {correo.upper()} ", "nombre": "Nueva persona", "rol": "gestor", "clave": "clave-inicial-123",
        "cargo_id": _cargo("Producción")})
    assert r.status_code == 201, r.text
    assert "clave-inicial-123" not in r.text and "clave_hash" not in r.text
    u = r.json()["usuario"]
    assert u["correo"] == correo and u["rol"] == "gestor" and u["cargo"]["nombre"] == "Producción" and u["activo"] is True
    assert r.json()["mensaje"]
    fila = db.uno("select * from usuarios where id=:i", i=u["id"])
    assert fila["viajero_id"]                                   # toda cuenta viaja: se le crea su perfil
    assert "cuenta creada" in _pasos(u["id"])
    _sesion(correo, "clave-inicial-123")                         # la contraseña inicial sirve para entrar


def test_crear_con_datos_invalidos_responde_422_con_el_campo(cliente):
    existente = _crear(cliente)
    casos = [({"correo": "sin-arroba"}, "correo"), ({"clave": "corta"}, "clave"), ({"rol": "jefe"}, "rol"),
             ({"correo": existente["correo"]}, "correo"), ({"cargo_id": 999999}, "cargo_id")]
    for cambio, campo in casos:
        datos = {"correo": _correo(), "nombre": "Inválida", "rol": "colaborador", "clave": "clave-inicial-123", **cambio}
        error = _error(cliente.post(f"{V1}/usuarios", json=datos, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
        assert campo in error["fields"], (cambio, error)
    assert db.uno("select count(*) n from usuarios where correo=:c", c=existente["correo"])["n"] == 1


# ---------- cambios ----------
def test_cambiar_el_rol_cierra_sus_sesiones_y_queda_el_evento(cliente):
    u = _crear(cliente)
    sesion = _sesion(u["correo"], u["clave"])
    r = cliente.post(f"{V1}/usuarios/{u['id']}/rol", json={"rol": "gestor"}, headers=_csrf(cliente))
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["rol"] == "gestor"
    assert sesion.get(f"{V1}/auth/me").status_code == 401           # el permiso nuevo exige entrar de nuevo
    assert "rol cambiado" in _pasos(u["id"])
    error = _error(cliente.post(f"{V1}/usuarios/{u['id']}/rol", json={"rol": "jefe"}, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
    assert "rol" in error["fields"]


def test_dejar_de_gestionar_quita_los_proyectos(cliente):
    u = _crear(cliente, rol="gestor")
    r = cliente.post(f"{V1}/usuarios/{u['id']}/proyectos", json={"proyectos_ids": [2, 1, 1, 999999]}, headers=_csrf(cliente))
    assert r.status_code == 200, r.text
    assert [p["id"] for p in r.json()["usuario"]["proyectos"]] == [1, 2]       # se ignora lo que no existe
    assert "proyectos asignados" in _pasos(u["id"])
    r = cliente.post(f"{V1}/usuarios/{u['id']}/rol", json={"rol": "colaborador"}, headers=_csrf(cliente))
    assert r.json()["usuario"]["proyectos"] == []


def test_nadie_se_quita_su_propio_rol_de_administracion(cliente):
    error = _error(cliente.post(f"{V1}/usuarios/{_admin_id()}/rol", json={"rol": "colaborador"}, headers=_csrf(cliente)),
                   409, "INVALID_STATE")
    assert "No puedes quitarte tu propio rol" in error["message"]
    assert db.uno("select rol from usuarios where id=:i", i=_admin_id())["rol"] == "admin"


def test_otra_administracion_si_puede_quitarle_el_rol_a_una_cuenta_admin(cliente):
    otra = _crear(cliente, rol="admin")
    r = cliente.post(f"{V1}/usuarios/{otra['id']}/rol", json={"rol": "colaborador"}, headers=_csrf(cliente))
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "colaborador"


def test_desactivar_y_reactivar(cliente):
    u = _crear(cliente)
    sesion = _sesion(u["correo"], u["clave"])
    r = cliente.post(f"{V1}/usuarios/{u['id']}/estado", json={"activo": False}, headers=_csrf(cliente))
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["activo"] is False and "desactivada" in r.json()["mensaje"]
    assert sesion.get(f"{V1}/auth/me").status_code == 401
    assert TestClient(app).post(f"{V1}/auth/login", json={"correo": u["correo"], "clave": u["clave"]}).status_code == 401
    r = cliente.post(f"{V1}/usuarios/{u['id']}/estado", json={"activo": False}, headers=_csrf(cliente))
    assert r.status_code == 200 and r.json()["mensaje"].startswith("Sin cambios")
    r = cliente.post(f"{V1}/usuarios/{u['id']}/estado", json={"activo": True}, headers=_csrf(cliente))
    assert r.json()["usuario"]["activo"] is True and "reactivada" in r.json()["mensaje"]
    _sesion(u["correo"], u["clave"])
    assert _pasos(u["id"])[-2:] == ["cuenta desactivada", "cuenta reactivada"]


def test_nadie_desactiva_su_propia_cuenta(cliente):
    error = _error(cliente.post(f"{V1}/usuarios/{_admin_id()}/estado", json={"activo": False}, headers=_csrf(cliente)),
                   409, "INVALID_STATE")
    assert "No puedes desactivar tu propia cuenta" in error["message"]
    assert db.uno("select activo from usuarios where id=:i", i=_admin_id())["activo"] == 1
    assert cliente.get(f"{V1}/auth/me").status_code == 200


def test_restablecer_la_clave_cierra_sus_sesiones_y_no_la_devuelve(cliente):
    u = _crear(cliente)
    sesion = _sesion(u["correo"], u["clave"])
    error = _error(cliente.post(f"{V1}/usuarios/{u['id']}/clave", json={"clave": "corta"}, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
    assert "clave" in error["fields"]
    r = cliente.post(f"{V1}/usuarios/{u['id']}/clave", json={"clave": "clave-nueva-456789"}, headers=_csrf(cliente))
    assert r.status_code == 200 and "clave-nueva-456789" not in r.text
    assert sesion.get(f"{V1}/auth/me").status_code == 401
    _sesion(u["correo"], "clave-nueva-456789")
    assert "contraseña restablecida" in _pasos(u["id"])


def test_asignar_y_quitar_el_cargo(cliente):
    u = _crear(cliente)
    r = cliente.post(f"{V1}/usuarios/{u['id']}/cargo", json={"cargo_id": _cargo("Edición de video")}, headers=_csrf(cliente))
    assert r.status_code == 200 and r.json()["usuario"]["cargo"]["nombre"] == "Edición de video"
    assert "cargo asignado" in _pasos(u["id"])
    r = cliente.post(f"{V1}/usuarios/{u['id']}/cargo", json={"cargo_id": None}, headers=_csrf(cliente))
    assert r.json()["usuario"]["cargo"] is None
    error = _error(cliente.post(f"{V1}/usuarios/{u['id']}/cargo", json={"cargo_id": 999999}, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
    assert "cargo_id" in error["fields"]


def test_una_cuenta_inexistente_responde_404(cliente):
    for accion, cuerpo in (("rol", {"rol": "gestor"}), ("estado", {"activo": False}), ("clave", {"clave": "clave-nueva-456789"}),
                           ("cargo", {"cargo_id": None}), ("proyectos", {"proyectos_ids": []})):
        _error(cliente.post(f"{V1}/usuarios/999999/{accion}", json=cuerpo, headers=_csrf(cliente)), 404, "NOT_FOUND")


# ---------- cargos ----------
def test_administracion_crea_renombra_y_desactiva_cargos(cliente):
    nombre = f"Cargo {uuid.uuid4().hex[:6]}"
    r = cliente.post(f"{V1}/cargos", json={"nombre": f"  {nombre} "}, headers=_csrf(cliente))
    assert r.status_code == 201, r.text
    cargo = r.json()
    assert cargo["nombre"] == nombre and cargo["activo"] is True and cargo["personas"] == 0
    _error(cliente.post(f"{V1}/cargos", json={"nombre": nombre.lower()}, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
    _error(cliente.post(f"{V1}/cargos", json={"nombre": "ab"}, headers=_csrf(cliente)), 422, "VALIDATION_ERROR")
    r = cliente.post(f"{V1}/cargos/{cargo['id']}", json={"nombre": f"{nombre} aéreo"}, headers=_csrf(cliente))
    assert r.status_code == 200 and r.json()["nombre"] == f"{nombre} aéreo"
    r = cliente.post(f"{V1}/cargos/{cargo['id']}", json={"activo": False}, headers=_csrf(cliente))
    assert r.json()["activo"] is False
    lista = {c["id"]: c for c in cliente.get(f"{V1}/cargos").json()["items"]}
    assert lista[cargo["id"]]["activo"] is False
    pasos = [e["paso"] for e in db.todos("select paso from eventos where entidad='cargo' and entidad_id=:i order by id", i=cargo["id"])]
    assert pasos == ["cargo creado", "cargo renombrado", "cargo desactivado"]
    _error(cliente.post(f"{V1}/cargos/999999", json={"activo": True}, headers=_csrf(cliente)), 404, "NOT_FOUND")


def test_la_pantalla_actual_sigue_protegiendo_igual(cliente):
    """La ruta de las pantallas llama al mismo servicio: el mismo aviso y nada cambia."""
    r = cliente.post(f"/admin/usuarios/{_admin_id()}", data={"accion": "estado", "activo": "0"}, follow_redirects=False)
    assert "No%20puedes%20desactivar%20tu%20propia%20cuenta" in r.headers["location"]
    assert db.uno("select activo from usuarios where id=:i", i=_admin_id())["activo"] == 1
