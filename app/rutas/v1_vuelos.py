"""API v1: estado de los vuelos del día y «Actualizar ahora». Contrato en `contracts/api-v1.md`.

Solo administración, como el tablero de `/admin/viajes`. La lógica (ventana, caché, topes y avisos) está en
`servicios.monitoreo_vuelos`; la API y la pantalla la llaman igual, a través de `servicios.tablero`.
"""
from fastapi import APIRouter, Depends, Path, Query

from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, solo_admin
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_vuelos import ResultadoActualizacion, VuelosDelDia
from ..servicios import acceso, monitoreo_vuelos, tablero

router = APIRouter(prefix=PREFIJO + "/vuelos", tags=["vuelos"])


@router.get("", response_model=VuelosDelDia, responses=errores(401, 403, 422))
def vuelos(fecha: str = Query("", max_length=40, description="AAAA-MM-DD. Sin fecha (o no válida): hoy y los vuelos en curso."),
           _yo: dict = Depends(solo_admin)):
    """Tramos de los viajes aprobados. Pensado para pedirse cada 15 s con la pestaña visible: cada tramo se consulta solo
    dentro de su ventana (desde 3 h antes de salir hasta la llegada), con caché y topes."""
    dia = monitoreo_vuelos.fecha_valida(fecha)
    return {"fecha": dia, "hoy": monitoreo_vuelos.hoy(), "tramos": tablero.vuelos_para_mostrar(dia)}


@router.post("/{tramo_id}/actualizar", response_model=ResultadoActualizacion, responses=errores(401, 403, 404, 422))
def actualizar(tramo_id: int = Path(ge=1, le=2**31 - 1), yo: dict = Depends(escritura)):
    """Salta la caché (una vez por minuto), nunca la ventana ni los topes. Si no consulta, `motivo` dice por qué."""
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    r = tablero.actualizar_vuelo(tramo_id)
    if not r:
        raise ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])
    return {"consultado": r["consultado"], "motivo": r["motivo"], "mensaje": r["mensaje"], "tramo": tablero.tramo_para_mostrar(tramo_id)}
