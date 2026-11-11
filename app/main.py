"""Rutas de la aplicación: viajes (reto 1), gastos (reto 2), tablero y flujo de la información."""
import hashlib
import hmac
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from datos.semilla import sembrar

from . import aeropuertos, config, db
from .servicios import agente, almacen, analitica, costo, eventos, extraccion, modelo, precios, validacion

AQUI = Path(__file__).parent
app = FastAPI(title="Operación de proyectos")
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
plantillas = Jinja2Templates(directory=AQUI / "templates")
plantillas.env.globals.update(modo=config.modo, categorias=config.CATEGORIAS)
plantillas.env.filters["dinero"] = lambda v, m="USD": "—" if v is None else f"{v:,.2f} {m}"
plantillas.env.filters["json"] = db.de_json

# En local la base se prepara sola; en un despliegue la migración es un paso aparte (python -m datos.semilla)
if config.LOCAL:
    sembrar()


# ---------- acceso ----------
def _firma() -> str:
    return hmac.new(config.APP_CLAVE.encode(), b"sesion", hashlib.sha256).hexdigest()


@app.middleware("http")
async def acceso(request: Request, call_next):
    libre = request.url.path.startswith(("/static", "/entrar", "/salud"))
    if config.APP_CLAVE and not libre and request.cookies.get("sesion") != _firma():
        return RedirectResponse("/entrar", status_code=303)
    return await call_next(request)


@app.get("/salud")
def salud():
    return {"estado": "ok"}


@app.get("/entrar", response_class=HTMLResponse)
def entrar(request: Request, error: int = 0):
    return plantillas.TemplateResponse(request, "entrar.html", {"error": error})


@app.post("/entrar")
def entrar_enviar(clave: str = Form("")):
    if config.APP_CLAVE and hmac.compare_digest(clave.encode(), config.APP_CLAVE.encode()):
        r = RedirectResponse("/", status_code=303)
        r.set_cookie("sesion", _firma(), httponly=True, samesite="lax", secure=not config.LOCAL, max_age=12 * 3600)
        return r
    return RedirectResponse("/entrar?error=1", status_code=303)


# ---------- utilidades ----------
def _nombre(request: Request) -> str:
    """Nombre de quien usa la aplicación, recordado en el navegador."""
    return unquote(request.cookies.get("nombre", ""))


def _recordar(respuesta, nombre: str):
    if nombre:
        respuesta.set_cookie("nombre", quote(nombre), max_age=90 * 86400, samesite="lax")
    return respuesta


def _ctx(**extra):
    return {"proyectos": db.todos_cache("select * from proyectos order by id"),
            "viajeros": db.todos_cache("select * from viajeros order by id"), **extra}


def _indicadores() -> dict:
    g = db.uno("""select count(*) n,
                  sum(case when estado='aprobado_auto' then 1 else 0 end) auto,
                  sum(case when estado='revision' then 1 else 0 end) revision,
                  sum(case when estado in ('aprobado','aprobado_auto') then total_usd else 0 end) real_usd
                  from gastos""")
    d = db.uno("select count(*) n, coalesce(sum(total),0) previsto from decisiones")
    ext = db.uno("select count(*) n from eventos where paso='consulta externa'")
    n = g["n"] or 0
    return {"gastos": n, "auto": g["auto"] or 0, "revision": g["revision"] or 0,
            "pct_auto": round(100 * (g["auto"] or 0) / n) if n else 0,
            "real": g["real_usd"] or 0, "decisiones": d["n"], "previsto": d["previsto"], "externas": ext["n"]}


# ---------- inicio ----------
@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    return plantillas.TemplateResponse(request, "inicio.html", _ctx(
        ind=_indicadores(),
        solicitudes=db.todos("""select s.*, p.nombre proyecto, v.nombre viajero from solicitudes s
                                left join proyectos p on p.id=s.proyecto_id left join viajeros v on v.id=s.viajero_id
                                order by s.id desc limit 15""")))


# ---------- reto 1: viajes ----------
@app.get("/viajes/nuevo", response_class=HTMLResponse)
def viaje_nuevo(request: Request, error: str = ""):
    return plantillas.TemplateResponse(request, "viaje_nuevo.html", _ctx(
        aeropuertos=aeropuertos.AEROPUERTOS, error=error, mi_nombre=_nombre(request)))


