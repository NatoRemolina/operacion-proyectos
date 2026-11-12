"""Envíos repetidos de un mismo recibo: la misma clave de la misma persona devuelve el mismo gasto.

Cada envío con clave deja una fila en `envios_soporte`. Quien la crea tiene la concesión (un dueño y un vencimiento)
mientras lee el recibo; un reintento con la misma clave recibe el gasto que ya existe, aunque siga en lectura.
Si el dueño se cae o tarda más que la concesión, el siguiente reintento recupera el envío: el gasto pasa a revisión
y el dueño anterior ya no puede escribir (se le cambia el dueño).
"""
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.exc import IntegrityError

from .. import config, db
from . import eventos, revision

VIGENCIA = timedelta(minutes=15)
LARGO_MAXIMO = 200
INTERRUMPIDA = "La lectura del recibo se interrumpió. Administración revisará el soporte, que quedó guardado."

envios_soporte = db._tabla(
    "envios_soporte",  # una fila por (persona, clave); solo la usa el servidor
    Column("usuario_id", Integer, ForeignKey("usuarios.id", name="fk_envios_soporte_usuario_id"), nullable=False),
    Column("clave", Text, nullable=False), Column("huella", Text, nullable=False), Column("estado", Text, nullable=False),
    db._ref("envios_soporte", "gasto_id", "gastos"), Column("propietario", Text), Column("expira", Text), Column("creado", Text),
    UniqueConstraint("usuario_id", "clave", name="ux_envios_persona_clave"),
)


class ConflictoEnvio(ValueError):
    """La clave ya se usó con otro archivo u otro viaje."""


class EnvioEnCurso(ValueError):
    """Otro proceso tiene la concesión del envío."""


def huella(contenido: bytes, contexto: dict) -> str:
    """El archivo junto con lo que se pidió (viaje, proyecto, persona): la misma clave con otro viaje es otro envío."""
    return hashlib.sha256(contenido + json.dumps(contexto, sort_keys=True, default=str).encode()).hexdigest()


def _vence() -> str:
    return (datetime.now(UTC) + VIGENCIA).strftime("%Y-%m-%d %H:%M:%S")


def _bloqueada(usuario_id: int, clave: str) -> dict:
    return db.uno("select * from envios_soporte where usuario_id=:u and clave=:c" + ("" if config.ES_SQLITE else " for update"),
                  u=usuario_id, c=clave)


def marcar_interrumpido(gasto_id: int, detalle: str = INTERRUMPIDA) -> bool:
    """Un gasto que quedó «procesando» pasa a revisión con su motivo. Lo ya decidido no se toca."""
    hecho = db.uno("select id from gastos where id=:i and estado='procesando'", i=gasto_id)
    if hecho:
        db.ejecutar("""update gastos set estado='revision', motivos=:m, alertas=:a where id=:i and estado='procesando'""",
                    i=gasto_id, m=json.dumps(["lectura_fallida"]), a=json.dumps([detalle], ensure_ascii=False))
        revision.subir_version(gasto_id)
        eventos.registrar("gasto", gasto_id, "enviado a revisión", detalle, "recuperación del envío")
    return bool(hecho)


def reclamar(usuario_id: int, clave: str, huella_envio: str) -> tuple[dict, bool]:
    """Devuelve (envío, repetido). Repetido: ya hay un gasto para esta clave y no hay que leer de nuevo.

    Lanza ConflictoEnvio si la clave se usó con otro contenido, y EnvioEnCurso si otro proceso la está atendiendo
    y todavía no creó el gasto.
    """
    token = secrets.token_hex(16)
    with db.transaccion() as c:
        try:
            with c.begin_nested():   # la clave puede existir ya: el error se atrapa y la transacción sigue
                nuevo = db.insertar("envios_soporte", usuario_id=usuario_id, clave=clave, huella=huella_envio,
                                    estado="procesando", propietario=token, expira=_vence(), creado=db.ahora())
            return db.uno("select * from envios_soporte where id=:i", i=nuevo), False
        except IntegrityError:
            pass
        fila = _bloqueada(usuario_id, clave)
        if fila["huella"] != huella_envio:
            raise ConflictoEnvio("Esa clave de envío ya se usó con otro archivo o con otro viaje.")
        vencido = fila["estado"] == "fallido" or (fila["estado"] == "procesando" and (fila["expira"] or "") <= db.ahora())
        if fila["gasto_id"]:
            if vencido:
                marcar_interrumpido(fila["gasto_id"])
                # Se cambia el dueño: el proceso anterior, si vuelve, ya no puede escribir sobre la revisión recuperada
                db.actualizar("envios_soporte", fila["id"], estado="completado", propietario=token)
                return {**fila, "estado": "completado", "propietario": token}, True
            return fila, True
        if not vencido:
            raise EnvioEnCurso("Ese envío todavía se está procesando. Reintenta en un momento con la misma clave.")
        db.actualizar("envios_soporte", fila["id"], estado="procesando", propietario=token, expira=_vence())
        return {**fila, "estado": "procesando", "propietario": token}, False


def comprobar(op: dict):
    """Dentro de una transacción: confirma que el envío sigue siendo de este proceso, y lo bloquea hasta el final."""
    fila = db.uno("select propietario from envios_soporte where id=:i" + ("" if config.ES_SQLITE else " for update"), i=op["id"])
    if not fila or fila["propietario"] != op["propietario"]:
        raise EnvioEnCurso("Otro proceso recuperó este envío.")


def enlazar(op: dict, gasto_id: int):
    comprobar(op)
    db.actualizar("envios_soporte", op["id"], gasto_id=gasto_id)


def terminar(op: dict, estado: str):
    """Libera la concesión: `completado` o `fallido`. Solo lo hace su dueño."""
    db.ejecutar("update envios_soporte set estado=:e where id=:i and propietario=:p", e=estado, i=op["id"], p=op["propietario"])
