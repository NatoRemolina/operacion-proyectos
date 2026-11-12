"""Justificación de cada gasto: por escrito o con nota de voz, desde la web, la API v1 y Telegram."""
import pytest
from test_telegram import SECRETO, _ultimo, bot  # noqa: F401  (bot es un fixture)

from app import api_v1, db
from app.servicios import acceso, justificaciones, memoria, telegram

V1 = "/api/v1"
AUDIO = b"OggS" + b"\x00" * 64
_serie = iter(range(51000, 59999))


def _gasto_web(cliente_, ejemplos, viaje_id: int, justificacion: str = "") -> int:
    r = cliente_.post("/gastos/cargar", data={"canal": "web", "viaje_id": viaje_id, "justificacion": justificacion},
                      headers={"X-Envio": "pagina"},
                      files={"archivos": ("r.png", (ejemplos / "recibo_gasolina.png").read_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["gastos"][0]


def _filas(gid: int) -> list[dict]:
    return db.todos("select * from justificaciones where gasto_id=:g order by id", g=gid)


# ---------- web ----------
def test_al_cargar_un_gasto_se_guarda_su_justificacion(piloto, ejemplos, viaje_aprobado):
    gid = _gasto_web(piloto, ejemplos, viaje_aprobado["id"], "  Gasolina del carro   de alquiler para ir al set ")
    [j] = _filas(gid)
    assert (j["tipo"], j["canal"], j["texto"], j["transcripcion"]) == ("texto", "web", "Gasolina del carro de alquiler para ir al set", "no_aplica")
    assert j["palabras"] == 9 and j["usuario_id"] == db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]
    assert "Gasolina del carro de alquiler" in piloto.get(f"/gastos/{gid}").text
    assert db.uno("select id from eventos where entidad='gasto' and entidad_id=:g and paso='justificación recibida'", g=gid)


def test_sin_justificacion_el_gasto_igual_se_registra_y_se_puede_justificar_despues(piloto, ejemplos, viaje_aprobado):
    gid = _gasto_web(piloto, ejemplos, viaje_aprobado["id"])
    assert not _filas(gid) and "¿Para qué fue este gasto?" in piloto.get(f"/gastos/{gid}").text
    r = piloto.post(f"/gastos/{gid}/justificacion", data={"texto": "ok"}, follow_redirects=False)
    assert r.status_code == 303 and "aviso=" in r.headers["location"] and not _filas(gid)       # demasiado corta
    piloto.post(f"/gastos/{gid}/justificacion", data={"texto": "Peaje de la autopista hacia el lago"})
    piloto.post(f"/gastos/{gid}/justificacion", data={}, files={"audio": ("voz.ogg", AUDIO, "audio/ogg")})
    texto, audio = _filas(gid)
    assert texto["tipo"] == "texto" and audio["tipo"] == "audio" and audio["transcripcion"] == "pendiente"
    assert db.uno("select tipo, mime from documentos where id=:d", d=audio["documento_id"]) == {"tipo": "audio", "mime": "audio/ogg"}
    oido = piloto.get(f"/gastos/{gid}/justificacion/{audio['id']}/audio")
    assert oido.status_code == 200 and oido.headers["content-type"] == "audio/ogg" and oido.content == AUDIO


def test_solo_justifica_quien_hizo_el_gasto(piloto, piloto2, gestor, cliente, ejemplos, viaje_aprobado):
    gid = _gasto_web(piloto, ejemplos, viaje_aprobado["id"])
    # Otra persona no lo ve: 404, sin revelar que existe
    assert piloto2.post(f"/gastos/{gid}/justificacion", data={"texto": "No es mío"}, follow_redirects=False).status_code == 404
    assert piloto2.get(f"/gastos/{gid}/justificacion/1/audio").status_code == 404
    # El gestor y administración lo ven, pero la justificación es la voz de quien gastó
    for quien in (gestor, cliente):
        r = quien.post(f"/gastos/{gid}/justificacion", data={"texto": "Lo justifico por otra persona"}, follow_redirects=False)
        assert r.status_code == 303 and "Solo%20quien" in r.headers["location"]
    assert not _filas(gid)
    assert "La persona aún no ha justificado este gasto" in cliente.get(f"/gastos/{gid}").text


# ---------- API v1 ----------
def _csrf(c) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def test_la_api_recibe_y_devuelve_las_justificaciones(piloto, piloto2, gestor, ejemplos, viaje_aprobado):
    r = piloto.post(f"{V1}/gastos", headers=_csrf(piloto), data={"viaje_id": str(viaje_aprobado["id"]), "justificacion": "Hotel cerca del set"},
                    files={"archivo": ("r.png", (ejemplos / "recibo_gasolina.png").read_bytes(), "image/png")})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    [j] = r.json()["justificaciones"]
    assert j["texto"] == "Hotel cerca del set" and j["canal"] == "api" and j["tipo"] == "texto" and j["transcripcion"] == "no_aplica"

    otra = piloto.post(f"{V1}/gastos/{gid}/justificaciones", json={"texto": "Dos noches por el cambio de fecha"}, headers=_csrf(piloto))
    assert otra.status_code == 201 and [x["texto"] for x in otra.json()["justificaciones"]][-1] == "Dos noches por el cambio de fecha"
    assert piloto.get(f"{V1}/gastos/{gid}").json()["justificaciones"] == otra.json()["justificaciones"]

    assert piloto.post(f"{V1}/gastos/{gid}/justificaciones", json={"texto": "Sin token"}).json()["error"]["code"] == "CSRF_INVALID"
    assert piloto.post(f"{V1}/gastos/{gid}/justificaciones", json={"texto": "x"}, headers=_csrf(piloto)).status_code == 422
    assert piloto2.post(f"{V1}/gastos/{gid}/justificaciones", json={"texto": "No es mío"}, headers=_csrf(piloto2)).status_code == 404
    assert gestor.post(f"{V1}/gastos/{gid}/justificaciones", json={"texto": "Por otra persona"}, headers=_csrf(gestor)).status_code == 403
    assert len(_filas(gid)) == 2


# ---------- Telegram ----------
@pytest.fixture()
def chat(anonimo, bot):  # noqa: F811
    """Una cuenta nueva con su chat vinculado, para que sus gastos no se mezclen con los de otras pruebas."""
    correo = f"tg-{next(_serie)}@demo.local"
    uid = acceso.crear_usuario(correo, "Persona Telegram", "piloto", "clave-de-pruebas-2026")
    chat_id = next(_serie)
    entregar = lambda **m: anonimo.post("/telegram/webhook", headers=SECRETO, json={  # noqa: E731
        "update_id": next(_serie), "message": {"chat": {"id": chat_id, "type": "private"}, "from": {"username": "tg"}, **m}}).json()
    entregar(text=f"/start {telegram.nuevo_vinculo(uid)['codigo']}")
    return uid, entregar


def _ultimo_gasto(uid: int) -> int:
    return db.uno("select id from gastos where usuario_id=:u order by id desc limit 1", u=uid)["id"]


def test_el_bot_pregunta_para_que_fue_y_guarda_la_respuesta(chat, bot):  # noqa: F811
    uid, entregar = chat
    entregar(photo=[{"file_id": "gasolina", "file_size": 1000}])
    assert justificaciones.PREGUNTA in _ultimo(bot)
    gid = _ultimo_gasto(uid)
    assert entregar(text="Gasolina para llegar al set del lago")["estado"] == "procesado"
    [j] = _filas(gid)
    assert (j["canal"], j["tipo"], j["texto"]) == ("telegram", "texto", "Gasolina para llegar al set del lago")
    assert f"justificación del gasto #{gid}" in _ultimo(bot)
    assert db.uno("select tipo, gasto_id from telegram_mensajes where usuario_id=:u order by id desc limit 1", u=uid) == \
        {"tipo": "justificacion", "gasto_id": gid}
    # Ya justificado: el siguiente texto vuelve a ser una nota del viaje
    entregar(text="Mañana empezamos temprano")
    assert len(_filas(gid)) == 1 and "Nota guardada" in _ultimo(bot)


def test_el_pie_de_la_foto_es_la_justificacion(chat, bot):  # noqa: F811
    uid, entregar = chat
    entregar(photo=[{"file_id": "hotel", "file_size": 1000}], caption="V-2026-9999 Hotel de la segunda noche por lluvia")
    [j] = _filas(_ultimo_gasto(uid))
    assert j["texto"] == "Hotel de la segunda noche por lluvia"          # sin el código del viaje
    assert justificaciones.PREGUNTA not in _ultimo(bot)


def test_una_nota_de_voz_justifica_el_ultimo_gasto(chat, bot):  # noqa: F811
    uid, entregar = chat
    entregar(photo=[{"file_id": "gasolina", "file_size": 1000}])
    gid = _ultimo_gasto(uid)
    entregar(voice={"file_id": "voz", "file_size": 68})
    [j] = _filas(gid)
    assert j["tipo"] == "audio" and j["transcripcion"] == "pendiente" and j["documento_id"]   # sin modelo, queda pendiente
    assert f"justificación del gasto #{gid}" in _ultimo(bot)


# ---------- asistente y medición ----------
def test_el_asistente_lee_la_justificacion_y_no_duplica_el_audio(piloto, ejemplos, viaje_aprobado):
    gid = _gasto_web(piloto, ejemplos, viaje_aprobado["id"], "Comida del equipo en la jornada larga")
    piloto.post(f"/gastos/{gid}/justificacion", data={}, files={"audio": ("voz.ogg", AUDIO, "audio/ogg")})
    fichas = memoria.todas_las_fichas()
    propias = [f for f in fichas if f["tipo"] == "justificacion" and f"gasto #{gid}" in f["texto"]]
    assert len(propias) == 1 and "Comida del equipo" in propias[0]["texto"] and propias[0]["persona"].startswith("P-")
    audio = _filas(gid)[-1]["documento_id"]
    assert not [f for f in fichas if f["entidad"] == "documentos" and f["entidad_id"] == audio]


def test_cobertura_cuenta_los_gastos_justificados(piloto, ejemplos, viaje_aprobado):
    antes = justificaciones.cobertura()
    _gasto_web(piloto, ejemplos, viaje_aprobado["id"], "Taxi del aeropuerto al hotel")
    _gasto_web(piloto, ejemplos, viaje_aprobado["id"])
    despues = justificaciones.cobertura()
    assert despues["gastos"] == antes["gastos"] + 2 and despues["con_justificacion"] == antes["con_justificacion"] + 1
    assert 0 < despues["tasa"] < 1


def test_con_modelo_la_nota_de_voz_se_transcribe(piloto, ejemplos, viaje_aprobado, monkeypatch):
    from app.servicios import llm
    pedidos = []
    monkeypatch.setattr(llm, "activo", lambda: True)
    monkeypatch.setattr(llm, "generar", lambda contenidos, **k: pedidos.append(k) or
                        {"content": {"parts": [{"text": "  Pagué el parqueadero del set porque el carro del equipo no cabía. "}]}})
    gid = _gasto_web(piloto, ejemplos, viaje_aprobado["id"])
    piloto.post(f"/gastos/{gid}/justificacion", data={"texto": "Parqueadero"}, files={"audio": ("voz.ogg", AUDIO, "audio/ogg")})
    [j] = _filas(gid)
    assert j["transcripcion"] == "hecha" and pedidos[0]["uso"] == "transcripcion"
    assert j["texto"] == "Parqueadero Pagué el parqueadero del set porque el carro del equipo no cabía."
    assert "carro del equipo" in db.uno("select texto from documentos where id=:d", d=j["documento_id"])["texto"]
    # Si el modelo falla, el audio se conserva y queda marcado para reintentar
    def falla(*a, **k):
        raise llm.ErrorDelModelo("sin respuesta")
    monkeypatch.setattr(llm, "generar", falla)
    piloto.post(f"/gastos/{gid}/justificacion", data={}, files={"audio": ("voz.ogg", AUDIO, "audio/ogg")})
    assert _filas(gid)[-1]["transcripcion"] == "fallida" and _filas(gid)[-1]["documento_id"]
