"""Rutas frecuentes y sus precios: qué rutas se cotizan y viajan más y qué dicen los precios vistos de cada una.

Las cifras salen de lo que la plataforma ya guardó (observaciones del buscador, historial de la ruta y tarifas vistas),
depurado con `ofertas.depurar`. Son descriptivas: la señal compara el precio visto más reciente con el rango habitual
de la ruta y no promete lo que pasará.
"""
import re
from datetime import date, timedelta
from statistics import median, quantiles

from .. import db
from . import ofertas

TRAMOS = (("0-7", 0, 7), ("8-21", 8, 21), ("22-45", 22, 45), ("46+", 46, None))
DIAS = 90
UMBRAL_TENDENCIA = 5        # % de cambio entre la primera y la segunda mitad del historial para decir que sube o baja
MINIMO_RANGO_PROPIO = 5     # precios vistos para usar el rango propio de la ruta en vez del típico de Google


def tramo(dias: int | None) -> str | None:
    if dias is None:
        return None
    return next(n for n, desde, hasta in TRAMOS if dias >= desde and (hasta is None or dias <= hasta))


def _codigo(valor: str | None) -> str | None:
    """El código del aeropuerto de una cotización: «MIA» o «Miami (MIA)»; con varios, el primero."""
    if not valor:
        return None
    v = valor.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", v):
        return v
    m = re.search(r"\(([A-Z]{3})\)", valor) or re.match(r"([A-Z]{3})[,\-]", v)
    return m.group(1) if m else None


def _redondo(x, n=2):
    return None if x is None else round(float(x), n)


def senal(reciente: float | None, precios: list[float], tipico: tuple | None = None) -> dict:
    """«por debajo», «dentro» o «por encima» del rango habitual: el propio (percentiles 25 a 75) si hay suficientes
    precios vistos, si no el rango típico que informa Google. Orientativa: describe, no predice."""
    if reciente is None:
        return {"valor": "sin datos", "referencia": None, "rango": None}
    if len(precios) >= MINIMO_RANGO_PROPIO:
        q = quantiles(precios, n=4, method="inclusive")
        rango, referencia = (q[0], q[2]), "rango propio (p25–p75)"
    elif tipico and tipico[0] and tipico[1]:
        rango, referencia = (float(tipico[0]), float(tipico[1])), "rango típico de Google"
    else:
        return {"valor": "sin datos", "referencia": None, "rango": None}
    valor = "por debajo" if reciente < rango[0] else "por encima" if reciente > rango[1] else "dentro"
    return {"valor": valor, "referencia": referencia, "rango": [_redondo(rango[0]), _redondo(rango[1])], "precio": _redondo(reciente)}


def _tendencia(origen: str, destino: str) -> dict | None:
    """Cambio entre la primera y la segunda mitad del historial diario de la ruta (precio más bajo de cada día)."""
    puntos = db.todos("select fecha, min(precio) precio from historial_ruta where origen=:o and destino=:d group by fecha order by fecha",
                      o=origen, d=destino)
    if len(puntos) < 4:
        return None
    mitad = len(puntos) // 2
    antes, despues = median(p["precio"] for p in puntos[:mitad]), median(p["precio"] for p in puntos[mitad:])
    cambio = round((despues - antes) / antes * 100, 1) if antes else 0.0
    return {"cambio_pct": cambio, "sentido": "sube" if cambio > UMBRAL_TENDENCIA else "baja" if cambio < -UMBRAL_TENDENCIA else "estable"}


