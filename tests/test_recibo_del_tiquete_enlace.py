"""I-7 (QA del 16 nov): el recibo del tiquete cargado antes de la compra se enlaza, y el tiquete no cuenta dos veces.

- La lectura guardada de `correo_tiquete.eml` trae su localizador (QX7T2L): sin claves, el recibo del ejemplo se enlaza.
- Con el importe que coincide, el recibo también se enlaza si nombra un número de vuelo del itinerario decidido (en el
  comercio, en las líneas o en lo leído). Sin importe que coincida, nada se enlaza.
- Red de seguridad: si no se enlaza pero hay otro gasto de vuelo del mismo importe, el gasto nuevo nace en revisión con
  «Posible duplicado del gasto #N (mismo importe)», al registrar la compra y al subir el recibo después.
- El mismo archivo no sostiene dos gastos: subirlo otra vez no se enlaza al tiquete; queda aparte, como duplicado.
"""
import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, compras, gastos, llm, tiempo, validacion, viajes

V1 = "/api/v1"
PEDIDO = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
          "ida": "2026-12-08", "regreso": "2026-12-11"}
EML = Path("datos/ejemplos/correo_tiquete.eml")
DUPLICADO = "Posible duplicado del gasto #{} (mismo importe)"


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


@pytest.fixture(autouse=True, scope="module")
def _sin_rastro():
    """Los gastos de estas pruebas se borran al final: no deben correr las listas ni los totales de otras pruebas."""
    antes = db.uno("select coalesce(max(id), 0) m from gastos")["m"]
    yield
    for g in db.todos("select id, documento_id from gastos where id>:m", m=antes):
        db.ejecutar("update compras set gasto_id=null where gasto_id=:g", g=g["id"])
        for sql in ("delete from envios_soporte where gasto_id=:g", "delete from justificaciones where gasto_id=:g",
                    "delete from eventos where entidad='gasto' and entidad_id=:g", "delete from gastos where id=:g"):
            db.ejecutar(sql, g=g["id"])
        if g["documento_id"]:
            db.ejecutar("delete from documentos where id=:d", d=g["documento_id"])


@pytest.fixture()
def modelo(monkeypatch):
    """Lectura con el modelo encendido, con un doble: cada prueba fija lo que «lee»."""
    for nombre, valor in (("MODELO_API_URL", "http://modelo.test"), ("MODELO_API_KEY", "clave-de-prueba"),
                          ("MODELO_NOMBRE", "modelo-de-prueba"), ("MODELO_FORMATO", "gemini")):
        monkeypatch.setattr(config, nombre, valor)
    doble = {"respuesta": {}}

    def generar(contenidos, **opciones):
        lectura = {"comercio": "Viajes Andinos", "fecha": tiempo.hoy().isoformat(), "categoria": "vuelo", "total": 461.30,
                   "moneda": "USD", "confianza": 0.99, "dudas": [], "numero_factura": None, **doble["respuesta"]}
        return {"content": {"parts": [{"text": json.dumps(lectura)}]}, "finishReason": "STOP"}

    monkeypatch.setattr(llm, "generar", generar)
    return doble


def _decidir(piloto: TestClient, con: str | None = None) -> tuple[dict, dict]:
    """Cotiza MIA → LAS y decide: la recomendada, o el vuelo que nombra `con` (por ejemplo «1851»)."""
    cot = piloto.post(f"{V1}/cotizaciones", json=PEDIDO, headers=_csrf(piloto)).json()
    vuelo_id = next(v["id"] for v in cot["vuelos"] if con in json.dumps(v)) if con else cot["recomendada_id"]
    cuerpo = {"vuelo_id": vuelo_id} | ({} if vuelo_id == cot["recomendada_id"] else {"motivo": "Es el vuelo del recibo"})
    r = piloto.post(f"{V1}/cotizaciones/{cot['id']}/decision", json=cuerpo, headers=_csrf(piloto))
    assert r.status_code in (200, 201), r.text
    return cot, r.json()["viaje"]


def _por_comprar(viaje_id: int) -> dict:
    assert viajes.cambiar_estado(viaje_id, "aprobar", "", _admin(), confirmar_precio=True)[0]
    c = db.uno("select * from compras where viaje_id=:v and activa=1", v=viaje_id)
    return compras.cambiar_estado(c["id"], "se_comprara", c["version"], "Se compra hoy", _admin())


def _registrar(c: dict, precio: Decimal, localizador: str | None = None) -> dict:
    c = db.uno("select * from compras where id=:i", i=c["id"])
    hecho = compras.registrar_compra(c["id"], c["version"], localizador or "Q" + uuid.uuid4().hex[:5].upper(), precio,
                                     "American", _admin())
    return db.uno("select * from compras where id=:i", i=hecho["id"])


