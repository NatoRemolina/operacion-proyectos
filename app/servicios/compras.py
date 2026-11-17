"""Solicitud de compra del tiquete: nace al decidir y la lleva administración.

Estados: `solicitada` → `en_analisis` → `se_comprara` | `no_se_comprara` → `comprada` | `cancelada`.
- Una compra activa por viaje: cambiar la decisión actualiza la misma solicitud.
- Solo administración la mueve, y nunca la de su propio viaje (queda en la bitácora como autoaprobación impedida).
- Cada cambio exige la versión que se vio (conflicto si otra persona la cambió antes).
- «Se va a comprar» exige el viaje aprobado; «no se va a comprar» y «cancelada» exigen motivo. Cada decisión avisa al
  viajero (bitácora del viaje).
- Registrar la compra guarda localizador, precio pagado y vendedor, los días de anticipación y la diferencia con el
  precio cotizado, y crea el gasto del tiquete (categoría vuelo, `compras.gasto_id`): lo comprado suma en lo gastado del
  viaje y entra al Excel contable. «Aprobado si cuadra»: queda aprobado si lo pagado no supera lo cotizado al decidir en
  más de la regla `tolerancia_tiquete_pct`; si lo supera, o no hay precio cotizado, va a revisión y lo aprueba otra
  persona de administración. Si el recibo del tiquete ya estaba cargado (mismo localizador o mismo comercio, con el
  importe parecido), se enlaza ese gasto en vez de crear otro; si llega después, se une al del tiquete solo si el importe
  coincide (`tiquete_por_enlazar`), y con el mismo localizador y otro importe queda aparte, en revisión.
- Cancelar el tiquete ya comprado devuelve su gasto a revisión («Compra cancelada: revisar reembolso»): volver a
  comprar no deja dos tiquetes aprobados.
- Cuando el viaje cambia de estado (`al_cambiar_el_viaje`, desde `viajes.cambiar_estado`): «Se va a comprar» vuelve a
  análisis si el viaje deja de estar aprobado (también al cerrarlo: desde análisis tiene salida, «no se va a comprar»);
  con el tiquete ya comprado, rechazar o reabrir el viaje deja un evento y la compra muestra un aviso. Leer una compra
  nunca la cambia.

`clics_fuente` deja el rastro de cada enlace a una fuente o al vendedor (quién, qué vuelo, qué viaje, adónde).
"""
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import Column, Float, Integer, Text, text
from sqlalchemy.exc import IntegrityError

from .. import config, db
from . import costo, dinero, eventos, revision, tiempo, validacion, viajes

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
AVISO_COMPRADA = ("El tiquete ya está comprado y el viaje quedó «{estado}»: decide si se conserva o se cancela la compra "
                  "(cancelarla puede tener costo con la aerolínea).")


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
    if c:
        c["estado_texto"] = ESTADOS.get(c["estado"], c["estado"])
        c["viaje_codigo"] = viajes.codigo_viaje({"id": c["viaje_id"], "creado": c["viaje_creado"]})
        c["aviso"] = AVISO_COMPRADA.format(estado=viajes.ESTADOS.get(c["viaje_estado"], c["viaje_estado"]).lower()) \
            if c["estado"] == "comprada" and c["activa"] and c["viaje_estado"] in ("pendiente_aprobacion", "rechazado") else None
    return c


# ---------- cuando el viaje cambia de estado ----------
def al_cambiar_el_viaje(viaje_id: int, hacia: str, paso: str, quien: dict):
    """La compra activa del viaje frente a su estado nuevo. Va dentro de la transacción del cambio de estado del viaje.

    - «Se va a comprar» exige el viaje aprobado: si deja de estarlo (se reabre o se cierra), vuelve a análisis.
    - Con el tiquete comprado, rechazar o reabrir deja el evento; la compra muestra el aviso (`uno`) mientras dure.
    """
    with db.transaccion() as c:
        fila = db.uno("select id from compras where viaje_id=:v and activa=1", v=viaje_id)
        if not fila:
            return
        actual = _bloquear(c, fila["id"])
        if actual["estado"] == "se_comprara" and hacia != "aprobado":
            db.ejecutar("update compras set estado='en_analisis', version=version+1, actualizado=:t where id=:i",
                        t=db.ahora(), i=actual["id"])
            eventos.registrar("compra", actual["id"], "compra: vuelve a análisis",
                              f"el viaje quedó «{viajes.ESTADOS.get(hacia, hacia)}»", quien["nombre"])
        elif actual["estado"] == "comprada" and hacia in ("pendiente_aprobacion", "rechazado"):
            que = "reabierto" if hacia == "pendiente_aprobacion" else "rechazado"
            eventos.registrar("compra", actual["id"], f"viaje {que} con el tiquete comprado",
                              f"{actual['viaje_codigo']} · {actual['localizador'] or ''} · {paso}", quien["nombre"])


