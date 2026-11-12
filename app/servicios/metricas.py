"""Catálogo único de métricas. Cada cifra de la plataforma sale de aquí, con una sola definición.

Todas aceptan los mismos filtros (proyecto, desde, hasta y, donde aplica, persona) y leen de las vistas
analíticas `v_h_*`, que son también la superficie para herramientas externas de inteligencia de negocio.
"""
from collections import Counter
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from datetime import date, datetime
from statistics import mean, median

from .. import db
from . import costo, inteligencia, precios, validacion

APROBADOS = ("aprobado", "aprobado_auto")


def titular_solicitud(s: str) -> str:
    """SQL de quién viaja en la cotización `s`, con la regla de `viajes.titular_de`: el titular de su viaje;
    si aún no hay viaje, la cuenta activa del viajero; si no la hay, quien cotizó."""
    return (f"coalesce((select x.usuario_id from viajes x where x.solicitud_id={s}.id), "
            f"(select min(u.id) from usuarios u where u.viajero_id={s}.viajero_id and u.activo=1), {s}.usuario_id)")


def dueno(t: str) -> str:
    """SQL de a quién pertenece un gasto o una evidencia `t`: al titular de su viaje; sin viaje, a quien lo cargó."""
    return f"coalesce((select x.usuario_id from viajes x where x.id={t}.viaje_id), {t}.usuario_id)"


_SOLICITUDES_DE = f"select s.id from solicitudes s where {titular_solicitud('s')}=:persona_id"
# A quién pertenece cada hecho al filtrar por persona: a quien viaja
PERSONA = {
    "v_h_viaje": "v_h_viaje.usuario_id=:persona_id",
    "v_h_gasto": f"{dueno('v_h_gasto')}=:persona_id",
    "v_h_busqueda": f"{titular_solicitud('v_h_busqueda')}=:persona_id",
    "v_h_decision": f"v_h_decision.solicitud_id in ({_SOLICITUDES_DE})",
    "v_h_consulta": f"v_h_consulta.solicitud_id in ({_SOLICITUDES_DE})",
}


def _filtro(f: dict, campo_fecha: str = "fecha", alias: str = "", vista: str = "") -> tuple[str, dict]:
    p = f"{alias}." if alias else ""
    cond, par = ["1=1"], {}
    if f.get("proyecto_id"):
        cond.append(f"{p}proyecto_id=:proyecto_id"); par["proyecto_id"] = int(f["proyecto_id"])
    if f.get("desde"):
        cond.append(f"{p}{campo_fecha}>=:desde"); par["desde"] = f["desde"]
    if f.get("hasta"):
        cond.append(f"{p}{campo_fecha}<=:hasta"); par["hasta"] = f["hasta"] + " 99"
    if f.get("persona_id"):
        if vista not in PERSONA:   # falla cerrado: sin regla de pertenencia, mostrar todo sería mostrar lo de otros
            raise ValueError(f"No hay filtro por persona para {vista or 'esta consulta'}")
        cond.append(PERSONA[vista]); par["persona_id"] = int(f["persona_id"])
    return " and ".join(cond), par


_lectura: ContextVar[dict | None] = ContextVar("lectura", default=None)


@contextmanager
def una_lectura():
    """Dentro del bloque cada sección se calcula una vez por filtro: un tablero pide muchas cifras de la misma sección."""
    marca = _lectura.set({}) if _lectura.get() is None else None   # anidado, comparte la memoria del bloque de fuera
    try:
        yield
    finally:
        if marca:
            _lectura.reset(marca)


def _seccion(funcion, f: dict) -> dict:
    memo = _lectura.get()
    if memo is None:
        return funcion(f)
    clave = (funcion.__name__, tuple(sorted((k, v) for k, v in f.items() if v)))
    if clave not in memo:
        memo[clave] = funcion(f)
    return memo[clave]


def _horas(desde: str, hasta: str) -> float:
    return (datetime.fromisoformat(hasta) - datetime.fromisoformat(desde)).total_seconds() / 3600


