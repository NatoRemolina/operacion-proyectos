"""Indicadores con meta y semáforo para los dos retos, rastro de cada consulta al buscador y ficha por persona.

Las fórmulas viven en `metricas.CATALOGO` (una sola definición); aquí se añade lo que convierte una cifra
en indicador: para qué sirve, hacia dónde es mejor, la meta, el umbral de alerta y quién responde.
Las metas son supuestos editables en la tabla `reglas` (ámbito `kpi`), en la misma pantalla de Reglas.
"""
from collections import Counter
from datetime import date, timedelta
from statistics import median

from sqlalchemy import Column, Float, Integer, Text

from .. import db
from . import acceso, costo, metricas, ofertas, viajes

consultas_buscador = db._tabla(
    "consultas_buscador",  # una fila por consulta al buscador de precios; la respuesta completa está en `busquedas` con la misma clave
    Column("momento", Text), Column("solicitud_id", Integer), Column("usuario_id", Integer),
    Column("tipo", Text),     # vuelos, hoteles o tarifas
    Column("origen", Text),   # en vivo, guardado, guardado (otras fechas) o fallida
    Column("clave", Text), Column("duracion_ms", Integer), Column("resultados", Integer),
    Column("precio_min", Float), Column("precio_mediana", Float), Column("error", Text),
)


def registrar_consulta(tipo: str, origen: str, clave: str, solicitud_id: int | None, duracion_ms: int,
                       importes: list, error: str | None = None):
    u = acceso.actual()
    valores = sorted(float(p) for p in importes if p is not None)
    db.insertar("consultas_buscador", momento=db.ahora(), solicitud_id=solicitud_id, usuario_id=u["id"] if u else None,
                tipo=tipo, origen=origen, clave=clave, duracion_ms=duracion_ms, resultados=len(valores),
                precio_min=valores[0] if valores else None, precio_mediana=median(valores) if valores else None, error=error)


