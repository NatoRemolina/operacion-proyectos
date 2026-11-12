"""Asistente de administración: preguntas en lenguaje natural sobre lo que ha reportado cada persona."""
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db
from ..servicios import acceso, asistente, eventos, memoria, viajes
from ..web import SOLO_ADMIN, _ctx, _yo, plantillas

router = APIRouter()

MENU = [{"texto": "Asistente", "href": "/admin/asistente", "orden": 66, "rol": "admin"}]


def _ejemplos() -> list[str]:
    """Preguntas armadas con datos que existen, para que el primer clic ya responda algo."""
    salida = []
    piloto = db.uno("""select u.id from usuarios u where u.rol='colaborador' and exists (select 1 from viajes v where v.usuario_id=u.id)
                       order by u.id limit 1""") or db.uno("select id from usuarios where rol='colaborador' order by id limit 1")
    if piloto:
        salida.append(f"¿Qué ha reportado {viajes.codigo_persona(piloto['id'])} en su viaje?")
    v = db.uno("select id, creado from viajes order by id desc limit 1")
    if v:
        salida.append(f"¿Qué gastos tiene el viaje {viajes.codigo_viaje(v)}?")
    salida += ["¿Quién mencionó el parqueadero?", "¿Cuál es el gasto real aprobado?"]
    return salida


def _con_enlaces(request: Request, fuentes: list[dict]) -> list[dict]:
    """La ficha de una persona es de otro módulo: se enlaza solo si esa pantalla está publicada."""
    hay_ficha = any(getattr(r, "path", "").startswith("/admin/kpis/persona/") for r in request.app.routes)
    return [{**f, "enlace": f["enlace"] if f["tipo"] != "persona" or hay_ficha else None} for f in fuentes]


def _pagina(request: Request, **extra):
    asistente.asegurar_regla()
    yo = _yo()
    return plantillas.TemplateResponse(request, "asistente.html", _ctx(
        indice=memoria.estado(), ejemplos=_ejemplos(), tope=asistente.tope_diario(), usadas=asistente.usadas_hoy(yo["id"]),
        recientes=db.todos("""select pregunta, modo, duracion_ms, momento from asistente_consultas where usuario_id=:u
                              order by id desc limit 5""", u=yo["id"]), **extra))


@router.get("/admin/asistente", response_class=HTMLResponse)
def asistente_pagina(request: Request, aviso: str = ""):
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    return _pagina(request, aviso=aviso[:300], pregunta="", respuesta=None)


@router.post("/admin/asistente", response_class=HTMLResponse)
def asistente_preguntar(request: Request, pregunta: str = Form("")):
    """Función normal (no asíncrona): la llamada al modelo corre en un hilo y no detiene al resto del servidor."""
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    respuesta = asistente.responder(pregunta, _yo())
    respuesta["fuentes"] = _con_enlaces(request, respuesta["fuentes"])
    return _pagina(request, aviso="", pregunta=pregunta[:500], respuesta=respuesta)


@router.post("/admin/asistente/indice")
def asistente_indice():
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    resumen = memoria.actualizar()
    partes = [f"{d}: {r['error']}" if "error" in r else f"{d}: {r['enviadas']} fichas enviadas, {r['borradas']} borradas, {r['total']} en total"
              for d, r in resumen.items()]
    eventos.registrar("indice", None, "actualización pedida", " · ".join(partes), _yo()["nombre"])
    return RedirectResponse("/admin/asistente?aviso=" + quote("Índice actualizado. " + " · ".join(partes)), status_code=303)
