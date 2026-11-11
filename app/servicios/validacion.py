"""Reglas que deciden si un gasto entra solo o va a revisión humana."""
from .. import config, db
from . import costo

AGENCIAS = ("booking", "expedia", "hotels.com", "travelnow", "agoda", "priceline", "kayak", "trip.com")


def a_usd(total, moneda, cat: dict):
    if total is None or not moneda:
        return None
    if moneda == "USD":
        return round(total, 2)
    tasa = cat.get(("supuesto", "", "", f"tasa_{moneda}_USD"))
    return round(total * float(tasa["valor"]), 2) if tasa else None


def revisar(g: dict, proyecto: dict | None, gasto_id: int | None = None) -> dict:
    """Devuelve {estado, alertas, total_usd}. `g` son los campos extraídos."""
    cat = costo.catalogo()
    alertas, bloquea = [], False

    for campo, nombre in (("comercio", "comercio"), ("fecha", "fecha"), ("total", "total"), ("moneda", "moneda")):
        if g.get(campo) in (None, ""):
            alertas.append(f"Falta {nombre}.")
            bloquea = True

    partes = [g.get(c) for c in ("subtotal", "impuesto", "propina")]
    if g.get("total") is not None and g.get("subtotal") is not None:
        suma = sum(p or 0 for p in partes)
        if abs(suma - g["total"]) > 0.02:
            alertas.append(f"El total ({g['total']:.2f}) no coincide con subtotal + impuesto + propina ({suma:.2f}).")
            bloquea = True

    if g.get("dudas"):
        alertas.append("Campos poco legibles: " + ", ".join(g["dudas"]) + ".")
    if (g.get("confianza") or 0) < config.UMBRAL_CONFIANZA:
        alertas.append(f"Confianza de lectura {g.get('confianza') or 0:.0%}, por debajo del {config.UMBRAL_CONFIANZA:.0%}.")
        bloquea = True

    if not proyecto:
        alertas.append("Sin proyecto asignado.")
        bloquea = True
    elif g.get("fecha") and proyecto.get("fecha_inicio") and proyecto.get("fecha_fin"):
        if not (proyecto["fecha_inicio"] <= g["fecha"] <= proyecto["fecha_fin"]):
            # Los tiquetes se compran antes del viaje: solo avisa, no bloquea
            if g.get("categoria") == "vuelo" and g["fecha"] < proyecto["fecha_inicio"]:
                alertas.append("Comprado antes de las fechas del proyecto (normal en tiquetes).")
            else:
                alertas.append(f"La fecha {g['fecha']} está fuera del proyecto ({proyecto['fecha_inicio']} a {proyecto['fecha_fin']}).")
                bloquea = True

    total_usd = a_usd(g.get("total"), g.get("moneda"), cat)
    if g.get("total") is not None and g.get("moneda") and total_usd is None:
        alertas.append(f"No hay tasa de cambio configurada para {g['moneda']}.")
        bloquea = True

    if g.get("comercio") and g.get("fecha") and g.get("total") is not None:
        repetido = db.uno(
            "select id from gastos where lower(comercio)=lower(:c) and fecha=:f and total=:t and id<>:i and estado<>'rechazado'",
            c=g["comercio"], f=g["fecha"], t=g["total"], i=gasto_id or 0)
        if repetido:
            alertas.append(f"Posible duplicado del gasto #{repetido['id']}.")
            bloquea = True

    canal = (g.get("canal_reserva") or "").lower()
    if g.get("categoria") == "hotel" and any(a in canal for a in AGENCIAS):
        alertas.append(f"Fidelización: reservado por {g['canal_reserva']}; esta estadía no acumula puntos en el programa del hotel.")

    return {"estado": "revision" if bloquea else "aprobado_auto", "alertas": alertas, "total_usd": total_usd}
