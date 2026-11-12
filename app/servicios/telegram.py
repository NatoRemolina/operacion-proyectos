"""Canal de Telegram: la persona vincula su chat con su cuenta y envía los soportes de su viaje.

El chat nunca decide permisos: solo identifica a la persona. Qué viaje, qué proyecto y qué reglas
aplican lo resuelve la plataforma, igual que en la web.
"""
import re
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .. import config, db
from . import acceso, eventos, gastos, justificaciones, viajes

API = "https://api.telegram.org"
VIDA_VINCULO = timedelta(minutes=15)
AYUDA = ("Envíame la foto o el PDF de un recibo y lo registro en tu viaje.\n"
         "/viaje — ver a qué viaje van tus gastos\n"
         "/viaje V-2026-0001 — fijar otro viaje\n"
         "También puedes escribir el código del viaje en el pie de la foto, o mandar una nota de voz como evidencia.\n"
         "Después de cada recibo te pregunto para qué fue: respóndeme con un mensaje o una nota de voz.")


class ErrorTelegram(RuntimeError):
    """Fallo al hablar con Telegram. El mensaje nunca incluye la dirección, porque lleva la clave del bot."""


def activo() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN)


def _llamar(metodo: str, **datos) -> dict:
    try:
        r = httpx.post(f"{API}/bot{config.TELEGRAM_BOT_TOKEN}/{metodo}", json=datos, timeout=15)
        cuerpo = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise ErrorTelegram(f"{metodo}: {type(e).__name__}") from None
    if not cuerpo.get("ok"):
        raise ErrorTelegram(f"{metodo}: {str(cuerpo.get('description'))[:120]}")
    return cuerpo.get("result") or {}


