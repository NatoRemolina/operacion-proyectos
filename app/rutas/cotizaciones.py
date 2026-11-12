"""Reto 1: cotizar, comparar opciones y decidir. La decisión crea el viaje."""
import re
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import aeropuertos, config, db
from ..servicios import acceso, agente, costo, eventos, geografia, modelo, precios, viajes
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
@router.get("/viajes/nuevo", response_class=HTMLResponse)
def viaje_nuevo(request: Request, error: str = ""):
    return plantillas.TemplateResponse(request, "viaje_nuevo.html", _ctx(error=error))


def _lugar(texto: str) -> dict | None:
    """El lugar elegido en el buscador, solo con los campos esperados y coordenadas válidas; si no, ninguno."""
    datos = db.de_json(texto, None)
    if not isinstance(datos, dict) or not str(datos.get("nombre") or "").strip():
        return None
    try:
        lat, lon = float(datos["lat"]), float(datos["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"nombre": str(datos["nombre"]).strip()[:80], "region": str(datos.get("region") or "").strip()[:80],
            "pais": str(datos.get("pais") or "").strip()[:80], "lat": lat, "lon": lon}


def _lado(texto: str, codigos: str, lugar_json: str) -> dict | None:
    """Origen o destino de la cotización. Con aeropuertos marcados en el buscador: el lugar, la lista ordenada y el
    principal (el marcado más cercano al lugar, o el primero). Sin ellos, como antes: un aeropuerto por nombre o código.
    None si algo no se reconoce; `malo` dice qué."""
    if not codigos.strip():
        r = aeropuertos.resolver(texto)
        return {"codigo": r[0], "ciudad": r[1], "lista": None, "lugar": None} if r else {"malo": texto}
    marcados = list(dict.fromkeys(c.strip().upper() for c in codigos.split(",") if c.strip()))[:8]
    conocidos = geografia.aeropuertos_conocidos(marcados)
    malo = next((c for c in marcados if c not in conocidos), None)
    if malo or not marcados:
        return {"malo": malo or codigos}
    lugar = _lugar(lugar_json)
    principal = marcados[0]
    if lugar:
        con_distancia = [c for c in marcados if conocidos[c].get("lat") is not None]
        if con_distancia:
            principal = min(con_distancia, key=lambda c: geografia.distancia_km(lugar["lat"], lugar["lon"],
                                                                                 conocidos[c]["lat"], conocidos[c]["lon"]))
    return {"codigo": principal, "ciudad": lugar["nombre"] if lugar else (conocidos[principal].get("municipio") or principal),
            "lista": ",".join(sorted(marcados)), "lugar": lugar}


def _texto_lado(lado: dict) -> str:
    """Para la bitácora: «Moab, Utah, Estados Unidos (CNY, GJT, SLC)» o el código cuando no hubo lugar."""
    if not lado["lista"]:
        return lado["codigo"]
    lugar = lado["lugar"] or {}
    nombre = ", ".join(x for x in (lugar.get("nombre"), lugar.get("region"), lugar.get("pais")) if x) or "sin lugar"
    return f"{nombre} ({lado['lista'].replace(',', ', ')})"


@router.post("/viajes")
def viaje_crear(proyecto_id: int = Form(...), viajero_id: int = Form(0), origen: str = Form(""),
                destino: str = Form(""), ciudad: str = Form(""), ida: str = Form(...), regreso: str = Form(...),
                llegar_antes: str = Form(""), baterias_n: int = Form(0), baterias_wh: float = Form(0),
                maleta: str = Form(""), prob_cambio: float = Form(0), carro_dia: float = Form(0),
                solicitado_por: str = Form(""), viajero_nuevo: str = Form(""), para_otra_persona: str = Form(""),
                origen_aeropuertos: str = Form(""), destino_aeropuertos: str = Form(""),
                origen_lugar: str = Form(""), destino_lugar: str = Form("")):
    sale, llega = _lado(origen, origen_aeropuertos, origen_lugar), _lado(destino, destino_aeropuertos, destino_lugar)
    if "malo" in sale or "malo" in llega:
        malo = sale.get("malo") if "malo" in sale else llega["malo"]
        return RedirectResponse(f"/viajes/nuevo?error=No+reconozco+%22{quote(malo[:40])}%22.+Elige+una+ciudad+de+la+lista+o+escribe+el+c%C3%B3digo+de+tres+letras+del+aeropuerto.", status_code=303)
    desde, hacia = (sale["codigo"], sale["ciudad"]), (llega["codigo"], llega["ciudad"])
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
    solicitado_por, viajero_nuevo = _yo()["nombre"], viajero_nuevo.strip()[:80]  # quien consulta sale de la sesión
    # Todos viajan: quien cotiza viaja, salvo que gestión o administración marquen que es para otra persona.
    # Así el titular no sale de un campo que se olvidó cambiar.
    para_otra = para_otra_persona == "1" and _yo().get("rol") in ("gestor", "admin")
    if _yo().get("viajero_id") and not para_otra:
        viajero_id, viajero_nuevo = _yo()["viajero_id"], ""
    elif not acceso.es_admin(_yo()):
        viajero_nuevo = ""   # registrar viajeros es tarea de administración
    if viajero_nuevo:
        existente = db.uno("select id from viajeros where lower(nombre)=lower(:n)", n=viajero_nuevo)
        viajero_id = existente["id"] if existente else db.insertar("viajeros", nombre=viajero_nuevo, base=desde[1], rol="Viajero")
    if not viajero_id or not db.uno("select id from viajeros where id=:i", i=viajero_id):
        return RedirectResponse("/viajes/nuevo?error=Elige+qui%C3%A9n+viaja.", status_code=303)
    sid = db.insertar("solicitudes", proyecto_id=proyecto_id, viajero_id=viajero_id, origen=origen,
                      destino=destino, ciudad=ciudad, ida=ida, regreso=regreso,
                      llegar_antes=llegar_antes or None, baterias_n=baterias_n, baterias_wh=baterias_wh,
                      maleta=1 if maleta else 0, prob_cambio=prob_cambio / 100, carro_dia=carro_dia,
                      estado="buscando", creado=db.ahora(), solicitado_por=solicitado_por, usuario_id=_yo()["id"],
                      origen_lugar=sale["lugar"], destino_lugar=llega["lugar"],
                      origen_aeropuertos=sale["lista"], destino_aeropuertos=llega["lista"])
    eventos.registrar("solicitud", sid, "solicitud recibida", f"{origen}-{destino} {ida} a {regreso} · "
                      f"origen: {_texto_lado(sale)} · destino: {_texto_lado(llega)}", f"formulario · {solicitado_por}")
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
    return RedirectResponse(f"/viajes/{sid}", status_code=303)


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
    for v, esperado in zip(vuelos, modelo.precios_esperados(filas), strict=False):
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
        tarifas, origen = precios.tarifas_de_vuelo(sol["origen"], sol["destino"], sol["ida"], sol["regreso"],
                                                   db.de_json(o["datos"], {}), sid, permitir_en_vivo=True)
        if tarifas:
            db.actualizar("opciones", oid, tarifas={"lista": tarifas, "origen": origen})
            _registrar_ahorro(sid)
    return RedirectResponse(f"/viajes/{sid}#v{oid}", status_code=303)


@router.post("/viajes/{sid}/decidir")
def viaje_decidir(sid: int, vuelo_id: int = Form(0), hotel_id: int = Form(0), motivo: str = Form(""),
                  aprobado_por: str = Form(""), razones: list[str] = Form([])):
    c = _comparacion(sid) if _solicitud_propia(sid, para_modificar=True) else None
    if not c:
        return NO_ENCONTRADO
    previa = c["decision"]
    if previa and previa["vuelo_id"] == vuelo_id and (previa["hotel_id"] or 0) == hotel_id and (previa["motivo"] or "") == motivo.strip()[:300]:
        return RedirectResponse(f"/viajes/{sid}/ficha", status_code=303)   # mismo envío repetido: no se duplica la decisión
    bloqueo = viajes.bloquea_decision(sid)
    if bloqueo:
        return RedirectResponse(f"/viajes/{sid}?aviso={quote(bloqueo)}", status_code=303)
    aprobado_por = _yo()["nombre"]
    vuelo = next((v for v in c["vuelos"] + c["descartados"] if v["id"] == vuelo_id), None)
    hotel = next((h for h in c["hoteles"] if h["id"] == hotel_id), None)  # puede no haber hoteles para la ciudad
    if not vuelo:
        return RedirectResponse(f"/viajes/{sid}?aviso=Elige+un+vuelo+para+guardar+la+decisi%C3%B3n.", status_code=303)
    orden = c["vuelos"] + c["descartados"]
    recomendado = c["vuelos"][0] if c["vuelos"] else None
    siguio = bool(recomendado and recomendado["id"] == vuelo["id"])
    razones = [r for r in razones if r in config.RAZONES]
    if not siguio and len(motivo.strip()) < 5:
        # Cuando la persona se aparta de la recomendación, el porqué es el dato más valioso
        return RedirectResponse(f"/viajes/{sid}?aviso=Elegiste+una+opci%C3%B3n+distinta+a+la+recomendada%3A+cu%C3%A9ntanos+por+qu%C3%A9.", status_code=303)
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
                      total=total, motivo=motivo[:300], aprobado_por=aprobado_por, creado=db.ahora(), usuario_id=_yo()["id"],
                      razones=razones, recomendado_id=recomendado["id"] if recomendado else None,
                      siguio_recomendacion=1 if siguio else 0, posicion_elegida=orden.index(vuelo) + 1)
    # Foto de todo lo que se mostró: las reglas y las tarifas pueden cambiar después
    db.insertar_varios("elecciones", [
        {"decision_id": did, "solicitud_id": sid, "opcion_id": o["id"], "tipo": "vuelo", "posicion": i + 1,
         "elegida": int(o["id"] == vuelo["id"]), "recomendada": int(bool(recomendado) and o["id"] == recomendado["id"]),
         "descartada": int(bool(o["ev"]["descartada"])), "precio": o["v"]["precio"], "costo_esperado": o["ev"]["total"],
         "rasgos": {"aerolinea": o["v"]["aerolinea"], "escalas": o["v"]["escalas"], "duracion_min": o["v"]["duracion_min"],
                    "sale": o["v"]["sale"][11:], "llega": o["v"]["llega"][11:], "tarifa": o["ev"]["tarifa"]["nombre"],
                    "permite_cambio": o["ev"]["tarifa"]["permite_cambio"], "tarifas_reales": o["ev"]["tarifas_reales"],
                    "frente_esperado": o.get("frente_esperado"), "prob_cambio": c["sol"]["prob_cambio"],
                    "baterias": c["sol"]["baterias_n"], "maleta": c["sol"]["maleta"]},
         "creado": db.ahora()} for i, o in enumerate(orden)] + [
        {"decision_id": did, "solicitud_id": sid, "opcion_id": h["id"], "tipo": "hotel", "posicion": i + 1,
         "elegida": int(bool(hotel) and h["id"] == hotel["id"]), "recomendada": int(i == 0), "descartada": 0,
         "precio": h["h"]["total"], "costo_esperado": h["h"]["total"],
         "rasgos": {"calificacion": h["h"]["calificacion"], "clase": h["h"]["clase"], "programa": h["programa"]},
         "creado": db.ahora()} for i, h in enumerate(c["hoteles"])])
    db.actualizar("solicitudes", sid, estado="decidido")
    eventos.registrar("solicitud", sid, "decisión guardada", f"Total previsto {total:.2f} USD (ficha #{did})", aprobado_por or "usuario")
    # La decisión asigna el viaje a la persona: nace con su código y queda a la espera de que administración apruebe el presupuesto
    viajes.crear_desde_decision(did)
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


def _completar_ahorros():
    for s in db.todos("select id from solicitudes where ahorro_potencial is null"):
        _registrar_ahorro(s["id"])
