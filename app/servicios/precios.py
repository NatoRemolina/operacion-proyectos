"""Precios de vuelos y hoteles.

Orden de búsqueda: respuesta guardada para la misma consulta, consulta en vivo si hay
clave, y como último recurso una respuesta guardada de la misma ruta con otras fechas.
Cada resultado dice de dónde salió: "en vivo", "guardado" o "guardado (otras fechas)".
Cada búsqueda, también la leída de lo guardado o la fallida, deja una fila en `consultas_buscador`.
"""
import json
import re
import time
from datetime import UTC, date, datetime

import httpx

from .. import config, db
from . import eventos

URL = "https://serpapi.com/search.json"


_cupo = {"momento": None, "dato": None}


def cupo() -> dict | None:
    """Búsquedas que quedan en el plan del buscador. Consultarlo no gasta cupo; se recuerda diez minutos."""
    if not config.SERPAPI_KEY:
        return None
    ahora = datetime.now(UTC)
    if _cupo["momento"] and (ahora - _cupo["momento"]).total_seconds() < 600:
        return _cupo["dato"]
    try:
        d = httpx.get("https://serpapi.com/account.json", params={"api_key": config.SERPAPI_KEY}, timeout=8).json()
        dato = {"plan": d.get("plan_name"), "mensual": d.get("searches_per_month"), "usadas": d.get("this_month_usage"),
                "restantes": d.get("total_searches_left")}
    except (httpx.HTTPError, ValueError):
        dato = None
    _cupo.update(momento=ahora, dato=dato)
    return dato


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def _leer(nombre: str):
    """Busca una respuesta ya pagada: primero en los archivos del repositorio, luego en la tabla compartida."""
    archivo = config.DIR_RESPALDO / nombre
    if archivo.is_file():
        return json.loads(archivo.read_text())
    fila = db.uno("select cuerpo from busquedas where clave=:c order by id desc limit 1", c=nombre)
    return json.loads(fila["cuerpo"]) if fila else None


def _sin_reserva(datos):
    """La respuesta sin `booking_request` (URL y `post_data`): la plataforma nunca ejecuta una reserva y no lo guarda."""
    if isinstance(datos, dict):
        return {k: _sin_reserva(v) for k, v in datos.items() if k != "booking_request"}
    if isinstance(datos, list):
        return [_sin_reserva(v) for v in datos]
    return datos


def _guardar(nombre: str, datos: dict):
    """Una respuesta pagada no se pierde: va a la tabla compartida. El archivo es una copia de conveniencia.
    Antes de guardarla se quita lo que serviría para ejecutar una reserva."""
    cuerpo = json.dumps(_sin_reserva(datos), ensure_ascii=False)
    db.insertar("busquedas", clave=nombre, cuerpo=cuerpo, creado=db.ahora())
    try:
        config.DIR_RESPALDO_ESCRITURA.mkdir(parents=True, exist_ok=True)
        (config.DIR_RESPALDO_ESCRITURA / nombre).write_text(cuerpo)
    except OSError:
        pass  # disco de solo lectura: la tabla ya lo tiene


def _anotar(tipo: str, clave: str, origen: str, solicitud_id: int | None, inicio: float,
            precios: list | None = None, error=None):
    """Rastro de la consulta para los indicadores. La respuesta completa ya está en `busquedas`: aquí solo se referencia por la clave."""
    from . import kpis  # el registro vive con los indicadores que lo leen
    kpis.registrar_consulta(tipo, origen, clave, solicitud_id, int((time.perf_counter() - inicio) * 1000), precios or [],
                            str(error)[:300] if error else None)


SIN_DATOS = "Sin respuesta guardada para esta búsqueda y sin consulta en vivo disponible."


def _consultar(parametros: dict, entidad: str, entidad_id: int | None, que: str) -> dict:
    with eventos.cronometro() as t:
        r = httpx.get(URL, params={**parametros, "api_key": config.SERPAPI_KEY, "hl": "en", "currency": "USD"}, timeout=60)
        datos = r.json()
    if "error" in datos:
        eventos.registrar(entidad, entidad_id, "consulta externa fallida", f"{que}: {datos['error']}", "SerpApi", t())
        raise RuntimeError(datos["error"])
    eventos.registrar(entidad, entidad_id, "consulta externa", que, "SerpApi (en vivo)", t())
    return datos


