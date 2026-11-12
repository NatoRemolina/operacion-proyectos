"""Monitoreo, analítica de precios y flujo de la información."""
import csv
import io
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from datos.semilla import VISTAS

from .. import config, db
from ..servicios import analitica, eventos, metricas, precios
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
PESTANAS = {"viajes": "Viajes", "gastos": "Gastos", "busquedas": "Búsquedas", "modelo": "Modelo de lenguaje", "cupos": "Cupos",
            "auditoria": "Auditoría", "calidad": "Calidad"}
FECHA_DE_VISTA = {"v_h_viaje": "creado", "v_h_gasto": "creado", "v_h_busqueda": "creado", "v_h_decision": "creado", "v_h_lectura": "momento",
                  "v_h_evento": "momento"}
_ES_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _filtros(proyecto_id: int = 0, desde: str = "", hasta: str = "") -> dict:
    return {"proyecto_id": proyecto_id or None, "desde": desde if _ES_FECHA.match(desde) else None,
            "hasta": hasta if _ES_FECHA.match(hasta) else None}


def _datos_pestana(pestana: str, f: dict) -> dict:
    if pestana == "viajes":
        return metricas.viajes(f)
    if pestana == "gastos":
        return metricas.gastos(f)
    if pestana == "busquedas":
        _completar_ahorros()
        return metricas.busquedas(f)
    if pestana == "modelo":
        return metricas.uso_modelo(f)
    if pestana == "cupos":
        hoy = db.ahora()[:10]
        return {"buscador": precios.cupo(), "busquedas": metricas.busquedas(f),
                "modelo_hoy": db.uno("select count(*) n from llamadas_modelo where momento>=:h", h=hoy)["n"],
                "filas": [(t, db.uno(f"select count(*) n from {t}")["n"]) for t in
                          ("usuarios", "viajes", "gastos", "documentos", "telegram_mensajes", "solicitudes", "opciones", "decisiones", "elecciones", "observaciones",
                           "busquedas", "eventos", "llamadas_modelo", "errores")]}
    if pestana == "auditoria":
        donde, par = metricas._filtro({**f, "proyecto_id": None}, "momento")
        return {"eventos": db.todos(f"select * from v_h_evento where {donde} order by id desc limit 150", **par),
                "por_persona": db.todos(f"""select coalesce(usuario,'sistema') usuario, count(*) n from v_h_evento
                                            where {donde} group by coalesce(usuario,'sistema') order by n desc""", **par),
                "por_paso": db.todos(f"select paso, count(*) n from v_h_evento where {donde} group by paso order by n desc", **par),
                "errores": db.todos("""select e.*, u.nombre usuario from errores e left join usuarios u on u.id=e.usuario_id
                                       order by e.id desc limit 30""")}
    g = metricas.gastos(f)
    return {"pruebas": metricas.calidad_de_datos(), "calibracion": g["calibracion"], "por_campo": g["correccion_por_campo"],
            "tasa_correccion": g["tasa_correccion"], "evaluados": g["gastos_evaluados"],
            "umbral": config.UMBRAL_CONFIANZA}


@router.get("/admin/monitoreo", response_class=HTMLResponse)
def monitoreo(request: Request, pestana: str = "gastos", proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    pestana = pestana if pestana in PESTANAS else "gastos"
    f = _filtros(proyecto_id, desde, hasta)
    consulta = "&".join(f"{k}={v}" for k, v in f.items() if v)
    return plantillas.TemplateResponse(request, "monitoreo.html", _ctx(
        pestana=pestana, pestanas=PESTANAS, f=f, consulta=consulta, d=_datos_pestana(pestana, f),
        catalogo=[metricas.valor(n, f) for n in metricas.CATALOGO] if pestana == "calidad" else []))


@router.get("/admin/monitoreo/exportar.csv")
def monitoreo_exportar(vista: str, proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    """Descarga un hecho de la capa analítica con los mismos filtros de la pantalla."""
    if vista not in VISTAS:
        return NO_ENCONTRADO
    f = _filtros(proyecto_id, desde, hasta)
    if vista in ("v_h_lectura", "v_h_evento"):
        f["proyecto_id"] = None
    donde, par = metricas._filtro(f, FECHA_DE_VISTA[vista])
    filas = db.todos(f"select * from {vista} where {donde} order by id", **par)
    salida = io.StringIO()
    if filas:
        w = csv.DictWriter(salida, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    eventos.registrar("monitoreo", None, "exportación", f"{vista}: {len(filas)} filas")
    return Response("\ufeff" + salida.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{vista}.csv"'})


@router.get("/api/metricas", tags=["api"])
def api_metricas(nombre: str = "", proyecto_id: int = 0, desde: str = "", hasta: str = ""):
    """Sin `nombre` devuelve el catálogo; con `nombre`, el valor de esa métrica con los filtros dados."""
    f = _filtros(proyecto_id, desde, hasta)
    if not nombre:
        return [{"nombre": n, "titulo": t, "unidad": u, "para_que": p} for n, (t, u, p, _) in metricas.CATALOGO.items()]
    v = metricas.valor(nombre, f)
    return v if v else JSONResponse({"error": "Métrica desconocida"}, status_code=404)
