"""API v1: viajes visibles para la persona. Contrato en `contracts/api-v1.md`."""
from fastapi import APIRouter, Depends

from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, pagina, persona
from ..api_v1.esquemas import EstadoViaje, ListaViajes, ViajeDetalle, errores
from ..servicios import consultas

router = APIRouter(prefix=PREFIJO + "/viajes", tags=["viajes"])


@router.get("", response_model=ListaViajes, responses=errores(401, 422))
def lista(estado: EstadoViaje | None = None, paginacion: tuple = Depends(pagina), yo: dict = Depends(persona)):
    """Los suyos; el gestor, además los de sus proyectos; administración, todos. Más reciente primero."""
    limite, cursor = paginacion
    return consultas.lista_viajes(yo, estado, limite, cursor)


@router.get("/{id}", response_model=ViajeDetalle, responses=errores(401, 404, 422))
def detalle(id: int, yo: dict = Depends(persona)):
    v = consultas.viaje(yo, id)
    if not v:
        raise ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])
    return v