def alinear_con_el_viaje() -> int:
    """Migración: las compras que quedaron en «Se va a comprar» con el viaje sin aprobar (antes se corregían al leerlas)
    vuelven a análisis. Idempotente; devuelve cuántas movió."""
    filas = db.todos("""select c.id, v.estado from compras c join viajes v on v.id=c.viaje_id
                        where c.activa=1 and c.estado='se_comprara' and v.estado<>'aprobado'""")
    for f in filas:
        db.ejecutar("update compras set estado='en_analisis', version=version+1, actualizado=:t where id=:i and estado='se_comprara'",
                    t=db.ahora(), i=f["id"])
        eventos.registrar("compra", f["id"], "compra: vuelve a análisis", f"el viaje estaba «{viajes.ESTADOS.get(f['estado'], f['estado'])}»",
                          "migración")
    return len(filas)


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
        if accion == "cancelada" and actual["estado"] == "comprada" and actual["gasto_id"]:
            _gasto_a_revision(actual["gasto_id"], COMPRA_CANCELADA, CANCELADA_TEXTO, f"compra #{cid} · {motivo}", usuario)
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
        gasto_id = _gasto_del_tiquete(actual, localizador, precio_pagado, vendedor, usuario)
        db.actualizar("compras", cid, estado="comprada", localizador=localizador, precio_pagado=float(precio_pagado),
                      vendedor=vendedor, comprada=hoy, comprada_por=usuario["id"], actualizado=hoy, version=version + 1,
                      gasto_id=gasto_id,
                      anticipacion_dias=(date.fromisoformat(ida[:10]) - tiempo.hoy()).days if ida else None)
    eventos.registrar("compra", cid, "compra registrada", f"{localizador} · {vendedor} · {precio_pagado} USD · gasto #{gasto_id}",
                      usuario["nombre"])
    from . import capturas  # aquí: capturas usa el analizador, que usa compras
    try:   # la captura final del vuelo comprado es evidencia: si no se encola, la compra queda registrada igual
        capturas.al_comprar(cid)
    except Exception as e:  # noqa: BLE001
        eventos.registrar("compra", cid, "evidencia de compra no encolada", f"{type(e).__name__}: {str(e)[:200]}", "sistema")
    _avisar(actual, f"comprada a {vendedor}, localizador {localizador}", usuario)
    return uno(cid)


# ---------- el gasto del tiquete ----------
ORIGEN_COMPRA = "compra registrada"   # `gastos.origen_dato` del gasto que nace al registrar la compra
TOLERANCIA_TIQUETE = "tolerancia_tiquete_pct"   # regla editable: cuánto puede pasar lo pagado de lo cotizado (10 = 10 %)
SOBRE_COTIZADO, COMPRA_CANCELADA, IMPORTE_DISTINTO = "tiquete_sobre_cotizado", "compra_cancelada", "tiquete_importe_distinto"
CANCELADA_TEXTO = "Compra cancelada: revisar reembolso"
IMPORTE_DISTINTO_TEXTO = "Mismo localizador que el tiquete, importe distinto"
# Un recibo de vuelo del viaje y el tiquete, sin nada que los ate salvo el importe: se ven en revisión. Código propio,
# que volver a validar no quita (`gastos.CONSERVAN_REVISION`)
DUPLICADO, DUPLICADO_TEXTO = "tiquete_duplicado", "Posible duplicado del gasto #{} (mismo importe)"
UN_DOLAR = Decimal(1)


def importe_coincide(a: Decimal, b: Decimal) -> bool:
    """Dos importes del mismo tiquete: a un 1 % o a un dólar, lo que sea mayor."""
    return abs(a - b) <= max(abs(b) / 100, UN_DOLAR)


