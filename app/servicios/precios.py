"""Precios de vuelos y hoteles.

Orden de búsqueda: respuesta guardada para la misma consulta, consulta en vivo si hay
clave, y como último recurso una respuesta guardada de la misma ruta con otras fechas.
Cada resultado dice de dónde salió: "en vivo", "guardado" o "guardado (otras fechas)".
"""
import json
import re
from datetime import date, datetime, timezone

import httpx

from .. import config, db
from . import eventos

URL = "https://serpapi.com/search.json"


_cupo = {"momento": None, "dato": None}


def cupo() -> dict | None:
    """Búsquedas que quedan en el plan del buscador. Consultarlo no gasta cupo; se recuerda diez minutos."""
    if not config.SERPAPI_KEY:
        return None
    ahora = datetime.now(timezone.utc)
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


def _guardar(nombre: str, datos: dict):
    """Una respuesta pagada no se pierde: va a la tabla compartida. El archivo es una copia de conveniencia."""
    cuerpo = json.dumps(datos, ensure_ascii=False)
    db.insertar("busquedas", clave=nombre, cuerpo=cuerpo, creado=db.ahora())
    try:
        config.DIR_RESPALDO_ESCRITURA.mkdir(parents=True, exist_ok=True)
        (config.DIR_RESPALDO_ESCRITURA / nombre).write_text(cuerpo)
    except OSError:
        pass  # disco de solo lectura: la tabla ya lo tiene


def _consultar(parametros: dict, entidad: str, entidad_id: int | None, que: str) -> dict:
    with eventos.cronometro() as t:
        r = httpx.get(URL, params={**parametros, "api_key": config.SERPAPI_KEY, "hl": "en", "currency": "USD"}, timeout=60)
        datos = r.json()
    if "error" in datos:
        eventos.registrar(entidad, entidad_id, "consulta externa fallida", f"{que}: {datos['error']}", "SerpApi", t())
        raise RuntimeError(datos["error"])
    eventos.registrar(entidad, entidad_id, "consulta externa", que, "SerpApi (en vivo)", t())
    return datos


def _vuelo(f: dict) -> dict:
    tramos = f["flights"]
    return {
        "aerolinea": tramos[0]["airline"],
        "aerolineas": sorted({s["airline"] for s in tramos}),
        "numeros": [s["flight_number"] for s in tramos],
        "sale": tramos[0]["departure_airport"]["time"],
        "llega": tramos[-1]["arrival_airport"]["time"],
        "desde": tramos[0]["departure_airport"]["id"],
        "hasta": tramos[-1]["arrival_airport"]["id"],
        "escalas": len(tramos) - 1,
        "duracion_min": f.get("total_duration"),
        "precio": f.get("price"),
        "notas": f.get("extensions", []),
        "token": f.get("departure_token"),
    }


