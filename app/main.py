"""Aplicación web: viajes de grabación y gastos por proyecto.

Este archivo solo arma la aplicación: control de acceso y carga de las rutas.
Las pantallas viven en `app/rutas/`, una por área; lo que comparten, en `app/web.py`.
"""
import importlib
import pkgutil
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from datos.semilla import sembrar

from . import config, rutas, web
from .servicios import acceso
from .web import AQUI, SOLO_ADMIN, _asegurar, _error_registrado, _pagina_error

app = FastAPI(title="Operación de proyectos")
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")

# Se carga todo módulo de `app/rutas/`: añadir un área es añadir un archivo, sin tocar este
for _nombre in sorted(m.name for m in pkgutil.iter_modules(rutas.__path__)):
    _modulo = importlib.import_module(f"{rutas.__name__}.{_nombre}")
    if hasattr(_modulo, "router"):
        app.include_router(_modulo.router)
    web.MENU.extend(getattr(_modulo, "MENU", []))

# En local la base se prepara sola; en un despliegue la migración es un paso aparte (python -m datos.semilla)
if config.LOCAL:
    sembrar()


# ---------- acceso ----------
@app.middleware("http")
async def control_de_acceso(request: Request, call_next):
    """Identifica a quien llama y aplica el nivel de la ruta antes de ejecutar nada."""
    ruta = request.url.path
    necesario = acceso.nivel(ruta)
    request.state.peticion = secrets.token_hex(6)
    if request.method not in ("GET", "HEAD", "OPTIONS") and not acceso.mismo_origen(request.headers):
        return _asegurar(_pagina_error(403, "Petición rechazada", "El formulario no se envió desde esta plataforma. Vuelve a la página y repite la acción."))
    usuario = None if necesario == "publica" and ruta != "/entrar" else acceso.usuario_de(request.cookies.get(acceso.COOKIE))
    acceso.fijar(usuario)
    request.state.usuario = usuario
    if necesario != "publica":
        if not usuario:
            return Response(status_code=401) if ruta.startswith("/api") else RedirectResponse("/entrar", status_code=303)
        if necesario == "admin" and not acceso.es_admin(usuario):
            return _asegurar(JSONResponse({"error": "Solo administración"}, status_code=403) if ruta.startswith("/api") else SOLO_ADMIN)
    try:
        respuesta = await call_next(request)
    except Exception as e:  # nada se pierde en silencio: queda registrado y quien lo vio recibe un identificador
        return _error_registrado(request, e)
    respuesta.headers["X-Peticion"] = request.state.peticion
    return _asegurar(respuesta)


# Nombres que las pruebas y los guiones importan desde aquí
from .rutas.cotizaciones import _comparacion  # noqa: E402,F401
from .rutas.gastos import _numero  # noqa: E402,F401
from .web import _indicadores  # noqa: E402,F401
