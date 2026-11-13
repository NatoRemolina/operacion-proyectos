"""API v1: proyectos con previsto frente a real, alta y edición, tablero y exportación de sus gastos.

Contrato en `contracts/api-v1.md`, sección «Proyectos». La regla vive en `app/servicios/proyectos.py`, la misma que usan
las pantallas actuales: administración ve y edita todos; quien gestiona ve el tablero de los suyos; nadie más.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, pagina, persona
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_proyectos import DatosProyecto, ListaProyectos, ProyectoResumen, TableroProyecto
from ..servicios import acceso, consultas, contable, proyectos

router = APIRouter(prefix=PREFIJO + "/proyectos", tags=["proyectos"])


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _solo_admin(yo: dict) -> None:
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")


def _diferencia(real: float, previsto: float) -> str | None:
    return consultas.dinero(Decimal(str(real)) - Decimal(str(previsto)))


def _resumen(p: dict, comparacion: dict | None = None) -> dict:
    c = comparacion or proyectos.comparacion(p["id"])
    return {"id": p["id"], "nombre": p["nombre"], "cliente": p["cliente"], "ciudad": p["ciudad"],
            "fecha_inicio": p["fecha_inicio"], "fecha_fin": p["fecha_fin"], "moneda": p["moneda"],
            "viajes": p["viajes"], "gastos": p["gastos"],
            "previsto_usd": consultas.dinero(c["tot_previsto"]), "real_usd": consultas.dinero(c["tot_real"]),
            "diferencia_usd": _diferencia(c["tot_real"], c["tot_previsto"])}


def _datos(entrada: DatosProyecto) -> dict:
    try:
        return proyectos.validar(entrada.nombre, entrada.cliente, entrada.ciudad, entrada.fecha_inicio, entrada.fecha_fin,
                                 entrada.moneda)
    except proyectos.DatosInvalidos as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {e.campo: str(e)}) from None


@router.get("", response_model=ListaProyectos, responses=errores(401, 403, 422))
def lista(paginacion: tuple = Depends(pagina), yo: dict = Depends(persona)):
    """Administración, todos; quien gestiona, los suyos; el resto, 403. Más reciente primero."""
    if yo["rol"] not in ("admin", "gestor"):
        raise ErrorApi(403, "FORBIDDEN", "Los proyectos los ven administración y quien los gestiona.")
    limite, cursor = paginacion
    filas = proyectos.lista(yo, limite + 1, cursor)
    items = [_resumen(p) for p in filas[:limite]]
    return {"items": items, "siguiente": str(items[-1]["id"]) if len(filas) > limite else None}


@router.post("", status_code=201, response_model=ProyectoResumen, responses=errores(401, 403, 422))
def crear(entrada: DatosProyecto, yo: dict = Depends(escritura)):
    """Solo administración. Deja el evento `proyecto creado`."""
    _solo_admin(yo)
    pid = proyectos.crear(_datos(entrada), yo)
    return _resumen(proyectos.con_conteos(pid))


@router.get("/{id}", response_model=TableroProyecto, responses=errores(401, 404, 422))
def tablero(id: int, yo: dict = Depends(persona)):
    """Previsto frente a real por categoría, viajes y gastos del proyecto. Lo ajeno responde 404."""
    p = proyectos.con_conteos(id) if proyectos.visible(yo, id) else None
    if not p:
        raise _no_encontrado()
    c = proyectos.comparacion(id)
    desde, hasta = contable.mes_en_curso()
    return {
        "proyecto": _resumen(p, c),
        "categorias": [{"clave": f["clave"], "nombre": f["nombre"], "previsto_usd": consultas.dinero(f["previsto"]),
                        "real_usd": consultas.dinero(f["real"]), "diferencia_usd": _diferencia(f["real"], f["previsto"])}
                       for f in c["filas"]],
        "previsto_usd": consultas.dinero(c["tot_previsto"]), "real_usd": consultas.dinero(c["tot_real"]),
        "diferencia_usd": _diferencia(c["tot_real"], c["tot_previsto"]),
        "en_revision": proyectos.en_revision(id), "faltantes": c["faltantes"],
        "viajes": [consultas._viaje_resumen(v) for v in c["viajes"]],
        "gastos": [{**consultas._gasto_resumen(g), "viajero": g["viajero"]} for g in proyectos.gastos(id)],
        "periodo_contable": {"desde": desde, "hasta": hasta},
    }


@router.post("/{id}", response_model=ProyectoResumen, responses=errores(401, 403, 404, 422))
def editar(id: int, entrada: DatosProyecto, yo: dict = Depends(escritura)):
    """Solo administración. Se mandan todos los campos. Deja el evento `proyecto editado`."""
    _solo_admin(yo)
    if not proyectos.existe(id):
        raise _no_encontrado()
    proyectos.editar(id, _datos(entrada), yo)
    return _resumen(proyectos.con_conteos(id))


@router.get("/{id}/exportar.csv", response_class=Response, responses={
    **errores(401, 404, 422), 200: {"description": "Los gastos del proyecto en CSV", "content": {"text/csv": {}}}})
def exportar(id: int, yo: dict = Depends(persona)):
    """El mismo CSV que la pantalla actual del proyecto. Lo ajeno responde 404."""
    if not proyectos.visible(yo, id) or not proyectos.existe(id):
        raise _no_encontrado()
    return Response(proyectos.csv_gastos(id), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="gastos_proyecto_{id}.csv"', "Cache-Control": "no-store"})
