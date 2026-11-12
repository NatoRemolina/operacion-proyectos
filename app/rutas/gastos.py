"""Reto 2: cargar soportes, ver gastos y revisarlos."""
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .. import config, db
from ..servicios import acceso, almacen, eventos, justificaciones, telegram, validacion, viajes
from ..servicios import gastos as soportes
from ..web import (
    NO_ENCONTRADO,
    SOLO_ADMIN,
    _ctx,
    _gasto_propio,
    _indicadores,
    _viajes_para_cargar,
    _yo,
    plantillas,
)

router = APIRouter()

MENU = [{"texto": "Cargar gasto", "href": "/gastos/cargar", "orden": 40},
        {"texto": "Gastos", "href": "/gastos", "orden": 50, "contador": "gastos"}]


# ---------- reto 2: gastos ----------
SoporteRechazado = soportes.SoporteRechazado
_nombre_visible = soportes.nombre_visible


def _procesar(contenido: bytes, nombre: str, canal: str, proyecto_id: int | None, viajero_id: int | None, viaje_id: int = 0) -> int:
    """Registra un soporte a nombre de quien tiene la sesión. Sin viaje indicado, se busca el que le corresponde hoy."""
    yo = _yo()
    viaje, _ = viajes.resolver_para_gasto(yo, viaje_id or None) if yo else (None, [])
    return soportes.registrar(contenido, nombre, canal, yo or None, viaje, proyecto_id, viajero_id)


@router.get("/gastos", response_class=HTMLResponse)
def gastos(request: Request, estado: str = "", aviso: str = ""):
    donde, p = acceso.alcance(_yo(), "g")
    filtro = " and g.estado=:e" if estado else ""
    filas = db.todos(f"""select g.*, p.nombre proyecto, v.nombre viajero, d.nombre archivo, d.canal from gastos g
                         left join proyectos p on p.id=g.proyecto_id left join viajeros v on v.id=g.viajero_id
                         left join documentos d on d.id=g.documento_id where {donde}{filtro} order by g.id desc""", e=estado, **p)
    return plantillas.TemplateResponse(request, "gastos.html", _ctx(
        gastos=filas, estado=estado, ind=_indicadores() if acceso.es_admin(_yo()) else None, aviso=aviso[:300]))


@router.get("/gastos/cargar", response_class=HTMLResponse)
def gastos_cargar(request: Request):
    ejemplos = sorted(p.name for p in config.DIR_EJEMPLOS.iterdir() if p.suffix in (".png", ".pdf", ".jpg"))
    correos = sorted(p.name for p in config.DIR_EJEMPLOS.glob("*.eml"))
    elegido, _ = viajes.resolver_para_gasto(_yo())
    return plantillas.TemplateResponse(request, "cargar.html", _ctx(
        ejemplos=ejemplos, correos=correos, mis_viajes=_viajes_para_cargar(), elegido=elegido))


@router.post("/gastos/cargar")
def gastos_cargar_enviar(request: Request, archivos: list[UploadFile], proyecto_id: int = Form(0), viajero_id: int = Form(0),
                         canal: str = Form("web"), viaje_id: int = Form(0), justificacion: str = Form("")):
    """Función normal (no asíncrona): la lectura con el modelo corre en un hilo y no detiene al resto del servidor."""
    canal = canal if canal in ("web", "celular") else "web"
    hechos, errores = [], []
    for a in archivos[:config.MAX_ARCHIVOS_POR_CARGA]:
        try:
            gid = _procesar(a.file.read(config.MAX_BYTES_SOPORTE + 1), a.filename or "soporte", canal,
                            proyecto_id or None, viajero_id or None, viaje_id)
            hechos.append(gid)
            if justificacion.strip() and _yo():
                try:
                    justificaciones.registrar(gid, _yo(), canal, justificacion)
                except justificaciones.JustificacionRechazada:
                    pass  # demasiado corta: el gasto queda y se puede justificar desde su detalle
        except SoporteRechazado as e:
            errores.append(f"{_nombre_visible(a.filename or '')}: {e}")
    if len(archivos) > config.MAX_ARCHIVOS_POR_CARGA:
        errores.append(f"Solo se procesan {config.MAX_ARCHIVOS_POR_CARGA} archivos por envío.")
    if request.headers.get("x-envio") == "pagina":  # la página envía un archivo por petición y muestra el avance
        return JSONResponse({"gastos": hechos, "errores": errores}, status_code=200 if hechos or not errores else 400)
    destino = "/gastos" + (f"?aviso={quote(' '.join(errores)[:300])}" if errores else "")
    return RedirectResponse(destino, status_code=303)


@router.post("/gastos/ejemplos")
def gastos_ejemplos(nombres: list[str] = Form([]), proyecto_id: int = Form(0), viajero_id: int = Form(0), canal: str = Form("web"),
                    viaje_id: int = Form(0)):
    """Procesa soportes de la carpeta de ejemplos; con canal 'correo' simula la lectura de un buzón."""
    for n in nombres:
        archivo = config.DIR_EJEMPLOS / Path(n).name
        if archivo.is_file():
            try:
                _procesar(archivo.read_bytes(), archivo.name, "correo" if canal == "correo" else canal,
                          proyecto_id or None, viajero_id or None, viaje_id)
            except SoporteRechazado:
                continue
    return RedirectResponse("/gastos", status_code=303)