@app.post("/viajes")
def viaje_crear(proyecto_id: int = Form(...), viajero_id: int = Form(...), origen: str = Form(...),
                destino: str = Form(...), ciudad: str = Form(""), ida: str = Form(...), regreso: str = Form(...),
                llegar_antes: str = Form(""), baterias_n: int = Form(0), baterias_wh: float = Form(0),
                maleta: str = Form(""), prob_cambio: float = Form(0), carro_dia: float = Form(0),
                solicitado_por: str = Form(""), viajero_nuevo: str = Form("")):
    desde, hacia = aeropuertos.resolver(origen), aeropuertos.resolver(destino)
    if not desde or not hacia:
        malo = origen if not desde else destino
        return RedirectResponse(f"/viajes/nuevo?error=No+reconozco+%22{quote(malo[:40])}%22.+Elige+una+ciudad+de+la+lista+o+escribe+el+c%C3%B3digo+de+tres+letras+del+aeropuerto.", status_code=303)
    try:
        f_ida, f_regreso = date.fromisoformat(ida), date.fromisoformat(regreso)
    except ValueError:
        return RedirectResponse("/viajes/nuevo?error=Las+fechas+no+son+v%C3%A1lidas.", status_code=303)
    if f_regreso <= f_ida:
        return RedirectResponse("/viajes/nuevo?error=El+regreso+debe+ser+posterior+a+la+ida.", status_code=303)
    ida, regreso = f_ida.isoformat(), f_regreso.isoformat()
    # La hora límite siempre se refiere al día de llegada: se conserva la hora y se ata a la fecha de ida
    hora = llegar_antes[11:16] if len(llegar_antes) >= 16 else ""
    llegar_antes = f"{ida}T{hora}" if re.fullmatch(r"\d\d:\d\d", hora) else ""
    prob_cambio, baterias_n = min(max(prob_cambio, 0), 100), max(baterias_n, 0)
    origen, destino, ciudad = desde[0], hacia[0], ciudad.strip() or hacia[1]
    solicitado_por, viajero_nuevo = solicitado_por.strip()[:80], viajero_nuevo.strip()[:80]
    if not solicitado_por:
        return RedirectResponse("/viajes/nuevo?error=Escribe+tu+nombre+para+registrar+la+consulta.", status_code=303)
    if viajero_nuevo:
        existente = db.uno("select id from viajeros where lower(nombre)=lower(:n)", n=viajero_nuevo)
        viajero_id = existente["id"] if existente else db.insertar("viajeros", nombre=viajero_nuevo, base=desde[1], rol="Viajero")
    sid = db.insertar("solicitudes", proyecto_id=proyecto_id, viajero_id=viajero_id, origen=origen,
                      destino=destino, ciudad=ciudad, ida=ida, regreso=regreso,
                      llegar_antes=llegar_antes or None, baterias_n=baterias_n, baterias_wh=baterias_wh,
                      maleta=1 if maleta else 0, prob_cambio=prob_cambio / 100, carro_dia=carro_dia,
                      estado="buscando", creado=db.ahora(), solicitado_por=solicitado_por)
    eventos.registrar("solicitud", sid, "solicitud recibida", f"{origen}-{destino} {ida} a {regreso}", f"formulario · {solicitado_por}")
    sol = db.uno("select * from solicitudes where id=:i", i=sid)
    vuelos, origen_v, _ = precios.buscar_vuelos(sol["origen"], sol["destino"], ida, regreso, sid)
    for v in vuelos:
        tarifas, origen_t = precios.tarifas_de_vuelo(sol["origen"], sol["destino"], ida, regreso, v, sid)
        db.insertar("opciones", solicitud_id=sid, tipo="vuelo", titulo=" + ".join(v["numeros"]), precio=v["precio"],
                    moneda="USD", datos=v, tarifas={"lista": tarifas, "origen": origen_t}, origen_dato=origen_v, capturado=db.ahora())
    hoteles, origen_h = precios.buscar_hoteles(sol["ciudad"], ida, regreso, sid)
    for h in hoteles[:12]:
        db.insertar("opciones", solicitud_id=sid, tipo="hotel", titulo=h["nombre"], precio=h["total"], moneda="USD",
                    datos=h, tarifas=None, origen_dato=origen_h, capturado=db.ahora())
    db.actualizar("solicitudes", sid, estado="comparando")
    eventos.registrar("solicitud", sid, "opciones guardadas", f"{len(vuelos)} vuelos y {min(len(hoteles), 12)} hoteles", "aplicación")
    _registrar_ahorro(sid)
    return _recordar(RedirectResponse(f"/viajes/{sid}", status_code=303), solicitado_por)


