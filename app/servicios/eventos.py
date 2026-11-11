"""Bitácora de lo que le pasa a cada dato. Alimenta la página de flujo de la información."""
import time
from contextlib import contextmanager

from .. import db


def registrar(entidad: str, entidad_id: int | None, paso: str, detalle: str = "", fuente: str = "", duracion_ms: int = 0):
    db.insertar("eventos", momento=db.ahora(), entidad=entidad, entidad_id=entidad_id, paso=paso,
                detalle=detalle[:500], fuente=fuente, duracion_ms=duracion_ms)


@contextmanager
def cronometro():
    """Uso: `with cronometro() as t: ...` y luego `t()` da los milisegundos."""
    inicio = time.perf_counter()
    yield lambda: int((time.perf_counter() - inicio) * 1000)