def _dias(desde: str, hasta: str) -> int | None:
    try:
        return (date.fromisoformat(hasta[:10]) - date.fromisoformat(desde[:10])).days
    except (TypeError, ValueError):
        return None


def _pct(a, b):
    return round(100 * a / b) if b else None


def _percentil(valores: list[float], q: float):
    if not valores:
        return None
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(round(q * (len(orden) - 1))))]


# ---------- gastos ----------
def gastos(f: dict) -> dict:
    donde, par = _filtro(f, "creado", vista="v_h_gasto")
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
    por_moneda: dict[str, dict] = {}
    for g in filas:
        if g["estado"] in APROBADOS:
            m = por_moneda.setdefault(g["moneda"] or "—", {"moneda": g["moneda"] or "—", "gastos": 0, "total": 0.0, "total_usd": 0.0})
            m["gastos"] += 1; m["total"] += g["total"] or 0; m["total_usd"] += g["total_usd"] or 0
    # Del recibo a la carga: la fecha impresa en el soporte frente al momento en que llegó a la plataforma
    demora = [d for d in (_dias(g["fecha"], g["creado"]) for g in filas if g["fecha"] and g["creado"]) if d is not None]
    ahora = db.ahora()
    edades = [_horas(g["creado"], ahora) / 24 for g in filas if g["estado"] == "revision" and g["creado"]]
    return {
        "recibidos": n,
        "embudo": [("Recibidos", n), ("Aprobados solos", por_estado["aprobado_auto"]), ("En revisión", por_estado["revision"]),
                   ("Aprobados por una persona", por_estado["aprobado"]), ("Rechazados", por_estado["rechazado"])],
        "tasa_sin_intervencion": _pct(por_estado["aprobado_auto"], n),
        "pendientes": por_estado["revision"],
        "tiempo_mediana_s": round(median(tiempos)) if tiempos else None,
        "tiempo_mediana_h": round(median(tiempos) / 3600, 1) if tiempos else None,
        "tiempo_p90_s": round(_percentil(tiempos, 0.9)) if tiempos else None,
        "motivos": motivos.most_common(),
        "por_canal": Counter(g["canal"] or "—" for g in filas).most_common(),
        "por_viajero": Counter(g["viajero"] or "—" for g in filas).most_common(8),
        "real_por_categoria": sorted(((c, round(v, 2)) for c, v in real.items()), key=lambda x: -x[1]),
        "real_total": round(sum(real.values()), 2),
        "por_moneda": sorted(({**m, "total": round(m["total"], 2), "total_usd": round(m["total_usd"], 2)} for m in por_moneda.values()),
                             key=lambda m: -m["total_usd"]),
        "dias_recibo_a_carga": median(demora) if demora else None,
        "revision_mas_antigua_dias": round(max(edades), 1) if edades else (0.0 if filas else None),
        "revision_mediana_dias": round(median(edades), 1) if edades else None,
        "revision_antiguas": [{"id": g["id"], "comercio": g["comercio"], "persona": g["usuario"], "total_usd": g["total_usd"],
                               "dias": round(_horas(g["creado"], ahora) / 24, 1)}
                              for g in sorted((g for g in filas if g["estado"] == "revision" and g["creado"]), key=lambda g: g["creado"])[:8]],
        "tasa_correccion": _pct(sum(por_campo.values()), leidos),
        "correccion_por_campo": por_campo.most_common(),
        "gastos_evaluados": len(revisados),
        "calibracion": inteligencia.calibracion(),
    }