def _subir(c: TestClient, viaje_id: int, contenido: bytes | None = None, nombre: str = "tiquete.png"):
    contenido = contenido if contenido is not None else b"\x89PNG\r\n\x1a\n" + uuid.uuid4().bytes
    tipo = "message/rfc822" if nombre.endswith(".eml") else "image/png"
    r = c.post(f"{V1}/gastos", files={"archivo": (nombre, contenido, tipo)}, data={"viaje_id": str(viaje_id)}, headers=_csrf(c))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _gasto(gid: int) -> dict:
    g = db.uno("select * from gastos where id=:i", i=gid)
    return {**g, "alertas": db.de_json(g["alertas"], []), "motivos": db.de_json(g["motivos"], []),
            "extraido": db.de_json(g["extraido"], {}) or {}}


def _vuelos(viaje_id: int) -> list[dict]:
    return db.todos("select id, total_usd, estado, documento_id from gastos where viaje_id=:v and categoria='vuelo' order by id",
                    v=viaje_id)


def _numero_decidido(viaje_id: int) -> str:
    return db.uno("select numero from tramos_vuelo where viaje_id=:v order by sentido, orden", v=viaje_id)["numero"]


# ---------- el caso del QA, sin claves ----------
def test_la_lectura_guardada_del_correo_del_tiquete_trae_su_localizador(piloto):
    _, v = _decidir(piloto, "1851")
    g = _gasto(_subir(piloto, v["id"], EML.read_bytes(), "correo_tiquete.eml"))
    # «reutilizado» si otra prueba ya subió el mismo archivo: entonces es la misma lectura guardada
    assert g["origen_dato"] in ("guardado", "reutilizado") and g["extraido"]["numero_factura"] == "QX7T2L"
    assert any("AA 1851" in (linea["descripcion"] or "") for linea in g["extraido"]["lineas"])


def test_el_recibo_del_ejemplo_cargado_antes_es_el_unico_gasto_del_tiquete(piloto):
    """Andrés sube el correo del tiquete con el viaje ya aprobado y después administración registra la compra con
    «American», QX7T2L y USD 588: un solo gasto de vuelo, el del recibo, enlazado a la compra."""
    _, v = _decidir(piloto, "1851")
    c = _por_comprar(v["id"])
    recibo = _subir(piloto, v["id"], EML.read_bytes(), "correo_tiquete.eml")
    compra = _registrar(c, Decimal("588"), "QX7T2L")
    assert [f["id"] for f in _vuelos(v["id"])] == [recibo]
    assert compra["gasto_id"] == recibo
    g = _gasto(recibo)
    if Decimal("588") > Decimal(str(c["precio_cotizado"])) * Decimal("1.1"):   # Main Cabin frente a la tarifa Basic cotizada
        assert g["estado"] == "revision" and compras.SOBRE_COTIZADO in g["motivos"]
    assert not any(a.endswith("(mismo importe)") for a in g["alertas"])


# ---------- enlace por número de vuelo ----------
@pytest.mark.parametrize("donde", ["comercio", "lineas"])
def test_sin_localizador_se_enlaza_por_el_numero_de_vuelo_con_el_mismo_importe(piloto, modelo, donde):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado, numero = Decimal(str(c["precio_cotizado"])), _numero_decidido(v["id"])
    modelo["respuesta"] = {"total": float(pagado)} | (
        {"comercio": f"Aerolínea ({numero})"} if donde == "comercio" else
        {"lineas": [{"descripcion": f"Miami - Las Vegas · {numero} · Economy", "cantidad": 1, "total": float(pagado)}]})
    recibo = _subir(piloto, v["id"])
    assert _registrar(c, pagado)["gasto_id"] == recibo
    assert [f["id"] for f in _vuelos(v["id"])] == [recibo]


def test_el_numero_de_vuelo_sin_el_mismo_importe_no_enlaza(piloto, modelo):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado, numero = Decimal(str(c["precio_cotizado"])), _numero_decidido(v["id"])
    modelo["respuesta"] = {"comercio": f"Aerolínea ({numero})", "total": float(pagado + 40)}   # otro importe
    recibo = _subir(piloto, v["id"])
    compra = _registrar(c, pagado)
    assert compra["gasto_id"] != recibo and len(_vuelos(v["id"])) == 2
    assert not any(a.endswith("(mismo importe)") for a in _gasto(compra["gasto_id"])["alertas"])


