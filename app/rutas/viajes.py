"""El viaje: detalle, evidencias, aprobación de presupuesto y tablero."""
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .. import db
from ..servicios import acceso, almacen, monitoreo_vuelos, viajes
from ..web import (
    NO_ENCONTRADO,
    _ctx,
    _yo,
    plantillas,
)

router = APIRouter()

MENU = [{"texto": "Viajes", "href": "/admin/viajes", "orden": 30, "rol": "admin", "contador": "viajes", "prefijo": "/viaje/"},
        {"texto": "Mis viajes", "href": "/mi-cuenta", "orden": 30, "rol": "no_admin", "prefijo": "/viaje/"}]


def _viaje_visible(vid: int) -> dict | None:
    v = viajes.resumen(vid)
    return v if v and acceso.puede_ver(_yo(), v) else None


@router.get("/viaje/{vid}", response_class=HTMLResponse)
def viaje_detalle(request: Request, vid: int, aviso: str = ""):
    v = _viaje_visible(vid)
    if not v:
        return NO_ENCONTRADO
    return plantillas.TemplateResponse(request, "viaje_detalle.html", _ctx(
        v=v, aviso=aviso[:300], detalle=db.de_json(v["presupuesto_detalle"], []), propio=viajes.es_propio_de(v, _yo()),
        hay_otro_admin=acceso.es_admin(_yo()) and viajes.hay_otro_admin(_yo()),
        precio_por_confirmar=viajes.precio_por_confirmar(v["id"]) if v["estado"] == "pendiente_aprobacion" else None,
        gastos=db.todos("""select g.*, d.canal, d.nombre archivo from gastos g left join documentos d on d.id=g.documento_id
                           where g.viaje_id=:i order by g.id desc""", i=vid),
        evidencias=db.todos("select * from documentos where viaje_id=:i and tipo in ('audio','nota') order by id desc", i=vid),
        eventos=db.todos("select e.*, u.nombre usuario from eventos e left join usuarios u on u.id=e.usuario_id "
                         "where e.entidad='viaje' and e.entidad_id=:i order by e.id", i=vid)))


@router.get("/viaje/{vid}/evidencia/{doc}")
def viaje_evidencia(vid: int, doc: int):
    d = db.uno("select * from documentos where id=:d and viaje_id=:v and tipo='audio'", d=doc, v=vid) if _viaje_visible(vid) else None
    contenido = almacen.leer(d["ruta"]) if d and d["ruta"] else None
    if contenido is None:
        return NO_ENCONTRADO
    return Response(contenido, media_type=d["mime"], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


CAMPOS_VUELO = ("id", "viaje_id", "codigo", "titular", "sentido", "orden", "aerolinea", "numero", "fecha", "desde", "hasta",
                "sale_programada", "llega_programada", "llega_estimada", "estado", "estado_texto", "retraso", "retraso_salida",
                "retraso_llegada", "terminal", "puerta", "consultas", "actualizado", "hace_min", "llegar_antes", "en_destino",
                "no_llega", "omitida", "ultima_consulta", "aviso")


@router.get("/admin/viajes/vuelos", tags=["api"])
def viajes_vuelos(fecha: str = ""):
    """Tramos para el tablero (los de ese día; sin fecha, los de hoy y los de ayer o mañana que están en su ventana).
    Lo pide el tablero cada 15 s: cada tramo se consulta solo dentro de su ventana, fuera de la caché y de los topes."""
    ahora, reglas = monitoreo_vuelos.momento_actual(), monitoreo_vuelos.reglas()
    salida = []
    for t in monitoreo_vuelos.tablero(monitoreo_vuelos.fecha_valida(fecha), ahora, reglas):
        nuevo = monitoreo_vuelos.consultar(t["id"], ahora, reglas_=reglas)
        t = monitoreo_vuelos.completar({**t, **{k: v for k, v in nuevo.items() if k in t}}, ahora)
        salida.append({c: t.get(c) for c in CAMPOS_VUELO})
    return salida


@router.post("/admin/vuelos/{tramo_id}/actualizar")
def vuelo_actualizar(tramo_id: int, fecha: str = Form("")):
    """«Actualizar ahora»: salta la caché, nunca la ventana ni los topes."""
    t = db.uno("select fecha, numero from tramos_vuelo where id=:i", i=tramo_id)
    if not t:
        return NO_ENCONTRADO
    r = monitoreo_vuelos.consultar(tramo_id, forzar=True)
    mensaje = f"{t['numero']}: estado actualizado." if r["consultado"] else f"{t['numero']}: no se consultó ({r['motivo']})."
    dia = monitoreo_vuelos.fecha_valida(fecha)
    return RedirectResponse(f"/admin/viajes?{'fecha=' + dia + '&' if dia else ''}aviso={quote(mensaje)}#vuelos", status_code=303)


@router.get("/admin/viajes", response_class=HTMLResponse)
def viajes_admin(request: Request, aviso: str = "", fecha: str = ""):
    todos_ = viajes.lista()
    for v in todos_:   # lo propio no se aprueba aquí: lo hace otra persona de administración
        v["propio"] = viajes.es_propio_de(v, _yo())
        v["precio_por_confirmar"] = viajes.precio_por_confirmar(v["id"]) if v["estado"] == "pendiente_aprobacion" else None
    fecha = monitoreo_vuelos.fecha_valida(fecha)
    return plantillas.TemplateResponse(request, "viajes_admin.html", _ctx(
        hay_otro_admin=viajes.hay_otro_admin(_yo()), fecha=fecha, hoy=monitoreo_vuelos.hoy(),
        vuelos=monitoreo_vuelos.tablero(fecha),
        aviso=aviso[:300], pendientes=[v for v in todos_ if v["estado"] == "pendiente_aprobacion"],
        abiertos=[v for v in todos_ if v["estado"] == "aprobado"],
        otros=[v for v in todos_ if v["estado"] in ("rechazado", "cerrado")]))


@router.post("/admin/viajes/{vid}")
def viaje_estado(vid: int, accion: str = Form(...), motivo: str = Form(""), volver: str = Form(""),
                 confirmar_precio: str = Form("")):
    _, mensaje = viajes.cambiar_estado(vid, accion, motivo, _yo(), confirmar_precio == "1")
    destino = f"/viaje/{vid}" if volver == "detalle" else "/admin/viajes"
    return RedirectResponse(f"{destino}?aviso={quote(mensaje)}", status_code=303)


@router.get("/api/viajes", tags=["api"])
def api_viajes(estado: str = ""):
    """Viajes con su ejecución de presupuesto. Lo consulta el tablero cada pocos segundos."""
    campos = ("id", "codigo", "estado", "estado_texto", "en_curso", "titular", "proyecto", "origen", "destino", "ida", "regreso",
              "presupuesto_usd", "gastado", "en_revision", "pct", "n_gastos", "ultimo_gasto")
    filas = viajes.lista("v.estado=:e", e=estado) if estado in viajes.ESTADOS else viajes.lista()
    return [{c: v.get(c) for c in campos} for v in filas]
