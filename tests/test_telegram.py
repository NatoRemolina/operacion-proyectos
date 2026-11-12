"""Canal de Telegram con el bot simulado: ninguna prueba sale a internet."""
import pytest

from app import config, db
from app.servicios import telegram

SECRETO = {"X-Telegram-Bot-Api-Secret-Token": "secreto-de-pruebas"}
_serie = iter(range(1000, 9999))


@pytest.fixture()
def bot(monkeypatch, ejemplos):
    """Activa el canal y captura lo que el bot respondería; las descargas entregan un recibo de ejemplo."""
    enviados = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", SECRETO["X-Telegram-Bot-Api-Secret-Token"])
    monkeypatch.setattr(config, "TELEGRAM_BOT_NOMBRE", "bot_de_pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: enviados.append((metodo, d)) or {})
    archivos = {"gasolina": ejemplos / "recibo_gasolina.png", "hotel": ejemplos / "factura_hotel.pdf"}
    monkeypatch.setattr(telegram, "descargar", lambda file_id: b"OggS" + b"\x00" * 64 if file_id == "voz" else archivos[file_id].read_bytes())
    return enviados


def _entrega(anonimo, chat, update_id=None, **mensaje):
    cuerpo = {"update_id": update_id or next(_serie), "message": {"chat": {"id": chat, "type": "private"}, "from": {"username": "piloto_tg"}, **mensaje}}
    return anonimo.post("/telegram/webhook", json=cuerpo, headers=SECRETO)


def _ultimo(bot) -> str:
    return next(d["text"] for m, d in reversed(bot) if m == "sendMessage")


def _vincular(anonimo, correo, chat):
    uid = db.uno("select id from usuarios where correo=:c", c=correo)["id"]
    codigo = telegram.nuevo_vinculo(uid)["codigo"]
    _entrega(anonimo, chat, text=f"/start {codigo}")
    return uid, codigo


def test_sin_la_cabecera_secreta_no_entra_nada(anonimo, bot):
    cuerpo = {"update_id": 1, "message": {"chat": {"id": 5, "type": "private"}, "text": "hola"}}
    assert anonimo.post("/telegram/webhook", json=cuerpo).status_code == 403
    assert anonimo.post("/telegram/webhook", json=cuerpo, headers={"X-Telegram-Bot-Api-Secret-Token": "otro"}).status_code == 403
    assert not db.uno("select id from telegram_mensajes where update_id=1")


def test_canal_apagado_sin_configuracion(anonimo, monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    assert anonimo.post("/telegram/webhook", json={}, headers=SECRETO).status_code == 403


def test_chat_sin_vincular_no_registra_gastos(anonimo, bot):
    antes = db.uno("select count(*) n from gastos")["n"]
    assert _entrega(anonimo, 777001, photo=[{"file_id": "gasolina", "file_size": 1000}]).json()["estado"] == "sin_vincular"
    assert db.uno("select count(*) n from gastos")["n"] == antes and "no está vinculado" in _ultimo(bot)


def test_el_codigo_de_vinculo_sirve_una_sola_vez(anonimo, bot):
    uid, codigo = _vincular(anonimo, "piloto@demo.local", 777002)
    assert db.uno("select telegram_chat_id c from usuarios where id=:i", i=uid)["c"] == 777002
    assert "P-000" in _ultimo(bot)
    assert _entrega(anonimo, 777003, text=f"/start {codigo}").json()["estado"] == "sin_vincular"   # ya usado, desde otro chat
    assert not db.uno("select id from usuarios where telegram_chat_id=777003")
    assert not db.uno("select id from vinculos_telegram where huella=:c", c=codigo)               # solo se guarda la huella


def test_la_foto_de_un_recibo_queda_en_el_viaje(anonimo, bot, viaje_aprobado):
    uid, _ = _vincular(anonimo, "piloto@demo.local", 777002)
    entrega = next(_serie)
    foto = dict(photo=[{"file_id": "hotel", "file_size": 900}, {"file_id": "hotel", "file_size": 90_000}], caption=viaje_aprobado["codigo"])
    assert _entrega(anonimo, 777002, entrega, **foto).json()["estado"] == "procesado"
    g = db.uno("select g.*, d.canal from gastos g join documentos d on d.id=g.documento_id where g.usuario_id=:u order by g.id desc limit 1", u=uid)
    assert g["canal"] == "telegram" and g["viaje_id"] == viaje_aprobado["id"] and g["proyecto_id"] == viaje_aprobado["proyecto_id"]
    assert f"Gasto #{g['id']}" in _ultimo(bot) and viaje_aprobado["codigo"] in _ultimo(bot)
    firmado = db.uno("select usuario_id from eventos where entidad='gasto' and entidad_id=:i order by id limit 1", i=g["id"])
    assert firmado["usuario_id"] == uid                                       # el hecho queda firmado por la persona
    # Telegram reintenta la misma entrega: no se crea otro gasto
    assert _entrega(anonimo, 777002, entrega, **foto).json()["estado"] == "repetido"
    assert db.uno("select count(*) n from gastos where usuario_id=:u and viaje_id=:v", u=uid, v=viaje_aprobado["id"])["n"] >= 1
    assert db.uno("select count(*) n from telegram_mensajes where update_id=:e", e=entrega)["n"] == 1
    assert db.uno("select count(*) n from gastos g join documentos d on d.id=g.documento_id where d.canal='telegram' and g.id>=:i", i=g["id"])["n"] == 1


def test_persona_sin_viaje_el_gasto_se_guarda_en_revision(cliente, anonimo, bot):
    cliente.post("/admin/usuarios", data={"correo": "nueva@demo.local", "nombre": "Piloto Nueva", "rol": "piloto", "clave": "clave-de-nueva-1"})
    uid, _ = _vincular(anonimo, "nueva@demo.local", 777010)
    _entrega(anonimo, 777010, photo=[{"file_id": "gasolina", "file_size": 1000}])
    g = db.uno("select * from gastos where usuario_id=:u order by id desc limit 1", u=uid)
    assert g["estado"] == "revision" and "sin_viaje" in db.de_json(g["motivos"], []) and "quedó en revisión" in _ultimo(bot)


def test_comando_viaje_y_evidencias(anonimo, bot, viaje_aprobado):
    uid, _ = _vincular(anonimo, "piloto@demo.local", 777002)
    _entrega(anonimo, 777002, text=f"/viaje {viaje_aprobado['codigo']}")
    assert db.uno("select viaje_activo_id v from usuarios where id=:i", i=uid)["v"] == viaje_aprobado["id"]
    assert viaje_aprobado["codigo"] in _ultimo(bot) and "USD" in _ultimo(bot)
    antes = db.uno("select count(*) n from gastos")["n"]
    _entrega(anonimo, 777002, voice={"file_id": "voz", "file_size": 68})
    _entrega(anonimo, 777002, text="El parqueadero del hotel no dio recibo")
    tipos = [d["tipo"] for d in db.todos("select tipo from documentos where viaje_id=:v and usuario_id=:u and tipo<>'soporte' order by id",
                                         v=viaje_aprobado["id"], u=uid)]
    assert tipos == ["audio", "nota"]
    assert db.uno("select count(*) n from gastos")["n"] == antes             # las evidencias no crean gastos
    _entrega(anonimo, 777002, text="/viaje ninguno")
    assert db.uno("select viaje_activo_id v from usuarios where id=:i", i=uid)["v"] is None


def test_aviso_al_titular_cuando_se_aprueba_su_presupuesto(cliente, anonimo, bot, nuevo_viaje):
    _vincular(anonimo, "piloto@demo.local", 777002)
    v = nuevo_viaje(aprobar=True)
    assert "presupuesto aprobado" in _ultimo(bot) and v["codigo"] in _ultimo(bot)


def test_un_fallo_de_red_no_expone_la_clave_del_bot(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-muy-secreta")
    def falla(*a, **k):
        raise httpx.ConnectError("no se pudo conectar a https://api.telegram.org/botclave-muy-secreta/sendMessage")
    monkeypatch.setattr(httpx, "post", falla)
    with pytest.raises(telegram.ErrorTelegram) as e:
        telegram.enviar(1, "hola")
    assert "clave-muy-secreta" not in str(e.value) and e.value.__cause__ is None