# ---------- red de seguridad contra el doble conteo ----------
def test_un_recibo_anterior_del_mismo_importe_que_no_se_enlaza_deja_la_compra_en_revision(piloto, modelo):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    modelo["respuesta"] = {"comercio": "Viajes Andinos", "total": float(pagado)}   # ni localizador ni número de vuelo
    recibo = _subir(piloto, v["id"])
    compra = _registrar(c, pagado)                                    # dentro de lo cotizado: sin la red, aprobada
    assert compra["gasto_id"] != recibo and len(_vuelos(v["id"])) == 2
    g = _gasto(compra["gasto_id"])
    assert g["estado"] == "revision" and DUPLICADO.format(recibo) in g["alertas"] and compras.DUPLICADO in g["motivos"]


def test_un_recibo_anterior_de_otro_importe_deja_dos_gastos_sin_la_alerta(piloto, modelo):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    modelo["respuesta"] = {"comercio": "Viajes Andinos", "total": 45.00}   # el equipaje
    recibo = _subir(piloto, v["id"])
    compra = _registrar(c, pagado)
    assert compra["gasto_id"] != recibo and len(_vuelos(v["id"])) == 2
    g = _gasto(compra["gasto_id"])
    assert g["estado"] == "aprobado" and not any(a.endswith("(mismo importe)") for a in g["alertas"])


def test_un_recibo_posterior_del_mismo_importe_que_no_se_une_queda_en_revision(piloto, modelo):
    """El tiquete ya tiene su recibo; otro recibo de vuelo (otro archivo, otro comercio, otra fecha) por el mismo importe
    no se une, y no se aprueba en silencio."""
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    compra = _registrar(c, pagado)
    modelo["respuesta"] = {"numero_factura": compra["localizador"], "total": float(pagado)}
    assert _subir(piloto, v["id"]) == compra["gasto_id"]               # el primero se une al tiquete
    modelo["respuesta"] = {"comercio": "Agencia del Sur", "fecha": "2026-11-02", "total": float(pagado)}
    otro = _gasto(_subir(piloto, v["id"]))
    assert otro["id"] != compra["gasto_id"]
    assert otro["estado"] == "revision" and DUPLICADO.format(compra["gasto_id"]) in otro["alertas"]


# ---------- el mismo archivo dos veces ----------
def _aprobados_con_el_archivo(contenido: bytes) -> list[int]:
    huella = hashlib.sha256(contenido).hexdigest()
    return [f["id"] for f in db.todos("""select g.id from gastos g join documentos d on d.id=g.documento_id
                                         where d.huella=:h and g.estado in ('aprobado', 'aprobado_auto')""", h=huella)]


def test_el_mismo_correo_subido_otra_vez_tras_enlazarse_queda_como_duplicado(piloto):
    _, v = _decidir(piloto, "1851")
    c = _por_comprar(v["id"])
    eml = EML.read_bytes()
    recibo = _subir(piloto, v["id"], eml, "correo_tiquete.eml")
    compra = _registrar(c, Decimal("588"), "QX7T2L")
    assert compra["gasto_id"] == recibo
    otra_vez = _gasto(_subir(piloto, v["id"], eml, "correo_tiquete.eml"))
    assert otra_vez["id"] != recibo and otra_vez["estado"] == "revision" and "duplicado" in otra_vez["motivos"]
    assert len(_aprobados_con_el_archivo(eml)) <= 1


def test_el_mismo_archivo_no_se_enlaza_al_tiquete_si_ya_sostiene_otro_gasto(piloto, modelo):
    """El caso del QA: el recibo quedó aparte de la compra (aquí, sin nada que lo ate a ella) y alguien sube otra vez el
    mismo archivo. Antes se unía al gasto de la compra sin avisar, con el recibo anterior aprobado con el mismo soporte."""
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    archivo = b"\x89PNG\r\n\x1a\n" + uuid.uuid4().bytes
    modelo["respuesta"] = {"comercio": "Viajes Andinos", "total": float(pagado)}
    recibo = _subir(piloto, v["id"], archivo)
    compra = _registrar(c, pagado)
    assert compra["gasto_id"] != recibo
    otra_vez = _gasto(_subir(piloto, v["id"], archivo))
    assert otra_vez["id"] not in (recibo, compra["gasto_id"])
    assert otra_vez["estado"] == "revision" and "duplicado" in otra_vez["motivos"]
    assert _gasto(compra["gasto_id"])["documento_id"] is None          # el tiquete no toma el soporte de otro gasto
    assert len(_aprobados_con_el_archivo(archivo)) <= 1


