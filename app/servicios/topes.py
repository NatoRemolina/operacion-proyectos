"""Topes por día: cada unidad se reserva antes de gastar (una búsqueda paga, una lectura del modelo, una cotización).

`reservar` cuenta y escribe la reserva en una sola transacción, en fila con las demás reservas de la misma regla
(`db.cerrojo`): varias peticiones a la vez no pasan juntas el tope. El día es el de la empresa (`tiempo.inicio_del_dia`).
El valor de cada tope es una regla editable (Reglas y supuestos); si falta o está mal escrita, vale `LIMITES`.
"""
from sqlalchemy import Column, Integer, Text

from .. import db
from . import costo, tiempo

topes_reservas = db._tabla(
    "topes_reservas",   # una fila por unidad reservada de un tope; solo la usa el servidor
    Column("regla", Text, nullable=False), Column("usuario_id", Integer), Column("momento", Text, nullable=False),
    Column("detalle", Text),
)
# Sin clave foránea a `usuarios` a propósito: es un registro, como `eventos`; borrar una cuenta no borra su consumo

# Valor de cada tope si la regla falta. Cada servicio siembra su regla con la nota que la explica.
LIMITES: dict[str, int] = {
    "tope_cotizaciones_persona_dia": 20,
}


def limite(regla: str) -> int:
    return int(costo.supuesto(costo.catalogo(), regla, LIMITES.get(regla, 0)))


def usadas(regla: str, quien: dict | None = None) -> int:
    """Unidades reservadas hoy de `regla`: las de la persona o, sin ella, las de todos."""
    filtro, p = ("and usuario_id=:u", {"u": quien["id"]}) if quien else ("", {})
    return db.uno(f"select count(*) n from topes_reservas where regla=:r and momento>=:d {filtro}",  # noqa: S608
                  r=regla, d=tiempo.inicio_del_dia(), **p)["n"]


def reservar(regla: str, quien: dict | None, *, total: str | None = None, detalle: str = "") -> bool:
    """Reserva una unidad de `regla` (por persona y día) y, con `total`, también del tope del día de toda la empresa
    (las reservas de `regla` de todas las personas frente a la regla `total`). False si no alcanza: no se reserva nada."""
    with db.transaccion():
        db.cerrojo(("tope", regla))
        if quien and usadas(regla, quien) >= limite(regla):
            return False
        if total and usadas(regla) >= limite(total):
            return False
        db.insertar("topes_reservas", regla=regla, usuario_id=quien["id"] if quien else None, momento=db.ahora(),
                    detalle=detalle[:200] or None)
        return True