def _por_itinerario(tarifas: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for t in tarifas:
        grupos.setdefault(t["origen_fila"], []).append(t)
    return grupos


def prima_flexibilidad(tarifas: list[dict]) -> dict | None:
    """Cuánto más cuesta la tarifa con cambio gratis o maleta incluida frente a la básica del mismo itinerario y la misma
    fuente: la más barata de cada lado, mediana de los pares, en USD y en %."""
    usd, pct = [], []
    for grupo in _por_itinerario(tarifas).values():
        basicas = [t["precio"] for t in grupo if t["tarifa_normalizada"] == "basica"]
        flexibles = [t["precio"] for t in grupo if t["tarifa_normalizada"] in ("estandar", "flexible", "premium")
                     and (t.get("cambios") == "gratis" or t.get("maleta_usd") == 0)]
        if basicas and flexibles:
            b, f = min(basicas), min(flexibles)
            usd.append(f - b)
            pct.append((f - b) / b * 100)
    return {"usd": _redondo(median(usd)), "pct": _redondo(median(pct), 1), "pares": len(usd)} if usd else None


def aerolinea_agencia(tarifas: list[dict]) -> dict | None:
    """Precio más bajo de la aerolínea frente al de una agencia en el mismo itinerario; mediana de los pares."""
    pares = []
    for grupo in _por_itinerario(tarifas).values():
        propia = [t["precio"] for t in grupo if t.get("es_aerolinea") == 1]
        agencia = [t["precio"] for t in grupo if t.get("es_aerolinea") == 0]
        if propia and agencia:
            pares.append((min(propia), min(agencia)))
    if not pares:
        return None
    a, g = median(p[0] for p in pares), median(p[1] for p in pares)
    return {"aerolinea": _redondo(a), "agencia": _redondo(g), "diferencia_usd": _redondo(median(p[1] - p[0] for p in pares)),
            "pares": len(pares)}


def _cuentas(desde: str) -> dict[tuple, dict]:
    cuentas: dict[tuple, dict] = {}
    for s in db.todos("select origen, destino, origen_aeropuertos, destino_aeropuertos from solicitudes where creado>=:d", d=desde):
        clave = (_codigo(s["origen_aeropuertos"] or s["origen"]), _codigo(s["destino_aeropuertos"] or s["destino"]))
        if all(clave):
            cuentas.setdefault(clave, {"cotizaciones": 0, "viajes": 0})["cotizaciones"] += 1
    for v in db.todos("""select s.origen, s.destino, s.origen_aeropuertos, s.destino_aeropuertos from viajes v
                         join solicitudes s on s.id=v.solicitud_id where v.creado>=:d""", d=desde):
        clave = (_codigo(v["origen_aeropuertos"] or v["origen"]), _codigo(v["destino_aeropuertos"] or v["destino"]))
        if all(clave):
            cuentas.setdefault(clave, {"cotizaciones": 0, "viajes": 0})["viajes"] += 1
    return cuentas


def detalle(origen: str, destino: str, tarifas: list[dict] | None = None) -> dict:
    """Las cifras de precio de una ruta."""
    obs, _ = ofertas.depurar(db.todos("select * from observaciones where origen=:o and destino=:d", o=origen, d=destino),
                             clave_repetida=("id",), grupo_atipico=("origen", "destino"))
    precios = [float(o["precio"]) for o in obs]
    por_tramo: dict[str, list[float]] = {}
    for o in obs:
        if (t := tramo(o.get("anticipacion"))) is not None:
            por_tramo.setdefault(t, []).append(float(o["precio"]))
    mediana = median(precios) if precios else None
    ultimo = max((o["capturado"] or "" for o in obs), default=None)
    recientes = [float(o["precio"]) for o in obs if (o["capturado"] or "") == ultimo]
    tipicos = [(o["tipico_min"], o["tipico_max"]) for o in obs if (o["capturado"] or "") == ultimo and o.get("tipico_min")]
    if tarifas is None:
        tarifas, _ = ofertas.depurar(db.todos("select * from ofertas_tarifa where origen=:o and destino=:d", o=origen, d=destino))
    return {
        "observaciones": len(obs),
        "por_anticipacion": {n: _redondo(median(por_tramo[n])) for n, _, _ in TRAMOS if por_tramo.get(n)},
        "mediana": _redondo(mediana),
        "volatilidad": _redondo(median(abs(p - mediana) for p in precios)) if precios else None,
        "tendencia": _tendencia(origen, destino),
        "prima_flexibilidad": prima_flexibilidad(tarifas),
        "aerolinea_agencia": aerolinea_agencia(tarifas),
        "senal": senal(median(recientes) if recientes else None, precios, tipicos[0] if tipicos else None),
    }


def top(n: int = 10, dias: int = DIAS, hoy: date | None = None) -> list[dict]:
    """Las `n` rutas con más cotizaciones y viajes en los últimos `dias`, con sus cifras de precio."""
    desde = ((hoy or date.today()) - timedelta(days=dias)).isoformat()
    cuentas = sorted(_cuentas(desde).items(), key=lambda x: (-(x[1]["cotizaciones"] + x[1]["viajes"]), x[0]))[:n]
    todas, _ = ofertas.limpias()
    salida = []
    for (origen, destino), c in cuentas:
        tarifas = [t for t in todas if t["origen"] == origen and t["destino"] == destino]
        salida.append({"ruta": f"{origen} → {destino}", "origen": origen, "destino": destino, **c, **detalle(origen, destino, tarifas)})
    return salida
