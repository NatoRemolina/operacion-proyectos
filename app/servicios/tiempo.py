"""El día de la empresa: una sola zona (`config.ZONA_EMPRESA`) para los topes «por día», la fecha de hoy y los periodos.

Los momentos se guardan en UTC. Si los topes contaran el día en UTC, desde las 19:00 de Bogotá ya sería el día
siguiente: el tope se reiniciaría a media tarde y un viaje dejaría de estar en curso antes de tiempo.
"""
from datetime import UTC, date, datetime

from .. import config

FORMATO = "%Y-%m-%d %H:%M:%S"   # el de `db.ahora()`, con el que se comparan los momentos guardados


def ahora() -> datetime:
    """El instante actual, en UTC. Las pruebas lo reemplazan para fijar el reloj."""
    return datetime.now(UTC)


def hoy(momento: datetime | None = None) -> date:
    """La fecha de hoy en la zona de la empresa."""
    return (momento or ahora()).astimezone(config.ZONA_EMPRESA).date()


def _medianoche(local: datetime) -> str:
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).strftime(FORMATO)


def inicio_del_dia(momento: datetime | None = None) -> str:
    """Desde cuándo cuenta un tope «por día»: la medianoche de hoy en la zona de la empresa, en UTC."""
    return _medianoche((momento or ahora()).astimezone(config.ZONA_EMPRESA))


def inicio_del_mes(momento: datetime | None = None) -> str:
    """Desde cuándo cuenta un tope «por mes»: la medianoche del primer día del mes en la zona de la empresa, en UTC."""
    return _medianoche((momento or ahora()).astimezone(config.ZONA_EMPRESA).replace(day=1))
