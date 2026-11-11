"""Costo total esperado de una opción de viaje.

    costo = precio + equipaje + (probabilidad de cambio x costo de cambiar)
            - valor de lo acumulado

Cada línea del desglose dice de dónde salió el número: "buscador", "regla" o "supuesto".
"""
from datetime import datetime

from .. import db


def catalogo() -> dict:
    """Reglas indexadas por (ámbito, entidad, tarifa, clave)."""
    return {(r["ambito"], r["entidad"] or "", r["tarifa"] or "", r["clave"]): r for r in db.todos_cache("select * from reglas")}


def _regla(cat: dict, ambito: str, entidad: str, tarifa: str, clave: str):
    return cat.get((ambito, entidad, tarifa, clave)) or cat.get((ambito, entidad, "", clave))


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
    """Cuando el buscador no dio las tarifas, se asume la básica de la aerolínea según el catálogo."""
    a = vuelo["aerolinea"]
    mano = _regla(cat, "aerolinea", a, "basica", "equipaje_mano")
    costo_mano = _regla(cat, "aerolinea", a, "basica", "costo_equipaje_mano")
    maleta = _regla(cat, "aerolinea", a, "basica", "costo_maleta")
    incluye = (mano["valor"] == "si") if mano else True
    return {
        "nombre": "Tarifa más baja (supuesta)", "precio": float(vuelo["precio"]), "vende": a,
        "mano": 0 if incluye else float(costo_mano["valor"]) if costo_mano else supuesto(cat, "costo_equipaje_mano", 70),
        "maleta": float(maleta["valor"]) if maleta else supuesto(cat, "costo_maleta", 80),
        "permite_cambio": False, "reembolsable": False, "notas": vuelo.get("notas", []), "equipaje": [],
        "supuesta": True, "regla_mano": bool(mano),
    }


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
            lineas.append({"concepto": "Maleta facturada", "valor": tarifa["maleta"], "origen": origen_tarifa if not tarifa.get("supuesta") else "regla"})

    # Riesgo de cambio de fecha
    prob = sol["prob_cambio"] or 0
    if prob:
        if tarifa["permite_cambio"]:
            dif = supuesto(cat, "diferencia_tarifa_cambio", 60)
            lineas.append({"concepto": f"Riesgo de cambio ({prob:.0%} x diferencia de tarifa estimada {dif:.0f})",
                           "valor": round(prob * dif, 2), "origen": "supuesto"})
        else:
            lineas.append({"concepto": f"Riesgo de cambio ({prob:.0%} x perder el tiquete)",
                           "valor": round(prob * tarifa["precio"], 2), "origen": "supuesto"})
            avisos.append("No admite cambios: si la grabación se mueve, se pierde el tiquete.")

    # Millas y cuenta de empresa
    regla_acumula = _regla(cat, "aerolinea", aerolinea, "basica", "acumula") if basica else None
    acumula = not (regla_acumula and regla_acumula["valor"] == "no")
    if acumula:
        valor_milla = supuesto(cat, "valor_milla_usd", 0.012)
        por_usd = supuesto(cat, "millas_por_usd", 5) + (1 if empresa else 0)
        etiqueta = "Millas del viajero y de la cuenta de empresa" if empresa else "Millas del viajero"
        lineas.append({"concepto": f"{etiqueta} ({por_usd:g} por USD a {valor_milla} USD)",
                       "valor": -round(tarifa["precio"] * por_usd * valor_milla, 2), "origen": "supuesto"})
    elif basica:
        avisos.append("La tarifa básica de esta aerolínea no acumula millas.")

    # Hora límite de llegada
    if sol.get("llegar_antes"):
        try:
            if datetime.fromisoformat(vuelo["llega"].replace(" ", "T")) > datetime.fromisoformat(sol["llegar_antes"]):
                descartada = f"Llega a las {vuelo['llega'][11:]}, después de la hora límite."
        except ValueError:
            pass

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


def programa_hotel(nombre: str, cat: dict) -> str | None:
    bajo = nombre.lower()
    for (ambito, entidad, _t, clave), r in cat.items():
        if ambito == "hotel" and clave == "programa" and entidad.lower() in bajo:
            return r["valor"]
    return None


def noches(ida: str, regreso: str) -> int:
    return max((datetime.fromisoformat(regreso) - datetime.fromisoformat(ida)).days, 1)
