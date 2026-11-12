"""API v1: viajes visibles para la persona y el cambio de estado que hace administración. Contrato en `contracts/api-v1.md`."""
from fastapi import APIRouter, Depends

from .. import db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, pagina, persona
from ..api_v1.esquemas import CambioEstadoViaje, EstadoViaje, ListaViajes, ResultadoCambioEstado, ViajeDetalle, errores
from ..servicios import acceso, consultas, viajes

router = APIRouter(prefix=PREFIJO + "/viajes", tags=["viajes"])


def con_decision(items: list[dict], yo: dict) -> list[dict]:
    """Añade lo que la web necesita para decidir: si el viaje es de quien mira y si su precio espera confirmación."""
    if not items:
        return items
    filas = {f["id"]: f for f in db.todos(
        f"select id, usuario_id, viajero_id from viajes where id in ({','.join(str(int(v['id'])) for v in items)})")}
    for v in items:
        v["propio"] = viajes.es_propio_de(filas.get(v["id"]), yo)
        v["precio_por_confirmar"] = viajes.precio_por_confirmar(v["id"]) if v["estado"] == "pendiente_aprobacion" else None
    return items


def _detalle(yo: dict, id: int) -> dict:
    v = consultas.viaje(yo, id)
    if not v:
        raise ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])
    return con_decision([v], yo)[0]


@router.get("", response_model=ListaViajes, responses=errores(401, 422))
def lista(estado: EstadoViaje | None = None, paginacion: tuple = Depends(pagina), yo: dict = Depends(persona)):
    """Los suyos; el gestor, además los de sus proyectos; administración, todos. Más reciente primero."""
    limite, cursor = paginacion
    resultado = consultas.lista_viajes(yo, estado, limite, cursor)
    con_decision(resultado["items"], yo)
    return resultado


@router.get("/{id}", response_model=ViajeDetalle, responses=errores(401, 404, 422))
def detalle(id: int, yo: dict = Depends(persona)):
    return _detalle(yo, id)


@router.post("/{id}/estado", response_model=ResultadoCambioEstado, responses=errores(401, 403, 404, 409, 422))
def cambiar_estado(id: int, datos: CambioEstadoViaje, yo: dict = Depends(escritura)):
    """Aprobar, rechazar (con motivo), reabrir o cerrar. Solo administración, y nadie aprueba ni rechaza lo suyo:
    el intento responde 403 `SELF_APPROVAL` y queda en la bitácora. Si el precio del vuelo subió más que la
    tolerancia, aprobar responde 409 `PRICE_CONFIRMATION_REQUIRED` hasta que se mande `confirmar_precio`."""
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    v = viajes.uno(id)
    if not v:
        raise ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])
    accion, motivo = datos.accion, datos.motivo.strip()
    if accion in ("aprobar", "rechazar") and viajes.es_propio_de(v, yo):
        viajes.cambiar_estado(id, accion, motivo, yo)   # el servicio lo impide y deja el evento
        raise ErrorApi(403, "SELF_APPROVAL", viajes.NO_AUTOAPROBAR)
    desde, _, _ = viajes.TRANSICIONES[accion]
    if v["estado"] not in desde:
        raise ErrorApi(409, "INVALID_STATE", f"El viaje {v['codigo']} está {v['estado_texto'].lower()}: no se puede {accion}.")
    if accion == "rechazar" and len(motivo) < 5:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422],
                       {"motivo": "Escribe el motivo del rechazo (5 caracteres o más): la persona lo verá."})
    hecho, mensaje = viajes.cambiar_estado(id, accion, motivo, yo, datos.confirmar_precio)
    if not hecho:
        pendiente = viajes.precio_por_confirmar(id)
        if accion == "aprobar" and pendiente:
            raise ErrorApi(409, "PRICE_CONFIRMATION_REQUIRED", mensaje, {"precio": pendiente})
        raise ErrorApi(409, "INVALID_STATE", mensaje)
    return {"viaje": _detalle(yo, id), "mensaje": mensaje}