# ---------- consultas al buscador de precios ----------
def buscador(f: dict) -> dict:
    """Cada consulta al buscador deja una fila: en vivo, guardada, guardada de otras fechas o fallida.

    El autocompletado de lugares va aparte: sus reutilizaciones no se registran (son pulsaciones), así que mezclado
    bajaría la tasa de reutilización y movería la latencia. Se muestra como su propio dato, frente a su tope."""
    from . import geografia
    donde, par = _filtro(f, "momento", vista="v_h_consulta")
    filas = db.todos(f"select * from v_h_consulta where {donde} and tipo<>'autocompletado' order by id", **par)
    origen = Counter(c["origen"] for c in filas)
    vivo, reutilizadas = origen["en vivo"], origen["guardado"] + origen["guardado (otras fechas)"]
    latencias = [c["duracion_ms"] for c in filas if c["origen"] == "en vivo" and c["duracion_ms"] is not None]
    return {
        "consultas": len(filas), "en_vivo": vivo, "reutilizadas": reutilizadas, "fallidas": origen["fallida"],
        "tasa_reutilizacion": _pct(reutilizadas, vivo + reutilizadas),
        "tasa_fallidas": _pct(origen["fallida"], len(filas)),
        "latencia_mediana_ms": round(median(latencias)) if latencias else None,
        "por_origen": origen.most_common(),
        "por_tipo": Counter(c["tipo"] for c in filas).most_common(),
        "por_persona": Counter(c["usuario"] or "sistema" for c in filas).most_common(8),
        "por_ruta": Counter(f"{c['ruta_origen']} → {c['ruta_destino']}" if c["ruta_origen"] else "sin cotización"
                            for c in filas).most_common(8),
        "errores": [(c["momento"], c["tipo"], c["error"]) for c in filas if c["error"]][-10:],
        "autocompletado": geografia.uso_autocompletado(),
    }


def cupo(_f: dict | None = None) -> dict:
    """Cupo del plan del buscador. Es de la cuenta: no depende de proyecto, fechas ni persona."""
    c = precios.cupo()
    usado = _pct(c["usadas"], c["mensual"]) if c and c.get("mensual") and c.get("usadas") is not None else None
    return {"cupo": c, "usado_pct": usado}


# ---------- búsquedas y decisiones ----------
def busquedas(f: dict) -> dict:
    donde, par = _filtro(f, "creado", vista="v_h_busqueda")
    sols = db.todos(f"select * from v_h_busqueda where {donde} order by id", **par)
    donde, par = _filtro(f, "creado", vista="v_h_decision")
    decs = db.todos(f"select * from v_h_decision where {donde} order by id", **par)
    vigentes = list({d["solicitud_id"]: d for d in decs}.values())
    con_dato = [d for d in vigentes if d["siguio_recomendacion"] is not None]
    razones = Counter()
    for d in vigentes:
        razones.update(db.de_json(d["razones"], []) or [])
    from .. import config
    b = _seccion(buscador, f)
    etiquetadas = db.uno("select count(distinct decision_id) n, count(*) filas from elecciones")
    # De la cotización a la decisión cuenta la primera decisión: las siguientes son cambios de opinión
    primeras: dict[int, str] = {}
    for d in decs:
        primeras.setdefault(d["solicitud_id"], d["creado"])
    ids = ",".join(str(int(i)) for i in primeras)
    inicio = {s["id"]: s["creado"] for s in db.todos(f"select id, creado from solicitudes where id in ({ids})")} if ids else {}
    a_decision = [_horas(inicio[s], c) for s, c in primeras.items() if inicio.get(s) and c]
    anticipacion = [d for d in (_dias(x["creado"], x["ida"]) for x in vigentes if x["ida"] and x["creado"]) if d is not None]
    identificado = round(sum(s["ahorro_potencial"] or 0 for s in sols), 2)
    capturado = round(sum((db.de_json(d["desglose"], {}) or {}).get("ahorro") or 0 for d in vigentes), 2)
    return {
        "consultas": len(sols), "decisiones": len(vigentes),
        "por_ruta": Counter(f"{s['origen']} → {s['destino']}" for s in sols).most_common(8),
        "por_persona": Counter(s["usuario"] or s["solicitado_por"] or "—" for s in sols).most_common(8),
        "consultas_en_vivo": b["en_vivo"], "consultas_reutilizadas": b["reutilizadas"], "consultas_fallidas": b["fallidas"],
        "tasa_reutilizacion": b["tasa_reutilizacion"], "autocompletado": b["autocompletado"],
        "acuerdo": _pct(sum(1 for d in con_dato if d["siguio_recomendacion"]), len(con_dato)),
        "decisiones_con_dato": len(con_dato),
        "razones": [(config.RAZONES.get(r, r), n) for r, n in razones.most_common()],
        "ahorro_identificado": identificado, "ahorro_capturado": capturado,
        "captura_ahorro": _pct(capturado, identificado) if identificado > 0 else None,
        "horas_a_decision": round(median(a_decision), 1) if a_decision else None,
        "anticipacion_media_dias": round(mean(anticipacion), 1) if anticipacion else None,
        "decisiones_etiquetadas": etiquetadas["n"], "opciones_etiquetadas": etiquetadas["filas"], "minimo_para_entrenar": 50,
    }


