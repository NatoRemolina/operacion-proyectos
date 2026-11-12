"""Reglas que deciden si un gasto entra solo o va a revisión humana."""
import re
from datetime import date, timedelta

from .. import config, db
from . import costo

AGENCIAS = ("booking", "expedia", "hotels.com", "travelnow", "agoda", "priceline", "kayak", "trip.com")


MOTIVOS = {"campo_faltante": "Campo faltante", "total_no_cuadra": "El total no cuadra", "ilegible": "Lectura poco confiable",
           "sin_proyecto": "Sin proyecto", "fuera_de_fechas": "Fecha fuera del proyecto", "sin_tasa": "Moneda sin tasa de cambio",
           "duplicado": "Posible duplicado", "duplicado_aproximado": "Parecido a otro gasto", "atipico": "Importe atípico",
           "sin_puntos": "Fidelización perdida", "compra_anticipada": "Compra anticipada", "lectura_fallida": "Lectura fallida"}


class _Alertas(list):
    """Lista de textos que además recuerda el código de cada alerta."""

    def __init__(self):
        super().__init__()
        self.codigos: list[str] = []

    def agregar(self, codigo: str, texto: str):
        self.append(texto)
        self.codigos.append(codigo)


def _normal(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (texto or "").lower())


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
    alertas, bloquea, motivos = _Alertas(), False, []

    for campo, nombre in (("comercio", "comercio"), ("fecha", "fecha"), ("total", "total"), ("moneda", "moneda")):
        if g.get(campo) in (None, ""):
            alertas.agregar("campo_faltante", f"Falta {nombre}.")
            bloquea = True

    partes = [g.get(c) for c in ("subtotal", "impuesto", "propina")]
    if g.get("total") is not None and g.get("subtotal") is not None:
        suma = sum(p or 0 for p in partes)
        if abs(suma - g["total"]) > 0.02:
            alertas.agregar("total_no_cuadra", f"El total ({g['total']:.2f}) no coincide con subtotal + impuesto + propina ({suma:.2f}).")
            bloquea = True

    if g.get("dudas"):
        alertas.agregar("ilegible", "Campos poco legibles: " + ", ".join(g["dudas"]) + ".")
    if (g.get("confianza") or 0) < config.UMBRAL_CONFIANZA:
        alertas.agregar("ilegible", f"Confianza de lectura {g.get('confianza') or 0:.0%}, por debajo del {config.UMBRAL_CONFIANZA:.0%}.")
        bloquea = True

    if not proyecto:
        alertas.agregar("sin_proyecto", "Sin proyecto asignado.")
        bloquea = True
    elif g.get("fecha") and proyecto.get("fecha_inicio") and proyecto.get("fecha_fin"):
        if not (proyecto["fecha_inicio"] <= g["fecha"] <= proyecto["fecha_fin"]):
            # Los tiquetes se compran antes del viaje: solo avisa, no bloquea
            if g.get("categoria") == "vuelo" and g["fecha"] < proyecto["fecha_inicio"]:
                alertas.agregar("compra_anticipada", "Comprado antes de las fechas del proyecto (normal en tiquetes).")
            else:
                alertas.agregar("fuera_de_fechas", f"La fecha {g['fecha']} está fuera del proyecto ({proyecto['fecha_inicio']} a {proyecto['fecha_fin']}).")
                bloquea = True

    total_usd = a_usd(g.get("total"), g.get("moneda"), cat)
    if g.get("total") is not None and g.get("moneda") and total_usd is None:
        alertas.agregar("sin_tasa", f"No hay tasa de cambio configurada para {g['moneda']}.")
        bloquea = True

    if g.get("comercio") and g.get("fecha") and g.get("total") is not None:
        repetido = db.uno(
            "select id from gastos where lower(comercio)=lower(:c) and fecha=:f and total=:t and id<>:i and estado<>'rechazado'",
            c=g["comercio"], f=g["fecha"], t=g["total"], i=gasto_id or 0)
        if repetido:
            alertas.agregar("duplicado", f"Posible duplicado del gasto #{repetido['id']}.")
            bloquea = True
        else:
            # Duplicado aproximado: mismo comercio, fecha a un día de distancia e importe a menos del 1 %
            dia = date.fromisoformat(g["fecha"]) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", g["fecha"]) else None
            if dia:
                cerca = db.todos("""select id, comercio, total from gastos where fecha between :a and :b and id<>:i
                                    and estado<>'rechazado' and total is not null""",
                                 a=(dia - timedelta(days=1)).isoformat(), b=(dia + timedelta(days=1)).isoformat(), i=gasto_id or 0)
                parecido = next((c for c in cerca if _normal(c["comercio"]) == _normal(g["comercio"])
                                 and abs(c["total"] - g["total"]) <= 0.01 * max(abs(g["total"]), 1)), None)
                if parecido:
                    alertas.agregar("duplicado_aproximado", f"Muy parecido al gasto #{parecido['id']} (mismo comercio, fecha cercana, importe casi igual).")
                    bloquea = True

    # Importe atípico frente a lo habitual de su categoría (solo avisa; con pocos datos no opina)
    from . import inteligencia
    raro = inteligencia.es_atipico(g.get("categoria"), g.get("moneda"), g.get("total"), gasto_id or 0)
    if raro:
        alertas.agregar("atipico", raro)
        bloquea = True

    canal = (g.get("canal_reserva") or "").lower()
    if g.get("categoria") == "hotel" and any(a in canal for a in AGENCIAS):
        alertas.agregar("sin_puntos", f"Fidelización: reservado por {g['canal_reserva']}; esta estadía no acumula puntos en el programa del hotel.")

    return {"estado": "revision" if bloquea else "aprobado_auto", "alertas": list(alertas), "motivos": alertas.codigos,
            "total_usd": total_usd}