# ---------- catálogo de indicadores ----------
# reto: 1 cotización, 2 gastos. Las metas y umbrales son el valor inicial; los vigentes se leen de `reglas`.
KPIS = {
    # Reto 1: cotización
    "tasa_reutilizacion": dict(reto=1, sentido="mayor", meta=60, alerta=30, responsable="Operaciones", principal=True,
                               formula="Consultas resueltas con una respuesta guardada (misma búsqueda u otras fechas) ÷ consultas resueltas"),
    "tasa_consultas_fallidas": dict(reto=1, sentido="menor", meta=5, alerta=15, responsable="Operaciones",
                                    formula="Consultas fallidas ÷ todas las consultas al buscador"),
    "latencia_buscador": dict(reto=1, sentido="menor", meta=8000, alerta=20000, responsable="Operaciones",
                              formula="Mediana de la duración de las consultas en vivo, en milisegundos"),
    "cupo_usado": dict(reto=1, sentido="menor", meta=70, alerta=90, responsable="Operaciones",
                       formula="Búsquedas usadas este mes ÷ búsquedas del plan, según la cuenta del buscador"),
    "anticipacion_compra": dict(reto=1, sentido="mayor", meta=21, alerta=7, responsable="Operaciones",
                                formula="Promedio de días entre la decisión vigente de cada cotización y la fecha de ida"),
    "acuerdo_recomendacion": dict(reto=1, sentido="mayor", meta=70, alerta=50, responsable="Operaciones", principal=True,
                                  formula="Decisiones que eligen la opción recomendada ÷ decisiones con recomendación registrada"),
    "ahorro_identificado": dict(reto=1, sentido="mayor", meta=100, alerta=0, responsable="Finanzas", base=("busquedas", "consultas"),
                                formula="Suma por cotización de: costo esperado del vuelo más barato que sirve − costo esperado del recomendado"),
    "ahorro_capturado": dict(reto=1, sentido="mayor", meta=100, alerta=0, responsable="Finanzas", base=("busquedas", "decisiones"),
                             formula="Suma por decisión vigente de: costo esperado del más barato que sirve − costo esperado de lo elegido"),
    "captura_ahorro": dict(reto=1, sentido="mayor", meta=80, alerta=50, responsable="Finanzas", principal=True, base=("busquedas", "decisiones"),
                           formula="Ahorro capturado ÷ ahorro identificado"),
    "horas_cotizacion_decision": dict(reto=1, sentido="menor", meta=24, alerta=72, responsable="Operaciones",
                                      formula="Mediana de horas entre la cotización y su primera decisión"),
    "horas_decision_aprobacion": dict(reto=1, sentido="menor", meta=24, alerta=72, responsable="Finanzas", principal=True,
                                      formula="Mediana de horas entre el nacimiento del viaje (la decisión) y la aprobación del presupuesto"),
    # Reto 2: gastos, con la mirada de Finanzas
    "ejecucion_presupuesto": dict(reto=2, sentido="menor", meta=100, alerta=110, responsable="Finanzas", principal=True,
                                  formula="Gasto aprobado de los viajes aprobados o cerrados ÷ su presupuesto"),
    "viajes_sobre_presupuesto": dict(reto=2, sentido="menor", meta=0, alerta=1, responsable="Finanzas", base=("viajes", "con_presupuesto"),
                                     formula="Viajes aprobados o cerrados cuyo gasto aprobado supera el presupuesto"),
    "tasa_sin_intervencion": dict(reto=2, sentido="mayor", meta=70, alerta=40, responsable="Finanzas", principal=True,
                                  formula="Gastos aprobados solos ÷ gastos recibidos"),
    "dias_recibo_a_carga": dict(reto=2, sentido="menor", meta=3, alerta=10, responsable="Finanzas", principal=True,
                                formula="Mediana de días entre la fecha del recibo y su llegada a la plataforma"),
    "horas_carga_a_aprobacion": dict(reto=2, sentido="menor", meta=24, alerta=72, responsable="Finanzas",
                                     formula="Mediana de horas entre «documento recibido» y la aprobación del gasto"),
    "tasa_correccion": dict(reto=2, sentido="menor", meta=5, alerta=15, responsable="Finanzas",
                            formula="Campos que difieren entre lo leído y lo aprobado ÷ campos leídos"),
    "gastos_sin_viaje": dict(reto=2, sentido="menor", meta=0, alerta=2, responsable="Finanzas", base=("viajes", "gastos"),
                             formula="Gastos sin viaje asignado"),
    "pendientes_revision": dict(reto=2, sentido="menor", meta=5, alerta=15, responsable="Finanzas", base=("gastos", "recibidos"),
                                formula="Gastos en estado de revisión"),
    "revision_mas_antigua": dict(reto=2, sentido="menor", meta=2, alerta=7, responsable="Finanzas",
                                 formula="Días desde que llegó el gasto más antiguo que sigue en revisión"),
    "costo_por_recibo": dict(reto=2, sentido="menor", meta=0.01, alerta=0.05, responsable="Operaciones",
                             formula="Costo estimado de los tokens de lectura ÷ recibos leídos"),
}
# `base`: (sección, cifra) que cuenta sobre qué se mide. Si es cero, un conteo o una suma en cero no es un dato sino ausencia de
# datos: sin viajes, «cero viajes sobre presupuesto» se pintaría de verde sin que nada lo respalde.
SECCIONES = {"gastos": metricas.gastos, "viajes": metricas.viajes, "busquedas": metricas.busquedas}
RETOS = {1: "Cotización de viajes", 2: "Gastos (mirada de Finanzas)"}
ESTADOS = {"verde": "En meta", "ambar": "Atención", "rojo": "Fuera de meta", "sin datos": "Sin datos", "fuera de rango": "Fuera de rango"}
# Valores posibles de cada indicador (mínimo, máximo). Un valor fuera no es un logro sino un dato malo (por ejemplo, un recibo
# con fecha futura da días negativos): sin esto «−28 días» se pintaría «en meta» por ser menor que la meta.
# El ahorro puede ser negativo (se eligió algo más caro que lo más barato que sirve); las proporciones no pasan de 100 %.
PROPORCIONES = ("tasa_reutilizacion", "tasa_consultas_fallidas", "cupo_usado", "acuerdo_recomendacion", "tasa_sin_intervencion",
                "tasa_correccion")