def _registrar_ahorro(sid: int, c: dict | None = None):
    """Guarda con la consulta cuánto se evita al elegir por costo total y no por precio."""
    c = c or _comparacion(sid)
    if c and c["vuelos"] and c["mas_barato"]:
        mejor, barato = c["vuelos"][0]["ev"]["total"], c["mas_barato"]["ev"]["total"]
        db.actualizar("solicitudes", sid, precio_min_buscador=c["mas_barato"]["v"]["precio"], costo_mas_barato=barato,
                      costo_mejor=mejor, ahorro_potencial=round(max(barato - mejor, 0), 2))
    elif c:
        db.actualizar("solicitudes", sid, ahorro_potencial=0)  # sin vuelos válidos: no hay nada que comparar


def _comparacion(sid: int) -> dict | None:
    sol = db.uno("""select s.*, p.nombre proyecto, v.nombre viajero from solicitudes s
                    left join proyectos p on p.id=s.proyecto_id left join viajeros v on v.id=s.viajero_id
                    where s.id=:i""", i=sid)
    if not sol:
        return None
    cat = costo.catalogo()
    membresias = db.todos_cache("select * from membresias where viajero_id=:v or viajero_id is null", v=sol["viajero_id"])
    vuelos, hoteles = [], []
    for o in db.todos("select * from opciones where solicitud_id=:i order by id", i=sid):
        datos = db.de_json(o["datos"], {})
        if o["tipo"] == "vuelo":
            t = db.de_json(o["tarifas"], {}) or {}
            ev = costo.mejor_tarifa(datos, t.get("lista") or [], sol, membresias, cat)
            vuelos.append({"id": o["id"], "v": datos, "ev": ev, "origen_dato": o["origen_dato"],
                           "origen_tarifas": t.get("origen"), "capturado": o["capturado"], "tarifas_lista": t.get("lista") or []})
        else:
            hoteles.append({"id": o["id"], "h": datos, "origen_dato": o["origen_dato"],
                            "programa": costo.programa_hotel(datos["nombre"], cat)})
    # Precio esperado según el modelo (solo si hay un modelo utilizable)
    ref = db.uno("select tipico_min, tipico_max from observaciones where busqueda=:b limit 1",
                 b=f"{sol['origen']}_{sol['destino']}_{sol['ida']}_{sol['regreso']}") or {}
    f_ida = date.fromisoformat(sol["ida"])
    filas = [{"ruta": f"{sol['origen']}-{sol['destino']}", "aerolinea": v["v"]["aerolinea"], "escalas": v["v"]["escalas"],
              "duracion_min": v["v"]["duracion_min"], "hora_salida": int(v["v"]["sale"][11:13]) + int(v["v"]["sale"][14:16]) / 60,
              "dia_semana": f_ida.weekday(), "anticipacion": (f_ida - date.fromisoformat(sol["creado"][:10])).days,
              "noches": costo.noches(sol["ida"], sol["regreso"]), "tipico_min": ref.get("tipico_min"), "tipico_max": ref.get("tipico_max")}
             for v in vuelos]
    for v, esperado in zip(vuelos, modelo.precios_esperados(filas)):
        v["esperado"] = esperado
        v["frente_esperado"] = round((v["v"]["precio"] - esperado) / esperado * 100) if esperado else None
    validos = sorted([v for v in vuelos if not v["ev"]["descartada"]], key=lambda v: v["ev"]["total"])
    descartados = [v for v in vuelos if v["ev"]["descartada"]]
    hoteles.sort(key=lambda h: h["h"]["total"])
    mas_barato = min(vuelos, key=lambda v: v["v"]["precio"]) if vuelos else None
    aviso = None
    if validos and mas_barato and validos[0]["id"] != mas_barato["id"]:
        m = validos[0]
        aviso = (f"La opción más barata del buscador es {mas_barato['v']['aerolinea']} por {mas_barato['v']['precio']:.0f} USD, "
                 f"pero con el equipo, el riesgo de cambio y las millas su costo esperado es {mas_barato['ev']['total']:.0f} USD. "
                 f"La mejor es {m['v']['aerolinea']} {m['v']['numeros'][0]} ({m['ev']['tarifa']['nombre']}): {m['ev']['total']:.0f} USD.")
    n = costo.noches(sol["ida"], sol["regreso"])
    return {"sol": sol, "vuelos": validos, "descartados": descartados, "hoteles": hoteles, "aviso": aviso,
            "mas_barato": mas_barato, "hay_modelo": modelo.utilizable(),
            "baterias": costo.baterias(sol["baterias_n"], sol["baterias_wh"]), "noches": n,
            "carro": round((sol["carro_dia"] or 0) * n, 2), "membresias": membresias,
            "fallos": db.todos("select detalle from eventos where entidad='solicitud' and entidad_id=:i and paso='consulta externa fallida'", i=sid),
            "decision": db.uno("select * from decisiones where solicitud_id=:i order by id desc", i=sid)}


