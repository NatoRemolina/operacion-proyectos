"""API v1: gastos visibles para la persona, envío de un recibo y su archivo original. Contrato en `contracts/api-v1.md`."""
from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import Response

from .. import config, db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, pagina, persona
from ..api_v1.esquemas import EstadoGasto, GastoDetalle, ListaGastos, NuevaJustificacion, errores
from ..servicios import consultas, envios, justificaciones, viajes
from ..servicios import gastos as soportes

router = APIRouter(prefix=PREFIJO, tags=["gastos"])


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


@router.get("/gastos", response_model=ListaGastos, responses=errores(401, 422))
def lista(viaje_id: int | None = None, estado: EstadoGasto | None = None, paginacion: tuple = Depends(pagina),
          yo: dict = Depends(persona)):
    """Mismo alcance que los viajes. Más reciente primero."""
    limite, cursor = paginacion
    return consultas.lista_gastos(yo, viaje_id, estado, limite, cursor)


@router.get("/gastos/{id}", response_model=GastoDetalle, responses=errores(401, 404, 422))
def detalle(id: int, yo: dict = Depends(persona)):
    g = consultas.gasto(yo, id)
    if not g:
        raise _no_encontrado()
    return g


@router.post("/gastos", status_code=201, response_model=GastoDetalle, responses=errores(401, 403, 409, 413, 415, 422))
def enviar(response: Response, archivo: UploadFile = File(..., description="Foto (JPG, PNG, WebP), PDF o correo (.eml) de hasta 4,5 MB."),
           viaje_id: int | None = Form(None, description="Opcional. Sin él, se usa el viaje que corresponde hoy a la persona."),
           justificacion: str | None = Form(None, max_length=2000,
                                            description="Opcional. Para qué fue el gasto, con las palabras de la persona."),
           clave: str | None = Header(None, alias="Idempotency-Key", max_length=200,
                                      description="Un valor único por archivo, que se repite si se reintenta el mismo envío."),
           yo: dict = Depends(escritura)):
    """Lee y valida el recibo. Responde con su estado real: `aprobado_auto` o `revision` (que no es un error).

    Con `Idempotency-Key`, el reintento con el mismo archivo y el mismo `viaje_id` responde 200 con el mismo gasto
    (puede seguir `procesando`); con otro archivo u otro viaje, 409 `IDEMPOTENCY_CONFLICT`. Si el primer envío todavía
    no creó su gasto, 409 `REQUEST_IN_PROGRESS`: se reintenta con la misma clave.

    Función normal (no asíncrona): la lectura con el modelo corre en un hilo y no detiene al resto del servidor.
    """
    contenido = archivo.file.read(config.MAX_BYTES_SOPORTE + 1)
    if len(contenido) > config.MAX_BYTES_SOPORTE:
        raise ErrorApi(413, "PAYLOAD_TOO_LARGE", f"El archivo supera el máximo de {config.MAX_BYTES_SOPORTE / 1e6:.1f} MB.")
    if not contenido:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"archivo": "El archivo está vacío."})
    nombre = archivo.filename or "soporte"
    if not soportes.tipo_real(contenido, nombre):
        raise ErrorApi(415, "UNSUPPORTED_MEDIA_TYPE", "Tipo de archivo no admitido. Se aceptan fotos (JPG, PNG, WebP), PDF y correos (.eml).")
    # Con viaje indicado solo se acepta uno propio; si no lo es, el gasto queda sin viaje y en revisión
    viaje, _ = viajes.resolver_para_gasto(yo, viaje_id)
    try:
        # La huella del envío usa el viaje pedido, no el resuelto: el reintento debe coincidir aunque cambie el viaje del día
        gid, repetido = soportes.registrar_envio(contenido, nombre, "web", yo, viaje, viajero_id=yo.get("viajero_id"),
                                                 clave_idempotencia=clave, contexto={"viaje_id": viaje_id})
    except envios.ConflictoEnvio as e:
        raise ErrorApi(409, "IDEMPOTENCY_CONFLICT", str(e)) from e
    except envios.EnvioEnCurso as e:
        raise ErrorApi(409, "REQUEST_IN_PROGRESS", str(e)) from e
    except soportes.SoporteRechazado as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"archivo": str(e)}) from e
    if repetido:
        response.status_code = 200
        return consultas.gasto(yo, gid)
    if justificacion and len(justificacion.strip()) >= justificaciones.MINIMO:
        justificaciones.registrar(gid, yo, "api", justificacion)
    return consultas.gasto(yo, gid)


@router.post("/gastos/{id}/justificaciones", status_code=201, response_model=GastoDetalle, responses=errores(401, 403, 404, 422))
def justificar(id: int, cuerpo: NuevaJustificacion, yo: dict = Depends(escritura)):
    """Añade por escrito para qué fue el gasto. Solo quien lo hizo o quien viaja puede justificarlo."""
    g = consultas.gasto(yo, id)
    if not g:
        raise _no_encontrado()
    fila = db.uno("select usuario_id, viajero_id from gastos where id=:i", i=id)
    if not justificaciones.puede_justificar(yo, fila):
        raise ErrorApi(403, "FORBIDDEN", "Solo quien hizo el gasto o quien viaja puede justificarlo.")
    try:
        justificaciones.registrar(id, yo, "api", cuerpo.texto)
    except justificaciones.JustificacionRechazada as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"texto": str(e)}) from e
    return consultas.gasto(yo, id)


@router.get("/documentos/{id}/contenido", response_class=Response, responses={
    **errores(401, 404, 422),
    200: {"description": "El archivo original", "content": {t: {} for t in (*consultas.TIPOS_EN_LINEA, "text/plain")}}})
def contenido(id: int, yo: dict = Depends(persona)):
    """Se entrega aislado: sin adivinar el tipo, sin ejecutar nada y sin quedar en caché."""
    archivo = consultas.contenido_documento(yo, id)
    if not archivo:
        raise _no_encontrado()
    datos, tipo = archivo
    return Response(datos, media_type=tipo, headers={
        "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})
