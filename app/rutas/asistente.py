"""Asistente: preguntas en lenguaje natural sobre viajes, gastos y presupuesto.

Administración tiene la página completa (`/admin/asistente`) y el asistente flotante pregunta ahí. Colaborador y gestor
usan el asistente flotante, que pregunta a `/asistente`: la misma vía con el alcance de su sesión.
"""
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import db
from ..servicios import acceso, asistente, eventos, memoria, viajes
from ..web import SOLO_ADMIN, _ctx, _yo, plantillas

router = APIRouter()

# Lo que el panel flotante dice y sugiere depende del permiso de la sesión
BIENVENIDA = {
    "admin": "Pregunta por viajes, gastos, cotizaciones o indicadores. Responde con los datos de la plataforma y cita de dónde salen.",
    "gestor": ("Pregunta por tus viajes, tus gastos y tu presupuesto, y por los de los proyectos que gestionas: cuánto queda, "
               "por qué un gasto quedó en revisión y qué falta. Solo ves lo tuyo y lo de los proyectos que gestionas."),
    "colaborador": ("Pregunta por tus viajes, tus gastos y tu presupuesto: cuánto te queda, por qué un gasto quedó en revisión "
                    "y qué te falta por justificar. Solo ves lo tuyo."),
}
plantillas.env.globals.update(bienvenida_asistente=lambda yo: BIENVENIDA.get((yo or {}).get("rol"), ""),
                              preguntas_asistente=asistente.preguntas_sugeridas)

MENU = [{"texto": "Asistente", "href": "/admin/asistente", "orden": 66, "rol": "admin"}]

# Cómo se presenta cada vía de respuesta: (texto del chip, clase). La página y el asistente flotante usan lo mismo.
MODOS = {"asesor": ("Asesor con herramientas", "ok"), "modelo": ("Modelo de lenguaje con herramientas", "ok"),
         "determinista": ("Sin modelo: consultas directas", "azul"), "tope": ("Tope diario alcanzado", "aviso"),
         # una pregunta reserva su cupo «en curso» y queda «fallida» si algo la corta a mitad
         "en_curso": ("Respondiendo…", "azul"), "fallida": ("Sin respuesta: falló", "aviso")}


def modo_visible(modo: str) -> tuple[str, str]:
    return MODOS.get(modo, (modo, "aviso"))


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
        modo_visible=modo_visible, indice=memoria.estado(), ejemplos=_ejemplos(), tope=asistente.tope_diario(), usadas=asistente.usadas_hoy(yo["id"]),
        recientes=db.todos("""select pregunta, modo, duracion_ms, momento from asistente_consultas where usuario_id=:u
                              order by id desc limit 5""", u=yo["id"]), **extra))


@router.get("/admin/asistente", response_class=HTMLResponse)
def asistente_pagina(request: Request, aviso: str = ""):
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    return _pagina(request, aviso=aviso[:300], pregunta="", respuesta=None)


def _json(request: Request, respuesta: dict) -> JSONResponse:
    """Lo que pide el asistente flotante: solo la respuesta, sin la página."""
    texto, clase = modo_visible(respuesta["modo"])
    return JSONResponse({
        "texto": respuesta["texto"], "modo": respuesta["modo"], "modo_texto": texto, "modo_clase": clase,
        "fuentes": [{"codigo": f["codigo"], "enlace": f["enlace"]} for f in _con_enlaces(request, respuesta["fuentes"])],
        "herramientas": respuesta["herramientas"], "duracion_ms": respuesta["duracion_ms"],
        "usadas": asistente.usadas_hoy(_yo()["id"]), "tope": asistente.tope_diario()})


@router.post("/admin/asistente", response_class=HTMLResponse)
def asistente_preguntar(request: Request, pregunta: str = Form("")):
    """Función normal (no asíncrona): la llamada al modelo corre en un hilo y no detiene al resto del servidor."""
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    respuesta = asistente.responder(pregunta, _yo())
    if request.headers.get("x-envio") == "pagina":  # el asistente flotante pide solo la respuesta, sin la página
        return _json(request, respuesta)
    respuesta["fuentes"] = _con_enlaces(request, respuesta["fuentes"])
    return _pagina(request, aviso="", pregunta=pregunta[:500], respuesta=respuesta)


@router.post("/asistente")
def asistente_preguntar_persona(request: Request, pregunta: str = Form("")):
    """El asistente flotante de cualquier sesión. El alcance lo pone `asistente.responder` según quien pregunta."""
    return _json(request, asistente.responder(pregunta, _yo()))


@router.post("/admin/asistente/indice")
def asistente_indice():
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    resumen = memoria.actualizar()
    partes = [f"{d}: {r['error']}" if "error" in r else f"{d}: {r['enviadas']} fichas enviadas, {r['borradas']} borradas, {r['total']} en total"
              for d, r in resumen.items()]
    eventos.registrar("indice", None, "actualización pedida", " · ".join(partes), _yo()["nombre"])
    return RedirectResponse("/admin/asistente?aviso=" + quote("Índice actualizado. " + " · ".join(partes)), status_code=303)
