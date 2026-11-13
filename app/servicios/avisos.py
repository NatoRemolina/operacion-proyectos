"""Avisos salientes firmados (webhooks) hacia una integración como n8n. Por ahora, `gasto.registrado`.

Configuración (sin `N8N_WEBHOOK_URL` o sin `N8N_WEBHOOK_SECRETO` queda apagado y nada cambia):
- `N8N_WEBHOOK_URL`: adónde se manda el aviso (el webhook de producción del flujo en n8n).
- `N8N_WEBHOOK_SECRETO`: secreto compartido para la firma; también firma los enlaces al soporte.
- `URL_PUBLICA`: dirección pública de la plataforma, para armar el enlace al soporte (en local, http://localhost:8000).

Cada aviso es un POST JSON con estas cabeceras:
- `X-Inflight-Evento`: `gasto.registrado`.
- `X-Inflight-Entrega`: id único de la entrega; se repite en los reintentos, para no procesar dos veces.
- `X-Inflight-Firma`: `t=<segundos unix>,v1=<hex>`, donde hex = HMAC-SHA256(secreto, "<t>.<cuerpo tal cual llegó>").

El cuerpo lleva el gasto (viaje, proyecto, persona, fecha, comercio, categoría, totales, estado y alertas), la lectura
original del modelo (`lectura`, con número de factura, identificación tributaria y líneas de detalle; los números como
texto) y un enlace firmado al soporte que vence a los 15 minutos; descargarlo exige además una clave de servicio con
`soportes:leer`.

Entrega: un fallo del destino nunca rompe el registro del gasto. Se intenta enseguida con un tiempo de espera corto;
si falla, el aviso queda pendiente en `avisos_salientes` y se reintenta con espera creciente cuando se registra el
siguiente gasto o con `python -m datos.avisos reintentar` (que puede programarse). El enlace y la firma se generan en
cada intento, así que un reintento tardío nunca lleva un enlace vencido.
"""
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import Column, Integer, Text, UniqueConstraint

from .. import config, db
from . import dinero, eventos
from .viajes import codigo_persona, codigo_viaje

registro = logging.getLogger(__name__)

# Catálogo de eventos: un evento nuevo se declara aquí y se emite con `emitir(evento, datos)`; todos van firmados igual.
# `enlace_soporte`: si cada intento añade un enlace firmado y temporal al soporte del gasto (`datos["gasto_id"]`).
EVENTOS = {
    "gasto.registrado": {"enlace_soporte": True},
}
EVENTO_GASTO = "gasto.registrado"
VIGENCIA_ENLACE = 15 * 60                 # segundos
TIEMPO_ESPERA = httpx.Timeout(3.0, connect=2.0)
ESPERAS = (1, 5, 30, 120, 720)            # minutos antes de cada reintento; tras el último, queda como fallido
REINTENTOS_POR_VUELTA = 5

avisos_salientes = db._tabla(
    "avisos_salientes",  # bandeja de salida: un aviso por fila, con sus intentos
    Column("entrega", Text, nullable=False), Column("evento", Text, nullable=False), Column("gasto_id", Integer),
    Column("cuerpo", Text, nullable=False), Column("estado", Text, nullable=False), Column("intentos", Integer),
    Column("proximo", Text), Column("ultimo_error", Text), Column("respuesta", Integer), Column("creado", Text),
    Column("entregado", Text),
    UniqueConstraint("entrega", name="ux_avisos_salientes_entrega"),
)


# ---------- configuración ----------
def _destino() -> str:
    return os.getenv("N8N_WEBHOOK_URL", "").strip()


def _secreto() -> bytes:
    return os.getenv("N8N_WEBHOOK_SECRETO", "").strip().encode()


def url_publica() -> str:
    return (os.getenv("URL_PUBLICA", "").strip() or ("http://localhost:8000" if config.LOCAL else "")).rstrip("/")


def activo() -> bool:
    return bool(_destino() and _secreto() and url_publica())


# ---------- firmas ----------
def firmar(cuerpo: bytes, momento: int, secreto: bytes | None = None) -> str:
    """Valor de `X-Inflight-Firma` para un cuerpo, tal como lo verifica el flujo de n8n."""
    hexa = hmac.new(secreto or _secreto(), f"{momento}.".encode() + cuerpo, hashlib.sha256).hexdigest()
    return f"t={momento},v1={hexa}"


def _clave_enlaces() -> bytes:
    # Derivada del secreto del aviso: quien recibe el aviso no puede fabricar enlaces, y rotar el secreto los invalida
    return hmac.new(_secreto(), b"enlace-soporte-v1", hashlib.sha256).digest()


def _firma_enlace(gasto_id: int, vence: int) -> str:
    return hmac.new(_clave_enlaces(), f"soporte:{gasto_id}:{vence}".encode(), hashlib.sha256).hexdigest()


