"""API v1: gastos visibles para la persona, envío de un recibo, su archivo original, la nota de voz de una
justificación y la revisión de administración (con lo que necesita para revisar: lectura original, soporte y opciones).

Contrato en `contracts/api-v1.md`.
"""
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .. import config, db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, pagina, persona
from ..api_v1.esquemas import Dinero, EstadoGasto, EstadoViaje, GastoDetalle, ListaGastos, NuevaJustificacion, errores
from ..servicios import acceso, almacen, consultas, contable, dinero, envios, justificaciones, revision, viajes
from ..servicios import gastos as soportes
from .gastos import original_legible

router = APIRouter(prefix=PREFIJO, tags=["gastos"])


class CorreoDelSoporte(BaseModel):
    remitente: str | None = Field(description="Quién envió el correo, tal como viene en su cabecera.")
    asunto: str | None = Field(description="El asunto del correo.")


class GastoRevisable(GastoDetalle):
    correo: CorreoDelSoporte | None = Field(None, description="Si el soporte es un correo (.eml): de quién llegó y con qué asunto.")
    version: int = Field(description="Versión del gasto. La revisión la manda de vuelta para no pisar un cambio ajeno.")
    motivo_rechazo: str | None = Field(description="Por qué se rechazó, con las palabras de quien revisó.")
    puede_justificar: bool = Field(False, description="La persona de la sesión hizo el gasto o es quien viaja: puede contar para qué fue.")


class RevisionGasto(BaseModel):
    """Una revisión de administración. Los campos de datos que no se mandan se conservan como están."""
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0, description="La `version` del gasto que vio quien revisa.")
    accion: Literal["guardar", "aprobar", "excepcion", "rechazar"] = Field(
        description="`guardar` corrige y deja en revisión; `aprobar` aprueba si las reglas lo permiten (si no, guarda y "
                    "sigue en revisión); `excepcion` aprueba lo que las reglas no dejan pasar, con motivo; `rechazar`, con motivo.")
    motivo: str = Field("", max_length=500, description="Obligatorio para rechazar (5 caracteres o más) y para la excepción (8 o más).")
    comercio: str | None = Field(None, max_length=200)
    fecha: str | None = Field(None, max_length=10, description="AAAA-MM-DD")
    categoria: str | None = Field(None, max_length=40)
    subtotal: Dinero = None
    impuesto: Dinero = None
    propina: Dinero = None
    total: Dinero = None
    moneda: str | None = Field(None, max_length=3)
    metodo_pago: str | None = Field(None, max_length=200)
    canal_reserva: str | None = Field(None, max_length=200)
    viaje_id: int | None = Field(None, ge=0, description="Omitido conserva el viaje; 0 lo quita.")


class LecturaOriginal(BaseModel):
    """Lo que leyó el modelo del recibo, intacto: las correcciones de la revisión no lo cambian."""
    comercio: str | None
    fecha: str | None
    categoria: str | None
    subtotal: Dinero
    impuesto: Dinero
    propina: Dinero
    total: Dinero
    moneda: str | None
    metodo_pago: str | None
    canal_reserva: str | None
    confianza: float | None
    dudas: list[str] = Field(description="Campos de los que la lectura no estaba segura.")


class SoporteRevision(BaseModel):
    documento_id: int
    nombre: str | None
    forma: Literal["imagen", "pdf", "descarga"] = Field(
        description="Cómo mostrarlo: `imagen` y `pdf` se ven al lado; `descarga` (correo .eml o confirmación HTML "
                    "guardada como texto) se ofrece para descargar. El archivo sale de `/documentos/{id}/contenido`.")


class Categoria(BaseModel):
    clave: str
    nombre: str


class ViajeAsignable(BaseModel):
    id: int
    codigo: str
    estado: EstadoViaje
    estado_texto: str
    titular: str | None
    origen: str | None
    destino: str | None
    ida: str | None
    regreso: str | None


