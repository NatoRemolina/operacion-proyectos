"""Lo que comparten varias rutas de la API v1 al validar: filtros, paginación y la sesión del pedido.

Las rutas no se importan entre sí: lo común de la forma va aquí; lo que lleva datos, en `app/servicios`.
"""
import re
import secrets

from fastapi import Query, Request
from fastapi.responses import HTMLResponse

from ..servicios import acceso, precios
from ..web import plantillas
from . import MENSAJE_HTTP, ErrorApi

FILTRO_PROYECTO = Query(0, ge=0, description="0 o ausente: todos los proyectos.")
FILTRO_DESDE = Query("", max_length=40, description="AAAA-MM-DD. Una fecha no válida se ignora.")
FILTRO_HASTA = Query("", max_length=40, description="AAAA-MM-DD. Una fecha no válida se ignora.")


def pagina_estricta(limite: int = Query(20, ge=1, le=100, description="Cuántos elementos devolver (1 a 100)."),
                    cursor: str | None = Query(None, description="El valor de `siguiente` de la página anterior.")) -> tuple[int, int | None]:
    """La misma paginación que `api_v1.pagina`, con el cursor solo de dígitos ASCII: «²» o «٣» pasan `isdigit` y harían
    fallar `int` con un 500. Va aquí para no cambiar el borde común de la API."""
    if not cursor:
        return limite, None
    if not re.fullmatch(r"[1-9][0-9]{0,17}", cursor):
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"cursor": "El cursor no es válido. Usa el valor de `siguiente`."})
    return limite, int(cursor)


def sesion(request: Request) -> str:
    """El token de la sesión del pedido: firma los enlaces que solo sirven en esta sesión (`servicios.enlaces`)."""
    return request.cookies.get(acceso.COOKIE) or ""


# ---------- páginas de la pestaña que abre «Ver en el vendedor» o «Ir a…» (las ve una persona, no la web) ----------
SITIOS_PERMITIDOS = {"same-origin", "same-site", "none"}
AJENO = ("No encontramos ese vuelo", "Puede que el enlace esté incompleto o que no tengas acceso a esa cotización.")
OTRO_SITIO = ("Enlace no válido", "Abre la página del vendedor desde la plataforma.")
INCOMPLETO = ("El enlace no está completo", "Vuelve a abrir el desglose del vuelo y elige la tarifa otra vez.")
_CABECERAS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}


def _pagina(plantilla: str, estado: int, politica: str, **datos) -> HTMLResponse:
    return HTMLResponse(plantillas.get_template(plantilla).render(**datos), status_code=estado,
                        headers={**_CABECERAS, "Content-Security-Policy": politica})


def pagina_aviso(estado: int, titulo: str, texto: str) -> HTMLResponse:
    """Lo que ve la persona en la pestaña nueva cuando no se puede seguir: una página legible, no JSON."""
    return _pagina("api/aviso.html", estado, "default-src 'none'; base-uri 'none'; frame-ancestors 'none'", titulo=titulo, texto=texto)


VERIFICACION_AEROLINEA = ("La página del vendedor puede pedir una verificación (por ejemplo, deslizar una barra o "
                          "marcar «No soy un robot»): resuélvela tú en esa página. La plataforma no la resuelve.")


def pagina_envio(destino: dict) -> HTMLResponse:
    """Página mínima con el pedido de un solo uso del vendedor: antes de enviarlo dice qué vuelo elegir allí, el aviso
    si cambió el vendedor y que una verificación la resuelve la persona. Un clic en «Ir a {vendedor}» lo envía a
    Google, que redirige a su página oficial. Sin scripts: el envío lo hace el botón.

    `form-action https:`: Chrome aplica la directiva también a las redirecciones que siguen al envío, y Google redirige a
    la aerolínea (otro dominio). El destino ya pasó la lista blanca del servidor (solo https://www.google.com/travel/clk…)."""
    guia = precios.guia(destino.get("aviso"), destino.get("tiquete"))
    return _pagina("api/envio_vendedor.html", 200,
                   "default-src 'none'; form-action https:; base-uri 'none'; frame-ancestors 'none'",
                   vendedor=destino["vendedor"], url=destino["url"], campos=destino["campos"],
                   avisos=[t for t in (guia, VERIFICACION_AEROLINEA) if t])


def pagina_ir(titulo: str, google: str, datos: dict) -> HTMLResponse:
    """«Preparando tu enlace…»: pide `POST …/ir` con la sesión y envía el formulario al vendedor (o va a Google Flights).
    Los datos van como JSON escapado para el script (`tojson`)."""
    nonce = secrets.token_urlsafe(16)
    return _pagina("api/ir_a.html", 200, f"default-src 'none'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action https:; "
                                         "base-uri 'none'; frame-ancestors 'none'", nonce=nonce, titulo=titulo, google=google, datos=datos)
