"""Solicitud de compra del tiquete: nace al decidir y la lleva administración.

Estados: `solicitada` → `en_analisis` → `se_comprara` | `no_se_comprara` → `comprada` | `cancelada`.
- Una compra activa por viaje: cambiar la decisión actualiza la misma solicitud.
- Solo administración la mueve, y nunca la de su propio viaje (queda en la bitácora como autoaprobación impedida).
- Cada cambio exige la versión que se vio (conflicto si otra persona la cambió antes).
- «Se va a comprar» exige el viaje aprobado; «no se va a comprar» y «cancelada» exigen motivo. Cada decisión avisa al
  viajero (bitácora del viaje).
- Registrar la compra guarda localizador, precio pagado y vendedor, los días de anticipación y la diferencia con el
  precio cotizado.

`clics_fuente` deja el rastro de cada enlace a una fuente o al vendedor (quién, qué vuelo, qué viaje, adónde).
"""
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import Column, Float, Integer, Text, text
from sqlalchemy.exc import IntegrityError

from .. import config, db
from . import eventos, viajes

compras = db._tabla(
    "compras",
    db._ref("compras", "viaje_id", "viajes"), db._ref("compras", "solicitud_id", "solicitudes"),
    db._ref("compras", "decision_id", "decisiones"), db._ref("compras", "opcion_id", "opciones"),
    db._ref("compras", "solicitada_por", "usuarios"), db._ref("compras", "decidida_por", "usuarios"),
    db._ref("compras", "comprada_por", "usuarios"), db._ref("compras", "gasto_id", "gastos"),
    Column("activa", Integer, nullable=False), Column("estado", Text, nullable=False), Column("motivo", Text),
    Column("vendedor", Text), Column("localizador", Text), Column("precio_pagado", Float), Column("moneda", Text),
    Column("precio_cotizado", Float),          # el precio del buscador (la tarifa) al decidir
    Column("anticipacion_dias", Integer),      # días entre la compra y la ida
    Column("creado", Text), Column("decidido", Text), Column("comprada", Text), Column("actualizado", Text),
    Column("version", Integer, nullable=False),
)
clics_fuente = db._tabla(
    "clics_fuente",
    db._ref("clics_fuente", "usuario_id", "usuarios"), db._ref("clics_fuente", "compra_id", "compras"),
    db._ref("clics_fuente", "opcion_id", "opciones"), db._ref("clics_fuente", "viaje_id", "viajes"),
    db._ref("clics_fuente", "solicitud_id", "solicitudes"),
    Column("destino", Text, nullable=False),   # google_flights | google_hotels | vendedor | hotel_oficial
    Column("dominio", Text), Column("momento", Text), Column("peticion", Text),
)

ESTADOS = {"solicitada": "Solicitud de compra enviada", "en_analisis": "En análisis", "se_comprara": "Se va a comprar",
           "no_se_comprara": "No se va a comprar", "comprada": "Comprada", "cancelada": "Cancelada"}
# estado nuevo → desde qué estados se llega; «comprada» solo con el registro
TRANSICIONES = {"en_analisis": ("solicitada",), "se_comprara": ("solicitada", "en_analisis"),
                "no_se_comprara": ("solicitada", "en_analisis"), "cancelada": ("se_comprara", "comprada")}
CON_MOTIVO = ("no_se_comprara", "cancelada")
DESTINOS = ("google_flights", "google_hotels", "vendedor", "hotel_oficial")
LOCALIZADOR = re.compile(r"^[A-Z0-9]{5,8}$")
NO_PROPIA = "Nadie decide la compra de su propio viaje: debe hacerlo otra persona de administración."


class CompraImpedida(PermissionError):
    """La compra es del propio viaje de quien la quiere mover."""


class ConflictoVersion(ValueError):
    """Otra persona cambió la compra después de que se viera."""


class EstadoInvalido(ValueError):
    """El cambio no se puede hacer desde el estado actual (o falta el viaje aprobado)."""


class CompraBloqueada(ValueError):
    """El tiquete ya está en «Se va a comprar» o comprado: cambiar la decisión exige cancelar antes la compra."""


