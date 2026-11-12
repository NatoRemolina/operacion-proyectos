"""Borde de la API JSON v1: lo que comparten todos sus endpoints.

Contrato completo en `contracts/api-v1.md`. Reglas que aplica este módulo:

- Errores siempre en JSON: `{"error": {"code", "message", "fields"}, "request_id"}`. Nunca HTML ni redirecciones.
- La identidad sale de la sesión (cookie), nunca del cuerpo de la petición.
- Toda escritura exige el token CSRF en la cabecera `X-CSRF-Token`, además de un origen permitido.
- Lo que la persona no puede ver responde 404, no 403, para no revelar que existe.

Los endpoints viven en `app/rutas/v1_*.py` y usan las dependencias de aquí con `Depends(...)`.
"""
import hashlib
import hmac

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from ..servicios import acceso

PREFIJO = "/api/v1"


class ErrorApi(Exception):
    """Error de negocio o de permiso con su código estable. El manejador de `app/main.py` lo convierte en JSON."""

    def __init__(self, estado: int, codigo: str, mensaje: str, campos: dict | None = None):
        super().__init__(mensaje)
        self.estado, self.codigo, self.mensaje, self.campos = estado, codigo, mensaje, campos or {}


def respuesta_error(request: Request, estado: int, codigo: str, mensaje: str, campos: dict | None = None) -> JSONResponse:
    rid = getattr(request.state, "peticion", "")
    return JSONResponse({"error": {"code": codigo, "message": mensaje, "fields": campos or {}}, "request_id": rid},
                        status_code=estado, headers={"X-Peticion": rid, "Cache-Control": "no-store"})


# Códigos estables para los estados HTTP que produce el propio marco (ruta inexistente, método no admitido...)
CODIGO_HTTP = {400: "BAD_REQUEST", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED",
               409: "CONFLICT", 413: "PAYLOAD_TOO_LARGE", 415: "UNSUPPORTED_MEDIA_TYPE", 422: "VALIDATION_ERROR",
               429: "TOO_MANY_REQUESTS", 500: "INTERNAL_ERROR", 503: "SERVICE_UNAVAILABLE"}
MENSAJE_HTTP = {401: "Tu sesión no existe o venció. Vuelve a ingresar.", 404: "No encontramos ese recurso.",
                405: "Esa operación no está disponible en esta dirección.", 422: "Hay datos que no son válidos.",
                500: "Algo falló de nuestro lado. El error quedó registrado."}


# ---------- CSRF ----------
def token_csrf(token_sesion: str) -> str:
    """Token CSRF ligado a la sesión, sin guardar nada: HMAC con el token de la cookie como clave.

    Nunca es la huella guardada en `sesiones` (eso permitiría derivarlo de un volcado de la tabla).
    Cambia con cada sesión y no sirve fuera de ella.
    """
    return hmac.new(token_sesion.encode(), b"csrf-v1", hashlib.sha256).hexdigest()


def csrf_valido(request: Request) -> bool:
    sesion = request.cookies.get(acceso.COOKIE)
    enviado = request.headers.get("x-csrf-token", "")
    return bool(sesion and enviado) and hmac.compare_digest(enviado.encode(), token_csrf(sesion).encode())


# ---------- dependencias para los endpoints ----------
def persona(request: Request) -> dict:
    """La persona de la sesión. El control de acceso ya rechazó con 401 a quien no tiene sesión."""
    usuario = getattr(request.state, "usuario", None)
    if not usuario:
        raise ErrorApi(401, "UNAUTHENTICATED", MENSAJE_HTTP[401])
    return usuario


def escritura(request: Request) -> dict:
    """Para todo endpoint que cambia algo: sesión, origen permitido y token CSRF."""
    usuario = persona(request)
    if not acceso.origen_permitido(request.headers):
        raise ErrorApi(403, "ORIGIN_NOT_ALLOWED", "La petición no viene de un origen permitido.")
    if not csrf_valido(request):
        raise ErrorApi(403, "CSRF_INVALID", "Falta el token de seguridad o no es válido. Vuelve a cargar la página.")
    return usuario


def solo_admin(request: Request) -> dict:
    usuario = persona(request)
    if not acceso.es_admin(usuario):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    return usuario


def pagina(limite: int = Query(20, ge=1, le=100, description="Cuántos elementos devolver (1 a 100)."),
           cursor: str | None = Query(None, description="El valor de `siguiente` de la página anterior.")) -> tuple[int, int | None]:
    """Paginación por cursor de los listados: orden por id descendente y el cursor es el último id entregado."""
    if not cursor:
        return limite, None
    if not cursor.isdigit() or int(cursor) < 1:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"cursor": "El cursor no es válido. Usa el valor de `siguiente`."})
    return limite, int(cursor)
