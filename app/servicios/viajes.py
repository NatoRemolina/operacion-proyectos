"""El viaje: nace de una decisión, lo aprueba administración y agrupa los gastos y evidencias de una persona.

Aquí vive la regla de negocio que une la cotización (reto 1) con los gastos (reto 2):
persona -> cotización -> decisión -> VIAJE (presupuesto, estado) -> gastos y evidencias.
"""
import re
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError

from .. import db
from . import acceso, costo, eventos

ESTADOS = {"pendiente_aprobacion": "Pendiente de aprobación", "aprobado": "Aprobado", "rechazado": "Rechazado", "cerrado": "Cerrado"}
APROBADOS = ("aprobado", "aprobado_auto")
MARGEN_ANTES, MARGEN_DESPUES = 1, 2   # días alrededor del viaje en que un gasto todavía le pertenece
_CODIGO = re.compile(r"\bV-\d{4}-0*(\d+)\b", re.I)


def codigo_persona(usuario_id: int) -> str:
    return f"P-{usuario_id:04d}"


def codigo_viaje(v: dict) -> str:
    """Sale del identificador de la fila: no puede repetirse ni desfasarse."""
    return f"V-{(v.get('creado') or '0000')[:4]}-{v['id']:04d}"


def id_en_texto(texto: str | None) -> int | None:
    """Identificador del viaje si el texto trae un código como V-2026-0012."""
    m = _CODIGO.search(texto or "")
    return int(m.group(1)) if m else None


def _con_codigo(v: dict | None) -> dict | None:
    if v:
        v["codigo"] = codigo_viaje(v)
        v["estado_texto"] = ESTADOS.get(v["estado"], v["estado"])
        v["en_curso"] = en_curso(v)
    return v


def uno(viaje_id: int | None) -> dict | None:
    if not viaje_id:
        return None
    return _con_codigo(db.uno("""select v.*, s.origen, s.destino, s.ciudad, p.nombre proyecto, u.nombre titular, vj.nombre viajero
                                 from viajes v left join solicitudes s on s.id=v.solicitud_id
                                 left join proyectos p on p.id=v.proyecto_id left join usuarios u on u.id=v.usuario_id
                                 left join viajeros vj on vj.id=v.viajero_id where v.id=:i""", i=viaje_id))


def de_solicitud(solicitud_id: int) -> dict | None:
    fila = db.uno("select id from viajes where solicitud_id=:s", s=solicitud_id)
    return uno(fila["id"]) if fila else None


def lista(donde: str = "1=1", **parametros) -> list[dict]:
    """Viajes con su ejecución: lo aprobado y lo que espera revisión frente al presupuesto."""
    filas = db.todos(f"""select v.*, s.origen, s.destino, s.ciudad, p.nombre proyecto, u.nombre titular, vj.nombre viajero,
                         (select coalesce(sum(g.total_usd),0) from gastos g where g.viaje_id=v.id and g.estado in ('aprobado','aprobado_auto')) gastado,
                         (select coalesce(sum(g.total_usd),0) from gastos g where g.viaje_id=v.id and g.estado='revision') en_revision,
                         (select count(*) from gastos g where g.viaje_id=v.id) n_gastos,
                         (select max(g.creado) from gastos g where g.viaje_id=v.id) ultimo_gasto
                         from viajes v left join solicitudes s on s.id=v.solicitud_id
                         left join proyectos p on p.id=v.proyecto_id left join usuarios u on u.id=v.usuario_id
                         left join viajeros vj on vj.id=v.viajero_id where {donde} order by v.id desc""", **parametros)
    for v in filas:
        _con_codigo(v)
        v["pct"] = round(100 * (v["gastado"] or 0) / v["presupuesto_usd"]) if v["presupuesto_usd"] else None
    return filas


