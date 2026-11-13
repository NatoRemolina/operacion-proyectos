"""Costo total esperado de una opción de viaje.

    costo = precio + equipaje + (probabilidad de cambio x costo de cambiar)
            - valor de lo acumulado + traslado por carretera entre el aeropuerto y el lugar

Cada línea del desglose dice de dónde salió el número: "buscador", "regla" o "supuesto".
"""
import re
import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer

from .. import db
from . import geografia

# Membresía inventada para la demostración: la siembra la marca y las pantallas la rotulan «Dato de ejemplo»
db.membresias.append_column(Column("ejemplo", Integer))


def catalogo() -> dict:
    """Reglas indexadas por (ámbito, entidad, tarifa, clave)."""
    return {(r["ambito"], r["entidad"] or "", r["tarifa"] or "", r["clave"]): r for r in db.todos_cache("select * from reglas")}


def _regla(cat: dict, ambito: str, entidad: str, tarifa: str, clave: str):
    return cat.get((ambito, entidad, tarifa, clave)) or cat.get((ambito, entidad, "", clave))


def _numero(regla: dict | None, defecto: float) -> float:
    """Valor numérico de una regla; si falta o está mal escrito, el supuesto general. Nunca rompe una comparación."""
    try:
        return float(regla["valor"]) if regla else defecto
    except (TypeError, ValueError):
        return defecto


def supuesto(cat: dict, clave: str, defecto: float) -> float:
    r = cat.get(("supuesto", "", "", clave))
    try:
        return float(r["valor"]) if r else defecto
    except ValueError:
        return defecto


def baterias(n: int, wh: float) -> dict:
    """Clasifica las baterías de repuesto según los límites para pasajeros."""
    if not n or not wh:
        return {"nivel": "ok", "texto": "Sin baterías de repuesto declaradas."}
    if wh > 160:
        return {"nivel": "bloqueo", "texto": f"Baterías de {wh:g} Wh: superan 160 Wh y no pueden viajar con el pasajero. "
                                             "Hay que enviarlas por carga o alquilar en destino."}
    if wh > 100:
        extra = " Solo se permiten dos de repuesto." if n > 2 else ""
        return {"nivel": "aviso", "texto": f"Baterías de {wh:g} Wh: requieren aprobación previa de la aerolínea y van en cabina.{extra}",
                "bloquea": n > 2}
    return {"nivel": "ok", "texto": f"{n} baterías de {wh:g} Wh: permitidas en cabina sin trámite. Nunca en bodega."}


def _es_basica(nombre: str) -> bool:
    return "basic" in nombre.lower()


def tarifa_supuesta(vuelo: dict, cat: dict) -> dict:
    """Cuando el buscador no dio las tarifas, se asume la básica de la aerolínea según el catálogo, corregida con las
    condiciones que el buscador ya trae en el itinerario (`extensions`): cambio gratis o con cargo, maleta incluida, reembolso."""
    a = vuelo["aerolinea"]
    mano = _regla(cat, "aerolinea", a, "basica", "equipaje_mano")
    costo_mano = _regla(cat, "aerolinea", a, "basica", "costo_equipaje_mano")
    maleta = _regla(cat, "aerolinea", a, "basica", "costo_maleta")
    incluye = (mano["valor"] == "si") if mano else True
    texto = " ".join(vuelo.get("notas") or []).lower()
    cambio_gratis = "free change" in texto
    cambio_con_cargo = "changes for a fee" in texto or "change for a fee" in texto
    maleta_incluida = "checked bag included" in texto or "checked bags included" in texto
    return {
        "nombre": "Tarifa más baja (supuesta)", "precio": float(vuelo["precio"]), "vende": a,
        "mano": 0 if incluye else _numero(costo_mano, supuesto(cat, "costo_equipaje_mano", 70)),
        "maleta": 0 if maleta_incluida else _numero(maleta, supuesto(cat, "costo_maleta", 80)),
        "maleta_origen": "buscador" if maleta_incluida else None,
        "permite_cambio": (cambio_gratis or cambio_con_cargo) and "no ticket changes" not in texto,
        "cargo_cambio": supuesto(cat, "costo_cambio_usd", 75) if cambio_con_cargo and not cambio_gratis else 0,
        "reembolsable": "full refund" in texto, "notas": vuelo.get("notas", []), "equipaje": [],
        "supuesta": True, "regla_mano": bool(mano),
    }


