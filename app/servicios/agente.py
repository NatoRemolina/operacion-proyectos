"""Agente de recomendación de viajes, construido como grafo de estados.

    resumen ──> (¿hay modelo de lenguaje?) ──no──> fin  (explicación determinista)
                        │ sí
                        v
                     modelo <──> herramientas ──> fin

El agente no reserva ni decide: explica cuál opción conviene y por qué, usando como
herramientas las mismas funciones de la aplicación. Sin clave del modelo de lenguaje, o si
la llamada falla, responde el nodo determinista, que arma la explicación desde el desglose.
"""
import json
import time
from functools import lru_cache
from typing import TypedDict

import httpx

from .. import config, db
from . import costo, llm

MAX_VUELTAS = 5
PLAZO_TOTAL_S = 60   # toda la conversación con el modelo, no cada llamada
ESPERA_LLAMADA_S = 30

SISTEMA = """Eres un asistente que ayuda a un equipo de operaciones a elegir el viaje de un piloto de dron.
Usa las herramientas para consultar las opciones, sus desgloses, las reglas y el historial de precios.
Responde en español, en menos de 180 palabras, con: la opción recomendada, las tres razones principales con cifras,
y qué dato haría cambiar la recomendación. No inventes cifras: usa solo lo que devuelven las herramientas.
Distingue lo que viene del buscador, de una regla o de un supuesto. No reservas ni decides: recomiendas."""


class Estado(TypedDict, total=False):
    c: dict            # comparación completa de la solicitud
    pregunta: str
    base: str          # explicación determinista
    mensajes: list
    respuesta: str
    modo: str
    pasos: list        # herramientas usadas, para mostrar el recorrido
    vueltas: int
    inicio: float


# ---------- herramientas ----------
def _vuelo_corto(o: dict) -> dict:
    return {"opcion_id": o["id"], "aerolinea": o["v"]["aerolinea"], "vuelos": o["v"]["numeros"],
            "sale": o["v"]["sale"], "llega": o["v"]["llega"], "escalas": o["v"]["escalas"],
            "precio_buscador": o["v"]["precio"], "tarifa_recomendada": o["ev"]["tarifa"]["nombre"],
            "costo_total_esperado": o["ev"]["total"], "tarifas_reales": o["ev"]["tarifas_reales"],
            "precio_esperado_modelo": o.get("esperado"), "avisos": o["ev"]["avisos"]}


def h_listar_opciones(c: dict, **_) -> dict:
    return {"vuelos": [_vuelo_corto(o) for o in c["vuelos"][:8]],
            "descartados": [{"vuelos": o["v"]["numeros"], "motivo": o["ev"]["descartada"]} for o in c["descartados"]],
            "hoteles": [{"nombre": h["h"]["nombre"], "total": h["h"]["total"], "calificacion": h["h"]["calificacion"],
                         "programa": h["programa"]} for h in c["hoteles"][:5]],
            "equipo": c["baterias"]["texto"], "probabilidad_cambio": c["sol"]["prob_cambio"]}


def h_desglose(c: dict, opcion_id: int = 0, **_) -> dict:
    o = next((x for x in c["vuelos"] + c["descartados"] if x["id"] == int(opcion_id)), None)
    if not o:
        return {"error": "No existe esa opción."}
    return {"lineas": o["ev"]["lineas"], "total": o["ev"]["total"],
            "tarifas": [{"nombre": e["tarifa"]["nombre"], "precio": e["tarifa"]["precio"],
                         "permite_cambio": e["tarifa"]["permite_cambio"], "costo_esperado": e["total"]} for e in o["ev"]["todas"]]}


def h_reglas(c: dict, aerolinea: str = "", **_) -> dict:
    filas = db.todos("select entidad, tarifa, clave, valor, nota, confianza from reglas where ambito='aerolinea' and lower(entidad)=lower(:a)", a=aerolinea)
    return {"reglas": filas} if filas else {"reglas": [], "nota": "Sin reglas en el catálogo: se usan supuestos genéricos."}


def h_historial(c: dict, **_) -> dict:
    s = c["sol"]
    filas = db.todos("select fecha, precio from historial_ruta where busqueda=:b order by fecha",
                     b=f"{s['origen']}_{s['destino']}_{s['ida']}_{s['regreso']}")
    if not filas:
        return {"nota": "Sin historial para esta ruta y fechas."}
    precios = [f["precio"] for f in filas]
    return {"dias": len(filas), "minimo": min(precios), "maximo": max(precios), "actual": precios[-1],
            "hace_30_dias": precios[-31] if len(precios) > 30 else precios[0]}


def h_sensibilidad(c: dict, **_) -> dict:
    """Cómo cambia la opción ganadora al mover la probabilidad de cambio de fecha."""
    cat, cambios, anterior = costo.catalogo(), [], None
    for p in range(0, 101, 5):
        sol = {**c["sol"], "prob_cambio": p / 100}
        mejor = min(((o, costo.mejor_tarifa(o["v"], o["tarifas_lista"], sol, c["membresias"], cat)) for o in c["vuelos"]),
                    key=lambda par: par[1]["total"], default=None)
        if not mejor:
            break
        nombre = f"{mejor[0]['v']['aerolinea']} {mejor[0]['v']['numeros'][0]} ({mejor[1]['tarifa']['nombre']})"
        if nombre != anterior:
            cambios.append({"desde_probabilidad": p, "gana": nombre, "costo_esperado": mejor[1]["total"]})
            anterior = nombre
    return {"ganador_segun_probabilidad_de_cambio": cambios}


