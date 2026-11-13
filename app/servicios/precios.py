"""Precios de vuelos y hoteles.

Orden de búsqueda: respuesta guardada para la misma consulta, consulta en vivo si hay
clave, y como último recurso una respuesta guardada de la misma ruta con otras fechas.
Cada resultado dice de dónde salió: "en vivo", "guardado" o "guardado (otras fechas)".
Cada búsqueda, también la leída de lo guardado o la fallida, deja una fila en `consultas_buscador`.
"""
import base64
import json
import re
import time
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, quote, urlencode, urlsplit

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


def _guardar(nombre: str, datos: dict, archivo: bool = True):
    """Una respuesta pagada no se pierde: va a la tabla compartida. El archivo es una copia de conveniencia; las
    respuestas que solo valen en su momento (estado del vuelo, reconfirmación) no lo llevan, para no llenar la carpeta
    versionada de respaldos. Antes de guardarla se quita lo que serviría para ejecutar una reserva."""
    cuerpo = json.dumps(_sin_reserva(datos), ensure_ascii=False)
    db.insertar("busquedas", clave=nombre, cuerpo=cuerpo, creado=db.ahora())
    if not archivo:
        return
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


# ---------- enlace a la fuente: la misma búsqueda en Google Flights y Google Hotels ----------
DOMINIOS_FUENTE = frozenset({"www.google.com", "google.com"})


def es_fuente_google(url) -> bool:
    """Solo `https://www.google.com/travel/...`, sin credenciales ni puerto: lo único a lo que la plataforma enlaza."""
    if not isinstance(url, str):
        return False
    try:
        p = urlsplit(url)
        puerto = p.port
    except ValueError:
        return False
    return (p.scheme == "https" and p.hostname in DOMINIOS_FUENTE and puerto is None and not p.username
            and not p.password and p.path.startswith("/travel/"))


def _protobuf(campo: int, datos: bytes) -> bytes:
    """Un campo de longitud variable del formato que usa Google Flights en el parámetro `tfs`."""
    largo, n = b"", len(datos)
    while True:
        byte, n = n & 0x7F, n >> 7
        largo += bytes([byte | (0x80 if n else 0)])
        if not n:
            return bytes([campo << 3 | 2]) + largo + datos


def _tramo_tfs(fecha: str, desde: list[str], hasta: list[str]) -> bytes:
    aeropuerto = lambda c: b"\x08\x01" + _protobuf(2, c.encode())  # noqa: E731
    return _protobuf(3, _protobuf(2, fecha.encode()) + b"".join(_protobuf(13, aeropuerto(c)) for c in desde)
                     + b"".join(_protobuf(14, aeropuerto(c)) for c in hasta))


def construir_enlace_vuelos(origen: str | list[str], destino: str | list[str], ida: str, regreso: str) -> str:
    """La búsqueda de ida y vuelta, en clase económica y para una persona, como la arma el buscador en `google_flights_url`.
    Sirve cuando la respuesta guardada no lo trae."""
    o, d = codigos(origen), codigos(destino)
    tfs = b"\x08\x1c\x10\x02" + _tramo_tfs(ida, o, d) + _tramo_tfs(regreso, d, o) + b"\x40\x01\x48\x01\x70\x01\x98\x01\x01"
    return ("https://www.google.com/travel/flights?hl=en&gl=us&curr=USD&tfs="
            + base64.urlsafe_b64encode(tfs).decode().rstrip("=") + "&tfu=EgIIAQ")


_enlaces: dict[str, str] = {}   # lo leído de una respuesta guardada no cambia: no se vuelve a leer en cada comparación


def _enlace_guardado(nombre: str, campo: str) -> str | None:
    if nombre not in _enlaces:
        try:
            url = ((_leer(nombre) or {}).get("search_metadata") or {}).get(campo)
        except (ValueError, AttributeError):
            url = None
        if not es_fuente_google(url):
            return None
        _enlaces[nombre] = url
    return _enlaces[nombre]


def enlace_vuelos(origen: str | list[str], destino: str | list[str], ida: str, regreso: str) -> str:
    """La búsqueda exacta en Google Flights: la de la respuesta guardada de esas fechas o, si falta, una construida."""
    _, _, n_origen, n_destino = ruta(origen, destino)
    return (_enlace_guardado(f"vuelos_{n_origen}_{n_destino}_{ida}_{regreso}.json", "google_flights_url")
            or construir_enlace_vuelos(origen, destino, ida, regreso))