def _horas_texto(horas: float) -> str:
    return "menos de 1 h" if horas < 1 else f"unas {round(horas)} h"


def traslado(aeropuerto: dict | None, lugar: dict | None, con_carro: bool, cat: dict, hacia_aeropuerto: bool = False) -> dict | None:
    """Traslado por carretera entre un aeropuerto y el lugar, ida y vuelta. None si falta el lugar o las coordenadas, o si
    el aeropuerto está a menos del mínimo (se trata como el traslado de cualquier ciudad, sin línea extra).

    Sin carro es taxi o transfer (grupo `traslados`); con carro de alquiler el carro ya cubre el viaje y solo se suman
    combustible y peajes (grupo `combustible`). Así nada se cuenta dos veces."""
    if not aeropuerto or not lugar or aeropuerto.get("lat") is None or lugar.get("lat") is None:
        return None
    recta = geografia.distancia_km(lugar["lat"], lugar["lon"], aeropuerto["lat"], aeropuerto["lon"])
    if recta < supuesto(cat, "traslado_minimo_km", 30):
        return None
    factor, velocidad = supuesto(cat, "factor_carretera", 1.3), supuesto(cat, "velocidad_carretera_kmh", 70) or 70
    usd_km = supuesto(cat, "combustible_usd_km", 0.12) if con_carro else supuesto(cat, "traslado_usd_km", 0.35)
    km = recta * factor
    horas = round(km / velocidad, 1)
    que = "Combustible y peajes" if con_carro else "Traslado por carretera"
    return {"iata": aeropuerto.get("iata"), "km_carretera": round(km), "horas": horas, "valor": round(km * usd_km * 2, 2),
            "concepto": f"{que} {'hasta' if hacia_aeropuerto else 'desde'} {aeropuerto.get('iata')} ({round(km)} km, {_horas_texto(horas)})",
            "grupo": "combustible" if con_carro else "traslados",
            # De dónde sale la línea: reglas y valores usados, para poder rehacer la cuenta
            "calculo": {"km_linea_recta": round(recta, 1), "factor": factor, "km_carretera": round(km, 1), "velocidad_kmh": velocidad,
                        "horas": horas, "usd_km": usd_km, "ida_y_vuelta": True, "lugar": lugar.get("nombre"),
                        "reglas": ["traslado_minimo_km", "factor_carretera", "velocidad_carretera_kmh",
                                   "combustible_usd_km" if con_carro else "traslado_usd_km"]}}


# Programa de viajero frecuente de cada aerolínea, para ofrecer la inscripción cuando la persona no es socia.
# Una regla («aerolinea», nombre, «programa») en el catálogo manda sobre esta lista.
PROGRAMAS_AEROLINEA = {
    "American": "AAdvantage", "United": "MileagePlus", "Delta": "SkyMiles", "Southwest": "Rapid Rewards",
    "JetBlue": "TrueBlue", "Alaska": "Mileage Plan", "Frontier": "Frontier Miles", "Spirit": "Free Spirit",
    "Iberia": "Iberia Club", "Vueling": "Vueling Club", "Air Europa": "SUMA", "Lufthansa": "Miles & More",
    "TAP Air Portugal": "TAP Miles&Go", "British Airways": "British Airways Club", "Air France": "Flying Blue",
    "KLM": "Flying Blue", "Avianca": "LifeMiles", "LATAM": "LATAM Pass", "Copa": "ConnectMiles",
}


def programa_aerolinea(aerolinea: str, cat: dict) -> str:
    regla = _regla(cat, "aerolinea", aerolinea, "", "programa")
    return (regla and regla["valor"]) or PROGRAMAS_AEROLINEA.get(aerolinea) or f"el programa de {aerolinea}"


def _lugar(valor) -> dict | None:
    """El lugar de la solicitud llega como texto JSON desde la base o ya como diccionario."""
    lugar = db.de_json(valor, None) if isinstance(valor, str) else valor
    return lugar if isinstance(lugar, dict) else None


