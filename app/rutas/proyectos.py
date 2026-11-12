"""Proyectos: alta, edición y tablero de previsto frente a real."""
import re
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .. import config, db
from ..servicios import acceso, eventos, viajes
from ..web import (
    NO_ENCONTRADO,
    _ctx,
    _yo,
    plantillas,
)

router = APIRouter()


# ---------- proyectos: se crean y editan desde la plataforma ----------
def _proyecto_valido(nombre: str, cliente: str, ciudad: str, fecha_inicio: str, fecha_fin: str, moneda: str) -> tuple[dict | None, str]:
    nombre, moneda = nombre.strip()[:120], moneda.strip().upper()[:3]
    if len(nombre) < 3:
        return None, "El proyecto necesita un nombre."
    try:
        inicio, fin = date.fromisoformat(fecha_inicio), date.fromisoformat(fecha_fin)
    except ValueError:
        return None, "Las fechas del proyecto no son válidas."
    if fin < inicio:
        return None, "La fecha final no puede ser anterior a la inicial."
    if not re.fullmatch(r"[A-Z]{3}", moneda):
        return None, "La moneda es un código de tres letras, como USD o EUR."
    return {"nombre": nombre, "cliente": cliente.strip()[:120] or None, "ciudad": ciudad.strip()[:80] or None,
            "fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat(), "moneda": moneda}, ""


@router.get("/admin/proyectos", response_class=HTMLResponse)
def proyectos_admin(request: Request, aviso: str = ""):
    return plantillas.TemplateResponse(request, "proyectos_admin.html", _ctx(
        aviso=aviso[:200],
        lista=db.todos("""select p.*, (select count(*) from viajes v where v.proyecto_id=p.id) viajes,
                          (select count(*) from gastos g where g.proyecto_id=p.id) gastos from proyectos p order by p.id""")))


@router.post("/admin/proyectos")
def proyecto_crear(nombre: str = Form(""), cliente: str = Form(""), ciudad: str = Form(""), fecha_inicio: str = Form(""),
                   fecha_fin: str = Form(""), moneda: str = Form("USD")):
    datos, error = _proyecto_valido(nombre, cliente, ciudad, fecha_inicio, fecha_fin, moneda)
    if not datos:
        return RedirectResponse(f"/admin/proyectos?aviso={quote(error)}", status_code=303)
    pid = db.insertar("proyectos", **datos)
    eventos.registrar("proyecto", pid, "proyecto creado", f"{datos['nombre']} · {datos['fecha_inicio']} a {datos['fecha_fin']}", _yo()["nombre"])
    return RedirectResponse("/admin/proyectos?aviso=Proyecto+creado.", status_code=303)


@router.post("/admin/proyectos/{pid}")
def proyecto_editar(pid: int, nombre: str = Form(""), cliente: str = Form(""), ciudad: str = Form(""), fecha_inicio: str = Form(""),
                    fecha_fin: str = Form(""), moneda: str = Form("USD")):
    if not db.uno("select id from proyectos where id=:i", i=pid):
        return NO_ENCONTRADO
    datos, error = _proyecto_valido(nombre, cliente, ciudad, fecha_inicio, fecha_fin, moneda)
    if not datos:
        return RedirectResponse(f"/admin/proyectos?aviso={quote(error)}", status_code=303)
    db.actualizar("proyectos", pid, **datos)
    eventos.registrar("proyecto", pid, "proyecto editado", f"{datos['nombre']} · {datos['fecha_inicio']} a {datos['fecha_fin']}", _yo()["nombre"])
    return RedirectResponse("/admin/proyectos?aviso=Proyecto+actualizado.", status_code=303)


# ---------- tablero por proyecto ----------
def _proyecto_visible(pid: int) -> bool:
    """Administración ve todos; el gestor, los que gestiona; nadie más (responde como si no existiera)."""
    return acceso.es_admin(_yo()) or pid in acceso.proyectos_de(_yo())


@router.get("/proyectos/{pid}", response_class=HTMLResponse)
def proyecto(request: Request, pid: int):
    p = db.uno("select * from proyectos where id=:i", i=pid) if _proyecto_visible(pid) else None
    if not p:
        return NO_ENCONTRADO
    real = {r["categoria"]: r["t"] for r in db.todos(
        "select categoria, sum(total_usd) t from gastos where proyecto_id=:i and estado in ('aprobado','aprobado_auto') group by categoria", i=pid)}
    # El previsto es el presupuesto de los viajes del proyecto: la misma cifra que aprueba administración
    del_proyecto = viajes.lista("v.proyecto_id=:i and v.estado<>'rechazado'", i=pid)
    previsto: dict[str, float] = {}
    for v in del_proyecto:
        for l in db.de_json(v["presupuesto_detalle"], []) or []:
            previsto[l["grupo"]] = previsto.get(l["grupo"], 0) + l["valor"]
    compras = ("vuelo", "hotel", "alquiler_carro")   # se compran por separado; lo demás se cubre con los viáticos
    filas = [{"clave": c, "nombre": config.CATEGORIAS[c], "previsto": round(previsto.get(c, 0), 2), "real": round(real.get(c) or 0, 2)}
             for c in compras if previsto.get(c) or real.get(c)]
    en_destino = round(sum(t or 0 for c, t in real.items() if c not in compras), 2)
    if previsto.get("viaticos") or en_destino:
        filas.append({"clave": "viaticos", "nombre": "Viáticos y gastos en destino", "previsto": round(previsto.get("viaticos", 0), 2),
                      "real": en_destino})
    faltantes = [f["nombre"] for f in filas if f["previsto"] and not f["real"]]
    return plantillas.TemplateResponse(request, "proyecto.html", _ctx(
        p=p, filas=filas, faltantes=faltantes, decisiones=del_proyecto, viajes_proyecto=del_proyecto,
        tot_previsto=round(sum(f["previsto"] for f in filas), 2), tot_real=round(sum(f["real"] for f in filas), 2),
        pendientes=db.uno("select count(*) n from gastos where proyecto_id=:i and estado='revision'", i=pid)["n"],
        gastos=db.todos("""select g.*, v.nombre viajero from gastos g left join viajeros v on v.id=g.viajero_id
                           where g.proyecto_id=:i order by g.fecha""", i=pid)))


@router.get("/proyectos/{pid}/exportar.csv")
def proyecto_exportar(pid: int):
    if not _proyecto_visible(pid):
        return NO_ENCONTRADO
    filas = db.todos("select id,fecha,comercio,categoria,total,moneda,total_usd,estado,metodo_pago,origen_dato from gastos where proyecto_id=:i order by fecha", i=pid)
    columnas = ["id", "fecha", "comercio", "categoria", "total", "moneda", "total_usd", "estado", "metodo_pago", "origen_dato"]
    def celda(v):  # texto que empieza como fórmula se neutraliza para las hojas de cálculo
        t = str(v if v is not None else "").replace('"', "'")
        return '"' + ("'" + t if t[:1] in "=+-@" and not isinstance(v, int | float) else t) + '"'
    lineas = [",".join(columnas)] + [",".join(celda(f[c]) for c in columnas) for f in filas]
    return Response("\n".join(lineas), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="gastos_proyecto_{pid}.csv"'})