RANGOS = {n: (None, None) if n in ("ahorro_identificado", "ahorro_capturado", "captura_ahorro")
          else (0, 100) if n in PROPORCIONES else (0, None) for n in KPIS}
# Los que dicen algo de una persona. El cupo es de la cuenta; el costo de lectura, las fallas y la espera del buscador no dependen de ella
DE_PERSONA = [n for n in KPIS if n not in ("cupo_usado", "costo_por_recibo", "tasa_consultas_fallidas", "latencia_buscador")]


def asegurar_metas():
    """Crea en `reglas` la meta y el umbral de cada indicador que aún no los tenga. Nunca pisa un valor editado."""
    cat = costo.catalogo()
    for nombre, k in KPIS.items():
        titulo = metricas.CATALOGO[nombre][0]
        mejor = "mayor es mejor" if k["sentido"] == "mayor" else "menor es mejor"
        for clave, valor, nota in (
                ("meta", k["meta"], f"Meta de «{titulo}» ({mejor}). Desde aquí el semáforo está en verde."),
                ("umbral_alerta", k["alerta"], f"Umbral de alerta de «{titulo}» ({mejor}). Pasado este valor el semáforo está en rojo.")):
            if ("kpi", nombre, "", clave) not in cat:
                db.insertar("reglas", ambito="kpi", entidad=nombre, tarifa="", clave=clave, valor=f"{valor:g}", nota=nota,
                            fuente="Supuesto editable", confianza="supuesto", verificado=db.ahora()[:10])


def _numero(cat: dict, nombre: str, clave: str, defecto: float) -> float:
    r = cat.get(("kpi", nombre, "", clave))
    try:
        return float(r["valor"]) if r else defecto
    except ValueError:
        return defecto


def estado(valor, sentido: str, meta: float, alerta: float, rango: tuple = (None, None)) -> str:
    """Verde si cumple la meta, ámbar entre la meta y el umbral de alerta, rojo pasado el umbral. Sin valor no hay color,
    y un valor imposible para el indicador (fuera de `rango`) queda «fuera de rango», nunca en meta."""
    if valor is None:
        return "sin datos"
    minimo, maximo = rango
    if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
        return "fuera de rango"
    if sentido == "mayor":
        return "verde" if valor >= meta else "ambar" if valor >= alerta else "rojo"
    return "verde" if valor <= meta else "ambar" if valor <= alerta else "rojo"


def _valor(nombre: str, f: dict):
    valor = metricas.CATALOGO[nombre][3](f)
    base = KPIS[nombre].get("base")
    if valor is not None and base and not metricas._seccion(SECCIONES[base[0]], f)[base[1]]:
        return None
    return valor


def evaluar(f: dict, nombres: list[str] | None = None) -> list[dict]:
    """Valor, meta y semáforo de cada indicador con los filtros dados (proyecto, desde, hasta, persona)."""
    asegurar_metas()
    cat = costo.catalogo()
    salida = []
    with metricas.una_lectura():
        for nombre in nombres or list(KPIS):
            k = KPIS[nombre]
            titulo, unidad, para_que, _ = metricas.CATALOGO[nombre]
            meta, alerta = _numero(cat, nombre, "meta", k["meta"]), _numero(cat, nombre, "umbral_alerta", k["alerta"])
            valor = _valor(nombre, f)
            e = estado(valor, k["sentido"], meta, alerta, RANGOS[nombre])
            salida.append({"nombre": nombre, "titulo": titulo, "unidad": unidad, "para_que": para_que, "formula": k["formula"],
                           "sentido": k["sentido"], "meta": meta, "alerta": alerta, "responsable": k["responsable"],
                           "reto": k["reto"], "principal": k.get("principal", False), "valor": valor,
                           "estado": e, "estado_texto": ESTADOS[e]})
    return salida