def evaluar(vuelo: dict, tarifa: dict, sol: dict, membresias: list[dict], cat: dict) -> dict:
    """Desglose y costo esperado de un vuelo con una tarifa concreta."""
    aerolinea = vuelo["aerolinea"]
    origen_tarifa = "supuesto" if tarifa.get("supuesta") else "buscador"
    lineas = [{"concepto": f"Precio ({tarifa['nombre']})", "valor": tarifa["precio"], "origen": "buscador"}]
    avisos, descartada = [], None
    basica = tarifa.get("supuesta") or _es_basica(tarifa["nombre"])
    estatus = next((m for m in membresias if m["viajero_id"] and m["entidad"] == aerolinea and m["estatus"]), None)
    empresa = next((m for m in membresias if not m["viajero_id"] and m["entidad"] == aerolinea), None)

    # Equipaje de mano: obligatorio cuando viajan baterías
    lleva_equipo = (sol["baterias_n"] or 0) > 0
    if tarifa["mano"]:
        lineas.append({"concepto": "Equipaje de mano (el equipo va en cabina)", "valor": tarifa["mano"],
                       "origen": "regla" if tarifa.get("supuesta") else "buscador"})
        if lleva_equipo:
            avisos.append("Esta tarifa no incluye equipaje de mano y las baterías deben ir en cabina.")
    elif tarifa["mano"] is None and lleva_equipo:
        avisos.append("El buscador no informó si incluye equipaje de mano; confirmar antes de reservar.")

    # Maleta facturada
    if sol["maleta"]:
        beneficio = estatus and _regla(cat, "aerolinea", aerolinea, "", "estatus_maleta_gratis")
        if beneficio and beneficio["valor"] == "si":
            lineas.append({"concepto": f"Maleta facturada (gratis por estatus {estatus['estatus']})", "valor": 0.0, "origen": "regla"})
        elif tarifa["maleta"] is None:
            avisos.append("Costo de la maleta no informado.")
        else:
            lineas.append({"concepto": "Maleta facturada" + (" (incluida según el buscador)" if tarifa.get("maleta_origen") else ""),
                           "valor": tarifa["maleta"],
                           "origen": tarifa.get("maleta_origen") or (origen_tarifa if not tarifa.get("supuesta") else "regla")})

    # Riesgo de cambio de fecha
    prob = sol["prob_cambio"] or 0
    if prob:
        if tarifa["permite_cambio"]:
            dif, cargo = supuesto(cat, "diferencia_tarifa_cambio", 60), tarifa.get("cargo_cambio") or 0
            detalle = f"diferencia de tarifa estimada {dif:.0f}" + (f" + cargo por cambio {cargo:.0f}, según el buscador" if cargo else "")
            lineas.append({"concepto": f"Riesgo de cambio ({prob:.0%} x {detalle})",
                           "valor": round(prob * (dif + cargo), 2), "origen": "supuesto"})
        else:
            lineas.append({"concepto": f"Riesgo de cambio ({prob:.0%} x perder el tiquete)",
                           "valor": round(prob * tarifa["precio"], 2), "origen": "supuesto"})
            avisos.append("No admite cambios: si la grabación se mueve, se pierde el tiquete.")

    # Millas y cuenta de empresa: solo resta lo que de verdad se acumula (el viajero es socio o la empresa tiene cuenta)
    regla_acumula = _regla(cat, "aerolinea", aerolinea, "basica", "acumula") if basica else None
    acumula = not (regla_acumula and regla_acumula["valor"] == "no")
    if acumula:
        valor_milla, del_viajero = supuesto(cat, "valor_milla_usd", 0.012), supuesto(cat, "millas_por_usd", 5)
        socio = next((m for m in membresias if m["viajero_id"] and m["entidad"] == aerolinea), None)
        por_usd = (del_viajero if socio else 0) + (1 if empresa else 0)
        if por_usd:
            etiqueta = {(True, True): "Millas del viajero y de la cuenta de empresa", (True, False): "Millas del viajero",
                        (False, True): "Millas de la cuenta de empresa"}[(bool(socio), bool(empresa))]
            lineas.append({"concepto": f"{etiqueta} ({por_usd:g} por USD a {valor_milla} USD)",
                           "valor": -round(tarifa["precio"] * por_usd * valor_milla, 2), "origen": "supuesto"})
        if not socio:   # una oportunidad, no un ahorro: no resta hasta que la persona se inscriba
            n = round(tarifa["precio"] * del_viajero)
            avisos.append(f"Inscribirse en {programa_aerolinea(aerolinea, cat)} es gratis y acumularía "
                          f"~{_miles(n)} millas (≈ {n * valor_milla:.0f} USD).")
    elif basica:
        avisos.append("La tarifa básica de esta aerolínea no acumula millas.")

    # Traslado por carretera: del lugar de origen al aeropuerto real de salida y del de llegada al lugar de destino
    sale = traslado(geografia.aeropuerto(vuelo.get("desde")), _lugar(sol.get("origen_lugar")), False, cat, hacia_aeropuerto=True)
    llega = traslado(geografia.aeropuerto(vuelo.get("hasta")), _lugar(sol.get("destino_lugar")), (sol.get("carro_dia") or 0) > 0, cat)
    for t in (sale, llega):
        if t:
            lineas.append({"concepto": t["concepto"], "valor": t["valor"], "origen": "supuesto", "grupo": t["grupo"], "calculo": t["calculo"]})

    # Hora límite de llegada: con fecha y hora, porque el traslado puede cruzar la medianoche
    if sol.get("llegar_antes"):
        try:
            aterriza, limite = datetime.fromisoformat(vuelo["llega"].replace(" ", "T")), datetime.fromisoformat(sol["llegar_antes"])
            en_destino = aterriza + timedelta(hours=llega["horas"] if llega else 0)
            if aterriza > limite:
                descartada = f"Llega a las {vuelo['llega'][11:]}, después de la hora límite."
            elif en_destino > limite:
                descartada = f"Con el traslado llega a las {en_destino:%H:%M}, después de la hora límite."
            elif vuelo.get("a_menudo_retrasado") and en_destino + timedelta(minutes=30) > limite:
                avisos.append("Este vuelo suele retrasarse más de 30 minutos y con ese retraso llegaría después de la hora límite.")
        except (TypeError, ValueError):
            pass

    for e in vuelo.get("escalas_detalle") or []:
        if e.get("minutos") is not None and e["minutos"] < 60:
            avisos.append(f"Escala corta en {e.get('aeropuerto') or 'la conexión'} ({e['minutos']} min): riesgo de perder la conexión o el equipaje.")
        if e.get("nocturna"):
            avisos.append(f"Escala nocturna en {e.get('aeropuerto') or 'la conexión'}.")

    return {"tarifa": tarifa, "lineas": lineas, "total": round(sum(l["valor"] for l in lineas), 2),
            "avisos": avisos, "descartada": descartada}


