"""Límite de intentos de ingreso: por dirección y por correo, en una ventana corta.

Complementa el bloqueo progresivo de cada cuenta (`acceso.autenticar`): este corta también a quien prueba muchos
correos desde una dirección, o un mismo correo desde muchas, aunque la cuenta no exista. Se comprueba antes de
verificar la contraseña. La tabla guarda solo huellas: ni el correo ni la dirección quedan a la vista.
"""
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, Text

from .. import db

intentos_ingreso = db._tabla(
    "intentos_ingreso",   # una fila por intento fallido y por clave (dirección o correo); solo la usa el servidor
    Column("clave", Text, nullable=False), Column("momento", Text, nullable=False),
)

VENTANA = timedelta(minutes=15)
MAX_POR_DIRECCION = 20   # una oficina comparte dirección: más holgado que por correo
MAX_POR_CORREO = 10
CONSERVAR = timedelta(days=1)
DEMASIADOS = "Demasiados intentos de ingreso. Espera unos minutos y vuelve a intentar."


def _huella(prefijo: str, valor: str) -> str:
    return prefijo + ":" + hashlib.sha256(valor.encode()).hexdigest()[:32]


def clave_correo(correo: str) -> str:
    return _huella("correo", (correo or "").strip().lower())


def clave_direccion(direccion: str) -> str:
    return _huella("dir", direccion or "desconocida")


def _momento(delta: timedelta) -> str:
    return (datetime.now(UTC) - delta).strftime("%Y-%m-%d %H:%M:%S")


def _fallos(clave: str) -> int:
    return db.uno("select count(*) n from intentos_ingreso where clave=:c and momento>=:d", c=clave, d=_momento(VENTANA))["n"]


def limitado(direccion: str, correo: str) -> bool:
    """Si ya hubo demasiados fallos en la ventana desde esa dirección o con ese correo."""
    return _fallos(clave_direccion(direccion)) >= MAX_POR_DIRECCION or _fallos(clave_correo(correo)) >= MAX_POR_CORREO


def anotar_fallo(direccion: str, correo: str):
    db.insertar_varios("intentos_ingreso", [{"clave": clave_direccion(direccion), "momento": db.ahora()},
                                            {"clave": clave_correo(correo), "momento": db.ahora()}])
    db.ejecutar("delete from intentos_ingreso where momento<:d", d=_momento(CONSERVAR))   # la tabla no crece


def anotar_exito(correo: str):
    """Un ingreso bueno borra los fallos de ese correo (los de la dirección siguen contando)."""
    db.ejecutar("delete from intentos_ingreso where clave=:c", c=clave_correo(correo))