def en_curso(v: dict, hoy: date | None = None) -> bool:
    hoy = hoy or date.today()
    try:
        return v["estado"] == "aprobado" and \
            date.fromisoformat(v["ida"]) - timedelta(days=MARGEN_ANTES) <= hoy <= date.fromisoformat(v["regreso"]) + timedelta(days=MARGEN_DESPUES)
    except (TypeError, ValueError):
        return False


# ---------- presupuesto ----------
def presupuesto_de(decision: dict, solicitud: dict) -> tuple[float, list[dict]]:
    """Dinero que se espera pagar en el viaje: lo que se compra (vuelo, equipaje, hotel, carro) más los viáticos.

    Las líneas de valor esperado de la comparación (riesgo de cambio, millas) no son desembolsos y no entran. El
    traslado por carretera sí es dinero que se pagará: entra con su grupo, `traslados` (taxi o transfer) o
    `combustible` (con carro de alquiler), aunque su valor sea un supuesto.
    """
    lineas = [{"concepto": l["concepto"], "valor": round(l["valor"], 2), "grupo": l.get("grupo", "otros")}
              for l in (db.de_json(decision.get("desglose"), {}) or {}).get("lineas", [])
              if not (l.get("origen") == "supuesto" and l.get("grupo") == "vuelo")]
    try:
        dias = (date.fromisoformat(solicitud["regreso"]) - date.fromisoformat(solicitud["ida"])).days + 1
    except (TypeError, ValueError):
        dias = 0
    diario = costo.supuesto(costo.catalogo(), "viaticos_dia_usd", 75)
    if dias > 0 and diario > 0:
        lineas.append({"concepto": f"Viáticos ({dias} días x {diario:.0f})", "valor": round(dias * diario, 2), "grupo": "viaticos"})
    return round(sum(l["valor"] for l in lineas), 2), lineas


# ---------- nacimiento y estados ----------
def titular_de(solicitud: dict, creador_id: int | None) -> int | None:
    """Quien viaja: la cuenta vinculada al viajero de la cotización; si no existe, quien cotizó."""
    if solicitud.get("viajero_id"):
        u = db.uno("select id from usuarios where viajero_id=:v and activo=1 order by id limit 1", v=solicitud["viajero_id"])
        if u:
            return u["id"]
    return solicitud.get("usuario_id") or creador_id


def bloquea_decision(solicitud_id: int) -> str | None:
    """Con el presupuesto ya aprobado o el viaje cerrado, la decisión no se cambia sin que administración lo reabra."""
    v = de_solicitud(solicitud_id)
    if v and v["estado"] in ("aprobado", "cerrado"):
        return f"El viaje {v['codigo']} ya está {v['estado_texto'].lower()}: para cambiar la decisión, administración debe reabrirlo."
    return None


def crear_desde_decision(decision_id: int) -> dict:
    """Crea el viaje de una cotización o actualiza el que ya tiene. Es idempotente: una cotización, un viaje."""
    d = db.uno("select * from decisiones where id=:i", i=decision_id)
    s = db.uno("select * from solicitudes where id=:i", i=d["solicitud_id"])
    total, lineas = presupuesto_de(d, s)
    datos = dict(decision_id=d["id"], proyecto_id=s["proyecto_id"], usuario_id=titular_de(s, d.get("usuario_id")),
                 viajero_id=s["viajero_id"], ida=s["ida"], regreso=s["regreso"], presupuesto_usd=total,
                 presupuesto_detalle=lineas, estado="pendiente_aprobacion", aprobado_por=None, aprobado_en=None, motivo=None)
    previo = db.uno("select id from viajes where solicitud_id=:s", s=s["id"])
    if not previo:
        try:
            vid = db.insertar("viajes", solicitud_id=s["id"], creado=db.ahora(), **datos)
            v = uno(vid)
            eventos.registrar("viaje", vid, "viaje creado", f"{v['codigo']} · presupuesto {total:.2f} USD · titular {v['titular'] or '—'}")
            return v
        except IntegrityError:   # otra petición lo creó en el mismo instante
            previo = db.uno("select id from viajes where solicitud_id=:s", s=s["id"])
    db.actualizar("viajes", previo["id"], **datos)
    v = uno(previo["id"])
    eventos.registrar("viaje", v["id"], "presupuesto actualizado", f"{v['codigo']} · {total:.2f} USD · vuelve a aprobación")
    return v