def tendencia(f: dict, semanas: int = 8) -> dict:
    """Los indicadores principales semana a semana, calculados sobre los hechos de cada semana (lunes a domingo)."""
    try:
        fin = date.fromisoformat(f["hasta"]) if f.get("hasta") else date.today()
    except ValueError:
        fin = date.today()
    lunes = fin - timedelta(days=fin.weekday())
    inicios = [lunes - timedelta(weeks=i) for i in range(semanas - 1, -1, -1)]
    principales = [n for n, k in KPIS.items() if k.get("principal")]
    asegurar_metas()
    cat = costo.catalogo()
    filas = {n: [] for n in principales}
    with metricas.una_lectura():
        for ini in inicios:
            fs = {**f, "desde": ini.isoformat(), "hasta": (ini + timedelta(days=6)).isoformat()}
            for n in principales:
                valor = _valor(n, fs)
                filas[n].append({"valor": valor, "estado": estado(valor, KPIS[n]["sentido"], _numero(cat, n, "meta", KPIS[n]["meta"]),
                                                                   _numero(cat, n, "umbral_alerta", KPIS[n]["alerta"]), RANGOS[n])})
    return {"semanas": [i.isoformat() for i in inicios],
            "filas": [{"nombre": n, "titulo": metricas.CATALOGO[n][0], "unidad": metricas.CATALOGO[n][1], "puntos": filas[n]}
                      for n in principales]}


def tablero(f: dict) -> dict:
    """Todo lo del tablero con unos mismos filtros: indicadores, tendencia, desgloses y personas."""
    ofertas.actualizar_si_toca()   # las tarifas vistas quedan al día sin otro proceso (como mucho cada 10 minutos)
    with metricas.una_lectura():
        indicadores = evaluar(f)
        b, c = metricas._seccion(metricas.busquedas, f), metricas._seccion(metricas.buscador, f)
        g, v = metricas._seccion(metricas.gastos, f), metricas._seccion(metricas.viajes, f)
        return {
            "filtros": f, "kpis": indicadores, "resumen": Counter(k["estado"] for k in indicadores),
            "tendencia": tendencia(f),
            "cotizacion": {"cotizaciones_por_persona": b["por_persona"], "cotizaciones_por_ruta": b["por_ruta"],
                           "consultas_por_origen": c["por_origen"], "consultas_por_tipo": c["por_tipo"],
                           "consultas_por_persona": c["por_persona"], "consultas_por_ruta": c["por_ruta"],
                           "errores_buscador": c["errores"], "cupo": metricas.cupo()["cupo"]},
            "gastos": {"por_viaje": v["detalle"], "por_proyecto": v["por_proyecto"], "por_categoria": v["por_categoria"],
                       "por_moneda": g["por_moneda"], "revision_antiguas": g["revision_antiguas"], "real_total": g["real_total"]},
            "personas": personas(f), "por_cargo": por_cargo(f),
        }


