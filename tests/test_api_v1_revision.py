"""API v1, revisión completa de un gasto en la web nueva: lo que administración necesita para revisar sin ir a las
pantallas de administración (lectura original, cómo mostrar el soporte, categorías y viajes a los que reasignar) y la
nota de voz de una justificación. La escritura es `POST /gastos/{id}/revision`, que ya existía.

Las lecturas de recibos salen de las lecturas guardadas de `datos/ejemplos` (sin modelo de lenguaje en las pruebas).
"""
import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, justificaciones, viajes

V1 = "/api/v1"
AUDIO = b"OggS" + b"\x00" * 60   # basta la cabecera: el tipo se reconoce por el contenido


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    assert r.headers["Cache-Control"] == "no-store"
    return cuerpo


def _enviar(c: TestClient, ejemplos, nombre: str, viaje_id: int | None = None) -> dict:
    datos = {"viaje_id": str(viaje_id)} if viaje_id else {}
    r = c.post(f"{V1}/gastos", files={"archivo": (nombre, (ejemplos / nombre).read_bytes(), "application/octet-stream")},
               data=datos, headers=_csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def _revision(c: TestClient, gid: int):
    return c.get(f"{V1}/gastos/{gid}/revision")


def _persona(correo: str) -> dict:
    return db.uno("select * from usuarios where correo=:c", c=correo)


@pytest.fixture(autouse=True, scope="module")
def _sin_rastro():
    """Los recibos de ejemplo de este módulo no deben volver «duplicados» los que suben otras pruebas después."""
    antes = db.uno("select coalesce(max(id), 0) n from gastos")["n"]
    documentos = db.uno("select coalesce(max(id), 0) n from documentos")["n"]
    yield
    for tabla, campo in (("justificaciones", "gasto_id"), ("eventos", "entidad_id"), ("gastos", "id")):
        filtro = " and entidad='gasto'" if tabla == "eventos" else ""
        db.ejecutar(f"delete from {tabla} where {campo}>:n{filtro}", n=antes)
    db.ejecutar("delete from documentos where id>:n", n=documentos)   # también la nota de voz, que cuelga del viaje


@pytest.fixture(scope="module")
def recibo(piloto, viaje_aprobado, ejemplos) -> dict:
    """Un recibo del piloto, en su viaje aprobado."""
    return _enviar(piloto, ejemplos, "recibo_lisboa.png", viaje_aprobado["id"])


# ---------- acceso ----------
def test_los_datos_de_revision_son_solo_de_administracion(anonimo, piloto, gestor, recibo):
    _error(_revision(anonimo, recibo["id"]), 401, "UNAUTHENTICATED")
    for c in (piloto, gestor):   # el piloto ve su gasto y el gestor lo ve por su proyecto, pero no lo revisan
        _error(_revision(c, recibo["id"]), 403, "FORBIDDEN")


def test_un_gasto_que_no_existe_responde_404(cliente):
    _error(_revision(cliente, 999_999), 404, "NOT_FOUND")


# ---------- lectura original ----------
def test_trae_la_lectura_original_del_recibo(cliente, recibo):
    r = _revision(cliente, recibo["id"])
    assert r.status_code == 200, r.text
    assert r.headers["Cache-Control"] == "no-store"
    datos = r.json()
    original = db.de_json(db.uno("select extraido from gastos where id=:i", i=recibo["id"])["extraido"])
    leida = datos["lectura_original"]
    assert leida["comercio"] == original["comercio"] and leida["fecha"] == original["fecha"]
    assert leida["moneda"] == original["moneda"] and leida["total"] == f"{original['total']:.2f}"
    assert leida["confianza"] == original["confianza"] and leida["dudas"] == original.get("dudas", [])
    assert datos["gasto_id"] == recibo["id"] and datos["version"] == recibo["version"]


def test_la_lectura_original_no_cambia_al_corregir(cliente, piloto, viaje_aprobado, ejemplos):
    g = _enviar(piloto, ejemplos, "recibo_taxi.png", viaje_aprobado["id"])
    antes = _revision(cliente, g["id"]).json()
    r = cliente.post(f"{V1}/gastos/{g['id']}/revision", headers=_csrf(cliente),
                     json={"version": antes["version"], "accion": "guardar", "comercio": "Taxi corregido a mano",
                           "metodo_pago": "Tarjeta de la empresa"})
    assert r.status_code == 200, r.text
    despues = _revision(cliente, g["id"]).json()
    assert r.json()["comercio"] == "Taxi corregido a mano" and despues["lectura_original"] == antes["lectura_original"]
    # Lo que la ficha no trae y la revisión sí edita
    assert despues["metodo_pago"] == "Tarjeta de la empresa" and despues["version"] == antes["version"] + 1


def test_sin_lectura_guardada_la_lectura_original_es_nula(cliente, recibo):
    gid = db.insertar("gastos", usuario_id=_persona("piloto@demo.local")["id"], viajero_id=1, comercio=None,
                      estado="revision", creado=db.ahora())
    try:
        datos = _revision(cliente, gid).json()
        assert datos["lectura_original"] is None and datos["soporte"] is None
    finally:
        db.ejecutar("delete from gastos where id=:i", i=gid)


# ---------- soporte ----------
@pytest.mark.parametrize("nombre, forma", [("recibo_lisboa.png", "imagen"), ("factura_hotel.pdf", "pdf"),
                                           ("confirmacion_hotel.html", "descarga"), ("reserva_hotel.eml", "descarga")])
def test_dice_como_mostrar_el_soporte(cliente, piloto, viaje_aprobado, ejemplos, nombre, forma):
    g = _enviar(piloto, ejemplos, nombre, viaje_aprobado["id"])
    soporte = _revision(cliente, g["id"]).json()["soporte"]
    assert soporte["forma"] == forma and soporte["documento_id"] == g["documento_id"]
    assert soporte["nombre"]


# ---------- opciones para corregir ----------
def test_ofrece_las_categorias_con_su_nombre(cliente, recibo):
    categorias = _revision(cliente, recibo["id"]).json()["categorias"]
    assert categorias == [{"clave": c, "nombre": n} for c, n in config.CATEGORIAS.items()]


def test_ofrece_los_viajes_a_los_que_se_puede_reasignar(cliente, recibo, viaje_aprobado, nuevo_viaje):
    rechazado = nuevo_viaje(aprobar=False)
    db.actualizar("viajes", rechazado["id"], estado="rechazado")
    opciones = {v["id"]: v for v in _revision(cliente, recibo["id"]).json()["viajes"]}
    assert rechazado["id"] not in opciones   # como en la revisión de administración: un viaje rechazado no recibe gastos
    v = opciones[viaje_aprobado["id"]]
    assert v["codigo"] == viaje_aprobado["codigo"] and v["estado"] == "aprobado" and v["estado_texto"]
    assert set(v) == {"id", "codigo", "estado", "estado_texto", "titular", "origen", "destino", "ida", "regreso"}


# ---------- nadie revisa lo suyo ----------
def test_dice_si_el_gasto_es_propio_y_por_que_no_lo_revisa(cliente, recibo, ejemplos):
    ajeno = _revision(cliente, recibo["id"]).json()
    assert ajeno["propio"] is False and ajeno["aviso_propio"] is None
    suyo = _enviar(cliente, ejemplos, "recibo_diner.png")   # administración lo sube sin viaje: es suyo
    datos = _revision(cliente, suyo["id"]).json()
    assert datos["propio"] is True and viajes.NO_AUTORREVISAR in datos["aviso_propio"]


# ---------- nota de voz de una justificación ----------
@pytest.fixture(scope="module")
def nota_de_voz(recibo) -> int:
    return justificaciones.registrar(recibo["id"], _persona("piloto@demo.local"), "web", "", AUDIO, "nota.ogg")


def test_la_nota_de_voz_se_escucha_con_la_visibilidad_del_gasto(cliente, piloto, gestor, recibo, nota_de_voz):
    for c in (piloto, gestor, cliente):
        r = c.get(f"{V1}/gastos/{recibo['id']}/justificaciones/{nota_de_voz}/audio")
        assert r.status_code == 200, r.text
        assert r.content == AUDIO and r.headers["content-type"].startswith("audio/ogg")
        assert r.headers["X-Content-Type-Options"] == "nosniff" and "no-store" in r.headers["Cache-Control"]


def test_la_nota_de_voz_ajena_o_de_otro_gasto_responde_404(anonimo, piloto2, cliente, piloto, recibo, nota_de_voz,
                                                            viaje_aprobado, ejemplos):
    ruta = f"{V1}/gastos/{recibo['id']}/justificaciones/{nota_de_voz}/audio"
    _error(anonimo.get(ruta), 401, "UNAUTHENTICATED")
    _error(piloto2.get(ruta), 404, "NOT_FOUND")   # no ve el gasto: no sabe que existe
    otro = _enviar(piloto, ejemplos, "recibo_gasolina.png", viaje_aprobado["id"])
    _error(cliente.get(f"{V1}/gastos/{otro['id']}/justificaciones/{nota_de_voz}/audio"), 404, "NOT_FOUND")
    escrita = justificaciones.registrar(recibo["id"], _persona("piloto@demo.local"), "web", "Taxi al aeropuerto con el equipo")
    _error(cliente.get(f"{V1}/gastos/{recibo['id']}/justificaciones/{escrita}/audio"), 404, "NOT_FOUND")


# ---------- el recorrido dice si hubo correcciones (QA M-14) ----------
def _gasto_de_viaje(v: dict, comercio: str, total: float = 20) -> int:
    return db.insertar("gastos", viaje_id=v["id"], proyecto_id=v["proyecto_id"], viajero_id=v["viajero_id"], usuario_id=v["usuario_id"],
                       comercio=comercio, fecha=v["ida"], categoria="otros", total=total, moneda="USD", confianza=1.0,
                       estado="revision", creado=db.ahora(), version=0)


def _ultimo_paso(gid: int) -> str:
    return db.uno("select paso from eventos where entidad='gasto' and entidad_id=:i order by id desc limit 1", i=gid)["paso"]


def _revisar(c: TestClient, gid: int, **cuerpo):
    r = c.post(f"{V1}/gastos/{gid}/revision", json=cuerpo, headers=_csrf(c))
    assert r.status_code == 200, r.text
    return r.json()


def test_aprobar_sin_cambios_deja_aprobado_sin_corregido(cliente, nuevo_viaje):
    gid = _gasto_de_viaje(nuevo_viaje(), "Sonda aprobar sin cambios")
    assert _revisar(cliente, gid, version=0, accion="aprobar")["estado"] == "aprobado"
    assert _ultimo_paso(gid) == "aprobado en revisión"


def test_aprobar_con_cambios_deja_corregido_y_aprobado(cliente, nuevo_viaje):
    gid = _gasto_de_viaje(nuevo_viaje(), "Sonda aprobar con cambios")
    _revisar(cliente, gid, version=0, accion="aprobar", comercio="Sonda corregida a mano")
    assert _ultimo_paso(gid) == "corregido y aprobado"


def test_mandar_los_mismos_datos_no_cuenta_como_correccion(cliente, nuevo_viaje):
    v = nuevo_viaje()
    gid = _gasto_de_viaje(v, "Sonda mismos datos")
    _revisar(cliente, gid, version=0, accion="aprobar", comercio="Sonda mismos datos", total="20.00", moneda="usd", viaje_id=v["id"])
    assert _ultimo_paso(gid) == "aprobado en revisión"


def test_guardar_sin_cambios_no_dice_corregido(cliente, nuevo_viaje):
    gid = _gasto_de_viaje(nuevo_viaje(), "Sonda guardar sin cambios")
    assert _revisar(cliente, gid, version=0, accion="guardar")["estado"] == "revision"
    assert _ultimo_paso(gid) == "revisado, sigue en revisión"


def test_lo_aprobado_sin_cambios_cuenta_como_aprobado_en_revision(cliente, nuevo_viaje):
    """El Excel contable, el tiempo hasta aprobar y la memoria del asistente leen la bitácora: el paso nuevo cuenta igual."""
    from datetime import date

    from app.servicios import contable, memoria, metricas
    v = nuevo_viaje()
    gid = _gasto_de_viaje(v, "Sonda Excel sin cambios")
    _revisar(cliente, gid, version=0, accion="aprobar")
    dia = date.fromisoformat(v["ida"])
    fila = next(f for f in contable._filas(_persona("admin@demo.local"), dia, dia, None, ("aprobado",)) if f["id"] == gid)
    assert fila["aprobado_en_revision"]   # el Excel dice quién lo aprobó, no «automática»
    assert {"aprobado en revisión", "revisado, sigue en revisión"} <= set(memoria.EVENTOS_RELEVANTES)
    assert "aprobado en revisión" in metricas.PASOS_APROBACION


# ---------- ronda 1: la categoría tiene que ser del catálogo ----------
def test_una_categoria_que_no_existe_responde_422_en_su_campo(cliente, nuevo_viaje):
    gid = _gasto_de_viaje(nuevo_viaje(), "Sonda categoría inventada")
    r = cliente.post(f"{V1}/gastos/{gid}/revision", headers=_csrf(cliente),
                     json={"version": 0, "accion": "guardar", "categoria": "joyeria"})
    cuerpo = _error(r, 422, "VALIDATION_ERROR")
    assert "categoria" in cuerpo["error"]["fields"] and "Transporte terrestre" in cuerpo["error"]["fields"]["categoria"]
    g = db.uno("select categoria, version from gastos where id=:i", i=gid)
    assert g["categoria"] == "otros" and g["version"] == 0


def test_la_pantalla_de_administracion_tampoco_acepta_una_categoria_inventada(cliente, nuevo_viaje):
    v = nuevo_viaje()
    gid = _gasto_de_viaje(v, "Sonda categoría Jinja")
    r = cliente.post(f"/gastos/{gid}", data={"accion": "guardar", "version": 0, "categoria": "joyeria", "comercio": "Sonda categoría Jinja",
                                             "fecha": v["ida"], "total": "20", "moneda": "USD"}, follow_redirects=False)
    assert r.status_code == 303 and "revision=" in r.headers["location"]
    assert db.uno("select categoria, version from gastos where id=:i", i=gid) == {"categoria": "otros", "version": 0}