class DatosRevision(BaseModel):
    """Lo que la revisión de administración necesita además de la ficha del gasto (`GET /gastos/{id}`)."""
    gasto_id: int
    version: int = Field(description="La misma `version` del gasto; la revisión la manda de vuelta.")
    metodo_pago: str | None
    canal_reserva: str | None
    lectura_original: LecturaOriginal | None = Field(description="null si la lectura falló o el gasto no viene de un recibo leído.")
    soporte: SoporteRevision | None = Field(description="null si el gasto no tiene archivo original guardado.")
    categorias: list[Categoria]
    viajes: list[ViajeAsignable] = Field(description="Viajes a los que se puede reasignar: todos salvo los rechazados, "
                                                     "el más reciente primero.")
    propio: bool = Field(description="Es de quien revisa: nadie revisa lo suyo.")
    aviso_propio: str | None = Field(description="Si es propio, por qué no se revisa y si hay otra persona de "
                                                 "administración que pueda hacerlo.")


def marcar_propios(items: list[dict], yo: dict) -> list[dict]:
    """Añade de quién es cada gasto para quien mira: `propio` (nadie revisa lo suyo, la misma regla que la revisión)
    y `puede_justificar` (solo quien lo hizo o quien viaja). Así la web no ofrece botones que la API rechazaría."""
    if not items:
        return items
    ids = ",".join(str(int(g["id"])) for g in items)
    filas = {f["id"]: f for f in db.todos(f"select id, usuario_id, viajero_id, viaje_id from gastos where id in ({ids})")}
    for g in items:
        fila = filas.get(g["id"])
        g["propio"] = viajes.gasto_propio_de(fila, yo)
        g["puede_justificar"] = justificaciones.puede_justificar(yo, fila)
    return items


def _revisable(yo: dict, id: int) -> dict | None:
    g = consultas.gasto(yo, id)
    if not g:
        return None
    extra = db.uno("""select g.version, g.motivo_rechazo, d.texto from gastos g left join documentos d on d.id=g.documento_id
                      where g.id=:i""", i=id)
    return marcar_propios([{**g, "version": extra["version"] or 0, "motivo_rechazo": extra["motivo_rechazo"],
                            "correo": soportes.correo_de(extra["texto"])}], yo)[0]


def _campos(datos: RevisionGasto) -> dict:
    """Los datos que se mandaron. Un importe que no es un número finito se rechaza aquí; uno negativo o cero lo marcan las reglas."""
    campos = datos.model_dump(exclude_unset=True, exclude={"version", "accion", "motivo", "viaje_id"})
    for c in ("subtotal", "impuesto", "propina", "total"):
        if campos.get(c) is not None:
            try:
                campos[c] = float(dinero.decimal(campos[c]))
            except ValueError as e:
                raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {c: "Debe ser un importe como \"54.00\"."}) from e
    if campos.get("moneda"):
        campos["moneda"] = campos["moneda"].upper().strip()
    return campos


def _forma_soporte(mime: str | None) -> str:
    if mime in ("image/jpeg", "image/png", "image/webp"):
        return "imagen"
    return "pdf" if mime == "application/pdf" else "descarga"


def _lectura_original(extraido: str | None) -> dict | None:
    x = db.de_json(extraido, None) if extraido else None
    if not isinstance(x, dict):
        return None
    importes = {c: consultas.dinero(x.get(c)) if isinstance(x.get(c), int | float) else None
                for c in ("subtotal", "impuesto", "propina", "total")}
    return {**{c: x.get(c) for c in ("comercio", "fecha", "categoria", "moneda", "metodo_pago", "canal_reserva")},
            **importes, "confianza": x.get("confianza"), "dudas": [str(d) for d in x.get("dudas") or []]}


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


