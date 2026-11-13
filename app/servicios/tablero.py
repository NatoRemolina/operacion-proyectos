"""Lo que comparten las pantallas de KPIs y Monitoreo con la API v1: filtros, datos de cada pestaña y exportaciones.

Las cifras salen de `metricas` y `kpis`; aquí solo se arma lo que antes vivía dentro de las rutas Jinja,
para que la pantalla y la API respondan exactamente lo mismo.
"""
import re

from .. import config, db
from . import asesor, cotizacion, eventos, exportacion, kpis, metricas, precios, viajes

_ES_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def filtros(proyecto_id: int = 0, desde: str = "", hasta: str = "") -> dict:
    """Proyecto y fechas (AAAA-MM-DD). Lo que no es válido se ignora, como en la pantalla."""
    return {"proyecto_id": proyecto_id or None, "desde": desde if _ES_FECHA.match(desde or "") else None,
            "hasta": hasta if _ES_FECHA.match(hasta or "") else None}


def proyectos() -> list[dict]:
    return db.todos("select id, nombre from proyectos order by id")


# ---------- KPIs ----------
EXPORTABLES_KPIS = {"kpis": "indicadores", "consultas": "consultas al buscador", "personas": "personas"}


def tablero_kpis(f: dict) -> dict:
    cotizacion.completar_ahorros()
    return kpis.tablero(f)


def exportar_kpis(que: str, f: dict) -> tuple[str, str]:
    """CSV de indicadores, consultas al buscador o personas con los filtros dados, y su nombre de archivo. Deja el evento."""
    if que == "kpis":
        filas = [{c: k[c] for c in ("nombre", "titulo", "valor", "unidad", "estado", "meta", "alerta", "sentido", "responsable", "formula")}
                 for k in kpis.evaluar(f)]
    elif que == "personas":
        filas = kpis.personas(f)
    else:
        donde, par = metricas._filtro(f, "momento")
        filas = db.todos(f"select * from v_h_consulta where {donde} order by id", **par)
    eventos.registrar("kpis", None, "exportación", f"{EXPORTABLES_KPIS[que]}: {len(filas)} filas")
    return exportacion.csv_de(filas), f"kpis_{que}.csv"


# ---------- Monitoreo ----------
PESTANAS = {"viajes": "Viajes", "gastos": "Gastos", "busquedas": "Búsquedas", "modelo": "Modelo de lenguaje", "cupos": "Cupos",
            "auditoria": "Auditoría", "calidad": "Calidad"}
FECHA_DE_VISTA = {"v_h_viaje": "creado", "v_h_gasto": "creado", "v_h_busqueda": "creado", "v_h_decision": "creado", "v_h_lectura": "momento",
                  "v_h_evento": "momento", "v_h_consulta": "momento"}
TABLAS_CONTADAS = ("usuarios", "viajes", "gastos", "documentos", "telegram_mensajes", "solicitudes", "opciones", "decisiones", "elecciones",
                   "observaciones", "busquedas", "eventos", "llamadas_modelo", "errores")


def datos_pestana(pestana: str, f: dict) -> dict:
    if pestana == "viajes":
        return metricas.viajes(f)
    if pestana == "gastos":
        return metricas.gastos(f)
    if pestana == "busquedas":
        cotizacion.completar_ahorros()
        return metricas.busquedas(f)
    if pestana == "modelo":
        return metricas.uso_modelo(f)
    if pestana == "cupos":
        hoy = db.ahora()[:10]
        return {"buscador": precios.cupo(), "busquedas": metricas.busquedas(f),
                "modelo_hoy": db.uno("select count(*) n from llamadas_modelo where momento>=:h", h=hoy)["n"],
                "filas": [(t, db.uno(f"select count(*) n from {t}")["n"]) for t in TABLAS_CONTADAS]}
    if pestana == "auditoria":
        donde, par = metricas._filtro({**f, "proyecto_id": None}, "momento")
        return {"eventos": db.todos(f"select * from v_h_evento where {donde} order by id desc limit 150", **par),
                "por_persona": db.todos(f"""select coalesce(usuario,'sistema') usuario, count(*) n from v_h_evento
                                            where {donde} group by coalesce(usuario,'sistema') order by n desc""", **par),
                "por_paso": db.todos(f"select paso, count(*) n from v_h_evento where {donde} group by paso order by n desc", **par),
                "errores": db.todos("""select e.*, u.nombre usuario from errores e left join usuarios u on u.id=e.usuario_id
                                       order by e.id desc limit 30""")}
    g = metricas.gastos(f)
    return {"pruebas": metricas.calidad_de_datos(), "calibracion": g["calibracion"], "por_campo": g["correccion_por_campo"],
            "tasa_correccion": g["tasa_correccion"], "evaluados": g["gastos_evaluados"],
            "umbral": config.UMBRAL_CONFIANZA}


