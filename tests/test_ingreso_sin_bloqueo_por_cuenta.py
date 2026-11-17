"""I-9 (QA del 16 nov): el ingreso solo se limita por la ventana de `intentos.py`; no hay bloqueo por cuenta.

Nadie deja por fuera a la dueña de una cuenta fallando con su correo desde otra dirección. El 429 lleva `Retry-After`: los
segundos que faltan para que el fallo que hoy deja la clave en su máximo salga de la ventana. El cambio de contraseña
conserva su propio freno, que ya no toca el ingreso.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from app import api_v1, db
from app.main import app
from app.servicios import acceso, intentos

V1 = "/api/v1"
DOMINIO = "ingreso-i9.local"


def _cliente(direccion: str | None = None) -> TestClient:
    return TestClient(app, client=(direccion or f"192.0.2.{uuid.uuid4().int % 250 + 1}", 50000))


def _cuenta() -> tuple[int, str, str]:
    correo, clave = f"i9-{uuid.uuid4().hex[:8]}@{DOMINIO}", "clave-buena-i9-2026"
    return acceso.crear_usuario(correo, "Prueba I-9", "colaborador", clave), correo, clave


def _login(c: TestClient, correo: str, clave: str):
    return c.post(f"{V1}/auth/login", json={"correo": correo, "clave": clave})


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


@pytest.fixture(autouse=True)
def _ventana_limpia():
    db.ejecutar("delete from intentos_ingreso")
    yield
    db.ejecutar("delete from intentos_ingreso")
    db.ejecutar(f"update usuarios set activo=0 where correo like '%@{DOMINIO}'")


def test_fallos_desde_otra_direccion_no_dejan_por_fuera_a_la_duena():
    a, b = _cliente("192.0.2.10"), _cliente("192.0.2.11")
    codigos = [_login(a, "piloto2@demo.local", "equivocada-i9").status_code for _ in range(6)]
    assert codigos == [401] * 6                                     # ni el sexto fallo corta: no hay bloqueo por cuenta
    r = _login(b, "piloto2@demo.local", "demo-piloto2-2026")
    assert r.status_code == 200, r.text


def test_autenticar_no_escribe_bloqueo_en_la_cuenta():
    uid, correo, clave = _cuenta()
    for _ in range(7):
        assert acceso.autenticar(correo, "equivocada-i9") == (None, "Correo o contraseña incorrectos.")
    fila = db.uno("select fallos, bloqueado_hasta from usuarios where id=:i", i=uid)
    assert fila["fallos"] in (0, None) and fila["bloqueado_hasta"] is None
    assert acceso.autenticar(correo, clave)[0]["id"] == uid
    assert not hasattr(acceso, "MAX_FALLOS")


def test_diez_fallos_desde_una_direccion_dan_429_con_retry_after():
    _, correo, clave = _cuenta()
    a = _cliente()
    assert [_login(a, correo, "equivocada-i9").status_code for _ in range(intentos.MAX_POR_PAR)] == [401] * intentos.MAX_POR_PAR
    r = _login(a, correo, clave)                                    # desde la misma dirección, aunque sea la buena
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS", r.text
    assert 0 < int(r.headers["retry-after"]) <= intentos.VENTANA.total_seconds() + 1   # un segundo de más por el truncado
    assert _login(_cliente(), correo, clave).status_code == 200     # desde otra dirección entra


def test_muchos_correos_desde_una_direccion_limitan_otro_correo():
    _, correo, clave = _cuenta()
    a = _cliente()
    for _ in range(intentos.MAX_POR_DIRECCION + 1):
        _login(a, f"nadie-{uuid.uuid4().hex[:6]}@{DOMINIO}", "equivocada-i9")
    r = _login(a, correo, clave)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0, r.text


def test_el_formulario_entrar_responde_429_con_retry_after():
    _, correo, clave = _cuenta()
    a = _cliente()
    for _ in range(intentos.MAX_POR_PAR):
        r = a.post("/entrar", data={"correo": correo, "clave": "equivocada-i9"}, follow_redirects=False)
        assert r.status_code == 303 and "Demasiados" not in r.headers["location"]
    r = a.post("/entrar", data={"correo": correo, "clave": clave}, follow_redirects=False)
    assert r.status_code == 429 and "intentos" in r.text
    assert 0 < int(r.headers["retry-after"]) <= intentos.VENTANA.total_seconds() + 1   # un segundo de más por el truncado


def test_retry_after_cuenta_desde_el_fallo_que_deja_la_clave_en_su_maximo():
    direccion, correo = "192.0.2.50", f"reloj-{uuid.uuid4().hex[:6]}@{DOMINIO}"
    hace = lambda minutos: (datetime.now(UTC) - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    par = intentos.clave_par(direccion, correo)
    # 10 fallos: el más antiguo hace 14 minutos sale de la ventana en unos 60 s
    db.insertar_varios("intentos_ingreso", [{"clave": par, "momento": hace(14)}] + [{"clave": par, "momento": hace(2)}] * 9)
    assert 50 <= intentos.segundos_para_reintentar(direccion, correo) <= 62
    # con 11 (más del máximo) no basta con que salga el más antiguo: cuenta el segundo
    db.insertar("intentos_ingreso", clave=par, momento=hace(14.5))
    assert 50 <= intentos.segundos_para_reintentar(direccion, correo) <= 62
    # fuera de la ventana no cuentan; y nunca menos de 1
    db.ejecutar("delete from intentos_ingreso")
    assert intentos.segundos_para_reintentar(direccion, correo) == 1


def test_el_freno_de_la_clave_actual_no_bloquea_el_ingreso():
    """Cinco fallos con la actual cierran las sesiones (una sesión robada no prueba sin fin). La dueña vuelve a entrar,
    pero mientras esos fallos sigan en la ventana no puede volver a intentar el cambio: 429 sin mirar la contraseña."""
    uid, correo, clave = _cuenta()
    sesion = _cliente()
    assert _login(sesion, correo, clave).status_code == 200
    cuerpo = {"actual": "equivocada", "nueva": "clave-nueva-456789"}
    codigos = [sesion.post(f"{V1}/cuenta/clave", json=cuerpo, headers=_csrf(sesion)).status_code for _ in range(5)]
    assert codigos == [422, 422, 422, 422, 429]
    assert sesion.get(f"{V1}/auth/me").status_code == 401           # el quinto cierra las sesiones
    otra = _cliente()
    assert _login(otra, correo, clave).status_code == 200           # el ingreso no queda bloqueado
    r = otra.post(f"{V1}/cuenta/clave", json={"actual": clave, "nueva": "clave-nueva-456789"}, headers=_csrf(otra))
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS", r.text
    assert acceso.autenticar(correo, clave)[0]                      # la contraseña no cambió
    assert otra.get(f"{V1}/auth/me").status_code == 200             # y esa espera no vuelve a cerrar la sesión
    fila = db.uno("select fallos, bloqueado_hasta from usuarios where id=:i", i=uid)
    assert fila["fallos"] in (0, None) and fila["bloqueado_hasta"] is None


def test_acertar_la_actual_borra_sus_fallos():
    uid, correo, clave = _cuenta()
    sesion = _cliente()
    assert _login(sesion, correo, clave).status_code == 200
    for _ in range(4):
        sesion.post(f"{V1}/cuenta/clave", json={"actual": "equivocada", "nueva": "clave-nueva-456789"}, headers=_csrf(sesion))
    r = sesion.post(f"{V1}/cuenta/clave", json={"actual": clave, "nueva": "clave-nueva-456789"}, headers=_csrf(sesion))
    assert r.status_code == 200, r.text
    assert db.uno("select count(*) n from intentos_ingreso where clave=:c", c=intentos.clave_cuenta(uid))["n"] == 0


# ---------- ronda 1: el freno de la clave actual cuenta 24 horas ----------
def _envejecer(uid: int, minutos: float):
    """Los fallos de la clave actual de la cuenta pasan a ser de hace `minutos` (como si hubiera pasado ese tiempo)."""
    hace = (datetime.now(UTC) - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")
    db.ejecutar("update intentos_ingreso set momento=:m where clave=:c", m=hace, c=intentos.clave_cuenta(uid))


def _cambiar(c: TestClient, actual: str):
    return c.post(f"{V1}/cuenta/clave", json={"actual": actual, "nueva": "clave-nueva-456789"}, headers=_csrf(c))


def test_cuatro_fallos_cada_15_minutos_no_sirven_para_adivinar_la_actual():
    """Con una ventana de 15 minutos, 4 fallos cada 15 minutos nunca llegaban al quinto: unos 190 en 12 horas."""
    uid, correo, clave = _cuenta()
    sesion = _cliente()
    assert _login(sesion, correo, clave).status_code == 200
    assert [_cambiar(sesion, "equivocada").status_code for _ in range(4)] == [422] * 4
    _envejecer(uid, 16)
    r = _cambiar(sesion, "equivocada")
    assert r.status_code == 429 and r.json()["error"]["code"] == "TOO_MANY_ATTEMPTS", r.text
    assert sesion.get(f"{V1}/auth/me").status_code == 401                    # el quinto en 24 h cierra las sesiones


def test_tras_el_quinto_se_esperan_15_minutos_y_cada_fallo_vuelve_a_cerrar_las_sesiones():
    uid, correo, clave = _cuenta()
    sesion = _cliente()
    assert _login(sesion, correo, clave).status_code == 200
    assert [_cambiar(sesion, "equivocada").status_code for _ in range(5)] == [422] * 4 + [429]
    otra = _cliente()
    assert _login(otra, correo, clave).status_code == 200                    # el ingreso no se bloquea
    _envejecer(uid, 14)
    assert _cambiar(otra, clave).status_code == 429                         # a los 14 minutos, todavía espera
    _envejecer(uid, 16)
    assert _cambiar(otra, "equivocada").status_code == 429                  # pasada la espera, un fallo más vuelve a cerrar
    assert otra.get(f"{V1}/auth/me").status_code == 401
    tercera = _cliente()
    assert _login(tercera, correo, clave).status_code == 200
    _envejecer(uid, 16)
    assert _cambiar(tercera, clave).status_code == 200                      # y acertar después de la espera la cambia
    assert db.uno("select count(*) n from intentos_ingreso where clave=:c", c=intentos.clave_cuenta(uid))["n"] == 0


# ---------- ronda 1: esperar justo `Retry-After` basta ----------
def test_quien_espera_justo_retry_after_ya_no_esta_limitado():
    """Los momentos se guardan truncados al segundo y el corte compara con `>=`: sin un segundo de más, quien esperaba
    exactamente `Retry-After` podía recibir otro 429."""
    formato = "%Y-%m-%d %H:%M:%S"
    direccion, correo = "192.0.2.60", f"borde-{uuid.uuid4().hex[:6]}@{DOMINIO}"
    par = intentos.clave_par(direccion, correo)
    borde = (datetime.now(UTC) - intentos.VENTANA + timedelta(seconds=5)).strftime(formato)
    db.insertar_varios("intentos_ingreso", [{"clave": par, "momento": borde}] * intentos.MAX_POR_PAR)
    assert intentos.limitado(direccion, correo)
    espera = intentos.segundos_para_reintentar(direccion, correo)
    # pasan exactamente `espera` segundos: los fallos quedan `espera` segundos más viejos
    pasado = (datetime.strptime(borde, formato) - timedelta(seconds=espera)).strftime(formato)
    db.ejecutar("update intentos_ingreso set momento=:m where clave=:c", m=pasado, c=par)
    assert not intentos.limitado(direccion, correo)


def test_el_429_del_cambio_de_contrasena_lleva_retry_after():
    uid, correo, clave = _cuenta()
    sesion = _cliente()
    assert _login(sesion, correo, clave).status_code == 200
    for _ in range(4):
        _cambiar(sesion, "equivocada")
    r = _cambiar(sesion, "equivocada")                                       # el quinto: cierra y espera
    assert r.status_code == 429 and 0 < int(r.headers["retry-after"]) <= intentos.VENTANA.total_seconds() + 1, r.headers
    otra = _cliente()
    assert _login(otra, correo, clave).status_code == 200
    _envejecer(uid, 10)
    r = _cambiar(otra, clave)                                                # en la espera: 429 sin mirar la contraseña
    assert r.status_code == 429 and 290 <= int(r.headers["retry-after"]) <= 302, r.headers