# ---------- personas ----------
def personas(f: dict) -> list[dict]:
    """Una fila por cuenta con lo que le pertenece: cotizaciones, viajes, presupuesto, gasto y revisión."""
    sin_persona = {k: v for k, v in f.items() if k != "persona_id"}
    donde_s, par_s = metricas._filtro(sin_persona, "creado", alias="s")
    cot = {r["persona"]: r["n"] for r in db.todos(
        f"""select persona, count(*) n from (select {metricas.titular_solicitud('s')} persona from solicitudes s where {donde_s}) t
            group by persona""", **par_s)}
    donde_v, par_v = metricas._filtro(sin_persona, "creado")
    via = {r["usuario_id"]: r for r in db.todos(
        f"""select usuario_id, count(*) n,
                   sum(case when estado in ('aprobado','cerrado') then presupuesto_usd else 0 end) presupuesto,
                   sum(case when estado in ('aprobado','cerrado') then gastado_usd else 0 end) gastado,
                   sum(en_revision_usd) en_revision
            from v_h_viaje where {donde_v} group by usuario_id""", **par_v)}
    donde_g, par_g = metricas._filtro(sin_persona, "creado", alias="g")
    gas = {r["persona"]: r for r in db.todos(
        f"""select persona, count(*) n, sum(case when estado='revision' then 1 else 0 end) revision
            from (select {metricas.dueno('g')} persona, g.estado from gastos g where {donde_g}) t group by persona""", **par_g)}
    salida = []
    for u in db.todos("select id, nombre, correo, rol, activo from usuarios order by id"):
        v, g = via.get(u["id"]) or {}, gas.get(u["id"]) or {}
        presupuesto, gastado = v.get("presupuesto") or 0, v.get("gastado") or 0
        salida.append({**u, "codigo": viajes.codigo_persona(u["id"]), "rol_texto": acceso.NOMBRE_ROL.get(u["rol"], u["rol"]),
                       "cotizaciones": cot.get(u["id"], 0), "viajes": v.get("n", 0), "presupuesto": round(presupuesto, 2),
                       "gastado": round(gastado, 2), "en_revision": round(v.get("en_revision") or 0, 2),
                       "ejecucion": metricas._pct(gastado, presupuesto), "gastos": g.get("n", 0), "gastos_revision": g.get("revision") or 0})
    return salida


def por_cargo(f: dict | None = None) -> list[dict]:
    """Viajes, gasto aprobado y gasto en revisión por cargo. El cargo de un viaje es el de su titular; el de un gasto,
    el del titular de su viaje o, sin viaje, el de quien lo cargó. Las cuentas sin cargo salen como «Sin cargo»."""
    f = {k: v for k, v in (f or {}).items() if k != "persona_id"}
    donde_v, par_v = metricas._filtro(f, "creado")
    donde_g, par_g = metricas._filtro(f, "creado")
    filas: dict[str, dict] = {}
    for r in db.todos(f"select cargo, count(*) n from v_h_viaje where {donde_v} group by cargo", **par_v):
        filas[r["cargo"]] = {"cargo": r["cargo"], "viajes": r["n"], "gasto_usd": 0.0, "en_revision": 0.0}
    for r in db.todos(
            f"""select cargo, sum(case when estado in ('aprobado','aprobado_auto') then total_usd else 0 end) gasto,
                       sum(case when estado='revision' then total_usd else 0 end) revision
                from v_h_gasto where {donde_g} group by cargo""", **par_g):
        fila = filas.setdefault(r["cargo"], {"cargo": r["cargo"], "viajes": 0, "gasto_usd": 0.0, "en_revision": 0.0})
        fila["gasto_usd"], fila["en_revision"] = round(r["gasto"] or 0, 2), round(r["revision"] or 0, 2)
    return sorted(filas.values(), key=lambda x: (-x["gasto_usd"], x["cargo"]))


def _codigo_de(viaje_id, creado) -> str | None:
    return viajes.codigo_viaje({"id": viaje_id, "creado": creado}) if viaje_id else None