@router.get("/gastos", response_model=ListaGastos, responses=errores(401, 422))
def lista(viaje_id: int | None = None, estado: EstadoGasto | None = None, paginacion: tuple = Depends(pagina),
          yo: dict = Depends(persona)):
    """Mismo alcance que los viajes. Más reciente primero."""
    limite, cursor = paginacion
    resultado = consultas.lista_gastos(yo, viaje_id, estado, limite, cursor)
    marcar_propios(resultado["items"], yo)
    return resultado


@router.get("/gastos/contable", response_class=Response, responses={
    **errores(401, 403, 404, 422),
    200: {"description": "El libro (.xlsx) con las hojas «Gastos» y «Resumen»", "content": {contable.TIPO_XLSX: {}}}})
def libro_contable(request: Request,
                   desde: str | None = Query(None, description="AAAA-MM-DD, por la fecha del recibo. Por omisión, el 1 de enero del año en curso (hora de Nueva York)."),
                   hasta: str | None = Query(None, description="AAAA-MM-DD, incluido. Por omisión, el 31 de diciembre del año en curso (hora de Nueva York)."),
                   proyecto_id: int | None = Query(None, ge=1, le=contable.MAXIMO_ID,
                                                   description="Opcional. Solo administración o quien gestiona el proyecto."),
                   yo: dict = Depends(persona)):
    """Excel contable de los gastos aprobados (`aprobado` y `aprobado_auto`) del periodo, con el alcance de la sesión:
    administración, todo; quien gestiona, sus proyectos y lo suyo; el resto, solo lo suyo. Un `proyecto_id` que la
    persona no gestiona responde 403, exista o no. Va antes de `/gastos/{id}` para que «contable» no se lea como id."""
    anio = contable.anio_en_curso()
    desde, hasta = desde or anio[0], hasta or anio[1]
    try:
        contenido = contable.libro(yo, desde, hasta, proyecto_id, enlace_base=contable.origen_publico(str(request.base_url)))
    except contable.SinPermiso as e:
        raise ErrorApi(403, "FORBIDDEN", str(e)) from e
    except contable.ProyectoInexistente as e:
        raise _no_encontrado() from e
    except contable.FechaInvalida as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {e.campo: str(e)}) from e
    contable.registrar_descarga(desde, hasta, proyecto_id, "api")
    return Response(contenido, media_type=contable.TIPO_XLSX, headers=contable.cabeceras_descarga(desde, hasta, proyecto_id))


@router.get("/gastos/{id}", response_model=GastoRevisable, responses=errores(401, 404, 422))
def detalle(id: int, yo: dict = Depends(persona)):
    g = _revisable(yo, id)
    if not g:
        raise _no_encontrado()
    return g