@app.get("/viajes/{sid}", response_class=HTMLResponse)
def viaje(request: Request, sid: int):
    c = _comparacion(sid)
    if not c:
        return RedirectResponse("/", status_code=303)
    return plantillas.TemplateResponse(request, "viaje.html", _ctx(
        **c, mi_nombre=_nombre(request), agente=agente.recomendar(c, solo_determinista=True)))


@app.post("/viajes/{sid}/agente", response_class=HTMLResponse)
def viaje_agente(request: Request, sid: int, pregunta: str = Form("")):
    """Pregunta al agente. Con modelo de lenguaje usa las herramientas; sin él, responde el análisis determinista."""
    c = _comparacion(sid)
    if not c:
        return RedirectResponse("/", status_code=303)
    with eventos.cronometro() as t:
        r = agente.recomendar(c, pregunta.strip()[:400])
    eventos.registrar("solicitud", sid, "recomendación del agente", (pregunta.strip()[:120] or "recomendación general")
                      + " · herramientas: " + (", ".join(r["pasos"]) or "ninguna"), r["modo"], t())
    return plantillas.TemplateResponse(request, "viaje.html", _ctx(**c, mi_nombre=_nombre(request), agente=r, pregunta=pregunta))


@app.post("/viajes/{sid}/tarifas/{oid}")
def viaje_tarifas(sid: int, oid: int):
    """Trae las familias tarifarias reales de un vuelo (dos consultas al buscador)."""
    sol = db.uno("select * from solicitudes where id=:i", i=sid)
    o = db.uno("select * from opciones where id=:i and solicitud_id=:s", i=oid, s=sid)
    if sol and o:
        tarifas, origen = precios.tarifas_de_vuelo(sol["origen"], sol["destino"], sol["ida"], sol["regreso"],
                                                   db.de_json(o["datos"], {}), sid, permitir_en_vivo=True)
        if tarifas:
            db.actualizar("opciones", oid, tarifas={"lista": tarifas, "origen": origen})
            _registrar_ahorro(sid)
    return RedirectResponse(f"/viajes/{sid}#v{oid}", status_code=303)


@app.post("/viajes/{sid}/decidir")
def viaje_decidir(sid: int, vuelo_id: int = Form(0), hotel_id: int = Form(0), motivo: str = Form(""),
                  aprobado_por: str = Form("")):
    c = _comparacion(sid)
    if not c:
        return RedirectResponse("/", status_code=303)
    vuelo = next((v for v in c["vuelos"] + c["descartados"] if v["id"] == vuelo_id), None)
    hotel = next((h for h in c["hoteles"] if h["id"] == hotel_id), None)  # puede no haber hoteles para la ciudad
    if not vuelo:
        return RedirectResponse(f"/viajes/{sid}", status_code=303)
    lineas = [{**l, "grupo": "vuelo"} for l in vuelo["ev"]["lineas"]]
    if hotel:
        lineas.append({"concepto": f"Hotel: {hotel['h']['nombre']} ({c['noches']} noches)", "valor": hotel["h"]["total"],
                       "origen": "buscador", "grupo": "hotel"})
    if c["carro"]:
        lineas.append({"concepto": f"Carro de alquiler ({c['noches']} días x {c['sol']['carro_dia']:.0f})",
                       "valor": c["carro"], "origen": "supuesto", "grupo": "alquiler_carro"})
    total = round(sum(l["valor"] for l in lineas), 2)
    did = db.insertar("decisiones", solicitud_id=sid, proyecto_id=c["sol"]["proyecto_id"], vuelo_id=vuelo_id,
                      hotel_id=hotel["id"] if hotel else None, tarifa=vuelo["ev"]["tarifa"]["nombre"],
                      desglose={"lineas": lineas, "avisos": vuelo["ev"]["avisos"], "vuelo": vuelo["v"],
                                "hotel": hotel["h"] if hotel else None,
                                "origen_vuelo": vuelo["origen_dato"], "origen_hotel": hotel["origen_dato"] if hotel else None,
                                "aviso": c["aviso"], "baterias": c["baterias"],
                                # lo que se evita frente a la opción más barata del buscador, por costo esperado
                                "ahorro": round(max(c["mas_barato"]["ev"]["total"] - vuelo["ev"]["total"], 0), 2) if c["mas_barato"] else 0},
                      total=total, motivo=motivo, aprobado_por=aprobado_por, creado=db.ahora())
    db.actualizar("solicitudes", sid, estado="decidido")
    eventos.registrar("solicitud", sid, "decisión guardada", f"Total previsto {total:.2f} USD (ficha #{did})", aprobado_por or "usuario")
    return RedirectResponse(f"/viajes/{sid}/ficha", status_code=303)