def mejor_tarifa(vuelo: dict, tarifas: list[dict], sol: dict, membresias: list[dict], cat: dict) -> dict:
    """Evalúa todas las tarifas conocidas del vuelo y devuelve la de menor costo esperado."""
    candidatas = tarifas or [tarifa_supuesta(vuelo, cat)]
    evaluadas = sorted((evaluar(vuelo, t, sol, membresias, cat) for t in candidatas), key=lambda e: e["total"])
    mejor = dict(evaluadas[0])
    mejor["todas"] = evaluadas
    mejor["tarifas_reales"] = bool(tarifas)
    return mejor


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))


def programas_hotel(cat: dict) -> list[dict]:
    """Programas de fidelización de hoteles del catálogo: ámbito «hotel», una entidad por programa y sus marcas."""
    por_programa: dict[str, dict] = {}
    for (ambito, entidad, _t, clave), r in cat.items():
        if ambito == "hotel" and entidad:
            por_programa.setdefault(entidad, {})[clave] = r
    programas = []
    for nombre, reglas in por_programa.items():
        marcas = reglas.get("marcas")
        if not marcas:
            continue
        programas.append({
            "nombre": nombre, "marcas": [m.strip() for m in (marcas["valor"] or "").split(",") if m.strip()],
            "puntos_por_usd": _numero(reglas.get("puntos_por_usd"), 0), "valor_punto_usd": _numero(reglas.get("valor_punto_usd"), 0),
            "descuento_miembro": _numero(reglas.get("descuento_miembro"), 0),
            "fuente": marcas.get("fuente"), "confianza": marcas.get("confianza"), "verificado": marcas.get("verificado")})
    return programas


