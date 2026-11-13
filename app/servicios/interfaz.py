"""Retiro de las pantallas anteriores: cada página se redirige a su equivalente en la web.

Con `INTERFAZ_ANTIGUA=redirige` (y la dirección de la web en `ORIGENES_WEB`), quien abre una pantalla de la
plataforma anterior llega a la misma pantalla de la web. La API, los estáticos, la salud y el webhook de
Telegram no cambian: la web y las integraciones los siguen usando.
"""
import re

from .. import config

# Lo que sigue sirviendo la aplicación aunque las pantallas anteriores estén retiradas
SIGUEN = ("/api", "/static", "/salud", "/telegram/", "/openapi.json", "/favicon",
          "/analitica", "/flujo")   # todavía sin pantalla en la web

# Ruta anterior (expresión completa) → ruta de la web; `{n}` es el número capturado
EQUIVALENCIAS: list[tuple[str, str]] = [
    (r"/", "/"),
    (r"/entrar", "/entrar"),
    (r"/salir", "/entrar"),
    (r"/mi-cuenta(?:/.*)?", "/mi-cuenta"),
    (r"/viajes/nuevo", "/cotizar"),
    (r"/viajes/(\d+)(?:/.*)?", "/cotizar/{n}"),        # en la plataforma anterior, /viajes/N es la cotización
    (r"/viaje/(\d+)(?:/.*)?", "/viajes/{n}"),
    (r"/admin/viajes(?:/.*)?", "/viajes"),
    (r"/admin/vuelos(?:/.*)?", "/vuelos"),
    (r"/gastos/cargar", "/gastos/nuevo"),
    (r"/gastos/(\d+)(?:/.*)?", "/gastos/{n}"),
    (r"/gastos(?:/.*)?", "/gastos"),
    (r"/admin/proyectos(?:/.*)?", "/proyectos"),
    (r"/proyectos/(\d+)(?:/.*)?", "/proyectos/{n}"),
    (r"/admin/usuarios(?:/.*)?", "/usuarios"),
    (r"/admin/cargos(?:/.*)?", "/usuarios"),
    (r"/reglas(?:/.*)?", "/reglas"),
    (r"/admin/kpis/persona/(\d+)(?:/.*)?", "/kpis/persona/{n}"),
    (r"/admin/kpis(?:/.*)?", "/kpis"),
    (r"/admin/monitoreo(?:/.*)?", "/monitoreo"),
]


def activa() -> bool:
    return config.INTERFAZ_ANTIGUA == "redirige" and bool(config.ORIGENES_WEB)


def destino(ruta: str) -> str | None:
    """La dirección de la web para una ruta anterior, o None si la ruta sigue sirviéndose aquí."""
    if any(ruta == s or ruta.startswith(s) for s in SIGUEN):
        return None
    web = config.ORIGENES_WEB[0]
    for patron, nueva in EQUIVALENCIAS:
        m = re.fullmatch(patron, ruta)
        if m:
            return web + nueva.replace("{n}", m.group(1) if m.groups() else "")
    return web + "/"