@app.get("/viajes/{sid}/ficha", response_class=HTMLResponse)
def viaje_ficha(request: Request, sid: int):
    c = _comparacion(sid)
    if not c or not c["decision"]:
        return RedirectResponse(f"/viajes/{sid}", status_code=303)
    return plantillas.TemplateResponse(request, "ficha.html", _ctx(**c, d=db.de_json(c["decision"]["desglose"], {})))


# ---------- reto 2: gastos ----------
class SoporteRechazado(ValueError):
    """El archivo no se acepta; el mensaje se muestra a quien lo subió."""


def _tipo_real(contenido: bytes, nombre: str) -> tuple[str, str] | None:
    """Tipo según el contenido, no según lo que declara quien sube. Devuelve (tipo, extensión) o None."""
    if contenido[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp", "webp"
    if contenido[:5] == b"%PDF-":
        return "application/pdf", "pdf"
    if nombre.lower().endswith(".eml"):
        cabecera = contenido[:4000].decode("utf-8", "ignore").lower()
        if not cabecera.lstrip().startswith("<") and sum(c in cabecera for c in ("from:", "subject:", "date:", "to:")) >= 2:
            return "message/rfc822", "eml"
    return None


def _nombre_visible(nombre: str) -> str:
    """Nombre original solo para mostrarlo: sin rutas ni caracteres de control."""
    limpio = re.sub(r"[\x00-\x1f\\/]", "_", Path(nombre or "soporte").name)[:120]
    return limpio or "soporte"


def _procesar(contenido: bytes, nombre: str, canal: str, proyecto_id: int | None, viajero_id: int | None) -> int:
    if not contenido:
        raise SoporteRechazado("El archivo está vacío.")
    if len(contenido) > config.MAX_BYTES_SOPORTE:
        raise SoporteRechazado(f"El archivo pesa {len(contenido) / 1e6:.1f} MB; el máximo es {config.MAX_BYTES_SOPORTE / 1e6:.1f} MB.")
    tipo = _tipo_real(contenido, nombre)
    if not tipo:
        raise SoporteRechazado("Tipo de archivo no admitido. Se aceptan fotos (JPG, PNG, WebP), PDF y correos (.eml).")
    mime, extension = tipo
    nombre = _nombre_visible(nombre)
    huella = hashlib.sha256(contenido).hexdigest()
    try:
        ruta = almacen.guardar(almacen.clave(huella, extension), contenido, mime)
    except Exception as e:
        raise SoporteRechazado(f"No se pudo guardar el archivo ({type(e).__name__}). Intenta de nuevo.") from e
    doc = db.insertar("documentos", nombre=nombre, mime=mime, canal=canal, ruta=ruta, huella=huella, creado=db.ahora())
    gid = db.insertar("gastos", documento_id=doc, proyecto_id=proyecto_id, viajero_id=viajero_id, estado="procesando", creado=db.ahora())
    eventos.registrar("gasto", gid, "documento recibido", f"{nombre} ({mime})", f"canal: {canal}")
    # Un archivo idéntico ya leído no se vuelve a pagar: se reutiliza su lectura
    previo = db.uno("""select g.extraido from gastos g join documentos d on d.id=g.documento_id
                       where d.huella=:h and g.id<>:i and g.extraido is not null order by g.id limit 1""", h=huella, i=gid)
    with eventos.cronometro() as t:
        x = {**db.de_json(previo["extraido"], {}), "origen_dato": "reutilizado", "error": None} if previo else \
            extraccion.extraer(contenido, mime, nombre)
    eventos.registrar("gasto", gid, "datos extraídos", x.get("error") or f"{x['comercio']} · {x['total']} {x['moneda']} · confianza {x['confianza']:.0%}",
                      f"modelo ({x['origen_dato']})", t())
    proyecto = db.uno("select * from proyectos where id=:i", i=proyecto_id) if proyecto_id else None
    r = validacion.revisar(x, proyecto, gid)
    if x.get("error"):
        # Una lectura fallida nunca se aprueba sola
        r["alertas"].insert(0, x["error"])
        r["estado"] = "revision"
    original = {c: x.get(c) for c in extraccion.CAMPOS} | {"confianza": x["confianza"], "dudas": x.get("dudas", [])}
    db.actualizar("gastos", gid, **{c: x[c] for c in extraccion.CAMPOS if c != "ciudad"}, confianza=x["confianza"],
                  origen_dato=x["origen_dato"], estado=r["estado"], alertas=r["alertas"], total_usd=r["total_usd"],
                  extraido=None if x.get("error") else original)
    eventos.registrar("gasto", gid, "aprobado sin intervención" if r["estado"] == "aprobado_auto" else "enviado a revisión",
                      " ".join(r["alertas"]) or "Todas las validaciones en verde", "reglas de validación")
    return gid


@app.get("/gastos", response_class=HTMLResponse)
def gastos(request: Request, estado: str = "", aviso: str = ""):
    filtro = "where g.estado=:e" if estado else ""
    filas = db.todos(f"""select g.*, p.nombre proyecto, v.nombre viajero, d.nombre archivo, d.canal from gastos g
                         left join proyectos p on p.id=g.proyecto_id left join viajeros v on v.id=g.viajero_id
                         left join documentos d on d.id=g.documento_id {filtro} order by g.id desc""", e=estado)
    return plantillas.TemplateResponse(request, "gastos.html", _ctx(gastos=filas, estado=estado, ind=_indicadores(), aviso=aviso[:300]))


@app.get("/gastos/cargar", response_class=HTMLResponse)
def gastos_cargar(request: Request):
    ejemplos = sorted(p.name for p in config.DIR_EJEMPLOS.iterdir() if p.suffix in (".png", ".pdf", ".jpg"))
    correos = sorted(p.name for p in config.DIR_EJEMPLOS.glob("*.eml"))
    return plantillas.TemplateResponse(request, "cargar.html", _ctx(ejemplos=ejemplos, correos=correos))


@app.post("/gastos/cargar")
def gastos_cargar_enviar(request: Request, archivos: list[UploadFile], proyecto_id: int = Form(0), viajero_id: int = Form(0),
                         canal: str = Form("web")):
    """Función normal (no asíncrona): la lectura con el modelo corre en un hilo y no detiene al resto del servidor."""
    canal = canal if canal in ("web", "celular") else "web"
    hechos, errores = [], []
    for a in archivos[:config.MAX_ARCHIVOS_POR_CARGA]:
        try:
            hechos.append(_procesar(a.file.read(config.MAX_BYTES_SOPORTE + 1), a.filename or "soporte", canal,
                                    proyecto_id or None, viajero_id or None))
        except SoporteRechazado as e:
            errores.append(f"{_nombre_visible(a.filename or '')}: {e}")
    if len(archivos) > config.MAX_ARCHIVOS_POR_CARGA:
        errores.append(f"Solo se procesan {config.MAX_ARCHIVOS_POR_CARGA} archivos por envío.")
    if request.headers.get("x-envio") == "pagina":  # la página envía un archivo por petición y muestra el avance
        return JSONResponse({"gastos": hechos, "errores": errores}, status_code=200 if hechos or not errores else 400)
    destino = "/gastos" + (f"?aviso={quote(' '.join(errores)[:300])}" if errores else "")
    return RedirectResponse(destino, status_code=303)


@app.post("/gastos/ejemplos")
def gastos_ejemplos(nombres: list[str] = Form([]), proyecto_id: int = Form(0), viajero_id: int = Form(0), canal: str = Form("web")):
    """Procesa soportes de la carpeta de ejemplos; con canal 'correo' simula la lectura de un buzón."""
    for n in nombres:
        archivo = config.DIR_EJEMPLOS / Path(n).name
        if archivo.is_file():
            try:
                _procesar(archivo.read_bytes(), archivo.name, "correo" if canal == "correo" else canal, proyecto_id or None, viajero_id or None)
            except SoporteRechazado:
                continue
    return RedirectResponse("/gastos", status_code=303)


@app.get("/gastos/{gid}", response_class=HTMLResponse)
def gasto(request: Request, gid: int):
    g = db.uno("""select g.*, d.nombre archivo, d.mime, d.canal from gastos g
                  left join documentos d on d.id=g.documento_id where g.id=:i""", i=gid)
    if not g:
        return RedirectResponse("/gastos", status_code=303)
    return plantillas.TemplateResponse(request, "gasto.html", _ctx(
        g=g, alertas=db.de_json(g["alertas"], []),
        eventos=db.todos("select * from eventos where entidad='gasto' and entidad_id=:i order by id", i=gid)))


@app.get("/gastos/{gid}/soporte")
def gasto_soporte(gid: int):
    d = db.uno("select d.* from documentos d join gastos g on g.documento_id=d.id where g.id=:i", i=gid)
    contenido = almacen.leer(d["ruta"]) if d else None
    if contenido is None:
        return Response("No disponible", status_code=404)
    # Solo se sirven en línea tipos inertes; el resto se muestra como texto. El contenido se aísla del resto de la página.
    mime = d["mime"] if d["mime"] in ("image/jpeg", "image/png", "image/webp", "application/pdf") else "text/plain; charset=utf-8"
    return Response(contenido, media_type=mime, headers={
        "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "Cache-Control": "private, no-store"})


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


@app.post("/gastos/{gid}")
def gasto_guardar(gid: int, accion: str = Form(...), proyecto_id: int = Form(0), viajero_id: int = Form(0),
                  comercio: str = Form(""), fecha: str = Form(""), categoria: str = Form("otros"),
                  subtotal: str = Form(""), impuesto: str = Form(""), propina: str = Form(""), total: str = Form(""),
                  moneda: str = Form(""), metodo_pago: str = Form(""), canal_reserva: str = Form(""), revisor: str = Form(""),
                  motivo_excepcion: str = Form("")):
    if accion == "rechazar":
        db.actualizar("gastos", gid, estado="rechazado")
        eventos.registrar("gasto", gid, "rechazado en revisión", "", revisor or "revisor")
        return RedirectResponse("/gastos?estado=revision", status_code=303)
    campos = {"comercio": comercio.strip() or None, "fecha": fecha or None, "categoria": categoria,
              "subtotal": _numero(subtotal), "impuesto": _numero(impuesto), "propina": _numero(propina),
              "total": _numero(total), "moneda": moneda.upper().strip() or None,
              "metodo_pago": metodo_pago.strip() or None, "canal_reserva": canal_reserva.strip() or None}
    proyecto = db.uno("select * from proyectos where id=:i", i=proyecto_id) if proyecto_id else None
    # Una persona confirmó los datos: la confianza de lectura deja de ser el criterio
    r = validacion.revisar({**campos, "confianza": 1.0, "dudas": []}, proyecto, gid)
    estado = "aprobado" if r["estado"] == "aprobado_auto" else "revision"
    # Excepción justificada: una persona responde por un gasto que las reglas no dejan pasar (dos peajes iguales el mismo día)
    excepcion = accion == "excepcion" and estado == "revision"
    if excepcion and len(motivo_excepcion.strip()) < 8:
        r["alertas"].append("Para aprobar con excepción hay que escribir el motivo.")
    elif excepcion and campos["total"] is not None and campos["moneda"] and r["total_usd"] is not None:
        estado = "aprobado"
        r["alertas"].append(f"Aprobado con excepción: {motivo_excepcion.strip()[:200]}")
    db.actualizar("gastos", gid, **campos, proyecto_id=proyecto_id or None, viajero_id=viajero_id or None,
                  estado=estado, alertas=r["alertas"], total_usd=r["total_usd"])
    paso = "aprobado con excepción" if excepcion and estado == "aprobado" else \
        "corregido y aprobado" if estado == "aprobado" else "corregido, sigue en revisión"
    eventos.registrar("gasto", gid, paso, " ".join(r["alertas"]), revisor or "revisor")
    return RedirectResponse("/gastos" if estado == "aprobado" else f"/gastos/{gid}", status_code=303)


# ---------- tablero por proyecto ----------
@app.get("/proyectos/{pid}", response_class=HTMLResponse)
def proyecto(request: Request, pid: int):
    p = db.uno("select * from proyectos where id=:i", i=pid)
    if not p:
        return RedirectResponse("/", status_code=303)
    real = {r["categoria"]: r["t"] for r in db.todos(
        "select categoria, sum(total_usd) t from gastos where proyecto_id=:i and estado in ('aprobado','aprobado_auto') group by categoria", i=pid)}
    previsto: dict[str, float] = {}
    decisiones = db.todos("select * from decisiones where proyecto_id=:i order by id", i=pid)
    ultimas = {d["solicitud_id"]: d for d in decisiones}.values()  # una decisión vigente por solicitud
    for d in ultimas:
        for l in db.de_json(d["desglose"], {}).get("lineas", []):
            if l["origen"] != "supuesto" or l["grupo"] != "vuelo":  # el riesgo y las millas no son desembolsos
                previsto[l["grupo"]] = previsto.get(l["grupo"], 0) + l["valor"]
    filas = [{"clave": c, "nombre": n, "previsto": round(previsto.get(c, 0), 2), "real": round(real.get(c) or 0, 2)}
             for c, n in config.CATEGORIAS.items() if previsto.get(c) or real.get(c)]
    faltantes = [f["nombre"] for f in filas if f["previsto"] and not f["real"]]
    return plantillas.TemplateResponse(request, "proyecto.html", _ctx(
        p=p, filas=filas, faltantes=faltantes, decisiones=list(ultimas),
        tot_previsto=round(sum(f["previsto"] for f in filas), 2), tot_real=round(sum(f["real"] for f in filas), 2),
        pendientes=db.uno("select count(*) n from gastos where proyecto_id=:i and estado='revision'", i=pid)["n"],
        gastos=db.todos("""select g.*, v.nombre viajero from gastos g left join viajeros v on v.id=g.viajero_id
                           where g.proyecto_id=:i order by g.fecha""", i=pid)))


@app.get("/proyectos/{pid}/exportar.csv")
def proyecto_exportar(pid: int):
    filas = db.todos("select id,fecha,comercio,categoria,total,moneda,total_usd,estado,metodo_pago,origen_dato from gastos where proyecto_id=:i order by fecha", i=pid)
    columnas = ["id", "fecha", "comercio", "categoria", "total", "moneda", "total_usd", "estado", "metodo_pago", "origen_dato"]
    def celda(v):  # texto que empieza como fórmula se neutraliza para las hojas de cálculo
        t = str(v if v is not None else "").replace('"', "'")
        return '"' + ("'" + t if t[:1] in "=+-@" and not isinstance(v, (int, float)) else t) + '"'
    lineas = [",".join(columnas)] + [",".join(celda(f[c]) for c in columnas) for f in filas]
    return Response("\n".join(lineas), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="gastos_proyecto_{pid}.csv"'})


# ---------- flujo de la información ----------
@app.get("/flujo", response_class=HTMLResponse)
def flujo(request: Request):
    pasos = {r["paso"]: r["n"] for r in db.todos("select paso, count(*) n from eventos group by paso")}
    fuentes = db.todos("select fuente, count(*) n, avg(duracion_ms) ms from eventos where fuente<>'' group by fuente order by n desc")
    return plantillas.TemplateResponse(request, "flujo.html", _ctx(
        ind=_indicadores(), pasos=pasos, fuentes=fuentes,
        eventos=db.todos("select * from eventos order by id desc limit 60")))


# ---------- analítica ----------
def _completar_ahorros():
    for s in db.todos("select id from solicitudes where ahorro_potencial is null"):
        _registrar_ahorro(s["id"])


@app.get("/analitica", response_class=HTMLResponse)
def analitica_pagina(request: Request):
    _completar_ahorros()
    return plantillas.TemplateResponse(request, "analitica.html", _ctx(a=analitica.resumen()))


# ---------- API en JSON (contrato para un front aparte) ----------
@app.get("/api/analitica", tags=["api"])
def api_analitica():
    _completar_ahorros()
    return analitica.resumen()


@app.get("/api/solicitudes", tags=["api"])
def api_solicitudes():
    return db.todos("select * from solicitudes order by id desc")


@app.get("/api/solicitudes/{sid}", tags=["api"])
def api_solicitud(sid: int):
    c = _comparacion(sid)
    if not c:
        return Response(status_code=404)
    quitar = lambda o: {k: v for k, v in o.items() if k != "tarifas_lista"}
    return {"solicitud": c["sol"], "aviso": c["aviso"], "equipo": c["baterias"], "vuelos": [quitar(o) for o in c["vuelos"]],
            "descartados": [quitar(o) for o in c["descartados"]], "hoteles": c["hoteles"],
            "recomendacion": agente.recomendar(c, solo_determinista=True)}


@app.get("/api/gastos", tags=["api"])
def api_gastos(proyecto_id: int = 0):
    filtro = "where proyecto_id=:p" if proyecto_id else ""
    return db.todos(f"select * from gastos {filtro} order by id desc", p=proyecto_id)


@app.get("/api/observaciones", tags=["api"])
def api_observaciones(limite: int = 1000):
    return db.todos("select * from observaciones order by id desc limit :l", l=min(limite, 5000))


@app.get("/api/eventos", tags=["api"])
def api_eventos(limite: int = 200):
    return db.todos("select * from eventos order by id desc limit :l", l=min(limite, 1000))


# ---------- catálogo de reglas ----------
@app.get("/reglas", response_class=HTMLResponse)
def reglas(request: Request):
    return plantillas.TemplateResponse(request, "reglas.html", _ctx(
        reglas=db.todos("select * from reglas order by ambito, entidad, clave"),
        membresias=db.todos("select m.*, v.nombre viajero from membresias m left join viajeros v on v.id=m.viajero_id order by m.id")))


@app.post("/reglas/{rid}")
def regla_guardar(rid: int, valor: str = Form(...)):
    db.actualizar("reglas", rid, valor=valor.strip(), verificado=db.ahora()[:10])
    eventos.registrar("regla", rid, "regla editada", f"nuevo valor: {valor.strip()}", "usuario")
    return RedirectResponse("/reglas", status_code=303)