def programa_hotel(nombre: str, cat: dict) -> dict | None:
    """Programa del hotel según la marca que aparece en su nombre, sin distinguir mayúsculas ni tildes.
    Con dos marcas en el nombre («Holiday Inn Fairfield») manda la que aparece primero."""
    texto, mejor = _sin_tildes(nombre), None
    for p in programas_hotel(cat):
        for marca in p["marcas"]:
            m = _sin_tildes(marca)
            # una marca de una letra (W) solo cuenta al inicio: «Apartment w/ Patio» no es un hotel W
            hallado = re.search(rf"^{re.escape(m)}\b" if len(m) == 1 else rf"\b{re.escape(m)}s?\b", texto)
            if hallado and (mejor is None or (hallado.start(), -len(m)) < mejor[0]):
                mejor = ((hallado.start(), -len(m)), p)
    return mejor[1] if mejor else None


def _es_si(valor) -> bool:
    return _sin_tildes(str(valor or "")).strip() in ("si", "yes", "true", "1")


def evaluar_hotel(hotel: dict, membresias: list[dict], cat: dict, noches: int) -> dict:
    """Desglose y costo total de un hotel, espejo de `evaluar`. La tarifa de miembro y los puntos restan solo si hay
    membresía de ese programa (del viajero o de la empresa) o si el supuesto `inscripcion_gratis_hotel` vale «sí»;
    sin ninguna de las dos, inscribirse queda como oportunidad en los avisos."""
    tarifa = float(hotel.get("total") or (hotel.get("noche") or 0) * noches)
    lineas = [{"concepto": f"Tarifa total ({noches} noche{'' if noches == 1 else 's'})", "valor": tarifa, "origen": "buscador"}]
    avisos = []
    p = programa_hotel(hotel.get("nombre") or "", cat)
    membresia = next((m for m in membresias if p and _sin_tildes(m.get("entidad") or "") == _sin_tildes(p["nombre"])), None)
    socio = bool(membresia)
    if p:
        supone = not socio and _es_si((cat.get(("supuesto", "", "", "inscripcion_gratis_hotel")) or {}).get("valor"))
        descuento, por_usd, valor_punto = p["descuento_miembro"], p["puntos_por_usd"], p["valor_punto_usd"]
        pagado = round(tarifa * (1 - descuento), 2)
        if socio or supone:
            if descuento:
                lineas.append({"concepto": f"Tarifa de miembro (−{descuento * 100:g} %)", "valor": -round(tarifa * descuento, 2),
                               "origen": "supuesto"})
            if por_usd and valor_punto:
                lineas.append({"concepto": f"Puntos del programa ({por_usd:g} por USD a {valor_punto:g} USD)",
                               "valor": -round(pagado * por_usd * valor_punto, 2), "origen": "supuesto"})
        if supone:
            avisos.append(f"Supone que el viajero se inscribe gratis en {p['nombre']} al reservar (regla «inscripcion_gratis_hotel»).")
        avisos.append("Acumula solo con reserva directa.")
        if not socio and not supone:
            n = round(pagado * por_usd)
            avisos.append(f"Inscribirse en {p['nombre']} es gratis: tarifa de miembro (−{descuento * 100:g} %) y "
                          f"~{_miles(n)} puntos (≈ {n * valor_punto:.0f} USD) en esta estadía.")
    # Sin calificación no se descarta: falta el dato, no es un mal hotel
    minima, calificacion = supuesto(cat, "hotel_calificacion_minima", 3.5), hotel.get("calificacion")
    descartado = (f"Calificación {calificacion:.1f}, por debajo del mínimo de {minima:g}."
                  if calificacion is not None and minima and calificacion < minima else None)
    return {"programa": p["nombre"] if p else None, "socio": socio, "membresia_de_ejemplo": bool(membresia and membresia.get("ejemplo")),
            "tarifa": tarifa, "lineas": lineas,
            "total": round(sum(l["valor"] for l in lineas), 2), "avisos": avisos, "descartado": descartado}


def noches(ida: str, regreso: str) -> int:
    return max((datetime.fromisoformat(regreso) - datetime.fromisoformat(ida)).days, 1)