# ---------- viajes: presupuesto aprobado frente a gasto ----------
# Los gastos se registran por categoría y el presupuesto por grupo de compra: así se comparan
GRUPO_DE_CATEGORIA = {"vuelo": "vuelo", "hotel": "hotel", "alquiler_carro": "alquiler_carro"}   # lo demás sale de los viáticos
NOMBRE_GRUPO = {"vuelo": "Vuelo y equipaje", "hotel": "Hotel", "alquiler_carro": "Alquiler de carro",
                "viaticos": "Viáticos (comida, combustible, peajes, otros)"}


def viajes(f: dict) -> dict:
    donde, par = _filtro(f, "creado", vista="v_h_viaje")
    filas = db.todos(f"select * from v_h_viaje where {donde} order by id", **par)
    por_estado = Counter(v["estado"] for v in filas)
    con_presupuesto = [v for v in filas if v["estado"] in ("aprobado", "cerrado") and v["presupuesto_usd"]]
    previsto = sum(v["presupuesto_usd"] for v in con_presupuesto)
    gastado = sum(v["gastado_usd"] or 0 for v in con_presupuesto)
    esperas = []
    for v in filas:
        if v["aprobado_en"]:
            esperas.append((datetime.fromisoformat(v["aprobado_en"]) - datetime.fromisoformat(v["creado"])).total_seconds() / 3600)
    donde_g, par_g = _filtro(f, "creado", vista="v_h_gasto")
    gastos_ = db.todos(f"select viaje_id, canal from v_h_gasto where {donde_g}", **par_g)
    por_proyecto: dict[str, list[float]] = {}
    for v in con_presupuesto:
        x = por_proyecto.setdefault(v["proyecto"] or "—", [0.0, 0.0])
        x[0] += v["presupuesto_usd"]; x[1] += v["gastado_usd"] or 0
    previsto_grupo, real_grupo = Counter(), Counter()
    for v in con_presupuesto:
        for linea in db.de_json(v["presupuesto_detalle"], []) or []:
            previsto_grupo[GRUPO_DE_CATEGORIA.get(linea.get("grupo"), "viaticos")] += linea.get("valor") or 0
    ids = ",".join(str(int(v["id"])) for v in con_presupuesto)
    if ids:
        for g in db.todos(f"""select categoria, sum(total_usd) t from gastos where viaje_id in ({ids})
                              and estado in ('aprobado','aprobado_auto') group by categoria"""):
            real_grupo[GRUPO_DE_CATEGORIA.get(g["categoria"], "viaticos")] += g["t"] or 0
    return {
        "viajes": len(filas), "pendientes": por_estado["pendiente_aprobacion"], "aprobados": por_estado["aprobado"],
        "rechazados": por_estado["rechazado"], "cerrados": por_estado["cerrado"],
        "con_presupuesto": len(con_presupuesto),
        "presupuesto_aprobado": round(previsto, 2), "gastado": round(gastado, 2), "ejecucion": _pct(gastado, previsto),
        "sobre_presupuesto": sum(1 for v in con_presupuesto if (v["gastado_usd"] or 0) > v["presupuesto_usd"]),
        "horas_a_aprobacion": round(median(esperas), 1) if esperas else None,
        "gastos_sin_viaje": sum(1 for g in gastos_ if not g["viaje_id"]), "gastos": len(gastos_),
        "por_canal": Counter(g["canal"] or "—" for g in gastos_).most_common(),
        "por_titular": Counter(v["titular"] or "—" for v in filas).most_common(8),
        "por_proyecto": [{"proyecto": p, "presupuesto": round(a, 2), "gastado": round(b, 2), "pct": _pct(b, a)}
                         for p, (a, b) in sorted(por_proyecto.items())],
        "por_categoria": [{"grupo": NOMBRE_GRUPO[k], "presupuesto": round(previsto_grupo[k], 2), "gastado": round(real_grupo[k], 2),
                           "pct": _pct(real_grupo[k], previsto_grupo[k])} for k in NOMBRE_GRUPO if previsto_grupo[k] or real_grupo[k]],
        "detalle": [{"id": v["id"], "creado": v["creado"], "titular": v["titular"], "ruta": f"{v['origen']} → {v['destino']}", "ida": v["ida"], "estado": v["estado"],
                     "presupuesto": v["presupuesto_usd"], "gastado": v["gastado_usd"], "en_revision": v["en_revision_usd"],
                     "pct": _pct(v["gastado_usd"] or 0, v["presupuesto_usd"])} for v in filas],
    }


