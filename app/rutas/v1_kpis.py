"""API v1: indicadores con meta, semáforo y tendencia, ficha por persona y exportación. Contrato en `contracts/api-v1.md`.

Solo administración, como la pantalla `/admin/kpis`. Las cifras salen de `servicios.kpis`, la misma definición de la pantalla.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, solo_admin
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_kpis import FichaPersona, TableroKpis
from ..servicios import eventos, kpis, tablero, viajes

router = APIRouter(prefix=PREFIJO + "/kpis", tags=["kpis"])

FILTRO_PROYECTO = Query(0, ge=0, description="0 o ausente: todos los proyectos.")
FILTRO_DESDE = Query("", max_length=40, description="AAAA-MM-DD. Una fecha no válida se ignora.")
FILTRO_HASTA = Query("", max_length=40, description="AAAA-MM-DD. Una fecha no válida se ignora.")


def pares(filas) -> list[dict]:
    """Los desgloses del servicio son pares (etiqueta, cifra); en la API llevan nombre."""
    return [{"etiqueta": a, "valor": b} for a, b in filas or []]


def _grupo(fila: dict, clave: str) -> dict:
    return {"nombre": fila.get(clave), "presupuesto": fila.get("presupuesto"), "gastado": fila.get("gastado"), "pct": fila.get("pct")}


def _tablero(t: dict) -> dict:
    c, g = t["cotizacion"], t["gastos"]
    resumen = t["resumen"]
    return {
        "filtros": t["filtros"], "retos": [{"reto": r, "nombre": n} for r, n in kpis.RETOS.items()],
        "proyectos": tablero.proyectos(), "kpis": t["kpis"],
        "resumen": {"verde": resumen.get("verde", 0), "ambar": resumen.get("ambar", 0), "rojo": resumen.get("rojo", 0),
                    "sin_datos": resumen.get("sin datos", 0)},
        "tendencia": t["tendencia"],
        "cotizacion": {**{k: pares(c[k]) for k in ("cotizaciones_por_persona", "cotizaciones_por_ruta", "consultas_por_origen",
                                                    "consultas_por_tipo", "consultas_por_persona", "consultas_por_ruta")},
                       "errores_buscador": [{"momento": m, "tipo": tipo, "error": e} for m, tipo, e in c["errores_buscador"]],
                       "cupo": c["cupo"]},
        "gastos": {"por_viaje": [{**v, "codigo": viajes.codigo_viaje(v)} for v in g["por_viaje"]],
                   "por_proyecto": [_grupo(p, "proyecto") for p in g["por_proyecto"]],
                   "por_categoria": [_grupo(x, "grupo") for x in g["por_categoria"]],
                   "por_moneda": g["por_moneda"], "revision_antiguas": g["revision_antiguas"], "real_total": g["real_total"]},
        "personas": t["personas"], "por_cargo": t["por_cargo"],
    }


@router.get("", response_model=TableroKpis, responses=errores(401, 403, 422))
def tablero_kpis(proyecto_id: int = FILTRO_PROYECTO, desde: str = FILTRO_DESDE, hasta: str = FILTRO_HASTA,
                 _yo: dict = Depends(solo_admin)):
    """Indicadores de los dos retos con meta, semáforo y tendencia semanal, sus desgloses y la tabla de personas."""
    return _tablero(tablero.tablero_kpis(tablero.filtros(proyecto_id, desde, hasta)))


@router.get("/personas/{id}", response_model=FichaPersona, responses=errores(401, 403, 404, 422))
def ficha(id: int, _yo: dict = Depends(solo_admin)):
    """Todo lo de una persona por su ID y su línea de tiempo. Deja el evento «ficha consultada», como la pantalla."""
    p = kpis.ficha_persona(id)
    if not p:
        raise ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])
    eventos.registrar("kpis", id, "ficha consultada", p["usuario"]["codigo"])
    return {**p, "gastos_por_estado": pares(p["gastos_por_estado"]), "gastos_por_canal": pares(p["gastos_por_canal"])}


@router.get("/exportar.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}, **errores(401, 403, 422)})
def exportar(que: Literal["kpis", "consultas", "personas"] = Query(description="Indicadores, consultas al buscador o personas."),
             proyecto_id: int = FILTRO_PROYECTO, desde: str = FILTRO_DESDE, hasta: str = FILTRO_HASTA,
             _yo: dict = Depends(solo_admin)):
    """El mismo CSV que la pantalla, con los mismos filtros. Deja el evento «exportación»."""
    contenido, nombre = tablero.exportar_kpis(que, tablero.filtros(proyecto_id, desde, hasta))
    return Response(contenido, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


