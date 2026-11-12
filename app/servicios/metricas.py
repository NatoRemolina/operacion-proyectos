"""Catálogo único de métricas. Cada cifra de la plataforma sale de aquí, con una sola definición.

Todas aceptan los mismos filtros (proyecto, desde, hasta) y leen de las vistas analíticas `v_h_*`,
que son también la superficie para herramientas externas de inteligencia de negocio.
"""
from collections import Counter
from datetime import datetime
from statistics import median

from .. import db
from . import costo, inteligencia, validacion

APROBADOS = ("aprobado", "aprobado_auto")


def _filtro(f: dict, campo_fecha: str = "fecha", alias: str = "") -> tuple[str, dict]:
    p = f"{alias}." if alias else ""
    cond, par = ["1=1"], {}
    if f.get("proyecto_id"):
        cond.append(f"{p}proyecto_id=:proyecto_id"); par["proyecto_id"] = int(f["proyecto_id"])
    if f.get("desde"):
        cond.append(f"{p}{campo_fecha}>=:desde"); par["desde"] = f["desde"]
    if f.get("hasta"):
        cond.append(f"{p}{campo_fecha}<=:hasta"); par["hasta"] = f["hasta"] + " 99"
    return " and ".join(cond), par


def _pct(a, b):
    return round(100 * a / b) if b else None


def _percentil(valores: list[float], q: float):
    if not valores:
        return None
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(round(q * (len(orden) - 1))))]


# ---------- gastos ----------
def gastos(f: dict) -> dict:
    donde, par = _filtro(f, "creado")
    filas = db.todos(f"select * from v_h_gasto where {donde} order by id", **par)
    n = len(filas)
    por_estado = Counter(g["estado"] for g in filas)
    motivos = Counter()
    for g in filas:
        for m in set(db.de_json(g["motivos"], []) or []):
            motivos[validacion.MOTIVOS.get(m, m)] += 1

    # Tiempo de recibido a aprobado, a partir de la bitácora
    tiempos = []
    if filas:
        hechos = db.todos("""select entidad_id, paso, momento from eventos where entidad='gasto' and paso in
                             ('documento recibido','aprobado sin intervención','corregido y aprobado','aprobado con excepción')""")
        inicio = {e["entidad_id"]: e["momento"] for e in hechos if e["paso"] == "documento recibido"}
        ids = {g["id"] for g in filas}
        for e in hechos:
            if e["paso"] != "documento recibido" and e["entidad_id"] in ids and e["entidad_id"] in inicio:
                d = datetime.fromisoformat(e["momento"]) - datetime.fromisoformat(inicio[e["entidad_id"]])
                tiempos.append(d.total_seconds())

    revisados = [g for g in filas if g["extraido"] and g["estado"] in APROBADOS + ("rechazado",)]
    por_campo = Counter()
    for g in revisados:
        por_campo.update(inteligencia.campos_corregidos(g))
    leidos = len(revisados) * len(inteligencia.CAMPOS_COMPARADOS)

    real = Counter()
    for g in filas:
        if g["estado"] in APROBADOS and g["total_usd"]:
            real[g["categoria"] or "otros"] += g["total_usd"]
    return {
        "recibidos": n,
        "embudo": [("Recibidos", n), ("Aprobados solos", por_estado["aprobado_auto"]), ("En revisión", por_estado["revision"]),
                   ("Aprobados por una persona", por_estado["aprobado"]), ("Rechazados", por_estado["rechazado"])],
        "tasa_sin_intervencion": _pct(por_estado["aprobado_auto"], n),
        "pendientes": por_estado["revision"],
        "tiempo_mediana_s": round(median(tiempos)) if tiempos else None,
        "tiempo_p90_s": round(_percentil(tiempos, 0.9)) if tiempos else None,
        "motivos": motivos.most_common(),
        "por_canal": Counter(g["canal"] or "—" for g in filas).most_common(),
        "por_viajero": Counter(g["viajero"] or "—" for g in filas).most_common(8),
        "real_por_categoria": sorted(((c, round(v, 2)) for c, v in real.items()), key=lambda x: -x[1]),
        "real_total": round(sum(real.values()), 2),
        "tasa_correccion": _pct(sum(por_campo.values()), leidos),
        "correccion_por_campo": por_campo.most_common(),
        "gastos_evaluados": len(revisados),
        "calibracion": inteligencia.calibracion(),
    }