# ---------- ronda 1: la red también vale al asignar el viaje después (`gastos.asignar_viaje`, lo usa Telegram) ----------
def _sin_viaje(piloto: TestClient) -> int:
    """Un recibo subido sin viaje: con dos viajes posibles en las mismas fechas, queda sin asignar."""
    r = piloto.post(f"{V1}/gastos", files={"archivo": ("t.png", b"\x89PNG\r\n\x1a\n" + uuid.uuid4().bytes, "image/png")},
                    headers=_csrf(piloto))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _tiquete_con_su_recibo(piloto: TestClient, modelo: dict) -> tuple[dict, dict, Decimal]:
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    compra = _registrar(c, pagado)
    modelo["respuesta"] = {"numero_factura": compra["localizador"], "total": float(pagado)}
    assert _subir(piloto, v["id"]) == compra["gasto_id"]
    return v, compra, pagado


def test_la_alerta_del_mismo_importe_tiene_codigo_propio_que_volver_a_validar_no_quita():
    assert compras.DUPLICADO == "tiquete_duplicado"
    assert validacion.etiqueta(compras.DUPLICADO) == "Posible duplicado del tiquete"
    assert compras.DUPLICADO in gastos.CONSERVAN_REVISION


def test_un_recibo_sin_viaje_del_mismo_importe_asignado_despues_queda_en_revision(piloto, modelo):
    v, compra, pagado = _tiquete_con_su_recibo(piloto, modelo)
    _, otro = _decidir(piloto)
    _por_comprar(otro["id"])
    modelo["respuesta"] = {"comercio": "Agencia Única " + uuid.uuid4().hex[:6], "fecha": "2026-10-03", "total": float(pagado)}
    gid = _sin_viaje(piloto)
    assert _gasto(gid)["viaje_id"] is None
    gastos.asignar_viaje(gid, viajes.uno(v["id"]))
    g = _gasto(gid)
    assert g["estado"] == "revision" and compras.DUPLICADO in g["motivos"]
    assert DUPLICADO.format(compra["gasto_id"]) in g["alertas"]


def test_un_recibo_sin_viaje_se_une_al_tiquete_sin_soporte_al_asignarlo(piloto, modelo):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    compra = _registrar(c, pagado)                     # el tiquete, todavía sin recibo
    _, otro = _decidir(piloto)
    _por_comprar(otro["id"])
    modelo["respuesta"] = {"numero_factura": compra["localizador"], "total": float(pagado)}
    gid = _sin_viaje(piloto)
    documento = _gasto(gid)["documento_id"]
    hecho = gastos.asignar_viaje(gid, viajes.uno(v["id"]))
    assert hecho["id"] == compra["gasto_id"]           # devuelve el gasto que quedó: el del tiquete
    assert db.uno("select id from gastos where id=:i", i=gid) is None
    assert _gasto(compra["gasto_id"])["documento_id"] == documento
    assert [f["id"] for f in _vuelos(v["id"])] == [compra["gasto_id"]]


def test_reasignar_el_recibo_marcado_al_mismo_viaje_conserva_la_alerta(piloto, modelo):
    v, compra, pagado = _tiquete_con_su_recibo(piloto, modelo)
    modelo["respuesta"] = {"comercio": "Agencia del Sur", "fecha": "2026-11-02", "total": float(pagado)}
    otro = _subir(piloto, v["id"])
    assert _gasto(otro)["estado"] == "revision"
    gastos.asignar_viaje(otro, viajes.uno(v["id"]))
    g = _gasto(otro)
    assert g["estado"] == "revision" and g["motivos"].count(compras.DUPLICADO) == 1
    assert g["alertas"].count(DUPLICADO.format(compra["gasto_id"])) == 1


def test_quien_registro_la_compra_no_aprueba_el_tiquete_marcado_y_otra_persona_si(piloto, modelo, cliente, revisor):
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    # un importe propio, dentro de la tolerancia y a más del 1 % de lo cotizado: otras pruebas dejan tiquetes «American»
    # de hoy por lo cotizado, que las reglas de duplicados verían
    pagado = (Decimal(str(c["precio_cotizado"])) * Decimal("1.07")).quantize(Decimal("0.01")) + Decimal(uuid.uuid4().int % 90) / 100
    modelo["respuesta"] = {"comercio": "Viajes Andinos", "total": float(pagado)}
    recibo = _subir(piloto, v["id"])
    compra = _registrar(c, pagado)                     # la registra admin@demo.local, la sesión de `cliente`
    g = _gasto(compra["gasto_id"])
    assert g["id"] != recibo and g["estado"] == "revision" and compras.DUPLICADO in g["motivos"]
    cuerpo = {"version": g["version"], "accion": "aprobar"}
    r = cliente.post(f"{V1}/gastos/{g['id']}/revision", json=cuerpo, headers=_csrf(cliente))
    assert r.status_code == 403, r.text
    r = revisor.post(f"{V1}/gastos/{g['id']}/revision", json=cuerpo, headers=_csrf(revisor))
    assert r.status_code == 200 and r.json()["estado"] == "aprobado", r.text


