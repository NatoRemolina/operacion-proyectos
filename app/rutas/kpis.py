"""Indicadores con meta y semáforo, y la ficha de cada persona por su ID."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .. import db
from ..servicios import acceso, eventos, exportacion, kpis, metricas
from ..web import NO_ENCONTRADO, SOLO_ADMIN, _ctx, _yo, plantillas
from .analisis import _filtros
from .cotizaciones import _completar_ahorros

router = APIRouter()

MENU = [{"texto": "KPIs", "href": "/admin/kpis", "orden": 65, "rol": "admin"}]


def _consulta(f: dict) -> str:
    return "&".join(f"{k}={v}" for k, v in f.items() if v)


@router.get("/admin/kpis", response_class=HTMLResponse)
def tablero(request: Request, proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    _completar_ahorros()
    f = _filtros(proyecto_id, desde, hasta)
    return plantillas.TemplateResponse(request, "kpis.html", _ctx(
        t=kpis.tablero(f), f=f, consulta=_consulta(f), retos=kpis.RETOS))


@router.get("/admin/kpis/persona/{uid}", response_class=HTMLResponse)
def ficha(request: Request, uid: int):
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    p = kpis.ficha_persona(uid)
    if not p:
        return NO_ENCONTRADO
    eventos.registrar("kpis", uid, "ficha consultada", p["usuario"]["codigo"])
    return plantillas.TemplateResponse(request, "kpis_persona.html", _ctx(p=p))


@router.get("/api/kpis", tags=["api"])
def api_kpis(proyecto_id: int = 0, desde: str = "", hasta: str = "", persona_id: int = 0):
    """Indicadores con su meta y semáforo. Con `persona_id`, la ficha de esa persona."""
    if not acceso.es_admin(_yo()):
        return JSONResponse({"error": "Solo administración"}, status_code=403)
    if persona_id:
        p = kpis.ficha_persona(persona_id)
        return p if p else JSONResponse({"error": "Persona desconocida"}, status_code=404)
    _completar_ahorros()
    return kpis.tablero(_filtros(proyecto_id, desde, hasta))


EXPORTABLES = {"kpis": "indicadores", "consultas": "consultas al buscador", "personas": "personas"}


@router.get("/admin/kpis/exportar.csv")
def exportar(que: str = "kpis", proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    """Descarga los indicadores, las consultas al buscador o la tabla de personas con los mismos filtros de la pantalla."""
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    if que not in EXPORTABLES:
        return NO_ENCONTRADO
    f = _filtros(proyecto_id, desde, hasta)
    if que == "kpis":
        filas = [{c: k[c] for c in ("nombre", "titulo", "valor", "unidad", "estado", "meta", "alerta", "sentido", "responsable", "formula")}
                 for k in kpis.evaluar(f)]
    elif que == "personas":
        filas = kpis.personas(f)
    else:
        donde, par = metricas._filtro(f, "momento")
        filas = db.todos(f"select * from v_h_consulta where {donde} order by id", **par)
    eventos.registrar("kpis", None, "exportación", f"{EXPORTABLES[que]}: {len(filas)} filas")
    return Response(exportacion.csv_de(filas), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="kpis_{que}.csv"'})
