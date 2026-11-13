"""Lo que comparten las pantallas de KPIs y Monitoreo con la API v1: filtros, datos de cada pestaña y exportaciones.

Las cifras salen de `metricas` y `kpis`; aquí solo se arma lo que antes vivía dentro de las rutas Jinja,
para que la pantalla y la API respondan exactamente lo mismo.
"""
import re

from .. import config, db
from . import cotizacion, eventos, exportacion, kpis, metricas, precios

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