HERRAMIENTAS = {
    "listar_opciones": (h_listar_opciones, "Lista vuelos válidos ordenados por costo total esperado, vuelos descartados y hoteles.", {}),
    "desglose_de_opcion": (h_desglose, "Desglose del costo esperado de un vuelo y de todas sus tarifas conocidas.",
                           {"opcion_id": {"type": "integer"}}),
    "reglas_de_aerolinea": (h_reglas, "Reglas del catálogo propio para una aerolínea (equipaje, millas), con su nivel de confianza.",
                            {"aerolinea": {"type": "string"}}),
    "historial_de_ruta": (h_historial, "Precio más bajo de este viaje en los últimos 60 días.", {}),
    "sensibilidad": (h_sensibilidad, "Qué opción gana según la probabilidad de cambio de fecha.", {}),
}


def _esquemas() -> list[dict]:
    return [{"name": n, "description": d, "input_schema": {"type": "object", "properties": p, "required": list(p)}}
            for n, (_f, d, p) in HERRAMIENTAS.items()]


# ---------- nodos ----------
def nodo_resumen(e: Estado) -> Estado:
    c = e["c"]
    if not c["vuelos"]:
        return {"base": "No hay vuelos válidos para esta solicitud; revisa la hora límite o las fechas.", "pasos": []}
    m = c["vuelos"][0]
    tarifa = "con la tarifa más baja (supuesta)" if m["ev"]["tarifa"].get("supuesta") else f"en tarifa {m['ev']['tarifa']['nombre']}"
    partes = [f"Recomiendo {m['v']['aerolinea']} {' + '.join(m['v']['numeros'])} {tarifa}: "
              f"costo total esperado de {m['ev']['total']:.0f} USD (precio en el buscador: {m['v']['precio']:.0f} USD)."]
    barato = c.get("mas_barato")
    if barato and barato["id"] != m["id"]:
        partes.append(f"El más barato del buscador es {barato['v']['aerolinea']} por {barato['v']['precio']:.0f} USD, "
                      f"pero su costo esperado sube a {barato['ev']['total']:.0f} USD. "
                      + (" ".join(barato["ev"]["avisos"][:2]) if barato["ev"]["avisos"] else ""))
    if len(c["vuelos"]) > 1:
        s = c["vuelos"][1]
        partes.append(f"La segunda opción es {s['v']['aerolinea']} {s['v']['numeros'][0]}, a {s['ev']['total'] - m['ev']['total']:.0f} USD de diferencia.")
    if m.get("esperado"):
        dif = (m["v"]["precio"] - m["esperado"]) / m["esperado"]
        partes.append(f"Según el modelo de precios, este vuelo está {abs(dif):.0%} {'por debajo' if dif < 0 else 'por encima'} de lo esperado para la ruta.")
    if c["descartados"]:
        partes.append(f"Se descartaron {len(c['descartados'])} vuelos por llegar después de la hora límite.")
    cambios = h_sensibilidad(c)["ganador_segun_probabilidad_de_cambio"]
    if len(cambios) > 1:
        partes.append("Qué la cambiaría: " + "; ".join(f"desde {x['desde_probabilidad']} % de probabilidad de cambio gana {x['gana']}" for x in cambios) + ".")
    else:
        partes.append("La recomendación no cambia con la probabilidad de cambio de fecha entre 0 y 100 %.")
    if not m["ev"]["tarifas_reales"]:
        partes.append("Atención: las tarifas de este vuelo son supuestas; conviene traer las reales antes de decidir.")
    return {"base": "\n".join(partes), "pasos": ["resumen determinista"]}


def _hay_modelo(e: Estado) -> str:
    return "modelo" if config.modo()["extraccion"] == "en vivo" and e["c"]["vuelos"] else "fin"


def _nodo_modelo_cliente(e: Estado) -> Estado:
    """Turno del modelo con el cliente único. El historial se devuelve tal cual lo entregó el modelo."""
    pregunta = (e.get("pregunta") or "¿Cuál opción recomiendas y por qué?") + f"\n\nAnálisis previo de la aplicación:\n{e['base']}"
    contenidos = e.get("mensajes") or [{"role": "user", "parts": [llm.parte_texto(pregunta)]}]
    declaraciones = [{"name": n, "description": d, **({"parameters": {"type": "OBJECT", "properties": {k: {"type": v["type"].upper()} for k, v in p.items()}, "required": list(p)}} if p else {})}
                     for n, (_f, d, p) in HERRAMIENTAS.items()]
    try:
        candidato = llm.generar(contenidos, uso="agente", entidad_id=e["c"]["sol"]["id"], sistema=SISTEMA,
                                herramientas=declaraciones, tope_salida=4096)
    except llm.ErrorDelModelo as error:
        return {"respuesta": e["base"], "modo": f"determinista ({error})", "mensajes": contenidos}
    contenidos = contenidos + [candidato["content"]]
    return {"mensajes": contenidos, "respuesta": llm.texto_de(candidato) or e["base"], "modo": "modelo de lenguaje con herramientas",
            "vueltas": e.get("vueltas", 0) + 1, "inicio": e.get("inicio") or time.monotonic()}


