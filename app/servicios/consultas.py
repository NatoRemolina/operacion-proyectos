"""Lecturas con alcance para la API v1: viajes, gastos y soportes que la persona puede ver, ya con la forma del contrato.

Toda consulta parte de la persona de la sesión: los listados se limitan con `acceso.alcance` y los detalles con
`acceso.puede_ver`. Lo que no se puede ver devuelve None, igual que lo inexistente (la API responde 404 en ambos casos).
Contrato: `contracts/api-v1.md`.
"""
import re
from decimal import ROUND_HALF_UP, Decimal

from .. import db
from . import acceso, almacen, justificaciones, viajes

ESTADO_GASTO = {"procesando": "Procesando", "revision": "En revisión", "aprobado_auto": "Aprobado automático",
                "aprobado": "Aprobado", "rechazado": "Rechazado"}
# Solo se sirven con su tipo los formatos inertes; un correo se entrega como texto
TIPOS_EN_LINEA = ("image/jpeg", "image/png", "image/webp", "application/pdf")
_INSTANTE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


# ---------- formato de salida ----------
def dinero(valor) -> str | None:
    """Los importes están en coma flotante en la base; salen como cadena con dos cifras ("54.00")."""
    if valor is None:
        return None
    return str(Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def instante(valor: str | None) -> str | None:
    """Los instantes se guardan en UTC como "2026-11-12 04:13:13"; el contrato los pide "2026-11-12T04:13:13Z"."""
    if valor and _INSTANTE.match(valor):
        return valor.replace(" ", "T") + "Z"
    return valor


def persona(u: dict) -> dict:
    return {"id": u["id"], "codigo": viajes.codigo_persona(u["id"]), "nombre": u["nombre"], "rol": u["rol"], "correo": u["correo"]}


def _pagina(filas: list[dict], limite: int) -> dict:
    """Se piden limite+1 filas: si sobra una, hay página siguiente y el cursor es el último id entregado."""
    items = filas[:limite]
    return {"items": items, "siguiente": str(items[-1]["id"]) if len(filas) > limite else None}


# ---------- viajes ----------
def _viaje_resumen(v: dict) -> dict:
    return {
        "id": v["id"], "codigo": v["codigo"], "estado": v["estado"], "estado_texto": v["estado_texto"], "en_curso": v["en_curso"],
        "origen": v["origen"], "destino": v["destino"], "ida": v["ida"], "regreso": v["regreso"],
        "proyecto": {"id": v["proyecto_id"], "nombre": v["proyecto"]} if v["proyecto_id"] else None,
        "titular": {"id": v["usuario_id"], "codigo": viajes.codigo_persona(v["usuario_id"]), "nombre": v["titular"]}
        if v["usuario_id"] else None,
        "presupuesto_usd": dinero(v["presupuesto_usd"]), "gastado_usd": dinero(v["gastado"]),
        "en_revision_usd": dinero(v["en_revision"]), "ejecucion_pct": v["pct"], "gastos": v["n_gastos"],
    }


def lista_viajes(u: dict, estado: str | None = None, limite: int = 20, cursor: int | None = None) -> dict:
    donde, p = acceso.alcance(u, "v")
    if estado:
        donde, p = donde + " and v.estado=:_estado", {**p, "_estado": estado}
    if cursor:
        donde, p = donde + " and v.id<:_cursor", {**p, "_cursor": cursor}
    filas = viajes.lista(donde, **p)[:limite + 1]
    return _pagina([_viaje_resumen(v) for v in filas], limite)


def viaje(u: dict, viaje_id: int) -> dict | None:
    v = viajes.resumen(viaje_id)
    if not v or not acceso.puede_ver(u, v):
        return None
    return {**_viaje_resumen(v),
            "presupuesto_detalle": [{"concepto": l.get("concepto", ""), "valor": dinero(l.get("valor")), "grupo": l.get("grupo", "otros")}
                                    for l in db.de_json(v["presupuesto_detalle"], []) or []],
            "motivo": v["motivo"], "aprobado_en": instante(v["aprobado_en"])}


# ---------- gastos ----------
_GASTOS = """select g.*, d.canal, v.creado viaje_creado from gastos g
             left join documentos d on d.id=g.documento_id left join viajes v on v.id=g.viaje_id"""


def _gasto_resumen(g: dict) -> dict:
    return {
        "id": g["id"],
        "viaje": {"id": g["viaje_id"], "codigo": viajes.codigo_viaje({"id": g["viaje_id"], "creado": g["viaje_creado"]})}
        if g["viaje_id"] else None,
        "comercio": g["comercio"], "fecha": g["fecha"], "categoria": g["categoria"],
        "total": dinero(g["total"]), "moneda": g["moneda"], "total_usd": dinero(g["total_usd"]),
        "estado": g["estado"], "estado_texto": ESTADO_GASTO.get(g["estado"], g["estado"]), "creado": instante(g["creado"]),
    }


def lista_gastos(u: dict, viaje_id: int | None = None, estado: str | None = None, limite: int = 20,
                 cursor: int | None = None) -> dict:
    donde, p = acceso.alcance(u, "g")
    for condicion, nombre, valor in (("g.viaje_id=:_viaje", "_viaje", viaje_id), ("g.estado=:_estado", "_estado", estado),
                                     ("g.id<:_cursor", "_cursor", cursor)):
        if valor:
            donde, p = f"{donde} and {condicion}", {**p, nombre: valor}
    filas = db.todos(f"{_GASTOS} where {donde} order by g.id desc limit :_n", _n=limite + 1, **p)
    return _pagina([_gasto_resumen(g) for g in filas], limite)


def gasto(u: dict, gasto_id: int) -> dict | None:
    g = db.uno(f"{_GASTOS} where g.id=:_id", _id=gasto_id)
    if not g or not acceso.puede_ver(u, g):
        return None
    return {**_gasto_resumen(g),
            "subtotal": dinero(g["subtotal"]), "impuesto": dinero(g["impuesto"]), "propina": dinero(g["propina"]),
            "motivos": db.de_json(g["motivos"], []) or [], "alertas": db.de_json(g["alertas"], []) or [],
            "canal": g["canal"] or "web", "documento_id": g["documento_id"],
            "lectura": {"origen": g["origen_dato"] or "sin datos", "confianza": g["confianza"]},
            "justificaciones": [{k: j[k] for k in ("id", "tipo", "canal", "texto", "transcripcion", "creado")}
                                for j in justificaciones.de_gasto(gasto_id)]}


# ---------- soportes ----------
def contenido_documento(u: dict, documento_id: int) -> tuple[bytes, str] | None:
    """El archivo original de un soporte y el tipo con que se sirve. Se ve si se ve el gasto al que pertenece."""
    d = db.uno("""select d.ruta, d.mime, g.usuario_id, g.viajero_id, g.proyecto_id from documentos d
                  join gastos g on g.documento_id=d.id where d.id=:i""", i=documento_id)
    if not d or not d["ruta"] or not acceso.puede_ver(u, d):
        return None
    contenido = almacen.leer(d["ruta"])
    if contenido is None:
        return None
    return contenido, d["mime"] if d["mime"] in TIPOS_EN_LINEA else "text/plain; charset=utf-8"