class CampoInvalido(ValueError):
    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo


# ---------- nace al decidir ----------
def solicitar(decision_id: int, usuario: dict) -> dict:
    """La solicitud de compra del viaje de la decisión. Si el viaje ya tiene una activa que no se decidió, se actualiza
    con la decisión nueva (una activa por viaje)."""
    d = db.uno("select * from decisiones where id=:i", i=decision_id)
    viaje = viajes.de_solicitud(d["solicitud_id"])
    desglose = db.de_json(d["desglose"], {}) or {}
    datos = {"decision_id": decision_id, "opcion_id": d["vuelo_id"], "precio_cotizado": desglose.get("precio_tarifa"),
             "actualizado": db.ahora()}
    with db.transaccion():
        actual = db.uno("select * from compras where viaje_id=:v and activa=1", v=viaje["id"])
        if actual and actual["estado"] in ("solicitada", "en_analisis"):
            db.actualizar("compras", actual["id"], version=actual["version"] + 1, **datos)
            cid = actual["id"]
        else:
            if actual and actual["estado"] in ("se_comprara", "comprada"):
                raise CompraBloqueada(bloqueo(d["solicitud_id"]) or "La compra del tiquete ya está decidida.")
            if actual:   # no se va a comprar o cancelada: queda como historia y nace otra
                db.actualizar("compras", actual["id"], activa=0)
            cid = db.insertar("compras", viaje_id=viaje["id"], solicitud_id=d["solicitud_id"], solicitada_por=usuario["id"],
                              activa=1, estado="solicitada", creado=db.ahora(), version=1, moneda="USD", **datos)
    eventos.registrar("compra", cid, "solicitud de compra", f"{viaje['codigo']} · decisión #{decision_id}", usuario["nombre"])
    return uno(cid)



def rellenar() -> int:
    """Migración: los viajes ya decididos (pendientes o aprobados) que no tienen compra activa reciben una en
    «solicitada», con la decisión vigente y quien la tomó. Idempotente; devuelve cuántas creó."""
    hechas = 0
    for f in db.todos("""select v.decision_id, d.usuario_id from viajes v join decisiones d on d.id=v.decision_id
                         where v.estado in ('pendiente_aprobacion', 'aprobado')
                           and not exists (select 1 from compras c where c.viaje_id=v.id and c.activa=1)
                         order by v.id"""):
        try:
            solicitar(f["decision_id"], {"id": f["usuario_id"], "nombre": "migración"})
            hechas += 1
        except IntegrityError:
            pass   # otra petición la creó en el mismo instante
    return hechas


# ---------- leer ----------
def uno(cid: int) -> dict | None:
    c = db.uno("""select c.*, v.creado viaje_creado, v.estado viaje_estado, v.presupuesto_usd, v.usuario_id viaje_usuario_id,
                         v.viajero_id viaje_viajero_id, v.ida, s.ida solicitud_ida, u.nombre solicitada_por_nombre
                  from compras c join viajes v on v.id=c.viaje_id left join solicitudes s on s.id=c.solicitud_id
                  left join usuarios u on u.id=c.solicitada_por where c.id=:i""", i=cid)
    if c and c["estado"] == "se_comprara" and c["viaje_estado"] != "aprobado" and _volver_a_analisis(c):
        return uno(cid)
    if c:
        c["estado_texto"] = ESTADOS.get(c["estado"], c["estado"])
        c["viaje_codigo"] = viajes.codigo_viaje({"id": c["viaje_id"], "creado": c["viaje_creado"]})
    return c


def _volver_a_analisis(c: dict) -> bool:
    """«Se va a comprar» exige el viaje aprobado: si se reabrió o se rechazó, la compra vuelve a análisis (con su rastro).
    Se hace al leerla, porque el cambio de estado del viaje vive en otro servicio."""
    with db.transaccion() as conexion:
        if not config.ES_SQLITE:
            conexion.execute(text("select id from compras where id=:i for update"), {"i": c["id"]})
        if (db.uno("select estado from compras where id=:i", i=c["id"]) or {}).get("estado") != "se_comprara":
            return False   # otra petición ya la movió
        db.ejecutar("update compras set estado='en_analisis', version=version+1, actualizado=:t where id=:i",
                    t=db.ahora(), i=c["id"])
    eventos.registrar("compra", c["id"], "compra: vuelve a análisis",
                      f"el viaje quedó «{viajes.ESTADOS.get(c['viaje_estado'], c['viaje_estado'])}»", "sistema")
    return True


