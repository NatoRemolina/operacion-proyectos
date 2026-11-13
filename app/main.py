"""Aplicación web: viajes de grabación y gastos por proyecto.

Este archivo solo arma la aplicación: control de acceso y carga de las rutas.
Las pantallas viven en `app/rutas/`, una por área; lo que comparten, en `app/web.py`.
"""
import importlib
import pkgutil
import secrets
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from datos.semilla import sembrar

from . import config, rutas, web
from .api_v1 import CODIGO_HTTP, MENSAJE_HTTP, ErrorApi, respuesta_error
from .servicios import acceso
from .web import AQUI, SOLO_ADMIN, _asegurar, _error_registrado, _pagina_error

app = FastAPI(title="Operación de proyectos", redoc_url=None)
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")

# Se carga todo módulo de `app/rutas/`: añadir un área es añadir un archivo, sin tocar este
for _nombre in sorted(m.name for m in pkgutil.iter_modules(rutas.__path__)):
    _modulo = importlib.import_module(f"{rutas.__name__}.{_nombre}")
    if hasattr(_modulo, "router"):
        app.include_router(_modulo.router)
    web.MENU.extend(getattr(_modulo, "MENU", []))

# En local la base se prepara sola; en un despliegue la migración es un paso aparte (python -m datos.semilla)
if config.PREPARAR_BASE_LOCAL:
    sembrar()


# ---------- acceso ----------
@app.middleware("http")
async def control_de_acceso(request: Request, call_next):
    """Identifica a quien llama y aplica el nivel de la ruta antes de ejecutar nada."""
    ruta = request.url.path
    necesario = acceso.nivel(ruta)
    request.state.peticion = secrets.token_hex(6)
    es_v1 = ruta.startswith(acceso.API_V1)
    escribe = request.method not in ("GET", "HEAD", "OPTIONS")
    if es_v1:
        # API v1: siempre JSON. El origen se comprueba aquí; el token CSRF, en cada endpoint que escribe.
        if escribe and not acceso.origen_permitido(request.headers):
            return _asegurar(respuesta_error(request, 403, "ORIGIN_NOT_ALLOWED", "La petición no viene de un origen permitido."))
    elif escribe and not acceso.mismo_origen(request.headers):
        return _asegurar(_pagina_error(403, "Petición rechazada", "El formulario no se envió desde esta plataforma. Vuelve a la página y repite la acción."))
    # Un tablero que se actualiza solo no cuenta como actividad: una pestaña olvidada no mantiene viva la sesión
    usuario = None if necesario == "publica" and ruta != "/entrar" else \
        acceso.usuario_de(request.cookies.get(acceso.COOKIE), tocar=ruta != "/api/viajes")
    acceso.fijar(usuario)
    request.state.usuario = usuario
    if necesario == "api" and not usuario:
        return _asegurar(respuesta_error(request, 401, "UNAUTHENTICATED", MENSAJE_HTTP[401]))
    if necesario not in ("publica", "api"):
        if not usuario:
            if ruta.startswith("/api"):
                return Response(status_code=401)
            if request.headers.get("x-envio") == "pagina":   # la carga de recibos espera JSON, no una página de ingreso
                return _asegurar(JSONResponse({"gastos": [], "errores": ["Tu sesión se cerró. Ingresa de nuevo y vuelve a enviar este recibo."],
                                               "sesion": "vencida"}, status_code=401))
            if escribe:
                return _asegurar(_pagina_error(401, "Tu sesión se cerró", "Lo que enviaste no se guardó. Ingresa de nuevo en otra pestaña "
                                               "y vuelve a enviar el formulario desde esta página para no perder lo escrito."))
            destino = ruta + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse("/entrar" + (f"?siguiente={quote(destino)}" if ruta != "/" else ""), status_code=303)
        if necesario == "admin" and not acceso.es_admin(usuario):
            return _asegurar(JSONResponse({"error": "Solo administración"}, status_code=403) if ruta.startswith("/api") else SOLO_ADMIN)
    try:
        respuesta = await call_next(request)
    except Exception as e:  # nada se pierde en silencio: queda registrado y quien lo vio recibe un identificador
        return _error_registrado(request, e)
    respuesta.headers["X-Peticion"] = request.state.peticion
    return _asegurar(respuesta)


# ---------- errores ----------
# La API v1 responde siempre con su contrato JSON; las pantallas, con una página legible.
@app.exception_handler(ErrorApi)
async def _error_api(request: Request, e: ErrorApi):
    return respuesta_error(request, e.estado, e.codigo, e.mensaje, e.campos)


@app.exception_handler(StarletteHTTPException)
async def _error_http(request: Request, e: StarletteHTTPException):
    if request.url.path.startswith(acceso.API_V1):
        return respuesta_error(request, e.status_code, CODIGO_HTTP.get(e.status_code, "HTTP_ERROR"),
                               MENSAJE_HTTP.get(e.status_code, str(e.detail)))
    if request.url.path.startswith("/api"):
        return JSONResponse({"error": str(e.detail)}, status_code=e.status_code)
    if e.status_code == 404:
        return web.NO_ENCONTRADO
    return _pagina_error(e.status_code, "No se pudo completar la petición", "Vuelve a la página anterior e inténtalo de nuevo.")


@app.exception_handler(RequestValidationError)
async def _error_validacion(request: Request, e: RequestValidationError):
    if request.url.path.startswith(acceso.API_V1):
        campos = {".".join(str(p) for p in err["loc"][1:]) or "cuerpo": err["msg"] for err in e.errors()}
        return respuesta_error(request, 422, "VALIDATION_ERROR", MENSAJE_HTTP[422], campos)
    if request.url.path.startswith("/api"):
        return JSONResponse({"error": "Datos no válidos"}, status_code=422)
    return _pagina_error(422, "Hay datos que no son válidos", "Revisa lo que escribiste o vuelve a la página anterior.")


# Nombres que las pruebas y los guiones importan desde aquí
from .rutas.cotizaciones import _comparacion  # noqa: E402,F401
from .rutas.gastos import _numero  # noqa: E402,F401
from .web import _indicadores  # noqa: E402,F401