TRANSICIONES = {   # acción: (estados desde los que se permite, estado al que lleva, paso que se registra)
    "aprobar": (("pendiente_aprobacion",), "aprobado", "presupuesto aprobado"),
    "rechazar": (("pendiente_aprobacion",), "rechazado", "presupuesto rechazado"),
    "reabrir": (("aprobado", "rechazado", "cerrado"), "pendiente_aprobacion", "viaje reabierto"),
    "cerrar": (("aprobado",), "cerrado", "viaje cerrado"),
}


NO_AUTOAPROBAR = "Nadie aprueba ni rechaza su propio presupuesto: debe hacerlo otra persona de administración."


def es_propio_de(viaje: dict | None, u: dict | None) -> bool:
    """El viaje es de la persona: es su titular o es quien viaja. A diferencia de `acceso.es_propio`, ser admin no cuenta."""
    if not viaje or not u:
        return False
    return viaje.get("usuario_id") == u["id"] or bool(u.get("viajero_id") and viaje.get("viajero_id") == u["viajero_id"])


def hay_otro_admin(u: dict) -> bool:
    """Si existe otra cuenta de administración activa que pueda aprobar lo de esta persona."""
    return bool(db.uno("select id from usuarios where rol='admin' and activo=1 and id<>:i limit 1", i=u["id"]))


def impedir_autoaprobacion(entidad: str, entidad_id: int, quien: dict, que: str) -> None:
    """Deja constancia de cada intento de aprobar o revisar lo propio: quién y qué."""
    eventos.registrar(entidad, entidad_id, "autoaprobación impedida", f"{quien['nombre']} intentó {que}", quien["nombre"])


def cambiar_estado(viaje_id: int, accion: str, motivo: str, quien: dict) -> tuple[bool, str]:
    """Solo administración mueve el estado, y nadie aprueba ni rechaza su propio presupuesto.

    Devuelve (hecho, mensaje para mostrar).
    """
    v = uno(viaje_id)
    if not v or accion not in TRANSICIONES:
        return False, "Viaje o acción no válidos."
    if not acceso.es_admin(quien):
        return False, "Solo un administrador puede aprobar, rechazar, reabrir o cerrar un viaje."
    if accion in ("aprobar", "rechazar") and es_propio_de(v, quien):
        impedir_autoaprobacion("viaje", viaje_id, quien, f"{accion} el presupuesto de su propio viaje {v['codigo']}")
        return False, NO_AUTOAPROBAR
    desde, hacia, paso = TRANSICIONES[accion]
    if v["estado"] not in desde:
        return False, f"El viaje {v['codigo']} está {v['estado_texto'].lower()}: no se puede {accion}."
    motivo = (motivo or "").strip()[:300]
    if accion == "rechazar" and len(motivo) < 5:
        return False, "Para rechazar un presupuesto hay que escribir el motivo."
    aprobado = hacia == "aprobado"
    db.actualizar("viajes", viaje_id, estado=hacia, motivo=motivo or None,
                  aprobado_por=quien["id"] if aprobado else None, aprobado_en=db.ahora() if aprobado else None)
    eventos.registrar("viaje", viaje_id, paso, f"{v['codigo']}" + (f" · {motivo}" if motivo else ""), quien["nombre"])
    from . import telegram  # el titular se entera por su chat, si lo tiene vinculado
    telegram.avisar(v["usuario_id"], f"Viaje {v['codigo']} ({v['origen']} → {v['destino']}, {v['ida']}): {paso}."
                    + (f"\nMotivo: {motivo}" if motivo else "")
                    + (f"\nPresupuesto: {v['presupuesto_usd']:.2f} USD. Ya puedes enviar tus recibos por aquí." if aprobado else ""))
    return True, f"{v['codigo']}: {paso}."