def nodo_modelo(e: Estado) -> Estado:
    if llm.activo():
        return _nodo_modelo_cliente(e)
    mensajes = e.get("mensajes") or [{"role": "user", "content":
        (e.get("pregunta") or "¿Cuál opción recomiendas y por qué?") + f"\n\nAnálisis previo de la aplicación:\n{e['base']}"}]
    try:
        r = httpx.post(config.MODELO_API_URL, timeout=ESPERA_LLAMADA_S,
                       headers={"x-api-key": config.MODELO_API_KEY, "content-type": "application/json", **config.MODELO_CABECERAS},
                       json={"model": config.MODELO_NOMBRE, "max_tokens": 900, "system": SISTEMA, "tools": _esquemas(), "messages": mensajes})
        r.raise_for_status()
        contenido = r.json().get("content", [])
    except Exception as error:
        return {"respuesta": e["base"], "modo": f"determinista (falló el modelo de lenguaje: {type(error).__name__})", "mensajes": mensajes}
    mensajes = mensajes + [{"role": "assistant", "content": contenido}]
    texto = "".join(b.get("text", "") for b in contenido if b.get("type") == "text").strip()
    return {"mensajes": mensajes, "respuesta": texto or e["base"], "modo": "modelo de lenguaje con herramientas",
            "vueltas": e.get("vueltas", 0) + 1, "inicio": e.get("inicio") or time.monotonic()}


def _siguiente(e: Estado) -> str:
    ultimo = (e.get("mensajes") or [{}])[-1]
    pide = (ultimo.get("role") == "assistant" and any(b.get("type") == "tool_use" for b in ultimo.get("content", []))) or \
           (ultimo.get("role") == "model" and any("functionCall" in p for p in ultimo.get("parts", [])))
    a_tiempo = time.monotonic() - (e.get("inicio") or time.monotonic()) < PLAZO_TOTAL_S
    return "herramientas" if pide and a_tiempo and e.get("vueltas", 0) < MAX_VUELTAS else "fin"


def nodo_herramientas(e: Estado) -> Estado:
    resultados, pasos = [], list(e.get("pasos", []))
    if e["mensajes"][-1].get("role") == "model":
        for p in e["mensajes"][-1]["parts"]:
            llamada = p.get("functionCall")
            if not llamada:
                continue
            funcion = HERRAMIENTAS.get(llamada.get("name"))
            try:
                salida = funcion[0](e["c"], **(llamada.get("args") or {})) if funcion else {"error": "Herramienta desconocida."}
            except Exception as error:
                salida = {"error": type(error).__name__}
            pasos.append(llamada.get("name"))
            resultados.append({"functionResponse": {"name": llamada.get("name"), "response": json.loads(json.dumps(salida, default=str))}})
        return {"mensajes": e["mensajes"] + [{"role": "user", "parts": resultados}], "pasos": pasos}
    for b in e["mensajes"][-1]["content"]:
        if b.get("type") != "tool_use":
            continue
        funcion = HERRAMIENTAS.get(b["name"])
        try:
            salida = funcion[0](e["c"], **(b.get("input") or {})) if funcion else {"error": "Herramienta desconocida."}
        except Exception as error:
            salida = {"error": type(error).__name__}
        pasos.append(b["name"])
        resultados.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(salida, ensure_ascii=False, default=str)})
    return {"mensajes": e["mensajes"] + [{"role": "user", "content": resultados}], "pasos": pasos}


@lru_cache(maxsize=1)
def _grafo():
    """El grafo se arma la primera vez que se usa: la biblioteca pesa y no hace falta para arrancar."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(Estado)
    g.add_node("resumen", nodo_resumen)
    g.add_node("modelo", nodo_modelo)
    g.add_node("herramientas", nodo_herramientas)
    g.add_edge(START, "resumen")
    g.add_conditional_edges("resumen", _hay_modelo, {"modelo": "modelo", "fin": END})
    g.add_conditional_edges("modelo", _siguiente, {"herramientas": "herramientas", "fin": END})
    g.add_edge("herramientas", "modelo")
    return g.compile()



def recomendar(c: dict, pregunta: str = "", solo_determinista: bool = False) -> dict:
    """Devuelve {texto, modo, pasos}."""
    if solo_determinista:
        r = nodo_resumen({"c": c})
        return {"texto": r["base"], "modo": "determinista", "pasos": r["pasos"]}
    fin = _grafo().invoke({"c": c, "pregunta": pregunta})
    return {"texto": fin.get("respuesta") or fin["base"], "modo": fin.get("modo") or "determinista (sin clave del modelo de lenguaje)",
            "pasos": fin.get("pasos", [])}