# ---------- búsquedas y decisiones ----------
def busquedas(f: dict) -> dict:
    donde, par = _filtro(f, "creado")
    sols = db.todos(f"select * from v_h_busqueda where {donde} order by id", **par)
    decs = db.todos(f"select * from v_h_decision where {donde} order by id", **par)
    vigentes = list({d["solicitud_id"]: d for d in decs}.values())
    con_dato = [d for d in vigentes if d["siguio_recomendacion"] is not None]
    razones = Counter()
    for d in vigentes:
        razones.update(db.de_json(d["razones"], []) or [])
    from .. import config
    pasos = {r["paso"]: r["n"] for r in db.todos(
        "select paso, count(*) n from eventos where paso in ('consulta externa','lectura de respaldo','consulta externa fallida') group by paso")}
    vivo, reutilizadas = pasos.get("consulta externa", 0), pasos.get("lectura de respaldo", 0)
    etiquetadas = db.uno("select count(distinct decision_id) n, count(*) filas from elecciones")
    return {
        "consultas": len(sols), "decisiones": len(vigentes),
        "por_ruta": Counter(f"{s['origen']} → {s['destino']}" for s in sols).most_common(8),
        "por_persona": Counter(s["usuario"] or s["solicitado_por"] or "—" for s in sols).most_common(8),
        "consultas_en_vivo": vivo, "consultas_reutilizadas": reutilizadas, "consultas_fallidas": pasos.get("consulta externa fallida", 0),
        "tasa_reutilizacion": _pct(reutilizadas, vivo + reutilizadas),
        "acuerdo": _pct(sum(1 for d in con_dato if d["siguio_recomendacion"]), len(con_dato)),
        "decisiones_con_dato": len(con_dato),
        "razones": [(config.RAZONES.get(r, r), n) for r, n in razones.most_common()],
        "ahorro_identificado": round(sum(s["ahorro_potencial"] or 0 for s in sols), 2),
        "ahorro_capturado": round(sum((db.de_json(d["desglose"], {}) or {}).get("ahorro") or 0 for d in vigentes), 2),
        "decisiones_etiquetadas": etiquetadas["n"], "opciones_etiquetadas": etiquetadas["filas"], "minimo_para_entrenar": 50,
    }


# ---------- viajes: presupuesto aprobado frente a gasto ----------
def viajes(f: dict) -> dict:
    donde, par = _filtro(f, "creado")
    filas = db.todos(f"select * from v_h_viaje where {donde} order by id", **par)
    por_estado = Counter(v["estado"] for v in filas)
    con_presupuesto = [v for v in filas if v["estado"] in ("aprobado", "cerrado") and v["presupuesto_usd"]]
    previsto = sum(v["presupuesto_usd"] for v in con_presupuesto)
    gastado = sum(v["gastado_usd"] or 0 for v in con_presupuesto)
    esperas = []
    for v in filas:
        if v["aprobado_en"]:
            esperas.append((datetime.fromisoformat(v["aprobado_en"]) - datetime.fromisoformat(v["creado"])).total_seconds() / 3600)
    donde_g, par_g = _filtro(f, "creado")
    gastos_ = db.todos(f"select viaje_id, canal from v_h_gasto where {donde_g}", **par_g)
    return {
        "viajes": len(filas), "pendientes": por_estado["pendiente_aprobacion"], "aprobados": por_estado["aprobado"],
        "rechazados": por_estado["rechazado"], "cerrados": por_estado["cerrado"],
        "presupuesto_aprobado": round(previsto, 2), "gastado": round(gastado, 2), "ejecucion": _pct(gastado, previsto),
        "sobre_presupuesto": sum(1 for v in con_presupuesto if (v["gastado_usd"] or 0) > v["presupuesto_usd"]),
        "horas_a_aprobacion": round(median(esperas), 1) if esperas else None,
        "gastos_sin_viaje": sum(1 for g in gastos_ if not g["viaje_id"]), "gastos": len(gastos_),
        "por_canal": Counter(g["canal"] or "—" for g in gastos_).most_common(),
        "por_titular": Counter(v["titular"] or "—" for v in filas).most_common(8),
        "detalle": [{"id": v["id"], "titular": v["titular"], "ruta": f"{v['origen']} → {v['destino']}", "ida": v["ida"], "estado": v["estado"],
                     "presupuesto": v["presupuesto_usd"], "gastado": v["gastado_usd"], "en_revision": v["en_revision_usd"],
                     "pct": _pct(v["gastado_usd"] or 0, v["presupuesto_usd"])} for v in filas],
    }


# ---------- modelo de lenguaje ----------
def uso_modelo(f: dict) -> dict:
    donde, par = _filtro({k: v for k, v in f.items() if k != "proyecto_id"}, "momento")
    filas = db.todos(f"select * from v_h_lectura where {donde}", **par)
    cat = costo.catalogo()
    p_ent, p_sal = costo.supuesto(cat, "modelo_usd_por_millon_entrada", 0.5), costo.supuesto(cat, "modelo_usd_por_millon_salida", 3.0)
    por_uso = {}
    for u in sorted({x["uso"] for x in filas}):
        g = [x for x in filas if x["uso"] == u]
        bien = [x for x in g if x["estado_http"] == 200 and not x["error"]]
        ent, sal = sum(x["tokens_entrada"] or 0 for x in g), sum(x["tokens_salida"] or 0 for x in g)
        por_uso[u] = {"llamadas": len(g), "fallidas": len(g) - len(bien), "tokens_entrada": ent, "tokens_salida": sal,
                      "costo_usd": round(ent / 1e6 * p_ent + sal / 1e6 * p_sal, 4),
                      "latencia_mediana_ms": round(median(x["latencia_ms"] or 0 for x in g)) if g else None}
    recibos = por_uso.get("recibo", {})
    return {"por_uso": por_uso, "llamadas": len(filas),
            "costo_total_usd": round(sum(v["costo_usd"] for v in por_uso.values()), 4),
            "costo_por_recibo_usd": round(recibos["costo_usd"] / recibos["llamadas"], 4) if recibos.get("llamadas") else None,
            "modelos": sorted({x["modelo"] for x in filas if x["modelo"]}),
            "precio_entrada": p_ent, "precio_salida": p_sal,
            "errores": [(x["momento"], x["uso"], x["error"]) for x in filas if x["error"]][-10:]}