def _importe(valor) -> Decimal | None:
    try:
        return dinero.decimal(valor, positivo=True) if valor is not None else None
    except ValueError:
        return None


def _frente_a_lo_cotizado(pagado: Decimal, cotizado) -> str | None:
    """None si lo pagado cuadra con lo cotizado al decidir; si no, la alerta para quien revisa."""
    cotizado = _importe(cotizado)
    if cotizado is None:
        return f"Tiquete sin precio cotizado para comparar ({pagado:.2f} USD): lo revisa otra persona de administración"
    tolerancia = Decimal(str(costo.supuesto(costo.catalogo(), TOLERANCIA_TIQUETE, 10)))
    if pagado <= cotizado * (1 + tolerancia / 100):
        return None
    return f"Tiquete por encima de lo cotizado ({pagado:.2f} USD frente a {cotizado:.2f} USD)"


def _gasto_a_revision(gid: int, codigo: str, alerta: str, detalle: str, quien: dict):
    """El gasto vuelve a revisión con su motivo. Lo rechazado se queda como está."""
    g = db.uno("select estado, alertas, motivos from gastos where id=:i", i=gid)
    if not g or g["estado"] == "rechazado":
        return
    motivos, alertas = db.de_json(g["motivos"], []) or [], db.de_json(g["alertas"], []) or []
    if codigo not in motivos:
        motivos, alertas = [codigo, *motivos], [alerta, *alertas]
    db.actualizar("gastos", gid, estado="revision", motivos=motivos, alertas=alertas)
    revision.subir_version(gid)
    eventos.registrar("gasto", gid, alerta.lower() if codigo == COMPRA_CANCELADA else "enviado a revisión",
                      f"{alerta} · {detalle}", quien["nombre"])


def _recibo_ya_cargado(compra: dict, localizador: str, vendedor: str, pagado: Decimal) -> tuple[int | None, int | None]:
    """(recibo, parecido). `recibo`: el gasto de vuelo del viaje que ya trae el recibo de este tiquete, con el importe
    parecido y sin otra compra que lo use, y además el mismo localizador, el mismo comercio o un número de vuelo del
    itinerario decidido (en el comercio, en las líneas o en lo leído). `parecido`: si ninguno se ata, el primero con el
    mismo importe, que puede ser el mismo tiquete contado dos veces."""
    def numeros(*textos) -> set[str]:   # «AA 1851», «AA1851» y «AA-1851» son el mismo vuelo
        return {f"{a}{int(n)}" for t in textos
                for a, n in re.findall(r"\b([A-Z][A-Z0-9]|[0-9][A-Z]) ?-? ?(\d{1,4})\b", str(t or "").upper())}

    def textos(valor):   # todo lo leído del recibo, sin los nombres de los campos
        if isinstance(valor, dict):
            return [t for v in valor.values() for t in textos(v)]
        return [t for v in valor for t in textos(v)] if isinstance(valor, list) else [valor] if isinstance(valor, str) else []

    # Los vuelos decididos: los tramos de ida y regreso del viaje y, por si faltan, los números de la opción comprada
    decididos = [t["numero"] for t in db.todos("select numero from tramos_vuelo where viaje_id=:v", v=compra["viaje_id"])]
    if compra.get("opcion_id") and (opcion := db.uno("select datos from opciones where id=:i", i=compra["opcion_id"])):
        decididos += (db.de_json(opcion["datos"], {}) or {}).get("numeros") or []
    itinerario = numeros(*decididos)
    parecido = None
    for g in db.todos("""select g.id, g.comercio, g.total_usd, g.extraido from gastos g
                         where g.viaje_id=:v and g.categoria='vuelo' and g.documento_id is not null
                           and g.estado not in ('rechazado', 'procesando')
                           and not exists (select 1 from compras c where c.gasto_id=g.id) order by g.id""", v=compra["viaje_id"]):
        importe = _importe(g["total_usd"])
        if importe is None or not importe_coincide(importe, pagado):
            continue
        leido = db.de_json(g["extraido"], {}) or {}
        numero = str(leido.get("numero_factura") or "").strip().upper()
        if numero == localizador or validacion.mismo_comercio(g["comercio"], vendedor) \
                or itinerario & numeros(g["comercio"], *textos(leido)):
            return g["id"], None
        parecido = parecido or g["id"]
    return None, parecido