def enviar(chat_id: int, texto: str, botones: list[tuple[str, str]] | None = None):
    datos = {"chat_id": chat_id, "text": texto[:3500]}
    if botones:
        datos["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d}] for t, d in botones]}
    _llamar("sendMessage", **datos)


def avisar(usuario_id: int | None, texto: str):
    """Aviso al chat de una persona, si el canal está activo y lo tiene vinculado. Nunca interrumpe a quien llama."""
    if not activo() or not usuario_id:
        return
    u = db.uno("select telegram_chat_id from usuarios where id=:i and activo=1", i=usuario_id)
    if u and u["telegram_chat_id"]:
        try:
            enviar(u["telegram_chat_id"], texto)
        except ErrorTelegram:
            pass


def descargar(file_id: str) -> bytes:
    info = _llamar("getFile", file_id=file_id)
    if (info.get("file_size") or 0) > config.MAX_BYTES_SOPORTE:
        raise gastos.SoporteRechazado(f"El archivo pesa {info['file_size'] / 1e6:.1f} MB; el máximo es {config.MAX_BYTES_SOPORTE / 1e6:.1f} MB.")
    try:
        r = httpx.get(f"{API}/file/bot{config.TELEGRAM_BOT_TOKEN}/{info['file_path']}", timeout=30)
        r.raise_for_status()
    except (httpx.HTTPError, KeyError) as e:
        raise ErrorTelegram(f"descarga: {type(e).__name__}") from None
    return r.content


# ---------- vínculo entre el chat y la cuenta ----------
def _ahora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def nuevo_vinculo(usuario_id: int) -> dict:
    """Código de un solo uso. En la base solo queda su huella."""
    codigo = secrets.token_urlsafe(18)
    db.ejecutar("delete from vinculos_telegram where usuario_id=:u", u=usuario_id)
    db.insertar("vinculos_telegram", usuario_id=usuario_id, huella=acceso.huella(codigo),
                expira=(_ahora() + VIDA_VINCULO).strftime("%Y-%m-%d %H:%M:%S"))
    enlace = f"https://t.me/{config.TELEGRAM_BOT_NOMBRE}?start={codigo}" if config.TELEGRAM_BOT_NOMBRE else None
    return {"codigo": codigo, "enlace": enlace, "minutos": int(VIDA_VINCULO.total_seconds() // 60)}


def vincular(codigo: str, chat_id: int, alias: str) -> dict | None:
    v = db.uno("select * from vinculos_telegram where huella=:h and usado is null and expira>:a",
               h=acceso.huella(codigo), a=_ahora().strftime("%Y-%m-%d %H:%M:%S"))
    if not v:
        return None
    db.actualizar("vinculos_telegram", v["id"], usado=db.ahora())
    db.ejecutar("update usuarios set telegram_chat_id=null, telegram_usuario=null where telegram_chat_id=:c", c=chat_id)
    db.actualizar("usuarios", v["usuario_id"], telegram_chat_id=chat_id, telegram_usuario=(alias or "")[:60] or None)
    u = _persona(chat_id)
    eventos.registrar("usuario", u["id"], "Telegram vinculado", f"@{alias}" if alias else "", u["nombre"])
    return u


def desvincular(usuario_id: int):
    db.actualizar("usuarios", usuario_id, telegram_chat_id=None, telegram_usuario=None)


def _persona(chat_id: int) -> dict | None:
    return db.uno("""select id, correo, nombre, rol, viajero_id, telegram_chat_id, viaje_activo_id
                     from usuarios where telegram_chat_id=:c and activo=1""", c=chat_id)


# ---------- respuestas ----------
def _linea_viaje(v: dict) -> str:
    r = viajes.resumen(v["id"])
    return (f"{v['codigo']} · {v['origen']} → {v['destino']} · {v['ida']} a {v['regreso']} · {v['estado_texto']}\n"
            f"Aprobado {r['gastado']:.2f} de {v['presupuesto_usd'] or 0:.2f} USD"
            + (f" · en revisión {r['en_revision']:.2f}" if r["en_revision"] else ""))


def _resumen_gasto(gid: int, viaje: dict | None) -> str:
    g = db.uno("select * from gastos where id=:i", i=gid)
    estado = "aprobado" if g["estado"] in viajes.APROBADOS else "en revisión"
    lineas = [f"Gasto #{gid} — {estado}",
              f"{g['comercio'] or 'Comercio sin leer'} · {g['fecha'] or 'sin fecha'} · "
              + (f"{g['total']:.2f} {g['moneda'] or ''}" if g["total"] is not None else "total sin leer")]
    lineas += [f"• {a}" for a in (db.de_json(g["alertas"], []) or [])[:3]]
    if viaje:
        lineas.append(_linea_viaje(viaje))
    return "\n".join(lineas)


# ---------- entrada ----------
def procesar(update: dict) -> str:
    """Atiende una entrega de Telegram. Devuelve el estado con que quedó registrada."""
    try:
        mid = db.insertar("telegram_mensajes", update_id=update.get("update_id"), estado="recibido", momento=db.ahora())
    except IntegrityError:
        mid = _retomar_si_fallo(update.get("update_id"))
        if not mid:
            return "repetido"   # Telegram reintenta: la misma entrega no se procesa dos veces
    registro = {"estado": "procesado", "_entrega": update.get("update_id")}
    try:
        if "callback_query" in update:
            _boton(update["callback_query"], registro)
        elif "message" in update:
            _mensaje(update["message"], registro)
        else:
            registro["estado"] = "ignorado"
    except gastos.SoporteRechazado as e:
        registro["estado"] = "rechazado"
        _responder(registro, f"No pude registrar el archivo: {e}")
    except Exception:
        # Un fallo inesperado no queda como «procesado»: la misma entrega se puede volver a procesar
        registro["estado"] = "error"
        _responder(registro, "No pude procesar tu mensaje por un problema de nuestro lado. Vuelve a enviarlo en un momento.")
        raise
    finally:
        chat = registro.pop("_chat", None)
        registro.pop("_entrega", None)
        db.actualizar("telegram_mensajes", mid, chat_id=chat, **registro)
    return registro["estado"]


def _retomar_si_fallo(update_id) -> int | None:
    """Una entrega que quedó en `error` se puede procesar otra vez; la marca se cambia en una sola sentencia,
    así dos reintentos simultáneos no la toman los dos. Devuelve el registro retomado o None."""
    previa = db.uno("select id from telegram_mensajes where update_id=:u and estado='error'", u=update_id)
    if not previa:
        return None
    with db.transaccion() as c:
        tomada = c.execute(text("update telegram_mensajes set estado='recibido', momento=:m where id=:i and estado='error'"),
                           {"m": db.ahora(), "i": previa["id"]}).rowcount
    return previa["id"] if tomada else None


def _responder(registro: dict, texto: str, botones=None):
    if registro.get("_chat"):
        try:
            enviar(registro["_chat"], texto, botones)
        except ErrorTelegram:
            pass


def _mensaje(m: dict, registro: dict):
    chat = m.get("chat") or {}
    registro["_chat"] = chat.get("id")
    if chat.get("type") != "private":
        registro["estado"] = "ignorado"
        return
    texto = (m.get("text") or m.get("caption") or "").strip()
    registro["texto"] = texto[:500] or None
    if texto.startswith("/start"):
        registro["tipo"] = "vinculo"
        codigo = texto.partition(" ")[2].strip()
        u = vincular(codigo, chat["id"], (m.get("from") or {}).get("username", "")) if codigo else None
        if u:
            registro["usuario_id"] = u["id"]
            _responder(registro, f"Listo, {u['nombre']}. Este chat quedó vinculado a tu cuenta {viajes.codigo_persona(u['id'])}.\n\n{AYUDA}")
        else:
            registro["estado"] = "sin_vincular"
            _responder(registro, "Para usar este chat, entra a la plataforma, abre «Mi cuenta» y pulsa «Vincular Telegram». "
                                 "El enlace vale 15 minutos y sirve una sola vez.")
        return
    u = _persona(chat["id"])
    if not u:
        registro["estado"] = "sin_vincular"
        _responder(registro, "Este chat no está vinculado a ninguna cuenta. Entra a la plataforma, abre «Mi cuenta» y pulsa «Vincular Telegram».")
        return
    registro["usuario_id"] = u["id"]
    acceso.fijar(u)   # cada hecho queda firmado por la persona, igual que en la web

    if texto.startswith("/viaje"):
        registro["tipo"] = "comando"
        return _comando_viaje(u, texto.partition(" ")[2].strip(), registro)
    if texto.startswith("/"):
        registro["tipo"] = "comando"
        return _responder(registro, AYUDA)

    archivo = None
    if m.get("photo"):
        caben = [f for f in m["photo"] if (f.get("file_size") or 0) <= config.MAX_BYTES_SOPORTE] or m["photo"][:1]
        archivo = (max(caben, key=lambda f: f.get("file_size") or 0)["file_id"], "foto.jpg", "soporte")
    elif m.get("document"):
        archivo = (m["document"]["file_id"], m["document"].get("file_name") or "documento", "soporte")
    elif m.get("voice") or m.get("audio"):
        a = m.get("voice") or m.get("audio")
        archivo = (a["file_id"], a.get("file_name") or "nota_de_voz.ogg", "audio")

    viaje, candidatos = viajes.resolver_para_gasto(u, viajes.id_en_texto(texto))
    registro["viaje_id"] = viaje["id"] if viaje else None
    pendiente = justificaciones.gasto_por_justificar(u["id"]) if not m.get("photo") and not m.get("document") else None
    if pendiente and (texto or (archivo and archivo[2] == "audio")):
        return _justificar(u, pendiente, texto, archivo, registro)
    if not archivo:
        if not texto:
            registro["estado"] = "ignorado"
            return
        registro["tipo"] = "nota"
        registro["documento_id"] = gastos.guardar_evidencia(u, viaje, "telegram", "nota", texto=texto)
        return _responder(registro, f"Nota guardada{' en ' + viaje['codigo'] if viaje else ''}. Para registrar un gasto, envía la foto o el PDF del recibo.")

    file_id, nombre, clase = archivo
    contenido = descargar(file_id)
    if clase == "audio":
        registro["tipo"] = "audio"
        registro["documento_id"] = gastos.guardar_evidencia(u, viaje, "telegram", "audio", contenido, nombre, texto)
        return _responder(registro, f"Audio guardado como evidencia{' de ' + viaje['codigo'] if viaje else ''}.")

    registro["tipo"] = "soporte"
    # La entrega es la clave del envío: reprocesar una que quedó en error devuelve el mismo gasto, no crea otro.
    # La huella es solo el archivo: al reprocesar, el viaje que corresponde hoy podría ser otro
    entrega = registro.get("_entrega")
    gid = gastos.registrar(contenido, nombre, "telegram", u, viaje, viajero_id=u["viajero_id"], rapido=True,
                           clave_idempotencia=f"telegram:{entrega}" if entrega is not None else None, contexto={})
    registro["gasto_id"] = gid
    motivo = " ".join(re.sub(r"\bV-\d{4}-\d{4}\b", " ", texto, flags=re.IGNORECASE).split())
    justificado = False
    if len(motivo) >= justificaciones.MINIMO:   # el pie de la foto ya dice para qué fue
        try:
            justificaciones.registrar(gid, u, "telegram", motivo)
            justificado = True
        except justificaciones.JustificacionRechazada:
            pass
    botones = [(f"{c['codigo']} · {c['origen']} → {c['destino']} · {c['ida']}", f"v:{gid}:{c['id']}") for c in candidatos[:6]] if not viaje else None
    pie = "\n\n¿A qué viaje pertenece?" if botones else \
        ("\n\nNo tienes un viaje asignado: el gasto quedó en revisión." if not viaje else "")
    if not justificado:
        pie += "\n\n" + justificaciones.PREGUNTA
    _responder(registro, _resumen_gasto(gid, viaje) + pie, botones)


def _justificar(u: dict, gid: int, texto: str, archivo: tuple | None, registro: dict):
    """La respuesta a la pregunta del bot: un texto o una nota de voz que justifica el último gasto."""
    registro.update(tipo="justificacion", gasto_id=gid)
    audio = descargar(archivo[0]) if archivo else None
    try:
        jid = justificaciones.registrar(gid, u, "telegram", texto, audio, archivo[1] if archivo else "nota_de_voz")
    except justificaciones.JustificacionRechazada as e:
        registro["estado"] = "rechazado"
        return _responder(registro, f"No pude guardar la justificación: {e}")
    j = db.uno("select tipo, texto, transcripcion from justificaciones where id=:i", i=jid)
    eco = f"\n«{j['texto'][:300]}»" if j["tipo"] == "audio" and j["transcripcion"] == "hecha" and j["texto"] else ""
    _responder(registro, f"Gracias. Quedó como justificación del gasto #{gid}.{eco}")


def _comando_viaje(u: dict, argumento: str, registro: dict):
    if argumento.lower() in ("ninguno", "auto", "automatico", "automático"):
        db.actualizar("usuarios", u["id"], viaje_activo_id=None)
        return _responder(registro, "Hecho: vuelvo a elegir el viaje según tus fechas.")
    vid = viajes.id_en_texto(argumento)
    if vid:
        v = viajes.uno(vid)
        if not v or not acceso.es_propio(u, v):
            return _responder(registro, "No encuentro ese viaje entre los tuyos.")
        if v["estado"] != "aprobado":
            return _responder(registro, f"El viaje {v['codigo']} está {v['estado_texto'].lower()}; solo se puede fijar uno aprobado.")
        db.actualizar("usuarios", u["id"], viaje_activo_id=vid)
        registro["viaje_id"] = vid
        return _responder(registro, "Tus próximos gastos van a:\n" + _linea_viaje(v))
    viaje, candidatos = viajes.resolver_para_gasto(u)
    if viaje:
        registro["viaje_id"] = viaje["id"]
        return _responder(registro, "Tus gastos van a:\n" + _linea_viaje(viaje))
    if candidatos:
        return _responder(registro, "Tienes varios viajes posibles. Fija uno con /viaje y su código:\n"
                          + "\n".join(f"{c['codigo']} · {c['origen']} → {c['destino']} · {c['ida']}" for c in candidatos[:6]))
    _responder(registro, "No tienes viajes asignados. Cotiza y guarda la decisión en la plataforma; administración aprueba el presupuesto.")


def _boton(c: dict, registro: dict):
    chat = (c.get("message") or {}).get("chat") or {}
    registro.update(_chat=chat.get("id"), tipo="boton", texto=(c.get("data") or "")[:60])
    try:
        _llamar("answerCallbackQuery", callback_query_id=c.get("id"))
    except ErrorTelegram:
        pass
    u = _persona(chat.get("id") or 0)
    partes = (c.get("data") or "").split(":")
    if not u or len(partes) != 3 or partes[0] != "v" or not partes[1].isdigit() or not partes[2].isdigit():
        registro["estado"] = "ignorado"
        return
    acceso.fijar(u)
    registro["usuario_id"] = u["id"]
    g = db.uno("select * from gastos where id=:i", i=int(partes[1]))
    v = viajes.uno(int(partes[2]))
    if not g or not v or g["usuario_id"] != u["id"] or not acceso.es_propio(u, v):
        registro["estado"] = "ignorado"
        return
    registro.update(gasto_id=g["id"], viaje_id=v["id"])
    try:
        gastos.asignar_viaje(g["id"], v)
    except ValueError as e:   # la persona siempre recibe respuesta, aunque el gasto no se pueda mover
        registro["estado"] = "rechazado"
        return _responder(registro, f"No pude asignar el gasto #{g['id']} al viaje {v['codigo']}. {e}")
    _responder(registro, _resumen_gasto(g["id"], v))