def calidad_de_datos() -> list[dict]:
    """Comprobaciones que deberían dar siempre cero."""
    pruebas = [
        ("Gastos aprobados sin valor en USD", "select count(*) n from gastos where estado in ('aprobado','aprobado_auto') and total_usd is null"),
        ("Gastos aprobados sin proyecto", "select count(*) n from gastos where estado in ('aprobado','aprobado_auto') and proyecto_id is null"),
        ("Gastos atascados en proceso", "select count(*) n from gastos where estado='procesando'"),
        ("Decisiones sin opciones registradas", "select count(*) n from decisiones d where siguio_recomendacion is not null and not exists (select 1 from elecciones e where e.decision_id=d.id)"),
        ("Viajes sin titular", "select count(*) n from viajes where usuario_id is null"),
        ("Viajes aprobados sin presupuesto", "select count(*) n from viajes where estado='aprobado' and coalesce(presupuesto_usd,0)<=0"),
        ("Decisiones de vuelo sin viaje", "select count(*) n from decisiones d where d.vuelo_id is not null and not exists (select 1 from viajes v where v.solicitud_id=d.solicitud_id)"),
        ("Sesiones vencidas sin limpiar", "select count(*) n from sesiones where expira < :a"),
    ]
    return [{"prueba": t, "casos": db.uno(sql, a=db.ahora())["n"] if ":a" in sql else db.uno(sql)["n"]} for t, sql in pruebas]


CATALOGO = {
    "tasa_sin_intervencion": ("Gastos aprobados sin intervención", "%", "Trabajo manual evitado", lambda f: gastos(f)["tasa_sin_intervencion"]),
    "tiempo_a_aprobado": ("Mediana de recibido a aprobado", "s", "Cuello de botella de la revisión", lambda f: gastos(f)["tiempo_mediana_s"]),
    "tasa_correccion": ("Campos corregidos sobre campos leídos", "%", "Calidad real de la lectura", lambda f: gastos(f)["tasa_correccion"]),
    "pendientes_revision": ("Gastos esperando revisión", "gastos", "Carga de Finanzas", lambda f: gastos(f)["pendientes"]),
    "gasto_real": ("Gasto real aprobado", "USD", "Control financiero", lambda f: gastos(f)["real_total"]),
    "costo_por_recibo": ("Costo de leer un recibo", "USD", "Elección de modelo", lambda f: uso_modelo(f)["costo_por_recibo_usd"]),
    "acuerdo_recomendacion": ("Decisiones que siguen la recomendación", "%", "Validez de las reglas", lambda f: busquedas(f)["acuerdo"]),
    "ahorro_capturado": ("Ahorro capturado en decisiones", "USD", "Valor del comparador", lambda f: busquedas(f)["ahorro_capturado"]),
    "tasa_reutilizacion": ("Búsquedas resueltas sin pagar otra consulta", "%", "Costo del buscador", lambda f: busquedas(f)["tasa_reutilizacion"]),
    "presupuestos_pendientes": ("Viajes esperando aprobación de presupuesto", "viajes", "Carga de quien aprueba", lambda f: viajes(f)["pendientes"]),
    "ejecucion_presupuesto": ("Gasto aprobado sobre presupuesto aprobado", "%", "Vigilancia de los recursos por viaje", lambda f: viajes(f)["ejecucion"]),
    "gastos_sin_viaje": ("Gastos que no pertenecen a ningún viaje", "gastos", "Cumplimiento de la regla de negocio", lambda f: viajes(f)["gastos_sin_viaje"]),
    "decisiones_etiquetadas": ("Decisiones etiquetadas para entrenar", "decisiones", "Avance hacia el modelo de decisión", lambda f: busquedas(f)["decisiones_etiquetadas"]),
}


def valor(nombre: str, f: dict) -> dict | None:
    if nombre not in CATALOGO:
        return None
    titulo, unidad, para_que, funcion = CATALOGO[nombre]
    return {"nombre": nombre, "titulo": titulo, "unidad": unidad, "para_que": para_que, "valor": funcion(f), "filtros": f}