def ficha_persona(usuario_id: int) -> dict | None:
    """Todo lo de una persona por su ID, y nada de otra: cotizaciones, viajes, gastos, evidencias, eventos e indicadores.

    Pertenece a la persona lo que la tiene como titular (quien viaja); un gasto o evidencia sin viaje, a quien lo cargó.
    """
    u = db.uno("""select u.id, u.correo, u.nombre, u.rol, u.activo, u.creado, u.telegram_usuario, v.nombre viajero, v.base,
                         coalesce(c.nombre, 'Sin cargo') cargo
                  from usuarios u left join viajeros v on v.id=u.viajero_id left join cargos c on c.id=u.cargo_id where u.id=:i""", i=usuario_id)
    if not u:
        return None
    cotizaciones = db.todos(f"""select s.id, s.origen, s.destino, s.ciudad, s.ida, s.regreso, s.estado, s.creado, p.nombre proyecto,
                                       vj.id viaje_id, vj.creado viaje_creado, vj.estado viaje_estado
                                from solicitudes s left join proyectos p on p.id=s.proyecto_id left join viajes vj on vj.solicitud_id=s.id
                                where {metricas.titular_solicitud('s')}=:u order by s.id desc""", u=usuario_id)
    for c in cotizaciones:
        c["viaje"] = _codigo_de(c.pop("viaje_id"), c.pop("viaje_creado"))
    sus_viajes = viajes.lista("v.usuario_id=:u", u=usuario_id)
    gastos = db.todos(f"""select g.id, g.comercio, g.fecha, g.categoria, g.total, g.moneda, g.total_usd, g.estado, g.creado,
                                 g.viaje_id, vj.creado viaje_creado, d.canal
                          from gastos g left join documentos d on d.id=g.documento_id left join viajes vj on vj.id=g.viaje_id
                          where {metricas.dueno('g')}=:u order by g.id desc""", u=usuario_id)
    for g in gastos:
        g["viaje"] = _codigo_de(g["viaje_id"], g.pop("viaje_creado"))
    evidencias = db.todos(f"""select d.id, d.tipo, d.canal, d.nombre, d.mime, d.creado, d.texto, d.viaje_id, vj.creado viaje_creado
                              from documentos d left join viajes vj on vj.id=d.viaje_id
                              where {metricas.dueno('d')}=:u order by d.id desc""", u=usuario_id)
    for d in evidencias:
        d["viaje"] = _codigo_de(d["viaje_id"], d.pop("viaje_creado"))
    # Línea de tiempo: solo los hechos sobre lo suyo, aunque los haya registrado otra persona (por ejemplo, la aprobación)
    sobre = ["(e.entidad in ('usuario','acceso') and e.entidad_id=:u)"]
    for entidad, ids in (("solicitud", [c["id"] for c in cotizaciones]), ("viaje", [v["id"] for v in sus_viajes]),
                         ("gasto", [g["id"] for g in gastos])):
        if ids:
            sobre.append(f"(e.entidad='{entidad}' and e.entidad_id in ({','.join(str(int(i)) for i in ids)}))")
    linea = db.todos(f"""select e.momento, e.entidad, e.entidad_id, e.paso, e.detalle, e.fuente, q.nombre quien
                         from eventos e left join usuarios q on q.id=e.usuario_id
                         where {' or '.join(sobre)} order by e.id desc limit 200""", u=usuario_id)
    aprobados = [g for g in gastos if g["estado"] in metricas.APROBADOS]
    return {
        "usuario": {**u, "codigo": viajes.codigo_persona(u["id"]), "rol_texto": acceso.NOMBRE_ROL.get(u["rol"], u["rol"])},
        "cotizaciones": cotizaciones, "viajes": sus_viajes, "gastos": gastos, "evidencias": evidencias, "eventos": linea,
        "gastos_por_estado": Counter(g["estado"] for g in gastos).most_common(),
        "gastos_por_canal": Counter(g["canal"] or "—" for g in gastos).most_common(),
        "totales": {"presupuesto": round(sum(v["presupuesto_usd"] or 0 for v in sus_viajes if v["estado"] in ("aprobado", "cerrado")), 2),
                    "gastado": round(sum(g["total_usd"] or 0 for g in aprobados), 2),
                    "en_revision": round(sum(g["total_usd"] or 0 for g in gastos if g["estado"] == "revision"), 2)},
        "indicadores": evaluar({"persona_id": usuario_id}, DE_PERSONA),
    }