def enlace_hoteles(ciudad: str, entrada: str, salida: str, hotel: str | None = None) -> str:
    """La búsqueda en Google Hotels con sus fechas; con `hotel`, la del hotel en esa ciudad, para verlo primero.

    El buscador guarda un enlace sin fechas: se toma su texto de búsqueda y se le añaden las fechas, que Google lee del
    texto (comprobado el 13 de noviembre de 2026; los parámetros `checkin` y `checkout` los ignora)."""
    guardado = _enlace_guardado(f"hoteles_{_slug(ciudad)}_{entrada}_{salida}.json", "google_hotels_url")
    base, parametros = "https://www.google.com/travel/search", {"q": f"{ciudad} hotels", "hl": "en", "gl": "us"}
    if guardado:
        p = urlsplit(guardado)
        base, parametros = f"https://{p.hostname}{p.path}", {k: v[0] for k, v in parse_qs(p.query).items()}
    texto = f"{hotel}, {ciudad}" if hotel else parametros.get("q") or f"{ciudad} hotels"
    parametros["q"] = f"{texto} from {entrada} to {salida}"
    return f"{base}?{urlencode(parametros, quote_via=quote)}"


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


def _guardada(nombre: str) -> tuple:
    """(datos, origen del dato, clave) de la misma consulta ya pagada. Nunca la de otras fechas: el regreso y las
    opciones de reserva de otro día no describen el vuelo que se va a tomar."""
    datos = _leer(nombre)
    return (datos, "guardado", nombre) if datos is not None else (None, None, None)


def vuelo_regreso(vuelo_ida: dict, origenes: str | list[str], destinos: str | list[str], ida: str, regreso: str,
                  solicitud_id: int | None = None) -> dict | None:
    """El vuelo de regreso real de una opción de ida: una consulta con su `departure_token`.

    Se envían los mismos códigos que la búsqueda original, para aprovechar la caché del proveedor. De los regresos se
    toman los que salen del aeropuerto real de llegada de la ida y se elige el más barato. Orden: la misma consulta
    guardada (también la de «Traer tarifas» de antes, que guardaba regreso y reserva juntos, de las mismas fechas) →
    en vivo → nada. None sin token, sin clave ni respuesta guardada, si la consulta falla o si ningún regreso sale de
    ese aeropuerto."""
    origen, destino, n_origen, n_destino = ruta(origenes, destinos)
    clave = _clave_vuelo(vuelo_ida)
    inicio, nombre = time.perf_counter(), f"regreso_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json"
    datos, origen_dato, usada = _guardada(nombre)
    if datos is None:
        antiguo, origen_dato, usada = _guardada(f"tarifas_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json")
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
    datos, origen_dato, usada = _guardada(nombre)
    if datos is None:
        antiguo, origen_dato, usada = _guardada(f"tarifas_{n_origen}_{n_destino}_{ida}_{regreso}_{clave}.json")
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
        if not any(_leer(n) is not None for n in guardadas):
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
    if not vuelta:   # solo la ida sería el precio de otro itinerario (solo ida), no el del viaje decidido
        return {**sin, "motivo": "sin tramos del regreso"}
    fijado = {"outbound": ida, "return": vuelta}
    clave = "".join(s["flight_number"] for s in ida + vuelta)
    inicio = time.perf_counter()
    nombre = f"reconfirmacion_{clave}_{datetime.now(UTC):%Y%m%d%H%M}.json"
    try:
        datos = _consultar({"engine": "google_flights", "type": 1,
                            "selected_flights_json": json.dumps(fijado, separators=(",", ":"))},
                           "solicitud", decision.get("solicitud_id"), f"reconfirmación del precio de {clave}")
        _guardar(nombre, datos, archivo=False)
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
    return {"estado": "confirmado" if abs(ahora - float(antes)) < 0.005 else "cambio", "antes": float(antes), "ahora": ahora,
            "variacion": round(variacion, 4), "motivo": None}


# ---------- estado del vuelo el día del viaje ----------
_ESTADOS = (("cancel", "cancelado"), ("divert", "desviado"), ("land", "aterrizado"), ("arrived", "aterrizado"),
            ("delay", "retrasado"), ("late", "retrasado"), ("scheduled", "programado"))


