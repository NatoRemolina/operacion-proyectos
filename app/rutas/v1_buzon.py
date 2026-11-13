"""API v1: buzón de correo simulado. Solo administración. Contrato en `contracts/api-v1.md`.

La lógica es la de `servicios/buzon.py`, la misma que la pantalla de carga de administración.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import config
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, solo_admin
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_buzon import LecturaBuzon, MensajeBuzon, ResultadoBuzon
from ..servicios import acceso, buzon, consultas, viajes
from .v1_gastos import ViajeAsignable

router = APIRouter(prefix=PREFIJO + "/buzon", tags=["buzón simulado"])


class BuzonSimulado(BaseModel):
    simulado: bool = Field(True, description="Siempre verdadero: no hay un buzón real detrás.")
    aviso: str
    mensajes: list[MensajeBuzon]
    viajes: list[ViajeAsignable] = Field(description="Viajes aprobados o pendientes a los que se pueden cargar los correos.")


@router.get("", response_model=BuzonSimulado, responses=errores(401, 403))
def ver(yo: dict = Depends(solo_admin)):
    """Los correos (.eml) y confirmaciones en HTML de ejemplo que se pueden leer, y los viajes a los que cargarlos."""
    return {"simulado": True, "aviso": buzon.AVISO, "mensajes": buzon.mensajes(),
            "viajes": viajes.lista("v.estado in ('aprobado','pendiente_aprobacion')")}


@router.post("/lectura", response_model=ResultadoBuzon, responses=errores(401, 403, 422))
def leer(cuerpo: LecturaBuzon, yo: dict = Depends(escritura)):
    """Lee los correos elegidos por el canal «correo», como cualquier recibo: lectura, validación y estado real.
    Lo que no está en el buzón se devuelve en `errores` y no crea nada."""
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    viaje = viajes.uno(cuerpo.viaje_id) if cuerpo.viaje_id else None
    if cuerpo.viaje_id and not viaje:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"viaje_id": "Ese viaje no existe."})
    resultado = buzon.leer(cuerpo.nombres[: config.MAX_ARCHIVOS_POR_CARGA * 4], yo, viaje)
    return {"leidos": [g for g in (consultas.gasto(yo, gid) for gid in resultado["gastos"]) if g], "errores": resultado["errores"]}