def test_telegram_asigna_el_recibo_del_tiquete_y_responde_con_el_gasto_que_quedo(piloto, modelo, anonimo, monkeypatch):
    from app.servicios import telegram
    enviados = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", "secreto-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: enviados.append((metodo, d)) or {})
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    compra = _registrar(c, pagado)
    _, otro = _decidir(piloto)
    _por_comprar(otro["id"])
    modelo["respuesta"] = {"numero_factura": compra["localizador"], "total": float(pagado)}
    gid = _sin_viaje(piloto)
    uid, chat = db.uno("select id from usuarios where correo='piloto@demo.local'")["id"], 880_000 + uuid.uuid4().int % 99_000
    db.actualizar("usuarios", uid, telegram_chat_id=chat)
    try:
        r = anonimo.post("/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-de-pruebas"},
                         json={"update_id": chat, "callback_query": {"id": "q", "data": f"v:{gid}:{v['id']}",
                                                                     "message": {"chat": {"id": chat}}}})
        assert r.status_code == 200 and r.json()["estado"] == "procesado", r.text
        texto = next(d["text"] for m, d in reversed(enviados) if m == "sendMessage")
        assert f"Gasto #{compra['gasto_id']}" in texto
    finally:
        db.actualizar("usuarios", uid, telegram_chat_id=None)


# ---------- ronda 2: lo que cuelga del recibo pasa al tiquete al unirlos ----------
def _recibo_justificado_sin_viaje(piloto: TestClient, modelo: dict) -> tuple[dict, dict, int]:
    """Un tiquete comprado sin soporte y su recibo subido sin viaje, con la justificación que Telegram guarda del pie de
    la foto antes de mostrar los botones del viaje."""
    from app.servicios import justificaciones
    _, v = _decidir(piloto)
    c = _por_comprar(v["id"])
    pagado = Decimal(str(c["precio_cotizado"]))
    compra = _registrar(c, pagado)
    _, otro = _decidir(piloto)
    _por_comprar(otro["id"])
    modelo["respuesta"] = {"numero_factura": compra["localizador"], "total": float(pagado)}
    gid = _sin_viaje(piloto)
    u = db.uno("select * from usuarios where correo='piloto@demo.local'")
    justificaciones.registrar(gid, u, "telegram", "tiquete del viaje a Las Vegas")
    return v, compra, gid


def test_un_recibo_justificado_se_une_al_tiquete_al_asignarle_el_viaje(piloto, modelo):
    v, compra, gid = _recibo_justificado_sin_viaje(piloto, modelo)
    hecho = gastos.asignar_viaje(gid, viajes.uno(v["id"]))
    assert hecho["id"] == compra["gasto_id"]
    textos = [j["texto"] for j in db.todos("select texto from justificaciones where gasto_id=:g", g=compra["gasto_id"])]
    assert "tiquete del viaje a Las Vegas" in textos                      # la justificación queda en el tiquete
    for tabla in ("justificaciones", "envios_soporte", "avisos_salientes", "telegram_mensajes", "compras"):
        assert db.uno(f"select count(*) n from {tabla} where gasto_id=:g", g=gid)["n"] == 0, tabla   # nada huérfano


def test_telegram_une_al_tiquete_un_recibo_justificado(piloto, modelo, anonimo, monkeypatch):
    from app.servicios import telegram
    enviados = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", "secreto-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: enviados.append((metodo, d)) or {})
    v, compra, gid = _recibo_justificado_sin_viaje(piloto, modelo)
    uid, chat = db.uno("select id from usuarios where correo='piloto@demo.local'")["id"], 770_000 + uuid.uuid4().int % 99_000
    db.actualizar("usuarios", uid, telegram_chat_id=chat)
    try:
        r = anonimo.post("/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-de-pruebas"},
                         json={"update_id": chat, "callback_query": {"id": "q", "data": f"v:{gid}:{v['id']}",
                                                                     "message": {"chat": {"id": chat}}}})
        assert r.status_code == 200 and r.json()["estado"] == "procesado", r.text
        assert _gasto(compra["gasto_id"])["documento_id"] is not None
    finally:
        db.actualizar("usuarios", uid, telegram_chat_id=None)
