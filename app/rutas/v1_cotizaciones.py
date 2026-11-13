"""API v1: buscar lugares, cotizar, ver la comparación y decidir. Contrato en `contracts/api-v1.md`.

La lógica es la misma de las pantallas (`app/servicios/cotizacion.py`). Ver una cotización alcanza a quien la creó,
a quien viaja, al gestor del proyecto y a administración (`acceso.puede_ver`); decidirla, solo a los tres primeros
sin el gestor (`acceso.es_propio`). Lo que no se ve responde 404.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Path, Query, Response

from .. import config, db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, persona
from ..api_v1.esquemas_cotizacion import (
    ENTERO_MAXIMO,
    Cotizacion,
    FormularioCotizacion,
    LadoPedido,
    ListaLugares,
    NuevaCotizacion,
    NuevaDecision,
    errores_cotizacion,
)
from ..servicios import acceso, agente, consultas, costo, cotizacion, geografia, viajes

router = APIRouter(prefix=PREFIJO, tags=["cotizaciones"])

PUEDE_ELEGIR_VIAJERO = ("gestor", "admin")
TOPE_DIA = 20   # cotizaciones nuevas por persona y día; la regla `tope_cotizaciones_persona_dia` lo cambia


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _invalido(campo: str, mensaje: str) -> ErrorApi:
    return ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {campo: mensaje})


# ---------- lugares ----------
@router.get("/lugares", response_model=ListaLugares, responses=errores_cotizacion(401, 422))
def lugares(q: str = Query("", max_length=80, description="Lo escrito: país, ciudad, pueblo o código de aeropuerto."),
            google: bool = Query(False, description="Sumar las sugerencias de Google (con pausa: gasta cupo, con topes)."),
            limite: int = Query(8, ge=1, le=20), yo: dict = Depends(persona)):
    """Sugerencias para el campo de origen o destino. Mismos datos y mismos topes de Google que el formulario de siempre."""
    resultados, aviso = geografia.buscar_con_aviso(q, limite, yo, google)
    return {"resultados": [_sugerencia(r) for r in resultados], "aviso_google": aviso, "carretera": geografia.carretera()}


def _sugerencia(r: dict) -> dict:
    return {**{k: r.get(k) for k in ("tipo", "lat", "lon", "tambien", "aviso", "origen")},
            "id": str(r.get("id") or ""), "nombre": r.get("nombre") or "", "region": r.get("region") or "", "pais": r.get("pais") or "",
            "aeropuertos": [{"iata": a["iata"], "nombre": a.get("nombre"), "municipio": a.get("municipio"), "km": a.get("km"),
                             "horas": a.get("horas"), "grande": bool(a.get("grande"))} for a in r.get("aeropuertos") or []]}


# ---------- formulario ----------
@router.get("/cotizaciones/formulario", response_model=FormularioCotizacion, responses=errores_cotizacion(401))
def formulario(yo: dict = Depends(persona)):
    """Lo que hace falta para llenar una cotización: proyectos, quién puede viajar y las razones de la decisión."""
    propio, permitidos = yo.get("viajero_id"), cotizacion.proyectos_para_otros(yo)
    elige = yo["rol"] in PUEDE_ELEGIR_VIAJERO and (permitidos is None or bool(permitidos))
    viajeros = db.todos("select id, nombre, base from viajeros order by nombre") if elige else \
        db.todos("select id, nombre, base from viajeros where id=:i", i=propio or -1)
    return {"proyectos": [{"id": p["id"], "nombre": p["nombre"], "ciudad": p["ciudad"], "inicio": p["fecha_inicio"], "fin": p["fecha_fin"],
                           "para_otra_persona": permitidos is None or p["id"] in permitidos}
                          for p in db.todos("select * from proyectos order by id")],
            "viajeros": [{**v, "soy_yo": v["id"] == propio} for v in viajeros], "viajero_propio_id": propio,
            "elige_viajero": elige, "razones": [{"clave": k, "texto": v} for k, v in config.RAZONES.items()],
            "precios_en_vivo": bool(config.SERPAPI_KEY)}


# ---------- cotizar ----------
def _viajero(yo: dict, pedido: int | None) -> tuple[int, bool]:
    """(viajero, para otra persona). Cada quien cotiza para sí; administración, también para otra persona, y el gestor
    en los proyectos que gestiona (lo revisa `crear` con el proyecto)."""
    propio = yo.get("viajero_id")
    if pedido is None or pedido == propio:
        if not propio:
            raise _invalido("viajero_id", "Tu cuenta no viaja: elige quién viaja.")
        return propio, False
    if yo["rol"] not in PUEDE_ELEGIR_VIAJERO:
        raise ErrorApi(403, "FORBIDDEN", "Solo gestión y administración cotizan para otra persona.")
    return pedido, True


def _lado(nombre: str, lado: LadoPedido) -> dict:
    if not lado.texto.strip() and not lado.aeropuertos:
        raise _invalido(nombre, "Escribe un lugar o el código de un aeropuerto.")
    return {nombre: lado.texto, f"{nombre}_aeropuertos": ",".join(lado.aeropuertos),
            f"{nombre}_lugar": lado.lugar.model_dump() if lado.lugar else None}


@router.post("/cotizaciones", status_code=201, response_model=Cotizacion, responses=errores_cotizacion(401, 403, 409, 422, 429))
def crear(datos: NuevaCotizacion, response: Response, yo: dict = Depends(escritura),
          clave: str | None = Header(None, alias="Idempotency-Key", max_length=200,
                                     description="Un valor único por pedido, que se repite si se reintenta el mismo.")):
    """Guarda el pedido y busca vuelos y hoteles (una consulta para todos los aeropuertos marcados; lo guardado no se paga).
    Responde 201 con la comparación lista.

    Con `Idempotency-Key`, el reintento con el mismo pedido responde 200 con la misma cotización; con otro pedido, 409
    `IDEMPOTENCY_CONFLICT`; si el primero todavía está buscando, 409 `REQUEST_IN_PROGRESS`. Un pedido rechazado (422)
    deja la clave libre. Pasado el tope de cotizaciones nuevas del día por persona: 429 `TOO_MANY_REQUESTS`.
    """
    viajero_id, para_otra = _viajero(yo, datos.viajero_id)
    if not db.uno("select id from proyectos where id=:i", i=datos.proyecto_id):
        raise _invalido("proyecto_id", "Elige un proyecto de la lista.")
    if para_otra and not cotizacion.para_otros_en(yo, datos.proyecto_id):
        raise ErrorApi(403, "FORBIDDEN", "Para cotizar para otra persona elige uno de los proyectos que gestionas.")
    campos = {**_lado("origen", datos.origen), **_lado("destino", datos.destino)}
    envio = None
    if clave:
        try:
            envio, hecha = cotizacion.reclamar_envio(yo["id"], clave, cotizacion.huella_pedido(datos.model_dump(mode="json")))
        except cotizacion.ConflictoEnvio as e:
            raise ErrorApi(409, "IDEMPOTENCY_CONFLICT", str(e)) from e
        except cotizacion.EnvioEnCurso as e:
            raise ErrorApi(409, "REQUEST_IN_PROGRESS", str(e)) from e
        if hecha:
            response.status_code = 200
            return _cotizacion(yo, hecha)
    if _hechas_hoy(yo) >= _tope_dia():   # cada cotización nueva puede gastar dos búsquedas pagas
        if envio:
            cotizacion.soltar_envio(envio)
        raise ErrorApi(429, "TOO_MANY_REQUESTS", "Llegaste al tope de cotizaciones nuevas de hoy. Retoma una de las que ya "
                                                 "tienes o pide a administración que amplíe el tope.")
    try:
        sid = cotizacion.crear(yo, proyecto_id=datos.proyecto_id, viajero_id=viajero_id, para_otra_persona=para_otra,
                               ida=datos.ida.isoformat(), regreso=datos.regreso.isoformat(),
                               llegar_antes=f"{datos.ida.isoformat()}T{datos.hora_limite}" if datos.hora_limite else "",
                               ciudad=datos.ciudad_hotel, baterias_n=datos.baterias_n, baterias_wh=datos.baterias_wh,
                               maleta=datos.maleta, prob_cambio=datos.prob_cambio_pct, carro_dia=float(Decimal(datos.carro_dia_usd)),
                               canal="api v1", **campos)
    except cotizacion.CotizacionInvalida as e:
        if envio:
            cotizacion.soltar_envio(envio)
        raise _invalido(e.campo, str(e)) from e
    except cotizacion.FueraDeAlcance as e:
        if envio:
            cotizacion.soltar_envio(envio)
        raise ErrorApi(403, "FORBIDDEN", str(e)) from e
    except Exception:
        if envio:
            cotizacion.soltar_envio(envio)
        raise
    if envio:
        cotizacion.completar_envio(envio, sid)
    return _cotizacion(yo, sid)


def _tope_dia() -> int:
    return int(costo.supuesto(costo.catalogo(), "tope_cotizaciones_persona_dia", TOPE_DIA))


def _hechas_hoy(yo: dict) -> int:
    return db.uno("select count(*) n from solicitudes where usuario_id=:u and creado>=:h", u=yo["id"], h=db.ahora()[:10])["n"]


# ---------- ver ----------
def _fila(sid: int) -> dict | None:
    return db.uno("select usuario_id, viajero_id, proyecto_id from solicitudes where id=:i", i=sid)


IdCotizacion = Path(ge=1, le=ENTERO_MAXIMO)


@router.get("/cotizaciones/{id}", response_model=Cotizacion, responses=errores_cotizacion(401, 404, 422))
def detalle(id: int = IdCotizacion, yo: dict = Depends(persona)):
    if not acceso.puede_ver(yo, _fila(id)):
        raise _no_encontrado()
    return _cotizacion(yo, id)


# ---------- decidir ----------
@router.post("/cotizaciones/{id}/decision", response_model=Cotizacion, responses=errores_cotizacion(401, 403, 404, 409, 422))
def decidir(datos: NuevaDecision, id: int = IdCotizacion, yo: dict = Depends(escritura)):
    """Guarda la decisión y crea el viaje (o actualiza el que ya tiene la cotización), pendiente de aprobación.

    Si el vuelo no es el recomendado, `motivo` es obligatorio. El mismo envío repetido no duplica la decisión.
    Con el presupuesto ya aprobado o el viaje cerrado: 409 `DECISION_LOCKED` (administración debe reabrirlo).
    """
    fila = _fila(id)
    if not acceso.puede_ver(yo, fila):
        raise _no_encontrado()
    if not cotizacion.puede_decidir(yo, fila):
        raise ErrorApi(403, "FORBIDDEN", cotizacion.NO_DECIDE)
    try:
        cotizacion.decidir(yo, id, datos.vuelo_id, datos.hotel_id or 0, datos.motivo, datos.razones)
    except LookupError as e:
        raise _no_encontrado() from e
    except cotizacion.FueraDeAlcance as e:
        raise ErrorApi(403, "FORBIDDEN", str(e)) from e
    except cotizacion.DecisionBloqueada as e:
        raise ErrorApi(409, "DECISION_LOCKED", str(e)) from e
    except cotizacion.DecisionInvalida as e:
        raise _invalido(e.campo, str(e)) from e
    return _cotizacion(yo, id)


# ---------- forma del contrato ----------
_TIPO_POR_INICIO = (("Precio", "precio"), ("Equipaje de mano", "equipaje"), ("Maleta facturada", "equipaje"),
                    ("Riesgo de cambio", "riesgo_cambio"), ("Millas", "millas"))
_TIPO_POR_GRUPO = {"traslados": "traslado", "combustible": "traslado"}


def _tipo_linea(linea: dict) -> str:
    if linea.get("grupo") in _TIPO_POR_GRUPO:
        return _TIPO_POR_GRUPO[linea["grupo"]]
    return next((tipo for inicio, tipo in _TIPO_POR_INICIO if linea["concepto"].startswith(inicio)), "otro")


def _vuelo(o: dict, c: dict) -> dict:
    v, ev = o["v"], o["ev"]
    lineas = [{"concepto": l["concepto"], "valor_usd": consultas.dinero(l["valor"]), "origen": l.get("origen") or "supuesto",
               "tipo": _tipo_linea(l)} for l in ev["lineas"]]
    suma = dict.fromkeys(("precio", "equipaje", "riesgo_cambio", "millas", "traslado"), Decimal("0"))
    for l in lineas:
        clave = l["tipo"] if l["tipo"] in suma else "precio"   # «otro» no aparece hoy; si apareciera, cuenta con el precio
        suma[clave] += Decimal(l["valor_usd"] or "0")
    recomendada = bool(c["vuelos"]) and c["vuelos"][0]["id"] == o["id"]
    return {"id": o["id"], "aerolinea": v.get("aerolinea") or "", "numeros": v.get("numeros") or [], "desde": v.get("desde"),
            "hasta": v.get("hasta"), "sale": v.get("sale") or "", "llega": v.get("llega") or "", "escalas": v.get("escalas") or 0,
            "duracion_min": v.get("duracion_min"), "precio_usd": consultas.dinero(v.get("precio")),
            "tarifa": {"nombre": ev["tarifa"]["nombre"], "permite_cambio": bool(ev["tarifa"].get("permite_cambio")),
                       "reales": bool(ev.get("tarifas_reales"))},
            "costo_total_usd": consultas.dinero(ev["total"]),
            "desglose": {f"{k}_usd": consultas.dinero(x) for k, x in suma.items()}, "lineas": lineas,
            "avisos": ev["avisos"], "descartada": ev["descartada"], "recomendada": recomendada,
            "mas_barata": bool(c["mas_barato"]) and c["mas_barato"]["id"] == o["id"], "origen_dato": o["origen_dato"],
            "esperado_usd": consultas.dinero(o.get("esperado")), "frente_esperado_pct": o.get("frente_esperado")}


def _hotel(i: int, o: dict) -> dict:
    h = o["h"]
    return {"id": o["id"], "nombre": h.get("nombre") or "", "noche_usd": consultas.dinero(h.get("noche")),
            "total_usd": consultas.dinero(h.get("total")), "calificacion": h.get("calificacion"),
            "clase": int(h["clase"]) if h.get("clase") is not None else None, "programa": o["programa"],
            "origen_dato": o["origen_dato"], "recomendada": i == 0}


def _lado_salida(sol: dict, nombre: str) -> dict:
    return {"codigo": sol[nombre], "aeropuertos": cotizacion.codigos(sol, nombre),
            "lugar": cotizacion.lugar(sol[f"{nombre}_lugar"])}


def _origen_vuelos(sid: int) -> str | None:
    fila = db.uno("select origen from consultas_buscador where solicitud_id=:i and tipo='vuelos' order by id desc limit 1", i=sid)
    return fila["origen"] if fila else None


def _cotizacion(yo: dict, sid: int) -> dict:
    c = cotizacion.comparacion(sid)
    if not c:
        raise _no_encontrado()
    sol, d = c["sol"], c["decision"]
    viaje = viajes.de_solicitud(sid)
    bloqueo = viajes.bloquea_decision(sid)
    return {
        "id": sid, "estado": sol["estado"], "creado": consultas.instante(sol["creado"]), "solicitado_por": sol["solicitado_por"],
        "proyecto": {"id": sol["proyecto_id"], "nombre": sol["proyecto"]} if sol["proyecto_id"] else None,
        "viajero": {"id": sol["viajero_id"], "nombre": sol["viajero"]} if sol["viajero_id"] else None,
        "origen": _lado_salida(sol, "origen"), "destino": _lado_salida(sol, "destino"), "ciudad_hotel": sol["ciudad"],
        "ida": sol["ida"], "regreso": sol["regreso"], "noches": c["noches"],
        "hora_limite": (sol["llegar_antes"] or "")[11:16] or None,
        "baterias_n": sol["baterias_n"] or 0, "baterias_wh": sol["baterias_wh"] or 0, "maleta": bool(sol["maleta"]),
        "prob_cambio_pct": round((sol["prob_cambio"] or 0) * 100), "carro_usd": consultas.dinero(c["carro"]),
        "equipo": {"nivel": c["baterias"]["nivel"], "texto": c["baterias"]["texto"]},
        "origen_dato": _origen_vuelos(sid), "aviso": c["aviso"], "fallos": [f["detalle"] for f in c["fallos"]],
        "recomendacion": agente.recomendar(c, solo_determinista=True)["texto"],
        "vuelos": [_vuelo(o, c) for o in c["vuelos"]], "descartados": [_vuelo(o, c) for o in c["descartados"]],
        "hoteles": [_hotel(i, o) for i, o in enumerate(c["hoteles"])],
        "recomendada_id": c["vuelos"][0]["id"] if c["vuelos"] else None,
        "mas_barata_id": c["mas_barato"]["id"] if c["mas_barato"] else None,
        "decision": {"id": d["id"], "vuelo_id": d["vuelo_id"], "hotel_id": d["hotel_id"], "motivo": d["motivo"] or None,
                     "razones": db.de_json(d["razones"], []) or [], "total_usd": consultas.dinero(d["total"]),
                     "siguio_recomendacion": bool(d["siguio_recomendacion"]), "creado": consultas.instante(d["creado"]),
                     "aviso": (db.de_json(d["desglose"], {}) or {}).get("aviso_tope")} if d else None,
        "viaje": {**{k: viaje[k] for k in ("id", "codigo", "estado", "estado_texto")},
                  "presupuesto_usd": consultas.dinero(viaje["presupuesto_usd"])} if viaje else None,
        "puede_decidir": cotizacion.puede_decidir(yo, sol) and not bloqueo and bool(c["vuelos"] or c["descartados"]),
        "bloqueo": bloqueo,
    }