def catalogo(f: dict) -> list[dict]:
    return [metricas.valor(n, f) for n in metricas.CATALOGO]


def exportar_vista(vista: str, f: dict) -> str:
    """CSV de un hecho de la capa analítica con los filtros dados. Deja el evento. `vista` ya debe estar en `VISTAS`."""
    f = dict(f)
    if vista in ("v_h_lectura", "v_h_evento"):
        f["proyecto_id"] = None
    donde, par = metricas._filtro(f, FECHA_DE_VISTA[vista])
    filas = db.todos(f"select * from {vista} where {donde} order by id", **par)
    eventos.registrar("monitoreo", None, "exportación", f"{vista}: {len(filas)} filas")
    return exportacion.csv_de(filas)


# ---------- Monitoreo como cifras y tablas (lo que pinta la web) ----------
def _cifra(etiqueta: str, valor, pie: str = "", unidad: str | None = None) -> dict:
    return {"etiqueta": etiqueta, "valor": valor, "unidad": unidad, "pie": pie}


def _col(texto: str, unidad: str | None = None, fin: bool = False) -> dict:
    return {"texto": texto, "unidad": unidad, "fin": fin or unidad is not None}


def _tabla(titulo: str, columnas: list[dict], filas: list[list], vacio: str = "Sin datos todavía.", nota: str | None = None,
           barras: bool = False) -> dict:
    """`barras`: la segunda columna es una cifra que la web puede dibujar como barra (embudo, categorías)."""
    return {"titulo": titulo, "columnas": columnas, "filas": filas, "vacio": vacio, "nota": nota, "barras": barras}


def _pares(titulo: str, filas, c1: str, c2: str, vacio: str = "Sin datos todavía.", barras: bool = False) -> dict:
    return _tabla(titulo, [_col(c1), _col(c2, fin=True)], [[a, b] for a, b in filas or []], vacio, barras=barras)


def _enlace(texto: str, href: str) -> dict:
    return {"texto": texto, "href": href}


def _usd(v) -> str:
    return "—" if v is None else f"{v:,.2f} USD"


def _pestana_viajes(d: dict) -> tuple[list, list, list]:
    cifras = [_cifra("Presupuestos por aprobar", d["pendientes"], f"{d['viajes']} viajes en total · {d['aprobados']} aprobados"),
              _cifra("Ejecución del presupuesto", d["ejecucion"], f"{_usd(d['gastado'])} de {_usd(d['presupuesto_aprobado'])}", "%"),
              _cifra("Viajes sobre su presupuesto", d["sobre_presupuesto"], "gasto aprobado mayor al presupuesto"),
              _cifra("De la decisión a la aprobación", d["horas_a_aprobacion"], "mediana", "h"),
              _cifra("Gastos sin viaje", d["gastos_sin_viaje"], f"de {d['gastos']} gastos: incumplen la regla y esperan revisión")]
    tablas = [_tabla("Presupuesto frente a gasto, por viaje",
                     [_col("Viaje"), _col("Titular"), _col("Ruta"), _col("Ida"), _col("Estado"), _col("Presupuesto", "USD"),
                      _col("Aprobado", "USD"), _col("En revisión", "USD"), _col("Ejecución", "%")],
                     [[_enlace(viajes.codigo_viaje(v), f"/viajes/{v['id']}"), v["titular"], v["ruta"], v["ida"], v["estado"],
                       v["presupuesto"], v["gastado"], v["en_revision"], v["pct"]] for v in d["detalle"]],
                     "Sin viajes en el periodo."),
              _pares("Por dónde llegan los gastos", d["por_canal"], "Canal", "Gastos"),
              _pares("Viajes por persona", d["por_titular"], "Titular", "Viajes")]
    return cifras, tablas, [{"vista": "v_h_viaje", "texto": "Viajes"}]


def _pestana_gastos(d: dict) -> tuple[list, list, list]:
    p90 = d["tiempo_p90_s"] if d["tiempo_p90_s"] is not None else "—"
    cifras = [_cifra("Aprobados sin intervención", d["tasa_sin_intervencion"], f"de {d['recibidos']} recibidos", "%"),
              _cifra("Esperando revisión", d["pendientes"], "carga actual de quien revisa"),
              _cifra("De recibido a aprobado", d["tiempo_mediana_s"], f"mediana · percentil 90: {p90} s", "s"),
              _cifra("Campos corregidos", d["tasa_correccion"], f"sobre lo leído en {d['gastos_evaluados']} gastos ya cerrados", "%"),
              _cifra("Gasto real aprobado", d["real_total"], "convertido a USD", "USD")]
    tablas = [_pares("Embudo", d["embudo"], "Etapa", "Gastos", barras=True),
              _pares("Por qué van a revisión", d["motivos"], "Motivo", "Gastos", "Ningún gasto ha ido a revisión."),
              _tabla("Gasto real por categoría", [_col("Categoría"), _col("Gasto", "USD")],
                     [[a, b] for a, b in d["real_por_categoria"]], "Sin gastos aprobados en el periodo.", barras=True),
              _pares("Por dónde llegan", d["por_canal"], "Canal", "Gastos"),
              _pares("Por viajero", d["por_viajero"], "Viajero", "Gastos"),
              _pares("Campos que más se corrigen", d["correccion_por_campo"], "Campo", "Correcciones",
                     "Ninguna corrección: lo aprobado coincide con lo leído.")]
    return cifras, tablas, [{"vista": "v_h_gasto", "texto": "Gastos"}]


