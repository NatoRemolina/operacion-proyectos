"""Envíos repetidos (Idempotency-Key): la misma clave de la misma persona devuelve lo mismo. Es la única forma de
idempotencia de la plataforma: la usan los recibos (`SOPORTE`, el gasto) y las cotizaciones (`COTIZACION`, la solicitud).

Cada envío con clave deja una fila en su tabla. Quien la crea tiene la concesión (un dueño y un vencimiento) mientras
trabaja; un reintento con la misma clave recibe lo que ya existe. Si el dueño se cae o tarda más que la concesión, el
siguiente reintento la retoma y el dueño anterior ya no puede escribir (se le cambia el dueño). En un recibo, el gasto
existe desde el principio: al retomarlo pasa a revisión.
"""
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.exc import IntegrityError

from .. import config, db
from . import eventos, revision

VIGENCIA = timedelta(minutes=5)   # la función de la nube se corta a los 180 s: pasado esto, nadie va a terminar la lectura
LARGO_MAXIMO = 200
INTERRUMPIDA = "La lectura del recibo se interrumpió. Administración revisará el soporte, que quedó guardado."

envios_soporte = db._tabla(
    "envios_soporte",  # una fila por (persona, clave); solo la usa el servidor
    Column("usuario_id", Integer, ForeignKey("usuarios.id", name="fk_envios_soporte_usuario_id"), nullable=False),
    Column("clave", Text, nullable=False), Column("huella", Text, nullable=False), Column("estado", Text, nullable=False),
    db._ref("envios_soporte", "gasto_id", "gastos"), Column("propietario", Text), Column("expira", Text), Column("creado", Text),
    UniqueConstraint("usuario_id", "clave", name="ux_envios_persona_clave"),
)
envios_cotizacion = db._tabla(
    "envios_cotizacion",  # una fila por (persona, clave); solo la usa el servidor
    Column("usuario_id", Integer, ForeignKey("usuarios.id", name="fk_envios_cotizacion_usuario_id"), nullable=False),
    Column("clave", Text, nullable=False), Column("huella", Text, nullable=False), Column("estado", Text, nullable=False),
    db._ref("envios_cotizacion", "solicitud_id", "solicitudes"), Column("propietario", Text), Column("expira", Text),
    Column("creado", Text),
    UniqueConstraint("usuario_id", "clave", name="ux_envios_cotizacion_persona_clave"),
)


@dataclass(frozen=True)
class Registro:
    """Dónde se guardan los envíos de un tipo y qué crean."""
    tabla: str
    recurso: str        # la columna con lo creado: el gasto o la cotización
    conflicto: str      # la misma clave con otro contenido
    en_curso: str       # el primero todavía trabaja


SOPORTE = Registro("envios_soporte", "gasto_id", "Esa clave de envío ya se usó con otro archivo o con otro viaje.",
                   "Ese envío todavía se está procesando. Reintenta en un momento con la misma clave.")
COTIZACION = Registro("envios_cotizacion", "solicitud_id", "Esa clave ya se usó con otra cotización.",
                      "Esa cotización todavía se está buscando. Reintenta en un momento con la misma clave.")


class ConflictoEnvio(ValueError):
    """La clave ya se usó con otro archivo u otro viaje."""


class EnvioEnCurso(ValueError):
    """Otro proceso tiene la concesión del envío."""


def huella(contenido: bytes, contexto: dict) -> str:
    """El archivo junto con lo que se pidió (viaje, proyecto, persona): la misma clave con otro viaje es otro envío.
    Un pedido sin archivo (una cotización) va con `contenido` vacío."""
    return hashlib.sha256(contenido + json.dumps(contexto, sort_keys=True, default=str).encode()).hexdigest()


def _vence() -> str:
    return (datetime.now(UTC) + VIGENCIA).strftime("%Y-%m-%d %H:%M:%S")


def _bloqueada(registro: Registro, usuario_id: int, clave: str) -> dict:
    return db.uno(f"select * from {registro.tabla} where usuario_id=:u and clave=:c"  # noqa: S608  tabla de un registro fijo
                  + ("" if config.ES_SQLITE else " for update"), u=usuario_id, c=clave)


def marcar_interrumpido(gasto_id: int, detalle: str = INTERRUMPIDA) -> bool:
    """Un gasto que quedó «procesando» pasa a revisión con su motivo. Lo ya decidido no se toca."""
    hecho = db.uno("select id from gastos where id=:i and estado='procesando'", i=gasto_id)
    if hecho:
        db.ejecutar("""update gastos set estado='revision', motivos=:m, alertas=:a where id=:i and estado='procesando'""",
                    i=gasto_id, m=json.dumps(["lectura_fallida"]), a=json.dumps([detalle], ensure_ascii=False))
        revision.subir_version(gasto_id)
        eventos.registrar("gasto", gasto_id, "enviado a revisión", detalle, "recuperación del envío")
    return bool(hecho)