def enlace_soporte(gasto_id: int, ahora: int | None = None) -> str:
    vence = int(ahora if ahora is not None else time.time()) + VIGENCIA_ENLACE
    consulta = urlencode({"vence": vence, "firma": _firma_enlace(gasto_id, vence)})
    return f"{url_publica()}/api/v1/servicio/gastos/{gasto_id}/soporte?{consulta}"


def enlace_valido(gasto_id: int, vence: int | None, firma: str | None) -> str | None:
    """None si el enlace sirve; si no, el motivo: 'LINK_INVALID' o 'LINK_EXPIRED'."""
    if not _secreto() or vence is None or not firma:
        return "LINK_INVALID"
    if not hmac.compare_digest(firma.encode(), _firma_enlace(gasto_id, vence).encode()):
        return "LINK_INVALID"
    if vence < time.time() or vence > time.time() + VIGENCIA_ENLACE + 60:
        return "LINK_EXPIRED"
    return None


# ---------- cuerpo ----------
def _importe(valor) -> str | None:
    """Un número como texto con dos decimales («54.00»). Los números viajan como texto: Python y JavaScript no escriben
    igual los decimales (5.0 frente a 5), y el nodo de n8n puede verificar la firma volviendo a serializar el JSON."""
    try:
        return f"{dinero.decimal(valor):.2f}"
    except ValueError:   # vacío, ilegible o desmesurado: viaja vacío
        return None


def _lectura(extraido) -> dict | None:
    """La lectura original del modelo (`gastos.extraido`), con los números como texto. None si la lectura falló."""
    if not isinstance(extraido, dict):
        return None
    salida = {}
    for clave, valor in extraido.items():
        if clave == "lineas":
            salida[clave] = [{"descripcion": linea.get("descripcion"), "cantidad": _importe(linea.get("cantidad")),
                              "total": _importe(linea.get("total"))}
                             for linea in (valor if isinstance(valor, list) else []) if isinstance(linea, dict)]
        elif isinstance(valor, int | float) and not isinstance(valor, bool):
            salida[clave] = _importe(valor)
        else:
            salida[clave] = valor
    return salida


def _cuerpo_gasto(gasto_id: int) -> dict | None:
    # La persona del gasto se decide igual que en el Excel contable: titular del viaje, si no la cuenta del viajero,
    # si no quien lo cargó
    g = db.uno("""select g.id, g.fecha, g.comercio, g.categoria, g.total, g.moneda, g.total_usd, g.estado, g.alertas, g.extraido,
                         g.origen_dato, g.viaje_id, v.creado viaje_creado, p.nombre proyecto,
                         coalesce(v.usuario_id, (select min(x.id) from usuarios x where x.viajero_id=g.viajero_id), g.usuario_id) persona_id
                  from gastos g left join viajes v on v.id=g.viaje_id left join proyectos p on p.id=g.proyecto_id
                  where g.id=:i""", i=gasto_id)
    if not g:
        return None
    g["viaje"] = codigo_viaje({"id": g["viaje_id"], "creado": g["viaje_creado"]}) if g["viaje_id"] else None
    alertas = db.de_json(g["alertas"], [])
    lectura = db.de_json(g["extraido"], None)
    return {"gasto_id": g["id"], "viaje": g["viaje"], "proyecto": g["proyecto"], "fecha": g["fecha"],
            "comercio": g["comercio"], "total": _importe(g["total"]), "moneda": g["moneda"],
            # Lo leído de la factura, para guardarlo en Drive y en la hoja de lecturas
            "categoria": g["categoria"], "total_usd": _importe(g["total_usd"]), "estado": g["estado"],
            "alertas": [str(a) for a in alertas] if isinstance(alertas, list) else [],
            "persona": codigo_persona(g["persona_id"]) if g["persona_id"] else None,
            "enlace_gasto": f"{url_publica()}/gastos/{g['id']}" if url_publica() else None,
            "lectura": _lectura(lectura | {"origen_dato": g["origen_dato"]} if isinstance(lectura, dict) else None)}


def _serializar(datos: dict) -> bytes:
    # Compacto y sin escapar lo que no es ASCII: igual a JSON.stringify, para que n8n pueda verificar sobre el JSON leído
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode()