def bloqueo(solicitud_id: int) -> str | None:
    """Con el tiquete en «Se va a comprar» o comprado, el vuelo no se cambia sin cancelar antes la compra."""
    viaje = viajes.de_solicitud(solicitud_id)
    c = de_viaje(viaje["id"]) if viaje else None
    if c and c["estado"] in ("se_comprara", "comprada"):
        return (f"La compra del tiquete de {c['viaje_codigo']} está «{c['estado_texto']}»: para cambiar el vuelo, "
                "cancélala en Compras primero.")
    return None


def de_viaje(viaje_id: int) -> dict | None:
    f = db.uno("select id from compras where viaje_id=:v and activa=1", v=viaje_id)
    return uno(f["id"]) if f else None


def lista(estado: str | None = None) -> list[dict]:
    filtro = "and c.estado=:e" if estado else ""
    filas = db.todos(f"select c.id from compras c where c.activa=1 {filtro} order by c.id desc limit 200", e=estado)
    return [uno(f["id"]) for f in filas]


def clics(compra: dict) -> list[dict]:
    return db.todos("""select c.destino, c.dominio, c.momento, c.opcion_id, u.nombre usuario from clics_fuente c
                       left join usuarios u on u.id=c.usuario_id where c.viaje_id=:v or c.solicitud_id=:s
                       order by c.id desc limit 100""", v=compra["viaje_id"], s=compra["solicitud_id"])


# ---------- cambiar ----------
def _bloquear(c, cid: int) -> dict:
    if not config.ES_SQLITE:
        c.execute(text("select id from compras where id=:i for update"), {"i": cid})
    actual = uno(cid)
    if not actual:
        raise LookupError(cid)
    return actual


def _no_propia(actual: dict, usuario: dict, que: str):
    viaje = {"usuario_id": actual["viaje_usuario_id"], "viajero_id": actual["viaje_viajero_id"]}
    if viajes.es_propio_de(viaje, usuario):
        viajes.impedir_autoaprobacion("compra", actual["id"], usuario, f"{que} la compra de su propio viaje {actual['viaje_codigo']}")
        raise CompraImpedida(NO_PROPIA)


def _avisar(actual: dict, texto: str, usuario: dict):
    eventos.registrar("viaje", actual["viaje_id"], "aviso al viajero", f"Compra del tiquete de {actual['viaje_codigo']}: {texto}",
                      usuario["nombre"])


def cambiar_estado(cid: int, accion: str, version: int, motivo: str, usuario: dict) -> dict:
    motivo = (motivo or "").strip()[:300]
    if accion not in TRANSICIONES:
        raise CampoInvalido("accion", "Acción desconocida.")
    if accion in CON_MOTIVO and len(motivo) < 5:
        raise CampoInvalido("motivo", "Escribe el motivo (5 caracteres o más): la persona que viaja lo verá.")
    previa = uno(cid)
    if not previa:
        raise LookupError(cid)
    _no_propia(previa, usuario, f"pasar a «{ESTADOS[accion]}»")   # fuera de la transacción: el rastro no se revierte
    with db.transaccion() as c:
        actual = _bloquear(c, cid)
        if actual["version"] != version:
            raise ConflictoVersion("Otra persona cambió esta compra. Vuelve a cargarla y revisa antes de seguir.")
        if actual["estado"] not in TRANSICIONES[accion]:
            raise EstadoInvalido(f"La compra está «{actual['estado_texto']}»: no puede pasar a «{ESTADOS[accion]}».")
        if accion == "se_comprara" and actual["viaje_estado"] != "aprobado":
            raise EstadoInvalido(f"El viaje {actual['viaje_codigo']} no tiene el presupuesto aprobado: primero se aprueba.")
        db.actualizar("compras", cid, estado=accion, motivo=motivo or actual["motivo"], decidida_por=usuario["id"],
                      decidido=db.ahora(), actualizado=db.ahora(), version=version + 1)
    eventos.registrar("compra", cid, f"compra: {ESTADOS[accion].lower()}", motivo, usuario["nombre"])
    if accion != "en_analisis":
        _avisar(actual, f"{ESTADOS[accion].lower()}{f' ({motivo})' if motivo else ''}", usuario)
    return uno(cid)