def recuperar_si_atascado(gasto: dict) -> bool:
    """Un gasto «procesando» desde antes de la vigencia ya no tiene quién lo termine (el proceso se cortó o cayó):
    pasa a revisión, y el envío enlazado cambia de dueño para que el proceso anterior, si vuelve, no escriba."""
    limite = (datetime.now(UTC) - VIGENCIA).strftime("%Y-%m-%d %H:%M:%S")
    if gasto["estado"] != "procesando" or (gasto.get("creado") or "") > limite:
        return False
    db.ejecutar("update envios_soporte set estado='completado', propietario=:p where gasto_id=:g",
                p=secrets.token_hex(16), g=gasto["id"])
    return marcar_interrumpido(gasto["id"])


def reclamar(usuario_id: int, clave: str, huella_envio: str, registro: Registro = SOPORTE) -> tuple[dict, bool]:
    """Devuelve (envío, repetido). Repetido: lo que pidió esta clave ya existe (`envío[registro.recurso]`) y no hay que
    hacerlo de nuevo.

    Lanza ConflictoEnvio si la clave se usó con otro contenido, y EnvioEnCurso si otro proceso la está atendiendo
    y todavía no creó nada.
    """
    token = secrets.token_hex(16)
    tabla, recurso = registro.tabla, registro.recurso
    with db.transaccion() as c:
        try:
            with c.begin_nested():   # la clave puede existir ya: el error se atrapa y la transacción sigue
                nuevo = db.insertar(tabla, usuario_id=usuario_id, clave=clave, huella=huella_envio,
                                    estado="procesando", propietario=token, expira=_vence(), creado=db.ahora())
            return db.uno(f"select * from {tabla} where id=:i", i=nuevo), False  # noqa: S608  tabla de un registro fijo
        except IntegrityError:
            pass
        fila = _bloqueada(registro, usuario_id, clave)
        if fila["huella"] != huella_envio:
            raise ConflictoEnvio(registro.conflicto)
        vencido = fila["estado"] == "fallido" or (fila["estado"] == "procesando" and (fila["expira"] or "") <= db.ahora())
        if fila[recurso]:
            if vencido and registro is SOPORTE:
                marcar_interrumpido(fila["gasto_id"])
                # Se cambia el dueño: el proceso anterior, si vuelve, ya no puede escribir sobre la revisión recuperada
                db.actualizar(tabla, fila["id"], estado="completado", propietario=token)
                return {**fila, "estado": "completado", "propietario": token}, True
            return fila, True
        if not vencido:
            raise EnvioEnCurso(registro.en_curso)
        db.actualizar(tabla, fila["id"], estado="procesando", propietario=token, expira=_vence())
        return {**fila, "estado": "procesando", "propietario": token}, False


def comprobar(op: dict, registro: Registro = SOPORTE):
    """Dentro de una transacción: confirma que el envío sigue siendo de este proceso, y lo bloquea hasta el final."""
    fila = db.uno(f"select propietario from {registro.tabla} where id=:i"  # noqa: S608  tabla de un registro fijo
                  + ("" if config.ES_SQLITE else " for update"), i=op["id"])
    if not fila or fila["propietario"] != op["propietario"]:
        raise EnvioEnCurso("Otro proceso recuperó este envío.")


def enlazar(op: dict, gasto_id: int):
    comprobar(op)
    db.actualizar("envios_soporte", op["id"], gasto_id=gasto_id)


def terminar(op: dict, estado: str, registro: Registro = SOPORTE):
    """Libera la concesión: `completado` o `fallido`. Solo lo hace su dueño."""
    db.ejecutar(f"update {registro.tabla} set estado=:e where id=:i and propietario=:p",  # noqa: S608  tabla de un registro fijo
                e=estado, i=op["id"], p=op["propietario"])


def completar(op: dict, recurso_id: int, registro: Registro = COTIZACION):
    """Anota lo creado y da el envío por terminado. Solo lo hace su dueño: quien perdió la concesión no escribe."""
    db.ejecutar(f"""update {registro.tabla} set estado='completado', {registro.recurso}=:r
                    where id=:i and propietario=:p""", r=recurso_id, i=op["id"], p=op["propietario"])  # noqa: S608


def soltar(op: dict, registro: Registro = COTIZACION):
    """El pedido no creó nada (datos que no sirven o un fallo): la clave queda libre para reintentar. Solo su dueño."""
    db.ejecutar(f"delete from {registro.tabla} where id=:i and propietario=:p and {registro.recurso} is null",  # noqa: S608
                i=op["id"], p=op["propietario"])