def _vuelo(f: dict) -> dict | None:
    """Un itinerario de la respuesta, leído campo por campo con valor por defecto: un dato que falte en vivo no rompe
    la cotización. Sin tramos con horas de salida y llegada no hay vuelo que comparar (None)."""
    tramos = [t for t in f.get("flights") or [] if isinstance(t, dict)]
    if not tramos:
        return None
    sale, llega = tramos[0].get("departure_airport") or {}, tramos[-1].get("arrival_airport") or {}
    if len(sale.get("time") or "") < 16 or len(llega.get("time") or "") < 16:
        return None
    return {
        "aerolinea": tramos[0].get("airline") or "Aerolínea sin nombre",
        "aerolineas": sorted({s.get("airline") for s in tramos if s.get("airline")}),
        "numeros": [s.get("flight_number") or "s/n" for s in tramos],
        "sale": sale["time"],
        "llega": llega["time"],
        "desde": sale.get("id"),
        "hasta": llega.get("id"),
        "escalas": len(tramos) - 1,
        "duracion_min": f.get("total_duration"),
        "precio": f.get("price"),
        "notas": f.get("extensions") or [],
        "token": f.get("departure_token"),
        "booking": f.get("booking_token"),
        # Cada tramo con su número: el monitoreo del día del viaje los sigue uno por uno
        "tramos": [{"aerolinea": s.get("airline"), "numero": s.get("flight_number"),
                    "desde": (s.get("departure_airport") or {}).get("id"), "hasta": (s.get("arrival_airport") or {}).get("id"),
                    "sale": (s.get("departure_airport") or {}).get("time"), "llega": (s.get("arrival_airport") or {}).get("time")}
                   for s in tramos],
        # Sin costo de búsquedas: lo que ya trae la respuesta sobre retrasos y escalas
        "a_menudo_retrasado": any(s.get("often_delayed_by_over_30_min") for s in tramos),
        "escalas_detalle": [{"aeropuerto": e.get("id"), "minutos": e.get("duration"), "nocturna": bool(e.get("overnight"))}
                            for e in f.get("layovers") or [] if isinstance(e, dict)],
    }


def _vuelos(datos: dict) -> list[dict]:
    """Los itinerarios con precio que se pueden comparar, de mejores y otros."""
    return [v for v in (_vuelo(f) for f in datos.get("best_flights", []) + datos.get("other_flights", []) if f.get("price")) if v]


def codigos(valor: str | list[str]) -> list[str]:
    """Códigos de aeropuerto ordenados y sin repetir. Acepta un código, una lista o una cadena separada por comas."""
    partes = valor.split(",") if isinstance(valor, str) else valor
    return sorted({c.strip().upper() for c in partes if c and c.strip()})


def ruta(origen: str | list[str], destino: str | list[str]) -> tuple[str, str, str, str]:
    """Parámetros (códigos unidos por coma) y partes del nombre de archivo (unidos por guion) de una ruta.

    Siempre en el mismo orden y formato: un reintento envía exactamente los mismos parámetros y el proveedor lo sirve
    de su caché sin cobrarlo. Con un solo código, todo queda idéntico a como era antes de comparar varios aeropuertos."""
    o, d = codigos(origen), codigos(destino)
    return ",".join(o), ",".join(d), "-".join(o), "-".join(d)


def _avisar_ignorados(datos: dict, origen: str, destino: str, solicitud_id: int | None):
    """El bloque `airports` dice qué códigos usó la búsqueda; si ignoró alguno de los pedidos, queda registrado."""
    tramos = datos.get("airports") or []
    if not tramos:
        return
    usados = {lado: {(a.get("airport") or {}).get("id") for a in tramos[0].get(lado) or []} for lado in ("departure", "arrival")}
    faltan = [c for c in codigos(origen) if c not in usados["departure"]] + [c for c in codigos(destino) if c not in usados["arrival"]]
    if faltan:
        eventos.registrar("solicitud", solicitud_id, "aeropuertos ignorados por el buscador",
                          f"{', '.join(faltan)}: sin resultados en la búsqueda {origen} → {destino}", "SerpApi (en vivo)")


