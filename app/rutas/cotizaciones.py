"""Reto 1: cotizar, comparar opciones y decidir. La decisión crea el viaje."""
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import config, db
from ..servicios import agente, cotizacion, eventos, precios, viajes
from ..web import (
    NO_ENCONTRADO,
    _ctx,
    _solicitud_propia,
    _yo,
    plantillas,
)

router = APIRouter()

MENU = [{"texto": "Cotizar viaje", "href": "/viajes/nuevo", "orden": 20}]


# ---------- reto 1: viajes ----------
# La lógica vive en `app/servicios/cotizacion.py`; estas rutas la presentan como pantallas y redirecciones.
_comparacion, _completar_ahorros = cotizacion.comparacion, cotizacion.completar_ahorros   # otras pantallas las importan de aquí


@router.get("/viajes/nuevo", response_class=HTMLResponse)
def viaje_nuevo(request: Request, error: str = ""):
    return plantillas.TemplateResponse(request, "viaje_nuevo.html", _ctx(error=error))


@router.post("/viajes")
def viaje_crear(proyecto_id: int = Form(...), viajero_id: int = Form(0), origen: str = Form(""),
                destino: str = Form(""), ciudad: str = Form(""), ida: str = Form(...), regreso: str = Form(...),
                llegar_antes: str = Form(""), baterias_n: int = Form(0), baterias_wh: float = Form(0),
                maleta: str = Form(""), prob_cambio: float = Form(0), carro_dia: float = Form(0),
                solicitado_por: str = Form(""), viajero_nuevo: str = Form(""), para_otra_persona: str = Form(""),
                origen_aeropuertos: str = Form(""), destino_aeropuertos: str = Form(""),
                origen_lugar: str = Form(""), destino_lugar: str = Form(""),
                origen_agregar: str = Form(""), destino_agregar: str = Form("")):
    a_medias = (origen_agregar or destino_agregar).strip()
    if a_medias:   # quedó texto en «Agregar otro aeropuerto»: no se gasta una búsqueda con una lista que la persona no terminó
        return _volver_al_formulario(f'Quedó a medio agregar el aeropuerto "{a_medias[:40]}". '
                                     "Elígelo de la lista o borra ese texto antes de buscar.")
    try:   # quien consulta sale de la sesión: `solicitado_por` del formulario no se usa
        sid = cotizacion.crear(_yo(), proyecto_id=proyecto_id, viajero_id=viajero_id, origen=origen, destino=destino,
                               ciudad=ciudad, ida=ida, regreso=regreso, llegar_antes=llegar_antes, baterias_n=baterias_n,
                               baterias_wh=baterias_wh, maleta=bool(maleta), prob_cambio=prob_cambio, carro_dia=carro_dia,
                               viajero_nuevo=viajero_nuevo, para_otra_persona=para_otra_persona == "1",
                               origen_aeropuertos=origen_aeropuertos, destino_aeropuertos=destino_aeropuertos,
                               origen_lugar=origen_lugar, destino_lugar=destino_lugar)
    except cotizacion.CotizacionInvalida as e:
        return _volver_al_formulario(str(e))
    return RedirectResponse(f"/viajes/{sid}", status_code=303)


def _volver_al_formulario(error: str) -> RedirectResponse:
    return RedirectResponse(f"/viajes/nuevo?{urlencode({'error': error})}", status_code=303)


@router.get("/viajes/{sid}", response_class=HTMLResponse)
def viaje(request: Request, sid: int, aviso: str = ""):
    c = _comparacion(sid) if _solicitud_propia(sid) else None
    if not c:
        return NO_ENCONTRADO
    return plantillas.TemplateResponse(request, "viaje.html", _ctx(
        **c, agente=agente.recomendar(c, solo_determinista=True), aviso_form=aviso[:200], razones=config.RAZONES,
        el_viaje=viajes.de_solicitud(sid), editable=_solicitud_propia(sid, True)))


@router.post("/viajes/{sid}/agente", response_class=HTMLResponse)
def viaje_agente(request: Request, sid: int, pregunta: str = Form("")):
    """Pregunta al agente. Con modelo de lenguaje usa las herramientas; sin él, responde el análisis determinista."""
    c = _comparacion(sid) if _solicitud_propia(sid) else None
    if not c:
        return NO_ENCONTRADO
    with eventos.cronometro() as t:
        r = agente.recomendar(c, pregunta.strip()[:400])
    eventos.registrar("solicitud", sid, "recomendación del agente", (pregunta.strip()[:120] or "recomendación general")
                      + " · herramientas: " + (", ".join(r["pasos"]) or "ninguna"), r["modo"], t())
    return plantillas.TemplateResponse(request, "viaje.html", _ctx(**c, agente=r, pregunta=pregunta, razones=config.RAZONES,
                                                                   el_viaje=viajes.de_solicitud(sid), editable=_solicitud_propia(sid, True)))


@router.post("/viajes/{sid}/tarifas/{oid}")
def viaje_tarifas(sid: int, oid: int):
    """Trae las familias tarifarias reales de un vuelo (dos consultas al buscador)."""
    if not _solicitud_propia(sid, para_modificar=True):   # gasta cupo de pago: quien solo puede ver, no
        return NO_ENCONTRADO
    sol = db.uno("select * from solicitudes where id=:i", i=sid)
    o = db.uno("select * from opciones where id=:i and solicitud_id=:s", i=oid, s=sid)
    if sol and o:
        tarifas, origen = precios.tarifas_de_vuelo(cotizacion.codigos(sol, "origen"), cotizacion.codigos(sol, "destino"), sol["ida"], sol["regreso"],
                                                   db.de_json(o["datos"], {}), sid, permitir_en_vivo=True)
        if tarifas:
            db.actualizar("opciones", oid, tarifas={"lista": tarifas, "origen": origen})
            cotizacion.registrar_ahorro(sid)
    return RedirectResponse(f"/viajes/{sid}#v{oid}", status_code=303)


@router.post("/viajes/{sid}/decidir")
def viaje_decidir(sid: int, vuelo_id: int = Form(0), hotel_id: int = Form(0), motivo: str = Form(""),
                  aprobado_por: str = Form(""), razones: list[str] = Form([])):
    if not _solicitud_propia(sid, para_modificar=True):   # quien decide sale de la sesión: `aprobado_por` no se usa
        return NO_ENCONTRADO
    try:
        cotizacion.decidir(_yo(), sid, vuelo_id, hotel_id, motivo, razones)
    except LookupError:
        return NO_ENCONTRADO
    except (cotizacion.DecisionBloqueada, cotizacion.DecisionInvalida) as e:
        return RedirectResponse(f"/viajes/{sid}?{urlencode({'aviso': str(e)})}", status_code=303)
    return RedirectResponse(f"/viajes/{sid}/ficha", status_code=303)


@router.get("/viajes/{sid}/ficha", response_class=HTMLResponse)
def viaje_ficha(request: Request, sid: int):
    if not _solicitud_propia(sid):
        return NO_ENCONTRADO
    c = _comparacion(sid)
    if not c or not c["decision"]:
        return RedirectResponse(f"/viajes/{sid}", status_code=303)
    return plantillas.TemplateResponse(request, "ficha.html", _ctx(**c, d=db.de_json(c["decision"]["desglose"], {}),
                                                                   el_viaje=viajes.de_solicitud(sid)))