# ---------- entrega ----------
def _ahora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _fmt(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _entidad(aviso: dict) -> tuple[str, int]:
    """Dónde queda el rastro de la entrega: en el gasto si el aviso es de uno; si no, en el propio aviso."""
    return ("gasto", aviso["gasto_id"]) if aviso["gasto_id"] else ("aviso", aviso["id"])


def _intentar(aviso: dict) -> bool:
    """Un intento de entrega. Nunca lanza: el resultado queda en la fila y en la bitácora."""
    datos = json.loads(aviso["cuerpo"])
    if EVENTOS.get(aviso["evento"], {}).get("enlace_soporte") and datos.get("gasto_id"):
        datos["enlace_soporte"] = enlace_soporte(datos["gasto_id"])
        datos["enlace_vence_en_segundos"] = VIGENCIA_ENLACE
    datos = {"evento": aviso["evento"], "entrega": aviso["entrega"], **datos}
    cuerpo = _serializar(datos)
    cabeceras = {"Content-Type": "application/json", "User-Agent": "inflight-avisos/1",
                 "X-Inflight-Evento": aviso["evento"], "X-Inflight-Entrega": aviso["entrega"],
                 "X-Inflight-Firma": firmar(cuerpo, int(time.time()))}
    intentos = (aviso["intentos"] or 0) + 1
    estado_http, error = None, None
    try:
        r = httpx.post(_destino(), content=cuerpo, headers=cabeceras, timeout=TIEMPO_ESPERA, follow_redirects=False)
        estado_http = r.status_code
        if not 200 <= r.status_code < 300:
            error = f"El destino respondió {r.status_code}"
    except Exception as e:   # caída, tiempo agotado, dirección mal escrita: todo se registra y se reintenta
        error = f"{type(e).__name__}: {str(e)[:200]}"
    if error is None:
        db.actualizar("avisos_salientes", aviso["id"], estado="entregado", intentos=intentos, respuesta=estado_http,
                      entregado=db.ahora(), proximo=None, ultimo_error=None)
        eventos.registrar(*_entidad(aviso), "aviso entregado", f"{aviso['evento']} · intento {intentos}", "avisos")
        return True
    agotado = intentos > len(ESPERAS)
    db.actualizar("avisos_salientes", aviso["id"], estado="fallido" if agotado else "pendiente", intentos=intentos,
                  respuesta=estado_http, ultimo_error=error[:300],
                  proximo=None if agotado else _fmt(_ahora() + timedelta(minutes=ESPERAS[intentos - 1])))
    eventos.registrar(*_entidad(aviso), "aviso fallido" if agotado else "aviso no entregado",
                      f"{aviso['evento']} · intento {intentos} · {error}", "avisos")
    registro.warning("Aviso %s %s no entregado (intento %s): %s", aviso["evento"], aviso["entrega"], intentos, error)
    return False


def reintentar_pendientes(limite: int = REINTENTOS_POR_VUELTA) -> int:
    """Reintenta los avisos pendientes cuya espera ya pasó. Devuelve cuántos se entregaron."""
    if not activo():
        return 0
    vencidos = db.todos("select * from avisos_salientes where estado='pendiente' and proximo<=:a order by id limit :n",
                        a=db.ahora(), n=limite)
    return sum(_intentar(a) for a in vencidos)


def emitir(evento: str, datos: dict) -> int | None:
    """Pone un aviso del catálogo en la bandeja y lo intenta entregar. Devuelve el id del aviso, o None si están apagados.

    `datos` es el cuerpo del evento: lo que el flujo necesita y nada más (nunca claves, secretos ni rutas internas; el
    de `gasto.registrado` lleva la lectura de la factura y el código de la persona, no su nombre); `gasto_id`, si lo trae, enlaza el aviso con el gasto
    en la bitácora. Un evento fuera del catálogo es un error de programación: lanza `ValueError`. Un fallo del destino
    no lanza: queda en la bandeja para reintentarlo.
    """
    if evento not in EVENTOS:
        raise ValueError(f"Evento no declarado en avisos.EVENTOS: {evento}")
    if not activo():
        return None
    aid = db.insertar("avisos_salientes", entrega=str(uuid.uuid4()), evento=evento, gasto_id=datos.get("gasto_id"),
                      cuerpo=json.dumps(datos, ensure_ascii=False), estado="pendiente", intentos=0,
                      proximo=db.ahora(), creado=db.ahora())
    # Solo si el destino respondió se atienden de paso los que esperaban: con el destino caído no se suma espera
    if _intentar(db.uno("select * from avisos_salientes where id=:i", i=aid)):
        reintentar_pendientes()
    return aid


def gasto_registrado(gasto_id: int) -> None:
    """Avisa que se registró un gasto. Apagado sin configuración; nunca lanza ni deja de registrar el gasto."""
    try:
        if activo() and (cuerpo := _cuerpo_gasto(gasto_id)):
            emitir(EVENTO_GASTO, cuerpo)
    except Exception:   # el aviso es accesorio: el gasto ya quedó registrado
        registro.exception("No se pudo preparar el aviso %s del gasto %s", EVENTO_GASTO, gasto_id)
