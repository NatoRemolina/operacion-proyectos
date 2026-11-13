"""API v1, recorrido mínimo: ingreso, viajes, gastos, envío de un recibo y su archivo. Contrato en `contracts/api-v1.md`.

Las lecturas de recibos salen de las lecturas guardadas de `datos/ejemplos` (sin modelo de lenguaje en las pruebas).
"""
import re

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.main import app
from app.servicios import acceso
from datos import exportar_contrato

V1 = "/api/v1"
DINERO = re.compile(r"^-?\d+\.\d{2}$")
INSTANTE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _contrato(r, estado, codigo):
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"error", "request_id"} and set(cuerpo["error"]) == {"code", "message", "fields"}
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"]
    assert cuerpo["request_id"] and cuerpo["request_id"] == r.headers["X-Peticion"]
    assert r.headers["Cache-Control"] == "no-store"
    return cuerpo


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _enviar(c: TestClient, nombre: str, contenido: bytes, viaje_id: int | None = None, cabeceras: dict | None = None, **extra):
    datos = {"viaje_id": str(viaje_id)} if viaje_id else {}
    return c.post(f"{V1}/gastos", files={"archivo": (nombre, contenido, "application/octet-stream")}, data={**datos, **extra},
                  headers={**_csrf(c), **(cabeceras or {})})


def _todos(c: TestClient, ruta: str, limite: int = 100) -> list[dict]:
    """Recorre un listado completo siguiendo el cursor."""
    items, cursor = [], None
    while True:
        r = c.get(ruta, params={"limite": limite, **({"cursor": cursor} if cursor else {})})
        assert r.status_code == 200, r.text
        items += r.json()["items"]
        cursor = r.json()["siguiente"]
        if cursor is None:
            return items


def _ids(c: TestClient, ruta: str) -> set[int]:
    return {i["id"] for i in _todos(c, ruta)}


@pytest.fixture(scope="module")
def mundo(nuevo_viaje, viaje_aprobado, piloto, piloto2, ejemplos):
    """Un viaje y un gasto de cada piloto. El de piloto2 está en el proyecto 1 (el del gestor); hay otro suyo en el proyecto 2."""
    viaje2 = nuevo_viaje(viajero_id=2)
    viaje2_fuera = nuevo_viaje(viajero_id=2, proyecto_id=2)
    foto = (ejemplos / "recibo_lisboa.png").read_bytes()
    g1 = _enviar(piloto, "lisboa.png", foto, viaje_aprobado["id"])
    g2 = _enviar(piloto2, "lisboa.png", foto, viaje2["id"])
    g3 = _enviar(piloto2, "lisboa.png", foto, viaje2_fuera["id"])
    assert g1.status_code == g2.status_code == g3.status_code == 201, (g1.text, g2.text, g3.text)
    return {"viaje1": viaje_aprobado, "viaje2": viaje2, "viaje2_fuera": viaje2_fuera,
            "gasto1": g1.json(), "gasto2": g2.json(), "gasto2_fuera": g3.json(), "foto": foto}


