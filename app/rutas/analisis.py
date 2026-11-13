"""Monitoreo, analítica de precios y flujo de la información."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from datos.semilla import VISTAS

from .. import db
from ..servicios import analitica, metricas, tablero
from ..web import (
    NO_ENCONTRADO,
    _ctx,
    _indicadores,
    plantillas,
)
from .cotizaciones import _completar_ahorros

router = APIRouter()

MENU = [{"texto": "Monitoreo", "href": "/admin/monitoreo", "orden": 70, "rol": "admin"},
        {"texto": "Analítica de precios", "href": "/analitica", "orden": 93, "rol": "admin", "grupo": "Administración"},
        {"texto": "Flujo de la información", "href": "/flujo", "orden": 94, "rol": "admin", "grupo": "Administración"}]


# ---------- flujo de la información ----------
@router.get("/flujo", response_class=HTMLResponse)
def flujo(request: Request):
    pasos = {r["paso"]: r["n"] for r in db.todos("select paso, count(*) n from eventos group by paso")}
    fuentes = db.todos("select fuente, count(*) n, avg(duracion_ms) ms from eventos where fuente<>'' group by fuente order by n desc")
    return plantillas.TemplateResponse(request, "flujo.html", _ctx(
        ind=_indicadores(), pasos=pasos, fuentes=fuentes,
        eventos=db.todos("select * from eventos order by id desc limit 60")))


@router.get("/analitica", response_class=HTMLResponse)
def analitica_pagina(request: Request):
    _completar_ahorros()
    return plantillas.TemplateResponse(request, "analitica.html", _ctx(a=analitica.resumen()))


# ---------- monitoreo ----------
# Pestañas, filtros, datos y exportación viven en `servicios.tablero`: la pantalla y la API v1 responden lo mismo
PESTANAS, FECHA_DE_VISTA = tablero.PESTANAS, tablero.FECHA_DE_VISTA
_filtros, _datos_pestana = tablero.filtros, tablero.datos_pestana


@router.get("/admin/monitoreo", response_class=HTMLResponse)
def monitoreo(request: Request, pestana: str = "gastos", proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    pestana = pestana if pestana in PESTANAS else "gastos"
    f = _filtros(proyecto_id, desde, hasta)
    consulta = "&".join(f"{k}={v}" for k, v in f.items() if v)
    return plantillas.TemplateResponse(request, "monitoreo.html", _ctx(
        pestana=pestana, pestanas=PESTANAS, f=f, consulta=consulta, d=_datos_pestana(pestana, f),
        catalogo=tablero.catalogo(f) if pestana == "calidad" else []))


@router.get("/admin/monitoreo/exportar.csv")
def monitoreo_exportar(vista: str, proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    """Descarga un hecho de la capa analítica con los mismos filtros de la pantalla."""
    if vista not in VISTAS:
        return NO_ENCONTRADO
    return Response(tablero.exportar_vista(vista, _filtros(proyecto_id, desde, hasta)), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{vista}.csv"'})


@router.get("/api/metricas", tags=["api"])
def api_metricas(nombre: str = "", proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    """Sin `nombre` devuelve el catálogo; con `nombre`, el valor de esa métrica con los filtros dados."""
    f = _filtros(proyecto_id, desde, hasta)
    if not nombre:
        return [{"nombre": n, "titulo": t, "unidad": u, "para_que": p} for n, (t, u, p, _) in metricas.CATALOGO.items()]
    v = metricas.valor(nombre, f)
    return v if v else JSONResponse({"error": "Métrica desconocida"}, status_code=404)