def registrar_observaciones(datos: dict, origen: str, destino: str, ida: str, regreso: str, fuente: str) -> int:
    """Guarda cada vuelo de una respuesta del buscador como fila tabular. No duplica una búsqueda ya registrada."""
    clave = f"{origen}_{destino}_{ida}_{regreso}"
    if db.uno("select id from observaciones where busqueda=:b limit 1", b=clave):
        return 0
    capturado = (datos.get("search_metadata", {}).get("created_at") or db.ahora())[:10]
    info = datos.get("price_insights", {})
    tipico = info.get("typical_price_range") or [None, None]
    f_ida = date.fromisoformat(ida)
    filas = []
    for f in datos.get("best_flights", []) + datos.get("other_flights", []):
        if not f.get("price"):
            continue
        v = _vuelo(f)
        filas.append({
            "busqueda": clave, "origen": origen, "destino": destino, "ida": ida, "regreso": regreso,
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
         "fecha": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"), "precio": float(precio)}
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


def buscar_vuelos(origen: str, destino: str, ida: str, regreso: str, solicitud_id: int | None = None):
    """Devuelve (lista de vuelos, origen del dato, información de precios de la ruta)."""
    nombre = f"vuelos_{origen}_{destino}_{ida}_{regreso}.json"
    datos, origen_dato = _leer(nombre), "guardado"
    if datos is None and config.SERPAPI_KEY:
        try:
            datos = _consultar({"engine": "google_flights", "departure_id": origen, "arrival_id": destino,
                                "outbound_date": ida, "return_date": regreso},
                               "solicitud", solicitud_id, f"vuelos {origen}-{destino} {ida}")
            _guardar(nombre, datos)
            origen_dato = "en vivo"
        except Exception:
            datos = None
    if datos is None:
        otros = sorted(config.DIR_RESPALDO.glob(f"vuelos_{origen}_{destino}_*.json"))
        if otros:
            datos, origen_dato = json.loads(otros[0].read_text()), "guardado (otras fechas)"
    if datos is None:
        return [], "sin datos", {}
    if origen_dato != "en vivo":
        eventos.registrar("solicitud", solicitud_id, "lectura de respaldo", f"vuelos {origen}-{destino}", origen_dato)
    if origen_dato in ("en vivo", "guardado"):
        registrar_observaciones(datos, origen, destino, ida, regreso, "formulario" if solicitud_id else "recolector")
    vuelos = [_vuelo(f) for f in datos.get("best_flights", []) + datos.get("other_flights", []) if f.get("price")]
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


def tarifas_de_vuelo(origen: str, destino: str, ida: str, regreso: str, vuelo: dict,
                     solicitud_id: int | None = None, permitir_en_vivo: bool = False):
    """Familias tarifarias de un vuelo (dos consultas en vivo). Devuelve (tarifas, origen del dato)."""
    clave = "".join(n.replace(" ", "") for n in vuelo["numeros"])
    nombre = f"tarifas_{origen}_{destino}_{ida}_{regreso}_{clave}.json"
    datos, origen_dato = _leer(nombre), "guardado"
    if datos is None:
        otros = sorted(config.DIR_RESPALDO.glob(f"tarifas_{origen}_{destino}_*_{clave}.json"))
        if otros:
            datos, origen_dato = json.loads(otros[0].read_text()), "guardado (otras fechas)"
    if datos is None and permitir_en_vivo and config.SERPAPI_KEY and vuelo.get("token"):
        base = {"engine": "google_flights", "departure_id": origen, "arrival_id": destino,
                "outbound_date": ida, "return_date": regreso}
        try:
            vuelta = _consultar({**base, "departure_token": vuelo["token"]}, "solicitud", solicitud_id, f"regreso para {clave}")
            candidatos = vuelta.get("best_flights", []) + vuelta.get("other_flights", [])
            reserva = _consultar({**base, "booking_token": candidatos[0]["booking_token"]},
                                 "solicitud", solicitud_id, f"tarifas de {clave}")
            datos, origen_dato = {"regreso": vuelta, "reserva": reserva}, "en vivo"
            _guardar(nombre, datos)
        except Exception:
            datos = None
    if datos is None:
        return [], "sin datos"
    tarifas = [t for t in (_tarifa(o) for o in datos["reserva"].get("booking_options", [])) if t]
    return tarifas, origen_dato


def buscar_hoteles(ciudad: str, entrada: str, salida: str, solicitud_id: int | None = None):
    """Devuelve (lista de hoteles, origen del dato)."""
    nombre = f"hoteles_{_slug(ciudad)}_{entrada}_{salida}.json"
    datos, origen_dato = _leer(nombre), "guardado"
    if datos is None and config.SERPAPI_KEY:
        try:
            datos = _consultar({"engine": "google_hotels", "q": f"{ciudad} hotels", "check_in_date": entrada,
                                "check_out_date": salida, "adults": 1, "gl": "us"},
                               "solicitud", solicitud_id, f"hoteles {ciudad} {entrada}")
            _guardar(nombre, datos)
            origen_dato = "en vivo"
        except Exception:
            datos = None
    if datos is None:
        otros = sorted(config.DIR_RESPALDO.glob(f"hoteles_{_slug(ciudad)}_*.json"))
        if otros:
            datos, origen_dato = json.loads(otros[0].read_text()), "guardado (otras fechas)"
    if datos is None:
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
    return hoteles, origen_dato
