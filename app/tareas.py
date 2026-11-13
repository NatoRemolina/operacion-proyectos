"""Trabajador programado (pieza 5): la función `Tareas` en AWS, con la imagen de la API y este punto de entrada.

Una regla de EventBridge lo llama cada 15 minutos. En cada corrida encola el seguimiento del día (idempotente) y hace
hasta `POR_CORRIDA` capturas pendientes, de a una, con el turno del analizador y dentro del tope del día. El analizador
sigue sin acceso a la base: el trabajador le pasa la dirección y guarda lo que devuelve.

En local:  python -m app.tareas
"""
import time

from .servicios import capturas

POR_CORRIDA = 10
PLAZO_S = 900 - 240   # la función vive 15 minutos: no se empieza una captura (hasta tres invocaciones) sin margen


def procesar(hoy: str | None = None, plazo_s: float = PLAZO_S) -> dict:
    """Encola el seguimiento de hoy y hace capturas hasta vaciar la cola, llegar al tope o quedarse sin tiempo."""
    inicio = time.monotonic()
    seguimiento = capturas.encolar_seguimiento(hoy)
    hechas, listas = 0, 0
    while hechas < POR_CORRIDA and time.monotonic() - inicio < plazo_s:
        f = capturas.tomar()
        if not f:
            break
        final = capturas.hacer(f)
        hechas += 1
        listas += final["estado"] == "lista"
    return {"seguimiento": seguimiento, "procesadas": hechas, "listas": listas}


def manejador(evento, contexto) -> dict:
    """Punto de entrada de Lambda (la regla de EventBridge no manda nada que se use)."""
    r = procesar()
    print(f"tareas: {r}", flush=True)
    return r


if __name__ == "__main__":
    print(procesar())