def _gasto_del_tiquete(compra: dict, localizador: str, precio: Decimal, vendedor: str, usuario: dict) -> int:
    """El gasto de lo comprado: aprobado si cuadra con lo cotizado; si no, en revisión para otra persona de
    administración (lo registra quien compró, que no revisa lo suyo). Si el recibo ya estaba cargado, es ese gasto. Si
    hay otro gasto de vuelo con soporte y el mismo importe que no se ata a la compra, nace en revisión: nunca se aprueba
    en silencio lo que puede ser el mismo tiquete contado dos veces."""
    viaje = viajes.uno(compra["viaje_id"])
    alerta = _frente_a_lo_cotizado(precio, compra["precio_cotizado"])
    detalle = f"compra #{compra['id']} · {localizador} · {precio:.2f} USD"
    previo, parecido = _recibo_ya_cargado(compra, localizador, vendedor, precio)
    if previo:
        eventos.registrar("gasto", previo, "recibo ya cargado enlazado a la compra", detalle, usuario["nombre"])
        g = db.uno("select estado from gastos where id=:i", i=previo)
        if alerta and g["estado"] in ("aprobado_auto", "revision"):   # lo que aprobó una persona no se toca
            _gasto_a_revision(previo, SOBRE_COTIZADO, alerta, detalle, usuario)
        return previo
    alertas = [alerta] if alerta else []
    motivos = [SOBRE_COTIZADO] if alerta else []
    if parecido:
        alertas.append(DUPLICADO_TEXTO.format(parecido))
        motivos.append(DUPLICADO)
    gid = db.insertar("gastos", documento_id=None, proyecto_id=viaje["proyecto_id"], viajero_id=viaje["viajero_id"],
                      viaje_id=viaje["id"], comercio=vendedor, fecha=tiempo.hoy().isoformat(), categoria="vuelo",
                      total=float(precio), moneda="USD", total_usd=float(precio), canal_reserva=vendedor, confianza=1.0,
                      estado="revision" if motivos else "aprobado", alertas=alertas,
                      motivos=motivos, origen_dato=ORIGEN_COMPRA, creado=db.ahora(),
                      usuario_id=usuario["id"], revisado_por=None, version=1)
    eventos.registrar("gasto", gid, "gasto del tiquete comprado", f"{detalle}" + "".join(f" · {a}" for a in alertas),
                      usuario["nombre"])
    return gid


def _compra_del_viaje(viaje: dict | None, lectura: dict) -> dict | None:
    """La compra registrada del viaje frente a un recibo de vuelo recién leído, con el importe del recibo en USD."""
    if not viaje or lectura.get("categoria") != "vuelo" or lectura.get("error"):
        return None
    c = db.uno("""select c.gasto_id, c.localizador, c.precio_pagado, g.documento_id from compras c join gastos g on g.id=c.gasto_id
                  where c.viaje_id=:v and c.activa=1 and c.estado='comprada'""", v=viaje["id"])
    if not c:
        return None
    usd = validacion.a_usd(lectura.get("total"), lectura.get("moneda"), costo.catalogo())
    mismo = bool(c["localizador"]) and (lectura.get("numero_factura") or "").strip().upper() == c["localizador"]
    pagado = _importe(c["precio_pagado"])
    coincide = usd is not None and pagado is not None and importe_coincide(Decimal(str(usd)), pagado)
    return {**c, "mismo_localizador": mismo, "coincide": coincide}


def tiquete_por_enlazar(viaje: dict | None, lectura: dict) -> int | None:
    """El gasto del tiquete comprado del viaje al que se une un recibo recién leído, si todavía no tiene soporte: un recibo
    de vuelo con el mismo importe (a un 1 %, o un dólar). Con el mismo localizador y otro importe (el equipaje, por
    ejemplo) no se une: ver `localizador_con_otro_importe`."""
    c = _compra_del_viaje(viaje, lectura)
    return c["gasto_id"] if c and c["coincide"] and c["documento_id"] is None else None


def localizador_con_otro_importe(viaje: dict | None, lectura: dict) -> bool:
    """El recibo trae el localizador del tiquete comprado pero otro importe: queda como gasto aparte, en revisión."""
    c = _compra_del_viaje(viaje, lectura)
    return bool(c and c["mismo_localizador"] and not c["coincide"])


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