def registrar_observaciones(datos: dict, origen: str, destino: str, ida: str, regreso: str, fuente: str) -> int:
    """Guarda cada vuelo de una respuesta del buscador como fila tabular. No duplica una búsqueda ya registrada.

    `origen` y `destino` identifican la búsqueda (con varios aeropuertos, unidos por guion); cada fila lleva los
    aeropuertos reales de su vuelo."""
    clave = f"{origen}_{destino}_{ida}_{regreso}"
    if db.uno("select id from observaciones where busqueda=:b limit 1", b=clave):
        return 0
    capturado = (datos.get("search_metadata", {}).get("created_at") or db.ahora())[:10]
    info = datos.get("price_insights", {})
    tipico = info.get("typical_price_range") or [None, None]
    f_ida = date.fromisoformat(ida)
    filas = []
    for v in _vuelos(datos):
        filas.append({
            "busqueda": clave, "origen": v["desde"] or origen, "destino": v["hasta"] or destino, "ida": ida, "regreso": regreso,
            "aerolinea": v["aerolinea"], "escalas": v["escalas"], "duracion_min": v["duracion_min"],
            "hora_salida": int(v["sale"][11:13]) + int(v["sale"][14:16]) / 60, "dia_semana": f_ida.weekday(),
            "anticipacion": (f_ida - date.fromisoformat(capturado)).days,
            "noches": (date.fromisoformat(regreso) - f_ida).days, "precio": float(v["precio"]),
            "nivel_ruta": info.get("price_level"), "tipico_min": tipico[0], "tipico_max": tipico[1],
            "capturado": capturado, "fuente": fuente,
        })
    db.insertar_varios("observaciones", filas)
    db.insertar_varios("historial_ruta", [
        {"busqueda": clave, "origen": origen, "destino": destino,
         "fecha": datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d"), "precio": float(precio)}
        for ts, precio in info.get("price_history", [])])
    return len(filas)


def cargar_respaldos() -> int:
    """Pasa a la tabla de observaciones todas las respuestas de vuelos guardadas en disco."""
    total = 0
    ya = {f["busqueda"] for f in db.todos("select distinct busqueda from observaciones")}  # una sola consulta
    for archivo in sorted(config.DIR_RESPALDO.glob("vuelos_*.json")):
        partes = archivo.stem.split("_")
        if len(partes) == 5 and "_".join(partes[1:]) not in ya:
            total += registrar_observaciones(json.loads(archivo.read_text()), partes[1], partes[2], partes[3], partes[4], "respaldo")
    return total


def buscar_vuelos(origen: str | list[str], destino: str | list[str], ida: str, regreso: str, solicitud_id: int | None = None):
    """Devuelve (lista de vuelos, origen del dato, información de precios de la ruta).

    Con varios aeropuertos de origen o de destino hace una sola consulta con los códigos unidos por coma."""
    origen, destino, n_origen, n_destino = ruta(origen, destino)
    inicio, nombre, fallo = time.perf_counter(), f"vuelos_{n_origen}_{n_destino}_{ida}_{regreso}.json", None
    datos, origen_dato, clave = _leer(nombre), "guardado", nombre
    if datos is None and config.SERPAPI_KEY:
        try:
            datos = _consultar({"engine": "google_flights", "departure_id": origen, "arrival_id": destino,
                                "outbound_date": ida, "return_date": regreso},
                               "solicitud", solicitud_id, f"vuelos {origen}-{destino} {ida}")
            _guardar(nombre, datos)
            origen_dato = "en vivo"
            _avisar_ignorados(datos, origen, destino, solicitud_id)
        except Exception as e:
            datos, fallo = None, e
            _anotar("vuelos", nombre, "fallida", solicitud_id, inicio, error=e)
    if datos is None:
        otros = sorted(config.DIR_RESPALDO.glob(f"vuelos_{n_origen}_{n_destino}_*.json"))
        if otros:
            datos, origen_dato, clave = json.loads(otros[0].read_text()), "guardado (otras fechas)", otros[0].name
    if datos is None:
        if not fallo:
            _anotar("vuelos", nombre, "fallida", solicitud_id, inicio, error=SIN_DATOS)
        return [], "sin datos", {}
    if origen_dato != "en vivo":
        eventos.registrar("solicitud", solicitud_id, "lectura de respaldo", f"vuelos {origen}-{destino}", origen_dato)
    if origen_dato in ("en vivo", "guardado"):
        registrar_observaciones(datos, n_origen, n_destino, ida, regreso, "formulario" if solicitud_id else "recolector")
    vuelos = _vuelos(datos)
    _anotar("vuelos", clave, origen_dato, solicitud_id, inicio, [v["precio"] for v in vuelos])
    return vuelos, origen_dato, datos.get("price_insights", {})


def _tarifa(opcion: dict) -> dict | None:
    t = opcion.get("together") or opcion.get("departing")
    if not t or not t.get("price"):
        return None
    notas = t.get("extensions", [])
    equipaje = t.get("baggage_prices", [])
    mano, maleta = None, None
    for linea in equipaje:
        bajo = linea.lower()
        valor = re.search(r":\s*\$?(\d+)", linea)
        if "carry-on" in bajo:
            mano = 0 if "free" in bajo else (float(valor.group(1)) if valor else None)
        if "checked bag" in bajo:
            maleta = 0 if "free" in bajo else (float(valor.group(1)) if valor else None)
    texto = " ".join(notas).lower()
    return {
        "nombre": t.get("option_title") or "Tarifa",
        "vende": t.get("book_with"),
        "precio": float(t["price"]),
        "mano": mano,          # 0 = incluido, número = costo, None = no informado
        "maleta": maleta,
        "permite_cambio": "no ticket changes" not in texto and "change" in texto,
        "reembolsable": "full refund" in texto,
        "notas": notas,
        "equipaje": equipaje,
    }


def _clave_vuelo(vuelo: dict) -> str:
    return "".join(n.replace(" ", "") for n in vuelo.get("numeros") or [])


def _guardada(nombre: str, patron: str) -> tuple:
    """(datos, origen del dato, clave) de una respuesta ya pagada: la misma consulta o, si no, la de otras fechas."""
    datos = _leer(nombre)
    if datos is not None:
        return datos, "guardado", nombre
    otros = sorted(config.DIR_RESPALDO.glob(patron))
    if otros:
        return json.loads(otros[0].read_text()), "guardado (otras fechas)", otros[0].name
    return None, None, None


def vuelo_regreso(vuelo_ida: dict, origenes: str | list[str], destinos: str | list[str], ida: str, regreso: str,
                  solicitud_id: int | None = None) -> dict | None:
    """El vuelo de regreso real de una opción de ida: una consulta con su `departure_token`.

    Se envían los mismos códigos que la búsqueda original, para aprovechar la caché del proveedor. De los regresos se
    toman los que salen del aeropuerto real de llegada de la ida y se elige el más barato. Antes de pagar se busca la
    respuesta guardada (también la de «Traer tarifas» de antes, que guardaba regreso y reserva juntos).
    None sin token, sin clave ni respuesta guardada, si la consulta falla o si ningún regreso sale de ese aeropuerto."""
    origen, destino, n_origen, n_destino = ruta(origenes, destinos)
    clave = _clave_vuelo(vuelo_ida)
    inicio, nombre = time.perf_counter(), f"regreso_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json"
    datos, origen_dato, usada = _guardada(nombre, f"regreso_{n_origen}_{n_destino}_*_{clave}.json")
    if datos is None:
        antiguo, origen_dato, usada = _guardada(f"tarifas_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json",
                                                f"tarifas_{n_origen}_{n_destino}_*_{clave}.json")
        datos = (antiguo or {}).get("regreso")
    if datos is None:
        if not (config.SERPAPI_KEY and vuelo_ida.get("token")):
            return None
        try:
            datos = _consultar({"engine": "google_flights", "departure_id": origen, "arrival_id": destino,
                                "outbound_date": ida, "return_date": regreso, "departure_token": vuelo_ida["token"]},
                               "solicitud", solicitud_id, f"regreso para {clave}")
            _guardar(nombre, datos)
            origen_dato, usada = "en vivo", nombre
        except Exception as e:
            _anotar("regreso", nombre, "fallida", solicitud_id, inicio, error=e)
            return None
    candidatos = [v for v in _vuelos(datos) if not vuelo_ida.get("hasta") or v["desde"] == vuelo_ida["hasta"]]
    _anotar("regreso", usada, origen_dato, solicitud_id, inicio, [v["precio"] for v in candidatos])
    if not candidatos:
        return None
    elegido = min(candidatos, key=lambda v: v["precio"])
    elegido["origen_dato"] = origen_dato
    return elegido


def opciones_reserva(vuelo_ida: dict, vuelo_regreso_: dict, origenes: str | list[str], destinos: str | list[str], ida: str,
                     regreso: str, solicitud_id: int | None = None):
    """Opciones de reserva reales del itinerario (ida más regreso): una consulta con el `booking_token` del regreso.
    Devuelve (tarifas, origen del dato, precios de equipaje)."""
    origen, destino, n_origen, n_destino = ruta(origenes, destinos)
    clave = _clave_vuelo(vuelo_ida)
    inicio, nombre = time.perf_counter(), f"reserva_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json"
    datos, origen_dato, usada = _guardada(nombre, f"reserva_{n_origen}_{n_destino}_*_{clave}.json")
    if datos is None:
        antiguo, origen_dato, usada = _guardada(f"tarifas_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json",
                                                f"tarifas_{n_origen}_{n_destino}_*_{clave}.json")
        datos = (antiguo or {}).get("reserva")
    if datos is None:
        if not (config.SERPAPI_KEY and (vuelo_regreso_ or {}).get("booking")):
            return [], "sin datos", {}
        try:
            datos = _consultar({"engine": "google_flights", "departure_id": origen, "arrival_id": destino,
                                "outbound_date": ida, "return_date": regreso, "booking_token": vuelo_regreso_["booking"]},
                               "solicitud", solicitud_id, f"opciones de reserva de {clave}")
            _guardar(nombre, datos)
            origen_dato, usada = "en vivo", nombre
        except Exception as e:
            _anotar("tarifas", nombre, "fallida", solicitud_id, inicio, error=e)
            return [], "sin datos", {}
    tarifas = [t for t in (_tarifa(o) for o in datos.get("booking_options", [])) if t]
    _anotar("tarifas", usada, origen_dato, solicitud_id, inicio, [t["precio"] for t in tarifas])
    return tarifas, origen_dato, datos.get("baggage_prices") or {}


def tarifas_de_vuelo(origen: str | list[str], destino: str | list[str], ida: str, regreso: str, vuelo: dict,
                     solicitud_id: int | None = None, permitir_en_vivo: bool = False):
    """Familias tarifarias de un vuelo. Devuelve (tarifas, origen del dato).

    Sin permiso para consultar solo se leen las respuestas guardadas (y sin ellas no se buscó nada: no hay rastro que
    dejar). Con permiso son dos consultas, cada una con su fila en `consultas_buscador`: el regreso y las opciones de reserva."""
    if not permitir_en_vivo:
        _, _, n_origen, n_destino = ruta(origen, destino)
        clave = _clave_vuelo(vuelo)
        guardadas = [f"{p}_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json" for p in ("reserva", "tarifas")]
        hay = any(_leer(n) is not None for n in guardadas) or any(
            next(config.DIR_RESPALDO.glob(f"{p}_{n_origen}_{n_destino}_*_{clave}.json"), None) for p in ("reserva", "tarifas"))
        if not hay:
            return [], "sin datos"
        tarifas, origen_dato, _ = opciones_reserva(vuelo, None, origen, destino, ida, regreso, solicitud_id)
        return tarifas, origen_dato
    vuelta = vuelo_regreso(vuelo, origen, destino, ida, regreso, solicitud_id)
    if not vuelta:
        return [], "sin datos"
    tarifas, origen_dato, _ = opciones_reserva(vuelo, vuelta, origen, destino, ida, regreso, solicitud_id)
    return tarifas, origen_dato


def _segmentos(vuelo: dict | None) -> list[dict]:
    """Los tramos de un vuelo como los pide `selected_flights_json`: número sin espacios, aeropuertos y fecha de cada uno."""
    return [{"flight_number": (s.get("numero") or "").replace(" ", ""), "departure_id": s.get("desde"),
             "arrival_id": s.get("hasta"), "date": (s.get("sale") or "")[:10]}
            for s in (vuelo or {}).get("tramos") or [] if s.get("numero") and s.get("desde") and s.get("hasta")]


def reconfirmar(decision: dict) -> dict:
    """Precio vigente del itinerario elegido, fijado tramo por tramo con `selected_flights_json` (una consulta).

    Siempre en vivo: una respuesta guardada no dice el precio de hoy. Compara con la tarifa que usó la decisión (la de
    mismo nombre, si el proveedor la ofrece; si no, la más barata). Devuelve {"estado": "confirmado" | "cambio" |
    "sin datos", "antes", "ahora", "variacion" (fracción), "motivo"}."""
    d = db.de_json(decision.get("desglose"), {}) if isinstance(decision.get("desglose"), str) else decision.get("desglose") or {}
    antes = d.get("precio_tarifa") or (d.get("vuelo") or {}).get("precio")
    ida, vuelta = _segmentos(d.get("vuelo")), _segmentos(d.get("regreso"))
    sin = {"estado": "sin datos", "antes": antes, "ahora": None, "variacion": None}
    if not config.SERPAPI_KEY:
        return {**sin, "motivo": "sin clave del buscador"}
    if not ida:
        return {**sin, "motivo": "la decisión no tiene los tramos del vuelo"}
    fijado = {"outbound": ida, **({"return": vuelta} if vuelta else {})}
    clave = "".join(s["flight_number"] for s in ida + vuelta)
    inicio = time.perf_counter()
    nombre = f"reconfirmacion_{clave}_{datetime.now(UTC):%Y%m%d%H%M}.json"
    try:
        datos = _consultar({"engine": "google_flights", "type": 1 if vuelta else 2,
                            "selected_flights_json": json.dumps(fijado, separators=(",", ":"))},
                           "solicitud", decision.get("solicitud_id"), f"reconfirmación del precio de {clave}")
        _guardar(nombre, datos)
    except Exception as e:
        _anotar("reconfirmacion", nombre, "fallida", decision.get("solicitud_id"), inicio, error=e)
        return {**sin, "motivo": f"la consulta falló ({str(e)[:80]})"}
    tarifas = [t for t in (_tarifa(o) for o in datos.get("booking_options", [])) if t]
    _anotar("reconfirmacion", nombre, "en vivo", decision.get("solicitud_id"), inicio, [t["precio"] for t in tarifas])
    if not tarifas or not antes:
        return {**sin, "motivo": "la respuesta no trae opciones de reserva"}
    misma = [t for t in tarifas if t["nombre"] == decision.get("tarifa")]
    ahora = min(t["precio"] for t in misma or tarifas)
    variacion = (ahora - float(antes)) / float(antes)
    return {"estado": "confirmado" if abs(variacion) < 0.005 else "cambio", "antes": float(antes), "ahora": ahora,
            "variacion": round(variacion, 4), "motivo": None}


def buscar_hoteles(ciudad: str, entrada: str, salida: str, solicitud_id: int | None = None):
    """Devuelve (lista de hoteles, origen del dato)."""
    inicio, nombre, fallo = time.perf_counter(), f"hoteles_{_slug(ciudad)}_{entrada}_{salida}.json", None
    datos, origen_dato, clave = _leer(nombre), "guardado", nombre
    if datos is None and config.SERPAPI_KEY:
        try:
            datos = _consultar({"engine": "google_hotels", "q": f"{ciudad} hotels", "check_in_date": entrada,
                                "check_out_date": salida, "adults": 1, "gl": "us"},
                               "solicitud", solicitud_id, f"hoteles {ciudad} {entrada}")
            _guardar(nombre, datos)
            origen_dato = "en vivo"
        except Exception as e:
            datos, fallo = None, e
            _anotar("hoteles", nombre, "fallida", solicitud_id, inicio, error=e)
    if datos is None:
        otros = sorted(config.DIR_RESPALDO.glob(f"hoteles_{_slug(ciudad)}_*.json"))
        if otros:
            datos, origen_dato, clave = json.loads(otros[0].read_text()), "guardado (otras fechas)", otros[0].name
    if datos is None:
        if not fallo:
            _anotar("hoteles", nombre, "fallida", solicitud_id, inicio, error=SIN_DATOS)
        return [], "sin datos"
    if origen_dato != "en vivo":
        eventos.registrar("solicitud", solicitud_id, "lectura de respaldo", f"hoteles {ciudad}", origen_dato)
    hoteles = []
    for h in datos.get("properties", []):
        total = (h.get("total_rate") or {}).get("extracted_lowest")
        if h.get("type") != "hotel" or not total:
            continue
        noche = h.get("rate_per_night") or {}
        hoteles.append({
            "nombre": h["name"],
            "noche": noche.get("extracted_lowest"),
            "noche_sin_cargos": noche.get("extracted_before_taxes_fees"),
            "total": float(total),
            "calificacion": h.get("overall_rating"),
            "clase": h.get("extracted_hotel_class"),
            "vendedores": [p.get("source") for p in h.get("prices", []) if p.get("source")],
        })
    _anotar("hoteles", clave, origen_dato, solicitud_id, inicio, [h["total"] for h in hoteles])
    return hoteles, origen_dato
