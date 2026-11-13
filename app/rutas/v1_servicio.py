"""API v1 para integraciones (n8n): se entra con una clave de servicio, no con sesión.

Las rutas bajo `/api/v1/servicio/` no piden cookie ni token CSRF; cada una exige una clave de servicio vigente con el
permiso que necesita (`X-Clave-Servicio`). Lo que hace la clave queda en la bitácora con el nombre de la clave.
"""
from fastapi import APIRouter, Header, Query
from fastapi.responses import Response

from .. import db
from ..api_v1 import PREFIJO, ErrorApi
from ..api_v1.esquemas import errores
from ..servicios import almacen, avisos, claves_servicio, eventos

router = APIRouter(prefix=PREFIJO + "/servicio", tags=["integraciones"])

TIPOS_SOPORTE = ("image/jpeg", "image/png", "image/webp", "application/pdf", "message/rfc822")


def autorizar(clave: str | None, permiso: str) -> dict:
    try:
        return claves_servicio.autorizar(clave, permiso)
    except claves_servicio.ClaveInvalida as e:
        raise ErrorApi(401, "UNAUTHENTICATED", "Falta la clave de servicio, no existe o fue revocada.") from e
    except claves_servicio.SinPermiso as e:
        raise ErrorApi(403, "FORBIDDEN", "La clave de servicio no tiene permiso para esta operación.") from e


@router.get("/gastos/{id}/soporte", response_class=Response, responses={
    **errores(401, 403, 404, 422),
    200: {"description": "El archivo original del soporte", "content": {t: {} for t in TIPOS_SOPORTE}}})
def soporte(id: int,
            vence: int | None = Query(None, description="Del enlace firmado que trae el aviso `gasto.registrado`."),
            firma: str | None = Query(None, max_length=128, description="Del enlace firmado que trae el aviso."),
            clave: str | None = Header(None, alias=claves_servicio.CABECERA,
                                       description="Clave de servicio con el permiso `soportes:leer`.")):
    """El soporte original de un gasto, para guardarlo fuera de la plataforma. Se entrega como archivo adjunto, sin caché.

    Hacen falta las dos cosas: la clave de servicio y el enlace firmado del aviso, que vence a los 15 minutos.
    Un enlace filtrado no sirve sin la clave, y la clave sola no recorre los soportes por número."""
    servicio = autorizar(clave, "soportes:leer")
    motivo = avisos.enlace_valido(id, vence, firma)
    if motivo:
        raise ErrorApi(403, motivo, "El enlace al soporte venció: dura 15 minutos." if motivo == "LINK_EXPIRED"
                       else "El enlace al soporte no es válido.")
    d = db.uno("""select d.ruta, d.mime, d.nombre from gastos g join documentos d on d.id=g.documento_id
                  where g.id=:i and d.tipo='soporte'""", i=id)
    contenido = almacen.leer(d["ruta"]) if d and d["ruta"] else None
    if contenido is None:
        raise ErrorApi(404, "NOT_FOUND", "No encontramos ese soporte.")
    eventos.registrar("gasto", id, "soporte descargado por integración", d["nombre"] or "", servicio["nombre"])
    tipo = d["mime"] if d["mime"] in TIPOS_SOPORTE else "application/octet-stream"
    return Response(contenido, media_type=tipo, headers={
        "Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; sandbox"})