def _vacio(valor) -> str | None:
    """El proveedor escribe «-» cuando no hay dato (puerta o terminal sin asignar)."""
    valor = (str(valor).strip() if valor is not None else "")
    return None if valor in ("", "-", "—") else valor


def _fecha_bloque(texto: str | None, referencia: date) -> date | None:
    """«Sun, Dec 13» sin año: el año es el de la fecha del vuelo (o el siguiente si el vuelo cruza el fin de año)."""
    try:
        dia = datetime.strptime((texto or "").split(",")[-1].strip(), "%b %d").date()
    except ValueError:
        return None
    candidato = dia.replace(year=referencia.year)
    return candidato.replace(year=referencia.year + 1) if candidato < referencia - timedelta(days=180) else candidato


def _hora_bloque(texto: str | None) -> datetime | None:
    try:
        return datetime.strptime(_vacio(texto) or "", "%I:%M %p")
    except ValueError:
        return None


def _minutos_tarde(lado: dict) -> int | None:
    plan, real = _hora_bloque(lado.get("planned_time")), _hora_bloque(lado.get("actual_time"))
    if not plan or not real:
        return None
    minutos = int((real - plan).total_seconds() // 60)
    return minutos + 1440 if minutos < -720 else minutos - 1440 if minutos > 720 else minutos   # cruza la medianoche


def _hora_estimada(lado: dict, dia: date | None) -> str | None:
    hora = _hora_bloque(lado.get("actual_time")) or _hora_bloque(lado.get("planned_time"))
    if not hora or not dia:
        return None
    plan = _hora_bloque(lado.get("planned_time"))
    if plan and hora - plan < timedelta(hours=-12):   # la hora real pasó la medianoche
        dia = dia + timedelta(days=1)
    return f"{dia.isoformat()} {hora:%H:%M}"


def _estado_texto(texto: str, retraso: int | None) -> str:
    bajo = (texto or "").lower()
    estado = next((e for clave, e in _ESTADOS if clave in bajo), None)
    if estado:
        return estado
    return "retrasado" if (retraso or 0) >= 15 else "a tiempo"


def _bloque_estado(datos: dict, numero: str, fecha: str) -> dict | None:
    """El vuelo pedido dentro del bloque `answer_box` de tipo `flight_status`, si es de esa fecha."""
    caja = datos.get("answer_box") or {}
    if not isinstance(caja, dict) or caja.get("type") != "flight_status":
        return None
    candidatos = caja.get("flights") if isinstance(caja.get("flights"), list) else [caja]
    vuelo = next((v for v in candidatos if isinstance(v, dict)
                  and (v.get("flight_number") or "").replace(" ", "").upper() == numero), None)
    if not vuelo:
        return None
    salida, llegada = vuelo.get("departure") or {}, vuelo.get("arrival") or {}
    dia = date.fromisoformat(fecha)
    if _fecha_bloque(salida.get("date"), dia) != dia:
        return None
    r_salida, r_llegada = _minutos_tarde(salida), _minutos_tarde(llegada)
    return {"estado": _estado_texto(vuelo.get("flight_status"), max(r_salida or 0, r_llegada or 0)),
            "texto_estado": vuelo.get("flight_status"), "retraso_salida": r_salida, "retraso_llegada": r_llegada,
            "terminal_salida": _vacio(salida.get("terminal")), "puerta_salida": _vacio(salida.get("gate")),
            "terminal_llegada": _vacio(llegada.get("terminal")), "puerta_llegada": _vacio(llegada.get("gate")),
            "sale_estimada": _hora_estimada(salida, dia),
            "llega_estimada": _hora_estimada(llegada, _fecha_bloque(llegada.get("date"), dia) or dia)}


SIN_BLOQUE = "La respuesta no trae el bloque del vuelo para esa fecha (número inexistente o fecha fuera de rango)."


def estado_vuelo(numero: str, fecha: str, solicitud_id: int | None = None) -> dict | None:
    """Estado de un vuelo el día del viaje: motor `google` con `q = "Flight IB5634"` (Google Direct Answer Box API).

    Campos que se leen, según la documentación del proveedor (https://serpapi.com/direct-answer-box-api, ejemplos
    «Flight status answer box» y «Multiple flight statuses answer box», consultada el 12 de noviembre de 2026):
    `answer_box.type == "flight_status"`; `flight_number`, `flight_status` (texto libre: «Arriving late», «Arrived»,
    «Runway delay»...) y `departure` / `arrival` con `airport_name`, `planned_time` y `actual_time` («12:15 PM», hora
    local), `terminal`, `gate` («-» si no hay) y `date` («Tue, Jul 16», sin año). Con varios vuelos el bloque trae la
    lista `flights`. El proveedor no da los minutos de retraso: se calculan como hora real menos hora programada.

    La respuesta de ejemplo `datos/respaldo/estado_vuelo_IB5634_2026-12-13.json` se construyó a mano con esa forma
    (sin clave en este entorno no se hizo una consulta real); la respuesta real la obtiene quien integra.

    Con clave siempre se consulta en vivo (el estado cambia) y la respuesta se guarda con la hora en la clave; sin
    clave, o si la consulta falla, se usa la respuesta guardada de ese vuelo y fecha. Cada consulta deja su fila en
    `consultas_buscador` con tipo `estado_vuelo`. Devuelve {"estado", "retraso_salida", "retraso_llegada",
    "terminal_salida", "puerta_salida", "terminal_llegada", "puerta_llegada", "sale_estimada", "llega_estimada"} más
    "texto_estado" y "origen"; None si no hay respuesta o si no trae el bloque del vuelo para esa fecha."""
    compacto = numero.replace(" ", "").upper()
    inicio, fallo = time.perf_counter(), None
    guardado = f"estado_vuelo_{compacto}_{fecha}.json"
    datos, origen_dato, clave = None, "guardado", guardado
    if config.SERPAPI_KEY:
        nombre = f"estado_vuelo_{compacto}_{fecha}_{datetime.now(UTC):%H%M}.json"
        try:
            datos = _consultar({"engine": "google", "q": f"Flight {compacto}", "gl": "us"},
                               "solicitud", solicitud_id, f"estado del vuelo {numero} {fecha}")
            _guardar(nombre, datos, archivo=False)
            origen_dato, clave = "en vivo", nombre
        except Exception as e:
            datos, fallo = None, e
            _anotar("estado_vuelo", nombre, "fallida", solicitud_id, inicio, error=e)
    if datos is None:
        datos = _leer(guardado)
    if datos is None:
        if not fallo:
            _anotar("estado_vuelo", guardado, "fallida", solicitud_id, inicio, error=SIN_DATOS)
        return None
    r = _bloque_estado(datos, compacto, fecha)
    _anotar("estado_vuelo", clave, origen_dato, solicitud_id, inicio, error=None if r else SIN_BLOQUE)
    return {**r, "origen": origen_dato} if r else None


def _hoteles_con_otro_nombre(nombres, entrada: str, salida: str):
    """Respuesta guardada con otro nombre del mismo lugar («Lisbon» elegido en la lista, «lisboa» en el archivo).
    Primero las mismas fechas (archivo o tabla compartida) y después otras fechas (solo archivos). Devuelve (datos,
    clave, mismas fechas) o None."""
    slugs = [s for s in dict.fromkeys(_slug(n) for n in nombres) if s]
    if not slugs:
        return None
    archivos = {p.name for p in config.DIR_RESPALDO.glob("hoteles_*.json")}
    claves = archivos | {f["clave"] for f in db.todos("select distinct clave from busquedas where clave like 'hoteles_%'")}
    for s in slugs:
        if (clave := f"hoteles_{s}_{entrada}_{salida}.json") in claves and (datos := _leer(clave)) is not None:
            return datos, clave, True
    fechas = re.compile(r"\d{4}-\d\d-\d\d_\d{4}-\d\d-\d\d\.json")
    for s in slugs:
        otros = sorted(a for a in archivos if a.startswith(f"hoteles_{s}_") and fechas.fullmatch(a[len(f"hoteles_{s}_"):]))
        if otros:
            return json.loads((config.DIR_RESPALDO / otros[0]).read_text()), otros[0], False
    return None


def buscar_hoteles(ciudad: str, entrada: str, salida: str, solicitud_id: int | None = None, otros_nombres=()):
    """Devuelve (lista de hoteles, origen del dato). `otros_nombres` son los alternos del lugar elegido: solo se usan
    para encontrar una respuesta guardada cuando no hay consulta en vivo; la consulta en vivo usa `ciudad`."""
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
    if datos is None and (otro := _hoteles_con_otro_nombre([ciudad, *otros_nombres], entrada, salida)):
        datos, clave, mismas_fechas = otro
        origen_dato = "guardado" if mismas_fechas else "guardado (otras fechas)"
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
