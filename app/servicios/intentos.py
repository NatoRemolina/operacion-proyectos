"""Límite de intentos de ingreso en una ventana corta: por correo y dirección juntos, por dirección y solo por correo.

Complementa el bloqueo progresivo de cada cuenta (`acceso.autenticar`): corta a quien prueba un correo desde una
dirección (10), muchos correos desde una dirección (20) o un mismo correo desde muchas (50), aunque la cuenta no
exista. El umbral solo por correo es holgado para que fallar con el correo de otra persona desde otra dirección no la
deje por fuera. Se comprueba antes de verificar la contraseña. La tabla guarda solo huellas: ni el correo ni la
dirección quedan a la vista.
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
MAX_POR_PAR = 10          # el mismo correo desde la misma dirección
MAX_POR_DIRECCION = 20    # una oficina comparte dirección: más holgado
MAX_POR_CORREO = 50       # desde muchas direcciones: holgado, para no dejar por fuera a la dueña de la cuenta
CONSERVAR = timedelta(days=1)
DEMASIADOS = "Demasiados intentos de ingreso. Espera unos minutos y vuelve a intentar."


def _huella(prefijo: str, valor: str) -> str:
    return prefijo + ":" + hashlib.sha256(valor.encode()).hexdigest()[:32]


def clave_correo(correo: str) -> str:
    return _huella("correo", (correo or "").strip().lower())


def clave_direccion(direccion: str) -> str:
    return _huella("dir", direccion or "desconocida")


def clave_par(direccion: str, correo: str) -> str:
    return _huella("par", f"{(correo or '').strip().lower()}|{direccion or 'desconocida'}")


def _momento(delta: timedelta) -> str:
    return (datetime.now(UTC) - delta).strftime("%Y-%m-%d %H:%M:%S")


def _fallos(clave: str) -> int:
    return db.uno("select count(*) n from intentos_ingreso where clave=:c and momento>=:d", c=clave, d=_momento(VENTANA))["n"]


def limitado(direccion: str, correo: str) -> bool:
    """Si ya hubo demasiados fallos en la ventana con ese correo desde esa dirección, desde esa dirección o con ese correo."""
    return _fallos(clave_par(direccion, correo)) >= MAX_POR_PAR or _fallos(clave_direccion(direccion)) >= MAX_POR_DIRECCION \
        or _fallos(clave_correo(correo)) >= MAX_POR_CORREO


def avisar_limite(direccion: str, correo: str) -> bool:
    """True la primera vez en la ventana que se limita ese correo desde esa dirección: el evento «ingreso limitado» se
    escribe una vez por ventana, no en cada intento (quien insiste no llena la bitácora)."""
    marca = _huella("aviso", clave_par(direccion, correo))
    with db.transaccion():
        db.cerrojo(marca)
        if _fallos(marca):
            return False
        db.insertar("intentos_ingreso", clave=marca, momento=db.ahora())
    return True


def anotar_fallo(direccion: str, correo: str):
    ahora = db.ahora()
    db.insertar_varios("intentos_ingreso", [{"clave": clave_direccion(direccion), "momento": ahora},
                                            {"clave": clave_correo(correo), "momento": ahora},
                                            {"clave": clave_par(direccion, correo), "momento": ahora}])
    db.ejecutar("delete from intentos_ingreso where momento<:d", d=_momento(CONSERVAR))   # la tabla no crece


def anotar_exito(direccion: str, correo: str):
    """Un ingreso bueno borra los fallos de ese correo y los de ese correo desde esa dirección (los de la dirección
    siguen contando)."""
    db.ejecutar("delete from intentos_ingreso where clave in (:c, :p)", c=clave_correo(correo), p=clave_par(direccion, correo))