def registrar_compra(cid: int, version: int, localizador: str, precio_pagado: Decimal, vendedor: str, usuario: dict) -> dict:
    localizador = (localizador or "").strip().upper()
    vendedor = (vendedor or "").strip()[:60]
    if not LOCALIZADOR.match(localizador):
        raise CampoInvalido("localizador", "El localizador son 5 a 8 letras o números, como lo da la aerolínea.")
    if not (Decimal("0") < precio_pagado <= Decimal("99999.99")):
        raise CampoInvalido("precio_pagado", "El precio pagado debe estar entre 0,01 y 99.999,99 USD.")
    if not vendedor:
        raise CampoInvalido("vendedor", "Escribe a quién se le compró.")
    previa = uno(cid)
    if not previa:
        raise LookupError(cid)
    _no_propia(previa, usuario, "registrar")   # fuera de la transacción: el rastro no se revierte
    with db.transaccion() as c:
        actual = _bloquear(c, cid)
        if actual["version"] != version:
            raise ConflictoVersion("Otra persona cambió esta compra. Vuelve a cargarla y revisa antes de seguir.")
        if actual["estado"] != "se_comprara":
            raise EstadoInvalido(f"La compra está «{actual['estado_texto']}»: se registra solo cuando «Se va a comprar».")
        if actual["viaje_estado"] != "aprobado":
            raise EstadoInvalido(f"El viaje {actual['viaje_codigo']} ya no está aprobado: la compra vuelve a análisis.")
        hoy = db.ahora()
        ida = actual["ida"] or actual["solicitud_ida"]
        db.actualizar("compras", cid, estado="comprada", localizador=localizador, precio_pagado=float(precio_pagado),
                      vendedor=vendedor, comprada=hoy, comprada_por=usuario["id"], actualizado=hoy, version=version + 1,
                      anticipacion_dias=(date.fromisoformat(ida[:10]) - date.fromisoformat(hoy[:10])).days if ida else None)
    eventos.registrar("compra", cid, "compra registrada", f"{localizador} · {vendedor} · {precio_pagado} USD", usuario["nombre"])
    from . import capturas  # aquí: capturas usa el analizador, que usa compras
    try:   # la captura final del vuelo comprado es evidencia: si no se encola, la compra queda registrada igual
        capturas.al_comprar(cid)
    except Exception as e:  # noqa: BLE001
        eventos.registrar("compra", cid, "evidencia de compra no encolada", f"{type(e).__name__}: {str(e)[:200]}", "sistema")
    _avisar(actual, f"comprada a {vendedor}, localizador {localizador}", usuario)
    return uno(cid)


# ---------- rastro de los enlaces ----------
def registrar_clic(usuario: dict, sid: int, opcion_id: int | None, destino: str, url: str | None):
    """Quién abrió qué enlace de qué vuelo, para qué viaje y compra. Nunca rompe lo que lo llama."""
    if destino not in DESTINOS:
        return
    try:
        viaje = viajes.de_solicitud(sid)
        compra = db.uno("select id from compras where viaje_id=:v and activa=1", v=viaje["id"]) if viaje else None
        db.insertar("clics_fuente", usuario_id=usuario.get("id"), compra_id=compra["id"] if compra else None,
                    opcion_id=opcion_id, viaje_id=viaje["id"] if viaje else None, solicitud_id=sid, destino=destino,
                    dominio=(urlsplit(url).hostname if url else None), momento=db.ahora())
    except Exception as e:  # noqa: BLE001 (el rastro es secundario: el enlace se abre igual)
        print(f"compras: no se pudo registrar el clic: {type(e).__name__}", flush=True)
