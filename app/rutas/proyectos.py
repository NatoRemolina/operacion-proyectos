"""Proyectos: alta, edición y tablero de previsto frente a real. La regla vive en `app/servicios/proyectos.py`."""
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ..servicios import contable, proyectos
from ..web import (
    NO_ENCONTRADO,
    _ctx,
    _yo,
    plantillas,
)

router = APIRouter()


# ---------- proyectos: se crean y editan desde la plataforma ----------
@router.get("/admin/proyectos", response_class=HTMLResponse)
def proyectos_admin(request: Request, aviso: str = ""):
    return plantillas.TemplateResponse(request, "proyectos_admin.html", _ctx(aviso=aviso[:200], lista=proyectos.lista(_yo())[::-1]))


@router.post("/admin/proyectos")
def proyecto_crear(nombre: str = Form(""), cliente: str = Form(""), ciudad: str = Form(""), fecha_inicio: str = Form(""),
                   fecha_fin: str = Form(""), moneda: str = Form("USD")):
    try:
        datos = proyectos.validar(nombre, cliente, ciudad, fecha_inicio, fecha_fin, moneda)
    except proyectos.DatosInvalidos as e:
        return RedirectResponse(f"/admin/proyectos?aviso={quote(str(e))}", status_code=303)
    proyectos.crear(datos, _yo())
    return RedirectResponse("/admin/proyectos?aviso=Proyecto+creado.", status_code=303)


@router.post("/admin/proyectos/{pid}")
def proyecto_editar(pid: int, nombre: str = Form(""), cliente: str = Form(""), ciudad: str = Form(""), fecha_inicio: str = Form(""),
                    fecha_fin: str = Form(""), moneda: str = Form("USD")):
    if not proyectos.existe(pid):
        return NO_ENCONTRADO
    try:
        datos = proyectos.validar(nombre, cliente, ciudad, fecha_inicio, fecha_fin, moneda)
    except proyectos.DatosInvalidos as e:
        return RedirectResponse(f"/admin/proyectos?aviso={quote(str(e))}", status_code=303)
    proyectos.editar(pid, datos, _yo())
    return RedirectResponse("/admin/proyectos?aviso=Proyecto+actualizado.", status_code=303)


# ---------- tablero por proyecto ----------
@router.get("/proyectos/{pid}", response_class=HTMLResponse)
def proyecto(request: Request, pid: int):
    p = proyectos.uno(pid) if proyectos.visible(_yo(), pid) else None
    if not p:
        return NO_ENCONTRADO
    c = proyectos.comparacion(pid)
    return plantillas.TemplateResponse(request, "proyecto.html", _ctx(
        p=p, filas=c["filas"], faltantes=c["faltantes"], decisiones=c["viajes"], viajes_proyecto=c["viajes"], mes=contable.mes_en_curso(),
        tot_previsto=c["tot_previsto"], tot_real=c["tot_real"], pendientes=proyectos.en_revision(pid), gastos=proyectos.gastos(pid)))


@router.get("/proyectos/{pid}/exportar.csv")
def proyecto_exportar(pid: int):
    if not proyectos.visible(_yo(), pid):
        return NO_ENCONTRADO
    return Response(proyectos.csv_gastos(pid), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="gastos_proyecto_{pid}.csv"'})