# ---------- a qué viaje pertenece un gasto ----------
def de_persona(usuario: dict, estados: tuple = ("aprobado",)) -> list[dict]:
    marcas = ",".join(f"'{e}'" for e in estados if e in ESTADOS)
    return lista(f"(v.usuario_id=:u or (v.viajero_id is not null and v.viajero_id=:vj)) and v.estado in ({marcas})",
                 u=usuario["id"], vj=usuario.get("viajero_id") or -1)


def resolver_para_gasto(usuario: dict, viaje_id: int | None = None, hoy: date | None = None) -> tuple[dict | None, list[dict]]:
    """Devuelve (viaje, candidatos). Si no hay uno claro, el viaje es None y los candidatos permiten preguntar.

    Orden: el que la persona indica; el que fijó como activo; el aprobado que está en curso hoy;
    el próximo aprobado (los tiquetes se compran antes); y si no hay ninguno aprobado, el único pendiente.
    """
    hoy = hoy or date.today()
    if viaje_id:
        v = uno(viaje_id)   # cargar un gasto a un viaje es escribir en él: ver no basta
        return (v, []) if v and acceso.es_propio(usuario, v) else (None, [])
    if usuario.get("viaje_activo_id"):
        v = uno(usuario["viaje_activo_id"])
        if v and v["estado"] == "aprobado" and acceso.puede_ver(usuario, v):
            return v, []
    aprobados = de_persona(usuario)
    ahora = [v for v in aprobados if en_curso(v, hoy)]
    if len(ahora) == 1:
        return ahora[0], []
    if len(ahora) > 1:
        return None, ahora
    proximos = sorted((v for v in aprobados if (v["ida"] or "") >= hoy.isoformat()), key=lambda v: v["ida"])
    if proximos:
        mismo_dia = [v for v in proximos if v["ida"] == proximos[0]["ida"]]
        return (proximos[0], []) if len(mismo_dia) == 1 else (None, mismo_dia)
    if aprobados:
        return None, aprobados   # solo viajes ya pasados: mejor preguntar que adivinar
    pendientes = de_persona(usuario, ("pendiente_aprobacion",))
    return (pendientes[0], []) if len(pendientes) == 1 else (None, pendientes)


NO_AUTORREVISAR = "Nadie revisa sus propios gastos: debe hacerlo otra persona de administración."


def gasto_propio_de(gasto: dict | None, u: dict | None) -> bool:
    """El gasto es de la persona: se carga a su perfil de viajero, a un viaje suyo, o lo subió sin cargarlo a nadie más.

    Un recibo que administración sube a nombre de otra persona es de esa persona, no de quien lo subió.
    """
    if not gasto or not u:
        return False
    if u.get("viajero_id") and gasto.get("viajero_id") == u["viajero_id"]:
        return True
    if not gasto.get("viajero_id") and gasto.get("usuario_id") == u["id"]:
        return True
    return es_propio_de(uno(gasto.get("viaje_id")), u)


def revision_permitida(gid: int, antes: dict, despues: dict, quien: dict, accion: str) -> str | None:
    """Nadie revisa sus propios gastos, ni los que la revisión le asignaría a sí mismo. Devuelve el aviso si se impide."""
    if gasto_propio_de(antes, quien) or gasto_propio_de(despues, quien):
        impedir_autoaprobacion("gasto", gid, quien, f"{accion} su propio gasto #{gid} en la revisión")
        return NO_AUTORREVISAR
    return None


def gastado(viaje_id: int, excepto_gasto: int = 0) -> float:
    return db.uno("""select coalesce(sum(total_usd),0) t from gastos where viaje_id=:v and id<>:g
                     and estado in ('aprobado','aprobado_auto')""", v=viaje_id, g=excepto_gasto)["t"] or 0


def resumen(viaje_id: int) -> dict | None:
    filas = lista("v.id=:i", i=viaje_id)
    return filas[0] if filas else None