@router.post("/gastos", status_code=201, response_model=GastoRevisable, responses=errores(401, 403, 409, 413, 415, 422))
def enviar(response: Response, archivo: UploadFile = File(..., description="Foto (JPG, PNG, WebP), PDF, correo (.eml) o confirmación en HTML (.html) de hasta 4,5 MB."),
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
        raise ErrorApi(415, "UNSUPPORTED_MEDIA_TYPE", "Tipo de archivo no admitido. " + soportes.TIPOS_ADMITIDOS)
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
        return _revisable(yo, gid)
    if justificacion and len(justificacion.strip()) >= justificaciones.MINIMO:
        justificaciones.registrar(gid, yo, "api", justificacion)
    return _revisable(yo, gid)


@router.get("/gastos/{id}/revision", response_model=DatosRevision, responses=errores(401, 403, 404, 422))
def datos_revision(id: int, yo: dict = Depends(persona)):
    """Solo administración: la lectura original, cómo mostrar el soporte, las categorías y los viajes a los que se
    puede reasignar. Las mismas opciones que la revisión de las pantallas de administración."""
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    g = db.uno("""select g.*, d.id doc, d.nombre archivo, d.mime from gastos g left join documentos d on d.id=g.documento_id
                  where g.id=:i""", i=id)
    if not g:
        raise _no_encontrado()
    propio = viajes.gasto_propio_de(g, yo)
    aviso = None
    if propio:
        aviso = viajes.NO_AUTORREVISAR + ("" if viajes.hay_otro_admin(yo) else
                                          " Hace falta otra persona de administración para revisarlo: mientras tanto queda pendiente.")
    return {"gasto_id": id, "version": g["version"] or 0, "metodo_pago": g["metodo_pago"], "canal_reserva": g["canal_reserva"],
            "lectura_original": _lectura_original(g["extraido"]),
            "soporte": {"documento_id": g["doc"], "nombre": g["archivo"], "forma": _forma_soporte(g["mime"])} if g["doc"] else None,
            "categorias": [{"clave": c, "nombre": n} for c, n in config.CATEGORIAS.items()],
            "viajes": viajes.lista("v.estado<>'rechazado'"), "propio": propio, "aviso_propio": aviso}


@router.post("/gastos/{id}/revision", response_model=GastoRevisable, responses=errores(401, 403, 404, 409, 422))
def revisar(id: int, datos: RevisionGasto, yo: dict = Depends(escritura)):
    """Revisión de administración, con las mismas reglas que la web: versión esperada, nadie revisa lo suyo,
    motivo para rechazar y saldo del viaje releído con el viaje bloqueado. 200 con el gasto y su versión nueva."""
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    try:
        revision.guardar(id, yo, datos.version, datos.accion, _campos(datos), datos.motivo, viaje_id=datos.viaje_id)
    except LookupError as e:
        raise _no_encontrado() from e
    except revision.RevisionImpedida as e:
        raise ErrorApi(403, "FORBIDDEN", str(e)) from e
    except revision.ConflictoRevision as e:
        raise ErrorApi(409, "EDIT_CONFLICT", str(e)) from e
    except ValueError as e:
        raise ErrorApi(422, "VALIDATION_ERROR", str(e)) from e
    return _revisable(yo, id)


@router.post("/gastos/{id}/justificaciones", status_code=201, response_model=GastoRevisable, responses=errores(401, 403, 404, 422))
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
    return _revisable(yo, id)


@router.get("/gastos/{id}/justificaciones/{jid}/audio", response_class=Response, responses={
    **errores(401, 404, 422), 200: {"description": "La nota de voz tal como llegó", "content": {"audio/*": {}}}})
def audio_justificacion(id: int, jid: int, yo: dict = Depends(persona)):
    """La nota de voz de una justificación. Se oye si se ve el gasto; si no, 404, como el resto de lo ajeno."""
    if not consultas.gasto(yo, id):
        raise _no_encontrado()
    d = db.uno("""select d.ruta, d.mime from justificaciones j join documentos d on d.id=j.documento_id
                  where j.id=:j and j.gasto_id=:g and j.tipo='audio'""", j=jid, g=id)
    contenido = almacen.leer(d["ruta"]) if d and d["ruta"] else None
    if contenido is None:
        raise _no_encontrado()
    return Response(contenido, media_type=d["mime"] if (d["mime"] or "").startswith("audio/") else "application/octet-stream",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.get("/documentos/{id}/contenido", response_class=Response, responses={
    **errores(401, 404, 422),
    200: {"description": "El archivo original", "content": {t: {} for t in (*consultas.TIPOS_EN_LINEA, "text/plain")}}})
def contenido(id: int, yo: dict = Depends(persona)):
    """Se entrega aislado: sin adivinar el tipo, sin ejecutar nada y sin quedar en caché."""
    archivo = consultas.contenido_documento(yo, id)
    if not archivo:
        raise _no_encontrado()
    datos, _ = archivo
    d = db.uno("select mime, nombre from documentos where id=:i", i=id)
    datos, tipo = original_legible(datos, d["mime"])   # un correo: su adjunto o su texto, nunca el MIME crudo
    return Response(datos, media_type=tipo, headers={
        "Content-Disposition": soportes.disposicion(d["mime"], d["nombre"]), "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})
