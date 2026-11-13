"""API v1: Monitoreo por pestañas (viajes, gastos, búsquedas, modelo, cupos, auditoría y calidad) y exportación CSV.

Contrato en `contracts/api-v1.md`. Solo administración, como `/admin/monitoreo`; las cifras salen de `metricas`.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..api_v1 import PREFIJO, solo_admin
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_monitoreo import Pestana, PestanaMonitoreo
from ..servicios import tablero
from .v1_kpis import FILTRO_DESDE, FILTRO_HASTA, FILTRO_PROYECTO

router = APIRouter(prefix=PREFIJO + "/monitoreo", tags=["monitoreo"])

Vista = Literal["v_h_viaje", "v_h_gasto", "v_h_busqueda", "v_h_decision", "v_h_lectura", "v_h_evento", "v_h_consulta"]


@router.get("", response_model=PestanaMonitoreo, responses=errores(401, 403, 422))
def pestana(pestana: Pestana = Query("gastos", description="Sin pestaña: gastos."), proyecto_id: int = FILTRO_PROYECTO,
            desde: str = FILTRO_DESDE, hasta: str = FILTRO_HASTA, _yo: dict = Depends(solo_admin)):
    """Las cifras y tablas de una pestaña con los filtros. La auditoría no se filtra por proyecto, como en la pantalla."""
    return tablero.pestana_monitoreo(pestana, tablero.filtros(proyecto_id, desde, hasta))


@router.get("/exportar.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}, **errores(401, 403, 422)})
def exportar(vista: Vista = Query(description="Un hecho de la capa analítica."), proyecto_id: int = FILTRO_PROYECTO,
             desde: str = FILTRO_DESDE, hasta: str = FILTRO_HASTA, _yo: dict = Depends(solo_admin)):
    """El mismo CSV de la pantalla con los filtros. Deja el evento «exportación»."""
    return Response(tablero.exportar_vista(vista, tablero.filtros(proyecto_id, desde, hasta)), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{vista}.csv"', "Cache-Control": "no-store"})