# ---------- modelo de lenguaje ----------
def uso_modelo(f: dict) -> dict:
    donde, par = _filtro({k: v for k, v in f.items() if k not in ("proyecto_id", "persona_id")}, "momento")
    filas = db.todos(f"select * from v_h_lectura where {donde}", **par)
    cat = costo.catalogo()
    p_ent, p_sal = costo.supuesto(cat, "modelo_usd_por_millon_entrada", 0.5), costo.supuesto(cat, "modelo_usd_por_millon_salida", 3.0)

    def costo_de(x: dict) -> float:
        """El costo que informó el servicio (asesor) si lo hay; si no, tokens por el precio de referencia."""
        if x.get("costo_usd") not in (None, ""):
            with suppress(ValueError):
                return float(x["costo_usd"])
        return (x["tokens_entrada"] or 0) / 1e6 * p_ent + (x["tokens_salida"] or 0) / 1e6 * p_sal

    por_uso = {}
    for u in sorted({x["uso"] for x in filas}):
        g = [x for x in filas if x["uso"] == u]
        bien = [x for x in g if x["estado_http"] == 200 and not x["error"]]
        ent, sal = sum(x["tokens_entrada"] or 0 for x in g), sum(x["tokens_salida"] or 0 for x in g)
        por_uso[u] = {"llamadas": len(g), "fallidas": len(g) - len(bien), "tokens_entrada": ent, "tokens_salida": sal,
                      "costo_usd": round(sum(costo_de(x) for x in g), 4),
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
    "tasa_sin_intervencion": ("Gastos aprobados sin intervención", "%", "Trabajo manual evitado", lambda f: _seccion(gastos, f)["tasa_sin_intervencion"]),
    "tiempo_a_aprobado": ("Mediana de recibido a aprobado", "s", "Cuello de botella de la revisión", lambda f: _seccion(gastos, f)["tiempo_mediana_s"]),
    "tasa_correccion": ("Campos corregidos sobre campos leídos", "%", "Calidad real de la lectura", lambda f: _seccion(gastos, f)["tasa_correccion"]),
    "pendientes_revision": ("Gastos esperando revisión", "gastos", "Carga de Finanzas", lambda f: _seccion(gastos, f)["pendientes"]),
    "gasto_real": ("Gasto real aprobado", "USD", "Control financiero", lambda f: _seccion(gastos, f)["real_total"]),
    "costo_por_recibo": ("Costo de leer un recibo", "USD", "Elección de modelo", lambda f: _seccion(uso_modelo, f)["costo_por_recibo_usd"]),
    "acuerdo_recomendacion": ("Decisiones que siguen la recomendación", "%", "Validez de las reglas", lambda f: _seccion(busquedas, f)["acuerdo"]),
    "ahorro_capturado": ("Ahorro capturado en decisiones", "USD", "Valor del comparador", lambda f: _seccion(busquedas, f)["ahorro_capturado"]),
    "tasa_reutilizacion": ("Búsquedas resueltas sin pagar otra consulta", "%", "Costo del buscador", lambda f: _seccion(buscador, f)["tasa_reutilizacion"]),
    "presupuestos_pendientes": ("Viajes esperando aprobación de presupuesto", "viajes", "Carga de quien aprueba", lambda f: _seccion(viajes, f)["pendientes"]),
    "ejecucion_presupuesto": ("Gasto aprobado sobre presupuesto aprobado", "%", "Vigilancia de los recursos por viaje", lambda f: _seccion(viajes, f)["ejecucion"]),
    "gastos_sin_viaje": ("Gastos que no pertenecen a ningún viaje", "gastos", "Cumplimiento de la regla de negocio", lambda f: _seccion(viajes, f)["gastos_sin_viaje"]),
    "decisiones_etiquetadas": ("Decisiones etiquetadas para entrenar", "decisiones", "Avance hacia el modelo de decisión", lambda f: _seccion(busquedas, f)["decisiones_etiquetadas"]),
    "tasa_consultas_fallidas": ("Consultas al buscador que fallan", "%", "Fiabilidad del buscador", lambda f: _seccion(buscador, f)["tasa_fallidas"]),
    "latencia_buscador": ("Mediana de espera de una consulta en vivo", "ms", "Experiencia de quien cotiza", lambda f: _seccion(buscador, f)["latencia_mediana_ms"]),
    "cupo_usado": ("Cupo mensual del buscador ya usado", "%", "Cuándo reutilizar más o ampliar el plan", lambda f: cupo(f)["usado_pct"]),
    "anticipacion_compra": ("Días entre la decisión y la ida", "días", "Comprar con anticipación cuesta menos", lambda f: _seccion(busquedas, f)["anticipacion_media_dias"]),
    "ahorro_identificado": ("Ahorro identificado por el comparador", "USD", "Cuánto vale comparar por costo total", lambda f: _seccion(busquedas, f)["ahorro_identificado"]),
    "captura_ahorro": ("Ahorro capturado sobre identificado", "%", "Si las decisiones aprovechan lo que el comparador encuentra", lambda f: _seccion(busquedas, f)["captura_ahorro"]),
    "horas_cotizacion_decision": ("Mediana de la cotización a la decisión", "h", "Agilidad de quien decide el viaje", lambda f: _seccion(busquedas, f)["horas_a_decision"]),
    "horas_decision_aprobacion": ("Mediana de la decisión a la aprobación", "h", "Agilidad de quien aprueba el presupuesto", lambda f: _seccion(viajes, f)["horas_a_aprobacion"]),
    "viajes_sobre_presupuesto": ("Viajes con gasto aprobado mayor al presupuesto", "viajes", "Dónde ajustar presupuestos o pedir explicación", lambda f: _seccion(viajes, f)["sobre_presupuesto"]),
    "dias_recibo_a_carga": ("Mediana de días del recibo a la carga", "días", "Puntualidad al reportar gastos", lambda f: _seccion(gastos, f)["dias_recibo_a_carga"]),
    "horas_carga_a_aprobacion": ("Mediana de la carga a la aprobación del gasto", "h", "Cuello de botella de la revisión", lambda f: _seccion(gastos, f)["tiempo_mediana_h"]),
    "revision_mas_antigua": ("Días del gasto más antiguo en revisión", "días", "Que ningún gasto quede olvidado", lambda f: _seccion(gastos, f)["revision_mas_antigua_dias"]),
}


def valor(nombre: str, f: dict) -> dict | None:
    if nombre not in CATALOGO:
        return None
    titulo, unidad, para_que, funcion = CATALOGO[nombre]
    return {"nombre": nombre, "titulo": titulo, "unidad": unidad, "para_que": para_que, "valor": funcion(f), "filtros": f}