# ---------- ingreso, sesión y salida ----------
def test_login_correcto_devuelve_persona_token_y_cookie():
    c = TestClient(app)
    r = c.post(f"{V1}/auth/login", json={"correo": "PILOTO@demo.local ", "clave": "demo-piloto-2026"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"persona", "csrf_token", "demostracion"}
    assert set(cuerpo["persona"]) == {"id", "codigo", "nombre", "rol", "correo", "cargo"}   # nada de la huella de la contraseña
    assert cuerpo["persona"]["rol"] == "colaborador" and cuerpo["persona"]["codigo"] == f"P-{cuerpo['persona']['id']:04d}"
    assert "httponly" in r.headers["set-cookie"].lower() and c.cookies.get(acceso.COOKIE)
    assert cuerpo["csrf_token"] == api_v1.token_csrf(c.cookies.get(acceso.COOKIE))
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Peticion"]
    assert c.get(f"{V1}/auth/me").json()["persona"]["id"] == cuerpo["persona"]["id"]


def test_login_incorrecto_es_generico_y_tras_el_bloqueo_responde_429(anonimo):
    acceso.crear_usuario("bloqueo-api@demo.local", "Bloqueo", "colaborador", "clave-correcta-2026")
    inexistente = _contrato(anonimo.post(f"{V1}/auth/login", json={"correo": "nadie@demo.local", "clave": "x"}), 401, "INVALID_CREDENTIALS")
    for _ in range(acceso.MAX_FALLOS):
        equivocada = _contrato(anonimo.post(f"{V1}/auth/login", json={"correo": "bloqueo-api@demo.local", "clave": "equivocada"}),
                               401, "INVALID_CREDENTIALS")
        assert equivocada["error"]["message"] == inexistente["error"]["message"]   # no revela si la cuenta existe
    r = anonimo.post(f"{V1}/auth/login", json={"correo": "bloqueo-api@demo.local", "clave": "clave-correcta-2026"})
    _contrato(r, 429, "TOO_MANY_ATTEMPTS")                                         # bloqueada aunque la clave sea correcta
    assert not anonimo.cookies.get(acceso.COOKIE)


def test_login_valida_el_cuerpo_y_el_origen(anonimo):
    cuerpo = _contrato(anonimo.post(f"{V1}/auth/login", json={"correo": "piloto@demo.local"}), 422, "VALIDATION_ERROR")
    assert "clave" in cuerpo["error"]["fields"]
    ajeno = {"Origin": "https://sitio-ajeno.example", "Sec-Fetch-Site": "cross-site"}
    _contrato(anonimo.post(f"{V1}/auth/login", json={"correo": "piloto@demo.local", "clave": "demo-piloto-2026"}, headers=ajeno),
              403, "ORIGIN_NOT_ALLOWED")


def test_me_con_y_sin_sesion(piloto, anonimo):
    r = piloto.get(f"{V1}/auth/me")
    assert r.status_code == 200 and r.json()["persona"]["correo"] == "piloto@demo.local"
    assert r.json()["csrf_token"] == _csrf(piloto)["X-CSRF-Token"]
    assert r.json()["demostracion"] is True   # las pruebas corren en local con cuentas de demostración
    _contrato(anonimo.get(f"{V1}/auth/me"), 401, "UNAUTHENTICATED")


def test_logout_exige_csrf_y_revoca_la_sesion():
    c = TestClient(app)
    token = c.post(f"{V1}/auth/login", json={"correo": "piloto2@demo.local", "clave": "demo-piloto2-2026"}).json()["csrf_token"]
    _contrato(c.post(f"{V1}/auth/logout"), 403, "CSRF_INVALID")
    assert c.get(f"{V1}/auth/me").status_code == 200                               # sin token no se cerró nada
    cookie = c.cookies.get(acceso.COOKIE)
    r = c.post(f"{V1}/auth/logout", headers={"X-CSRF-Token": token})
    assert r.status_code == 204 and not r.content
    assert not db.uno("select id from sesiones where huella=:h", h=acceso.huella(cookie))   # revocada en el servidor
    _contrato(c.get(f"{V1}/auth/me"), 401, "UNAUTHENTICATED")
    otro = TestClient(app, cookies={acceso.COOKIE: cookie})                        # ni reutilizando la cookie vieja
    _contrato(otro.get(f"{V1}/auth/me"), 401, "UNAUTHENTICATED")


def test_el_rol_nunca_sale_del_cuerpo(piloto, cliente, ejemplos, mundo):
    c = TestClient(app)
    r = c.post(f"{V1}/auth/login", json={"correo": "piloto@demo.local", "clave": "demo-piloto-2026", "rol": "admin", "usuario_id": 1})
    assert r.json()["persona"]["rol"] == "colaborador"
    admin_id = cliente.get(f"{V1}/auth/me").json()["persona"]["id"]
    yo = piloto.get(f"{V1}/auth/me").json()["persona"]["id"]
    g = _enviar(piloto, "lisboa.png", mundo["foto"], mundo["viaje1"]["id"], rol="admin", usuario_id=str(admin_id))
    assert g.status_code == 201
    assert db.uno("select usuario_id from gastos where id=:i", i=g.json()["id"])["usuario_id"] == yo
    _contrato(c.get(f"{V1}/viajes/{mundo['viaje2_fuera']['id']}"), 404, "NOT_FOUND")   # el rol enviado tampoco abrió nada


# ---------- alcance ----------
def test_un_piloto_no_ve_lo_del_otro(piloto, mundo):
    viajes_ = _ids(piloto, f"{V1}/viajes")
    assert mundo["viaje1"]["id"] in viajes_
    assert not {mundo["viaje2"]["id"], mundo["viaje2_fuera"]["id"]} & viajes_
    gastos_ = _ids(piloto, f"{V1}/gastos")
    assert mundo["gasto1"]["id"] in gastos_ and mundo["gasto2"]["id"] not in gastos_
    assert piloto.get(f"{V1}/gastos", params={"viaje_id": mundo["viaje2"]["id"]}).json() == {"items": [], "siguiente": None}
    _contrato(piloto.get(f"{V1}/viajes/{mundo['viaje2']['id']}"), 404, "NOT_FOUND")
    _contrato(piloto.get(f"{V1}/gastos/{mundo['gasto2']['id']}"), 404, "NOT_FOUND")
    _contrato(piloto.get(f"{V1}/documentos/{mundo['gasto2']['documento_id']}/contenido"), 404, "NOT_FOUND")
    _contrato(piloto.get(f"{V1}/viajes/999999"), 404, "NOT_FOUND")                # lo ajeno y lo inexistente, igual


def test_el_otro_piloto_tampoco_ve_lo_del_primero(piloto2, mundo):
    assert mundo["viaje1"]["id"] not in _ids(piloto2, f"{V1}/viajes")
    assert mundo["gasto1"]["id"] not in _ids(piloto2, f"{V1}/gastos")
    _contrato(piloto2.get(f"{V1}/viajes/{mundo['viaje1']['id']}"), 404, "NOT_FOUND")
    _contrato(piloto2.get(f"{V1}/gastos/{mundo['gasto1']['id']}"), 404, "NOT_FOUND")
    _contrato(piloto2.get(f"{V1}/documentos/{mundo['gasto1']['documento_id']}/contenido"), 404, "NOT_FOUND")


def test_el_gestor_ve_lo_de_su_proyecto_y_nada_mas(gestor, mundo):
    viajes_, gastos_ = _ids(gestor, f"{V1}/viajes"), _ids(gestor, f"{V1}/gastos")
    assert {mundo["viaje1"]["id"], mundo["viaje2"]["id"]} <= viajes_ and mundo["viaje2_fuera"]["id"] not in viajes_
    assert {mundo["gasto1"]["id"], mundo["gasto2"]["id"]} <= gastos_ and mundo["gasto2_fuera"]["id"] not in gastos_
    assert gestor.get(f"{V1}/viajes/{mundo['viaje2']['id']}").status_code == 200
    assert gestor.get(f"{V1}/gastos/{mundo['gasto2']['id']}").status_code == 200
    assert gestor.get(f"{V1}/documentos/{mundo['gasto2']['documento_id']}/contenido").status_code == 200
    _contrato(gestor.get(f"{V1}/viajes/{mundo['viaje2_fuera']['id']}"), 404, "NOT_FOUND")
    _contrato(gestor.get(f"{V1}/gastos/{mundo['gasto2_fuera']['id']}"), 404, "NOT_FOUND")
    _contrato(gestor.get(f"{V1}/documentos/{mundo['gasto2_fuera']['documento_id']}/contenido"), 404, "NOT_FOUND")


def test_administracion_ve_todo(cliente, mundo):
    viajes_, gastos_ = _ids(cliente, f"{V1}/viajes"), _ids(cliente, f"{V1}/gastos")
    assert {mundo[k]["id"] for k in ("viaje1", "viaje2", "viaje2_fuera")} <= viajes_
    assert {mundo[k]["id"] for k in ("gasto1", "gasto2", "gasto2_fuera")} <= gastos_
    assert viajes_ == {f["id"] for f in db.todos("select id from viajes")}
    assert gastos_ == {f["id"] for f in db.todos("select id from gastos")}
    assert cliente.get(f"{V1}/documentos/{mundo['gasto2_fuera']['documento_id']}/contenido").status_code == 200


# ---------- forma de las respuestas ----------
def test_viaje_con_la_forma_del_contrato(piloto, mundo):
    v = piloto.get(f"{V1}/viajes/{mundo['viaje1']['id']}").json()
    assert v["codigo"] == mundo["viaje1"]["codigo"] and v["estado"] == "aprobado" and v["estado_texto"] == "Aprobado"
    assert v["titular"]["codigo"].startswith("P-") and v["proyecto"]["id"] == 1
    assert (v["origen"], v["destino"]) == ("MIA", "LAS")                         # códigos IATA
    assert DINERO.match(v["presupuesto_usd"]) and DINERO.match(v["gastado_usd"]) and DINERO.match(v["en_revision_usd"])
    assert v["presupuesto_detalle"] and all(DINERO.match(l["valor"]) for l in v["presupuesto_detalle"])
    assert INSTANTE.match(v["aprobado_en"]) and isinstance(v["en_curso"], bool) and isinstance(v["gastos"], int)
    resumen = next(i for i in piloto.get(f"{V1}/viajes", params={"limite": 100}).json()["items"] if i["id"] == v["id"])
    assert "presupuesto_detalle" not in resumen and resumen["gastado_usd"] == v["gastado_usd"]
    pendientes = piloto.get(f"{V1}/viajes", params={"estado": "pendiente_aprobacion", "limite": 100}).json()["items"]
    assert all(i["estado"] == "pendiente_aprobacion" for i in pendientes)
    assert piloto.get(f"{V1}/viajes", params={"estado": "inventado"}).status_code == 422


def test_gasto_con_la_forma_del_contrato(piloto, mundo):
    g = piloto.get(f"{V1}/gastos/{mundo['gasto1']['id']}").json()
    assert g == mundo["gasto1"]                                                    # lo que devolvió el envío es lo que hay
    assert g["viaje"] == {"id": mundo["viaje1"]["id"], "codigo": mundo["viaje1"]["codigo"]}
    assert g["canal"] == "web" and g["documento_id"] and INSTANTE.match(g["creado"])
    assert all(v is None or DINERO.match(v) for v in (g["total"], g["total_usd"], g["subtotal"], g["impuesto"], g["propina"]))
    assert isinstance(g["motivos"], list) and isinstance(g["alertas"], list) and set(g["lectura"]) == {"origen", "confianza"}
    revision = piloto.get(f"{V1}/gastos", params={"estado": "revision", "limite": 100}).json()["items"]
    assert all(i["estado"] == "revision" and i["estado_texto"] == "En revisión" for i in revision)


# ---------- envío de un recibo ----------
def test_enviar_un_recibo_devuelve_su_estado_real(piloto, mundo):
    # La regla de duplicados es global: aquí no se usa recibo_gasolina.png, que otra prueba espera aprobado solo
    r = _enviar(piloto, "lisboa.png", mundo["foto"], mundo["viaje1"]["id"], cabeceras={"Idempotency-Key": "prueba-lisboa-1"})
    assert r.status_code == 201, r.text                                            # la cabecera se acepta
    g = r.json()
    guardado = db.uno("select estado, total from gastos where id=:i", i=g["id"])
    assert g["estado"] in ("aprobado_auto", "revision") and g["estado"] == guardado["estado"]
    assert g["viaje"]["id"] == mundo["viaje1"]["id"] and g["total"] == f"{guardado['total']:.2f}"


def test_un_viaje_ajeno_deja_el_gasto_sin_viaje_y_en_revision(piloto, mundo):
    g = _enviar(piloto, "lisboa.png", mundo["foto"], mundo["viaje2"]["id"]).json()
    assert g["viaje"] is None and g["estado"] == "revision" and "sin_viaje" in g["motivos"]


def test_un_correo_se_acepta_y_se_entrega_como_texto(piloto, ejemplos, mundo):
    correo = (ejemplos / "correo_tiquete.eml").read_bytes()
    g = _enviar(piloto, "tiquete.eml", correo, mundo["viaje1"]["id"])
    assert g.status_code == 201, g.text
    r = piloto.get(f"{V1}/documentos/{g.json()['documento_id']}/contenido")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain") and r.content == correo


def test_envios_rechazados(piloto, mundo):
    _contrato(_enviar(piloto, "grande.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * config.MAX_BYTES_SOPORTE), 413, "PAYLOAD_TOO_LARGE")
    _contrato(_enviar(piloto, "foto.png", b"<html><script>alert(1)</script></html>"), 415, "UNSUPPORTED_MEDIA_TYPE")
    _contrato(_enviar(piloto, "vacio.png", b""), 422, "VALIDATION_ERROR")
    sin_csrf = piloto.post(f"{V1}/gastos", files={"archivo": ("lisboa.png", mundo["foto"], "image/png")})
    _contrato(sin_csrf, 403, "CSRF_INVALID")
    cuerpo = _contrato(piloto.post(f"{V1}/gastos", headers=_csrf(piloto)), 422, "VALIDATION_ERROR")
    assert "archivo" in cuerpo["error"]["fields"]


def test_enviar_sin_sesion_responde_401(anonimo, mundo):
    _contrato(anonimo.post(f"{V1}/gastos", files={"archivo": ("lisboa.png", mundo["foto"], "image/png")}), 401, "UNAUTHENTICATED")


# ---------- archivo original ----------
def test_el_documento_se_entrega_con_su_tipo_y_aislado(piloto, mundo):
    r = piloto.get(f"{V1}/documentos/{mundo['gasto1']['documento_id']}/contenido")
    assert r.status_code == 200 and r.content == mundo["foto"]
    assert r.headers["content-type"] == "image/png" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Content-Disposition"] == "inline" and r.headers["Cache-Control"] == "private, no-store"
    assert r.headers["X-Peticion"]
    _contrato(piloto.get(f"{V1}/documentos/999999/contenido"), 404, "NOT_FOUND")


# ---------- paginación ----------
def test_el_cursor_lleva_al_siguiente_y_el_ultimo_cierra(piloto, mundo):
    completos = [g["id"] for g in piloto.get(f"{V1}/gastos", params={"limite": 100}).json()["items"]]
    assert len(completos) >= 2 and completos == sorted(completos, reverse=True)    # más reciente primero
    vistos, cursor = [], None
    while True:
        r = piloto.get(f"{V1}/gastos", params={"limite": 1, **({"cursor": cursor} if cursor else {})}).json()
        assert len(r["items"]) == 1
        vistos.append(r["items"][0]["id"])
        if r["siguiente"] is None:
            break
        assert r["siguiente"] == str(r["items"][0]["id"])                          # el cursor es el último id entregado
        cursor = r["siguiente"]
    assert vistos == completos
    assert [v["id"] for v in _todos(piloto, f"{V1}/viajes", limite=1)] == \
        [v["id"] for v in piloto.get(f"{V1}/viajes", params={"limite": 100}).json()["items"]]


def test_limites_y_cursor_invalidos(piloto):
    for params in ({"limite": 0}, {"limite": 101}, {"limite": "x"}):
        _contrato(piloto.get(f"{V1}/viajes", params=params), 422, "VALIDATION_ERROR")
    cuerpo = _contrato(piloto.get(f"{V1}/gastos", params={"cursor": "abc"}), 422, "VALIDATION_ERROR")
    assert "cursor" in cuerpo["error"]["fields"]
    _contrato(piloto.get(f"{V1}/gastos/abc"), 422, "VALIDATION_ERROR")


# ---------- contrato publicado ----------
def test_el_openapi_versionado_coincide_con_la_api():
    """Si falla: ejecuta `python -m datos.exportar_contrato` y revisa que `contracts/api-v1.md` siga diciendo lo mismo."""
    assert exportar_contrato.DESTINO.read_text(encoding="utf-8") == exportar_contrato.texto()
    rutas = exportar_contrato.contrato()["paths"]
    esperadas = {("post", "/auth/login"), ("get", "/auth/me"), ("post", "/auth/logout"), ("get", "/viajes"), ("get", "/viajes/{id}"),
                 ("get", "/gastos"), ("get", "/gastos/contable"), ("get", "/gastos/{id}"), ("post", "/gastos"), ("post", "/gastos/{id}/justificaciones"),
                 ("post", "/gastos/{id}/revision"),
                 ("get", "/lugares"), ("get", "/cotizaciones/formulario"), ("post", "/cotizaciones"), ("get", "/cotizaciones/{id}"), ("post", "/cotizaciones/{id}/decision"),
                 ("get", "/resumen"), ("post", "/viajes/{id}/estado"),
                 ("get", "/documentos/{id}/contenido"), ("post", "/asistente"), ("post", "/asistente/voz")}
    esperadas |= {("get", "/kpis"), ("get", "/kpis/personas/{id}"), ("get", "/kpis/exportar.csv")}
    assert {(m, r.removeprefix(V1)) for r, ops in rutas.items() for m in ops} == esperadas
