"""API v1: catálogo de reglas y supuestos y edición de un valor. Solo administración. Contrato en `contracts/api-v1.md`.

La lógica es la de `servicios/reglas.py`, la misma que la pantalla de administración `/reglas`.
"""
from fastapi import APIRouter, Depends

from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, solo_admin
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_reglas import CatalogoReglas, EdicionRegla, Regla
from ..servicios import acceso
from ..servicios import reglas as catalogo_reglas

router = APIRouter(prefix=PREFIJO + "/reglas", tags=["reglas"])


@router.get("", response_model=CatalogoReglas, responses=errores(401, 403))
def catalogo(yo: dict = Depends(solo_admin)):
    """Las reglas agrupadas por ámbito (aerolíneas, programas de hotel, baterías, supuestos, metas de los KPI, cuentas
    contables y lo demás que exista) y las membresías de fidelización, en solo lectura."""
    return {"grupos": catalogo_reglas.catalogo(), "membresias": catalogo_reglas.membresias()}


@router.post("/{id}", response_model=Regla, responses=errores(401, 403, 404, 422))
def editar(id: int, cuerpo: EdicionRegla, yo: dict = Depends(escritura)):
    """Cambia el valor de una regla. Una regla numérica sigue siendo numérica (422 si no). Deja el evento «regla editada»."""
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    try:
        return catalogo_reglas.editar(id, cuerpo.valor, yo.get("nombre", "usuario"))
    except LookupError as e:
        raise ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404]) from e
    except catalogo_reglas.ReglaInvalida as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"valor": str(e)}) from e