def _pestana_busquedas(d: dict) -> tuple[list, list, list]:
    cifras = [_cifra("Consultas de viaje", d["consultas"], f"{d['decisiones']} con decisión guardada"),
              _cifra("Siguen la recomendación", d["acuerdo"], f"de {d['decisiones_con_dato']} decisiones con registro", "%"),
              _cifra("Ahorro identificado", d["ahorro_identificado"], "más barato que sirve − recomendado", "USD"),
              _cifra("Ahorro capturado", d["ahorro_capturado"], "en las decisiones guardadas", "USD"),
              _cifra("Resueltas sin pagar consulta", d["tasa_reutilizacion"],
                     f"{d['consultas_reutilizadas']} reutilizadas · {d['consultas_en_vivo']} en vivo", "%"),
              _cifra("Decisiones etiquetadas para entrenar", d["decisiones_etiquetadas"],
                     f"de {d['minimo_para_entrenar']} necesarias · {d['opciones_etiquetadas']} opciones mostradas")]
    tablas = [_pares("Rutas más consultadas", d["por_ruta"], "Ruta", "Consultas"),
              _pares("Quién consulta", d["por_persona"], "Persona", "Consultas"),
              _pares("Razones marcadas al decidir", d["razones"], "Razón", "Veces", "Aún no hay decisiones con razones.")]
    return cifras, tablas, [{"vista": "v_h_busqueda", "texto": "Consultas"}, {"vista": "v_h_decision", "texto": "Decisiones"}]


def _pestana_modelo(d: dict) -> tuple[list, list, list]:
    a = d["por_uso"].get("asesor") or {}
    cifras = [_cifra("Llamadas al modelo", d["llamadas"], ", ".join(d["modelos"]) or "sin llamadas registradas"),
              _cifra("Costo estimado", d["costo_total_usd"],
                     f"a {d['precio_entrada']:g} / {d['precio_salida']:g} USD por millón de tokens (entrada / salida)", "USD"),
              _cifra("Costo por recibo", d["costo_por_recibo_usd"], "promedio por lectura", "USD"),
              _cifra("Costo del asesor", a.get("costo_usd", 0), f"{a.get('llamadas', 0)} sesiones en el periodo · tope de "
                     f"{float(asesor.tope_usd_dia()):g} USD por día (supuesto asesor_usd_dia)", "USD")]
    tablas = [_tabla("Por uso", [_col("Uso"), _col("Llamadas", fin=True), _col("Fallidas", fin=True), _col("Tokens de entrada", fin=True),
                                 _col("Tokens de salida", fin=True), _col("Latencia mediana (ms)", fin=True), _col("Costo", "USD")],
                     [[u, x["llamadas"], x["fallidas"], x["tokens_entrada"], x["tokens_salida"], x["latencia_mediana_ms"], x["costo_usd"]]
                      for u, x in d["por_uso"].items()], "Sin llamadas en el periodo.",
                     "El costo es una estimación: tokens registrados por el precio de referencia, que se edita en Reglas. "
                     "Las sesiones del asesor (uso «asesor») llevan el costo que informa su servicio."),
              _tabla("Últimos errores del modelo", [_col("Momento (UTC)"), _col("Uso"), _col("Error")],
                     [list(e) for e in d["errores"]], "Sin errores.")]
    return cifras, tablas, [{"vista": "v_h_lectura", "texto": "Llamadas al modelo"}]


def _pestana_cupos(d: dict) -> tuple[list, list, list]:
    b, s = d["buscador"], d["busquedas"]
    cifras = [_cifra("Búsquedas restantes", b["restantes"], f"plan {b.get('plan') or '—'} · {b.get('usadas') or 0} de "
                     f"{b.get('mensual') or '—'} usadas este mes") if b else
              _cifra("Búsquedas restantes", None, "sin clave del buscador o sin respuesta: se trabaja con datos guardados"),
              _cifra("Consultas en vivo", s["consultas_en_vivo"], f"{s['consultas_fallidas']} fallidas"),
              _cifra("Respuestas reutilizadas", s["consultas_reutilizadas"], "no gastaron cupo")]
    ac = s.get("autocompletado")
    if ac:
        apagado = " · apagado (solo datos locales)" if ac.get("proveedor") == "local" else ""
        cifras.append(_cifra("Autocompletado de lugares este mes", ac["mes"],
                             f"de {ac['tope_mes']} del tope mensual · {ac['tope_persona_dia']} por persona y día{apagado}"))
    cifras.append(_cifra("Llamadas al modelo hoy", d["modelo_hoy"], "fecha en UTC"))
    return cifras, [_pares("Tamaño de los datos", d["filas"], "Tabla", "Filas")], []


