"""API v1: rutas frecuentes y precios, y la exactitud del modelo de precio. Contrato en `contracts/api-v1.md`.

Solo administración, como el tablero de KPI. Las cifras salen de `servicios.rutas_frecuentes` y `servicios.modelo`.
"""
from fastapi import APIRouter, Depends, Query

from ..api_v1 import PREFIJO, solo_admin
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_rutas_frecuentes import RutasFrecuentes
from ..servicios import modelo, ofertas, rutas_frecuentes

router = APIRouter(prefix=PREFIJO + "/kpis", tags=["kpis"])

MINIMO_DEMOSTRATIVO = 30   # menos observaciones que esto en la ruta más vista: las cifras son de demostración
AVISO = ("Con pocos datos las cifras son demostrativas: describen lo visto en las cotizaciones y búsquedas guardadas, no el "
         "mercado. La señal compara el último precio visto con el rango habitual de la ruta y no predice el precio futuro.")


@router.get("/rutas-frecuentes", response_model=RutasFrecuentes, responses=errores(401, 403, 422))
def rutas(n: int = Query(10, ge=1, le=50, description="Cuántas rutas."), _yo: dict = Depends(solo_admin)):
    """Las rutas más cotizadas y viajadas de los últimos 90 días con sus precios, y la exactitud del precio esperado."""
    ofertas.actualizar_si_toca()
    top = rutas_frecuentes.top(n=n)
    tarifas, _ = ofertas.limpias()
    return {"dias": rutas_frecuentes.DIAS, "rutas": top, "exactitud": modelo.exactitud(), "tarifas_vistas": len(tarifas),
            "pocos_datos": max((r["observaciones"] for r in top), default=0) < MINIMO_DEMOSTRATIVO, "aviso": AVISO}