@router.get("/gastos/{gid}", response_class=HTMLResponse)
def gasto(request: Request, gid: int, aviso: str = ""):
    g = db.uno("""select g.*, d.nombre archivo, d.mime, d.canal from gastos g
                  left join documentos d on d.id=g.documento_id where g.id=:i""", i=gid) if _gasto_propio(gid) else None
    if not g:
        return NO_ENCONTRADO
    return plantillas.TemplateResponse(request, "gasto.html", _ctx(
        g=g, alertas=db.de_json(g["alertas"], []), el_viaje=viajes.uno(g["viaje_id"]), aviso=aviso[:300],
        propio=viajes.gasto_propio_de(g, _yo()), no_autorrevisar=viajes.NO_AUTORREVISAR,
        hay_otro_admin=acceso.es_admin(_yo()) and viajes.hay_otro_admin(_yo()),
        justifs=justificaciones.de_gasto(gid), puede_justificar=justificaciones.puede_justificar(_yo(), g),
        mis_viajes=viajes.lista("v.estado<>'rechazado'") if acceso.es_admin(_yo()) else [],
        eventos=db.todos("select * from eventos where entidad='gasto' and entidad_id=:i order by id", i=gid)))


@router.get("/gastos/{gid}/soporte")
def gasto_soporte(gid: int):
    if not _gasto_propio(gid):
        return NO_ENCONTRADO
    d = db.uno("select d.* from documentos d join gastos g on g.documento_id=d.id where g.id=:i", i=gid)
    contenido = almacen.leer(d["ruta"]) if d else None
    if contenido is None:
        return Response("No disponible", status_code=404)
    # Solo se sirven en línea tipos inertes; el resto se muestra como texto. El contenido se aísla del resto de la página.
    mime = d["mime"] if d["mime"] in ("image/jpeg", "image/png", "image/webp", "application/pdf") else "text/plain; charset=utf-8"
    return Response(contenido, media_type=mime, headers={
        "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "Cache-Control": "private, no-store"})


@router.post("/gastos/{gid}/justificacion")
def gasto_justificar(gid: int, texto: str = Form(""), audio: UploadFile | None = None):
    """La persona explica para qué fue el gasto, por escrito o con una nota de voz."""
    g = db.uno("select id, usuario_id, viajero_id, proyecto_id from gastos where id=:i", i=gid)
    if not g or not acceso.puede_ver(_yo(), g):
        return NO_ENCONTRADO
    if not justificaciones.puede_justificar(_yo(), g):
        return RedirectResponse(f"/gastos/{gid}?aviso={quote('Solo quien hizo el gasto puede justificarlo.')}#justificacion", status_code=303)
    contenido = audio.file.read(config.MAX_BYTES_SOPORTE + 1) if audio and audio.filename else None
    try:
        justificaciones.registrar(gid, _yo(), "web", texto, contenido, audio.filename if contenido else "nota_de_voz")
    except justificaciones.JustificacionRechazada as e:
        return RedirectResponse(f"/gastos/{gid}?aviso={quote(str(e))}#justificacion", status_code=303)
    return RedirectResponse(f"/gastos/{gid}#justificacion", status_code=303)


@router.get("/gastos/{gid}/justificacion/{jid}/audio")
def gasto_justificacion_audio(gid: int, jid: int):
    if not _gasto_propio(gid):
        return NO_ENCONTRADO
    d = db.uno("""select d.ruta, d.mime from justificaciones j join documentos d on d.id=j.documento_id
                  where j.id=:j and j.gasto_id=:g""", j=jid, g=gid)
    contenido = almacen.leer(d["ruta"]) if d and d["ruta"] else None
    if contenido is None:
        return Response("No disponible", status_code=404)
    return Response(contenido, media_type=d["mime"] if (d["mime"] or "").startswith("audio/") else "application/octet-stream",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


def _numero(texto: str):
    """Acepta 1234.56, 1234,56, 1.234,56 y 1,234.56. Un valor ilegible queda vacío en vez de romper la página."""
    t = re.sub(r"[^0-9.,-]", "", texto or "")
    if not t:
        return None
    if "," in t and "." in t:  # el último separador es el decimal
        decimal = "," if t.rfind(",") > t.rfind(".") else "."
        t = t.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif t.count(",") + t.count(".") == 1:
        sep = "," if "," in t else "."
        entero, _, cola = t.partition(sep)
        t = entero + cola if len(cola) == 3 and entero not in ("", "0", "-") else entero + "." + cola  # 45.000 son miles
    else:
        t = t.replace(",", "").replace(".", "") if t.count(",") > 1 or t.count(".") > 1 else t
    try:
        return round(float(t), 2)
    except ValueError:
        return None


@router.post("/gastos/{gid}")
def gasto_guardar(gid: int, accion: str = Form(...), proyecto_id: int = Form(0), viajero_id: int = Form(0),
                  comercio: str = Form(""), fecha: str = Form(""), categoria: str = Form("otros"),
                  subtotal: str = Form(""), impuesto: str = Form(""), propina: str = Form(""), total: str = Form(""),
                  moneda: str = Form(""), metodo_pago: str = Form(""), canal_reserva: str = Form(""), revisor: str = Form(""),
                  motivo_excepcion: str = Form(""), viaje_id: int = Form(-1)):
    # Revisar es tarea de administración, y nadie revisa su propio gasto (la regla vive en el servicio)
    if not acceso.es_admin(_yo()):
        return SOLO_ADMIN
    previo = db.uno("select id, viaje_id, viajero_id, usuario_id from gastos where id=:i", i=gid)
    if not previo:
        return NO_ENCONTRADO
    # El formulario puede cambiar el viaje; si no lo trae, se conserva el que tenía
    el_viaje = viajes.uno(previo["viaje_id"] if viaje_id < 0 else viaje_id)
    if el_viaje:
        proyecto_id, viajero_id = el_viaje["proyecto_id"] or proyecto_id, el_viaje["viajero_id"] or viajero_id
    despues = previo if accion == "rechazar" else \
        {"usuario_id": previo["usuario_id"], "viajero_id": viajero_id or None, "viaje_id": el_viaje["id"] if el_viaje else None}
    impedido = viajes.revision_permitida(gid, previo, despues, _yo(), accion)
    if impedido:
        return RedirectResponse(f"/gastos/{gid}?aviso={quote(impedido)}", status_code=303)
    revisor = _yo()["nombre"]
    if accion == "rechazar":
        db.actualizar("gastos", gid, estado="rechazado", revisado_por=_yo()["id"])
        eventos.registrar("gasto", gid, "rechazado en revisión", "", revisor or "revisor")
        telegram.avisar(previo["usuario_id"], f"Tu gasto #{gid} fue rechazado en la revisión.")
        return RedirectResponse("/gastos?estado=revision", status_code=303)
    campos ={"comercio": comercio.strip() or None, "fecha": fecha or None, "categoria": categoria,
              "subtotal": _numero(subtotal), "impuesto": _numero(impuesto), "propina": _numero(propina),
              "total": _numero(total), "moneda": moneda.upper().strip() or None,
              "metodo_pago": metodo_pago.strip() or None, "canal_reserva": canal_reserva.strip() or None}
    # Aprobar relee lo gastado con los viajes bloqueados: dos aprobaciones a la vez no gastan el mismo saldo
    with db.transaccion() as c:
        for vid in sorted({previo["viaje_id"], el_viaje["id"] if el_viaje else None} - {None}):
            fila = db.bloquear_viaje(c, vid)
            if el_viaje and fila and vid == el_viaje["id"]:
                el_viaje = {**el_viaje, **fila}
        proyecto = db.uno("select * from proyectos where id=:i", i=proyecto_id) if proyecto_id else None
        # Una persona confirmó los datos: la confianza de lectura deja de ser el criterio
        r = validacion.revisar({**campos, "confianza": 1.0, "dudas": []}, proyecto, gid, el_viaje)
        estado = "aprobado" if r["estado"] == "aprobado_auto" else "revision"
        # Excepción justificada: una persona responde por un gasto que las reglas no dejan pasar (dos peajes iguales el mismo día)
        excepcion = accion == "excepcion" and estado == "revision"
        if excepcion and len(motivo_excepcion.strip()) < 8:
            r["alertas"].append("Para aprobar con excepción hay que escribir el motivo.")
        elif excepcion and campos["total"] is not None and campos["moneda"] and r["total_usd"] is not None:
            estado = "aprobado"
            r["alertas"].append(f"Aprobado con excepción: {motivo_excepcion.strip()[:200]}")
        db.actualizar("gastos", gid, **campos, proyecto_id=proyecto_id or None, viajero_id=viajero_id or None,
                      viaje_id=el_viaje["id"] if el_viaje else None, estado=estado, alertas=r["alertas"], motivos=r["motivos"], total_usd=r["total_usd"], revisado_por=_yo()["id"])
        paso = "aprobado con excepción" if excepcion and estado == "aprobado" else \
            "corregido y aprobado" if estado == "aprobado" else "corregido, sigue en revisión"
        eventos.registrar("gasto", gid, paso, " ".join(r["alertas"]), revisor or "revisor")
    if estado == "aprobado":
        telegram.avisar(previo["usuario_id"], f"Tu gasto #{gid} ({campos['comercio'] or 'sin comercio'}, "
                                              f"{campos['total'] or 0:.2f} {campos['moneda'] or ''}) fue aprobado.")
    return RedirectResponse("/gastos" if estado == "aprobado" else f"/gastos/{gid}", status_code=303)