def _pestana_auditoria(d: dict) -> tuple[list, list, list]:
    tablas = [_tabla("Actividad por persona", [_col("Persona"), _col("Acciones", fin=True)],
                     [[x["usuario"], x["n"]] for x in d["por_persona"]], "Sin actividad."),
              _tabla("Qué se hizo", [_col("Paso"), _col("Veces", fin=True)], [[x["paso"], x["n"]] for x in d["por_paso"]], "Sin actividad."),
              _tabla("Errores registrados", [_col("Momento (UTC)"), _col("Identificador"), _col("Ruta"), _col("Persona"), _col("Tipo"),
                                             _col("Mensaje")],
                     [[e["momento"], e["peticion"], e["ruta"], e["usuario"] or "—", e["tipo"], e["mensaje"]] for e in d["errores"]],
                     "Sin errores registrados."),
              _tabla("Últimos hechos", [_col("Momento (UTC)"), _col("Persona"), _col("Sobre"), _col("Paso"), _col("Detalle"), _col("Fuente"),
                                        _col("ms", fin=True)],
                     [[e["momento"], e["usuario"] or "sistema", f"{e['entidad']}{' #' + str(e['entidad_id']) if e['entidad_id'] else ''}",
                       e["paso"], e["detalle"], e["fuente"], e["duracion_ms"]] for e in d["eventos"]],
                     "Sin hechos en el periodo.", f"Los {len(d['eventos'])} más recientes (150 como máximo).")]
    return [], tablas, [{"vista": "v_h_evento", "texto": "Bitácora"}]


def _pestana_calidad(d: dict, f: dict) -> tuple[list, list, list]:
    tablas = [_tabla("Comprobaciones de los datos", [_col("Debe dar cero"), _col("Casos", fin=True)],
                     [[p["prueba"], p["casos"]] for p in d["pruebas"]], "Sin comprobaciones."),
              _tabla("¿La confianza del modelo predice las correcciones?",
                     [_col("Confianza declarada"), _col("Gastos", fin=True), _col("Corregidos", fin=True), _col("Tasa", "%")],
                     [[c["tramo"], c["gastos"], c["corregidos"], c["tasa"]] for c in d["calibracion"]], "Sin gastos evaluados.",
                     f"El umbral para aprobar sin revisión es {d['umbral'] * 100:.0f} %. Si los tramos por encima del umbral se corrigen "
                     f"poco y los de abajo mucho, el umbral está bien puesto; con {d['evaluados']} gastos evaluados la tabla todavía "
                     "muestra el método, no una conclusión."),
              _tabla("Catálogo de métricas", [_col("Métrica"), _col("Nombre en la API"), _col("Para qué sirve"), _col("Valor", fin=True)],
                     [[m["titulo"], m["nombre"], m["para_que"], None if m["valor"] is None else f"{m['valor']} {m['unidad']}"]
                      for m in catalogo(f)], "Sin métricas.",
                     "Las mismas cifras en /api/metricas?nombre=…&proyecto_id=…&desde=…&hasta=…")]
    return [], tablas, []


NOTA_MONITOREO = ("Cada cifra sale del catálogo de métricas, con una sola definición, y se calcula sobre los hechos registrados. "
                  "Con pocos datos las cifras muestran el método, no conclusiones.")


def pestana_monitoreo(pestana: str, f: dict) -> dict:
    """Una pestaña de Monitoreo lista para mostrar: cifras, tablas y las vistas que se pueden descargar."""
    d = datos_pestana(pestana, f)
    armar = {"viajes": _pestana_viajes, "gastos": _pestana_gastos, "busquedas": _pestana_busquedas, "modelo": _pestana_modelo,
             "cupos": _pestana_cupos, "auditoria": _pestana_auditoria}.get(pestana)
    cifras, tablas, exportar = armar(d) if armar else _pestana_calidad(d, f)
    return {"pestana": pestana, "titulo": PESTANAS[pestana], "nota": NOTA_MONITOREO,
            "pestanas": [{"clave": k, "titulo": t} for k, t in PESTANAS.items()], "filtros": f, "proyectos": proyectos(),
            "cifras": cifras, "tablas": tablas, "exportar": exportar}
