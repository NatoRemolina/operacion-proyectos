"""Proyectos: validación, alta y edición, previsto frente a real y exportación de sus gastos.

Lo usan las pantallas actuales (`app/rutas/proyectos.py`) y la API v1 (`app/rutas/v1_proyectos.py`): una sola regla.
"""
import re
from datetime import date

from .. import config, db
from . import acceso, eventos, exportacion, viajes

# Se compran por separado; lo demás (viáticos, traslados por carretera, combustible) se paga en el viaje
COMPRAS = ("vuelo", "hotel", "alquiler_carro")
COLUMNAS_CSV = ["id", "fecha", "comercio", "categoria", "total", "moneda", "total_usd", "estado", "metodo_pago", "origen_dato",
                "viajero", "viaje"]


class DatosInvalidos(ValueError):
    """Un dato del proyecto no es válido. `campo` dice cuál, para señalarlo en el formulario."""

    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo


def validar(nombre: str, cliente: str, ciudad: str, fecha_inicio: str, fecha_fin: str, moneda: str) -> dict:
    nombre, moneda = (nombre or "").strip()[:120], (moneda or "").strip().upper()[:3]
    if len(nombre) < 3:
        raise DatosInvalidos("nombre", "El proyecto necesita un nombre.")
    try:
        inicio = date.fromisoformat(fecha_inicio or "")
    except ValueError:
        raise DatosInvalidos("fecha_inicio", "Las fechas del proyecto no son válidas.") from None
    try:
        fin = date.fromisoformat(fecha_fin or "")
    except ValueError:
        raise DatosInvalidos("fecha_fin", "Las fechas del proyecto no son válidas.") from None
    if fin < inicio:
        raise DatosInvalidos("fecha_fin", "La fecha final no puede ser anterior a la inicial.")
    if not re.fullmatch(r"[A-Z]{3}", moneda):
        raise DatosInvalidos("moneda", "La moneda es un código de tres letras, como USD o EUR.")
    return {"nombre": nombre, "cliente": (cliente or "").strip()[:120] or None, "ciudad": (ciudad or "").strip()[:80] or None,
            "fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat(), "moneda": moneda}


def crear(datos: dict, quien: dict) -> int:
    pid = db.insertar("proyectos", **datos)
    eventos.registrar("proyecto", pid, "proyecto creado", f"{datos['nombre']} · {datos['fecha_inicio']} a {datos['fecha_fin']}", quien["nombre"])
    return pid


def editar(pid: int, datos: dict, quien: dict) -> None:
    db.actualizar("proyectos", pid, **datos)
    eventos.registrar("proyecto", pid, "proyecto editado", f"{datos['nombre']} · {datos['fecha_inicio']} a {datos['fecha_fin']}", quien["nombre"])


def uno(pid: int) -> dict | None:
    return db.uno("select * from proyectos where id=:i", i=pid)


def existe(pid: int) -> bool:
    return bool(db.uno("select id from proyectos where id=:i", i=pid))


def visible(u: dict, pid: int) -> bool:
    """Administración ve todos; el gestor, los que gestiona; nadie más (se responde como si no existiera)."""
    return acceso.es_admin(u) or (u["rol"] == "gestor" and pid in acceso.proyectos_de(u))


_CON_CONTEOS = """select p.*, (select count(*) from viajes v where v.proyecto_id=p.id) viajes,
                         (select count(*) from gastos g where g.proyecto_id=p.id) gastos from proyectos p"""


def lista(u: dict, limite: int | None = None, cursor: int | None = None) -> list[dict]:
    """Proyectos con cuántos viajes y gastos tienen. Administración, todos; el gestor, los suyos. El más reciente primero."""
    donde, p = "1=1", {}
    if not acceso.es_admin(u):
        donde, p = "p.id in (select proyecto_id from proyecto_miembros where usuario_id=:_yo)", {"_yo": u["id"]}
    if cursor:
        donde, p = f"{donde} and p.id<:_cursor", {**p, "_cursor": cursor}
    tope = f" limit {int(limite)}" if limite else ""
    return db.todos(f"{_CON_CONTEOS} where {donde} order by p.id desc{tope}", **p)


def con_conteos(pid: int) -> dict | None:
    return db.uno(f"{_CON_CONTEOS} where p.id=:i", i=pid)


def comparaciones(pids: list[int]) -> dict[int, dict]:
    """Previsto frente a real por categoría de varios proyectos con dos consultas en total (no dos por proyecto).

    El previsto es el presupuesto de los viajes del proyecto que no se rechazaron: la misma cifra que aprueba
    administración. El real, los gastos aprobados. Lo que se paga en el viaje se compara en una sola fila.
    """
    if not pids:
        return {}
    ids = ",".join(str(int(p)) for p in pids)   # enteros: no hay texto de nadie en la consulta
    reales: dict[int, dict[str, float]] = {p: {} for p in pids}
    for r in db.todos(f"""select proyecto_id, categoria, sum(total_usd) t from gastos
                          where proyecto_id in ({ids}) and estado in ('aprobado','aprobado_auto') group by proyecto_id, categoria"""):
        reales[r["proyecto_id"]][r["categoria"]] = r["t"]
    viajes_de: dict[int, list[dict]] = {p: [] for p in pids}
    for v in viajes.lista(f"v.proyecto_id in ({ids}) and v.estado<>'rechazado'"):
        viajes_de[v["proyecto_id"]].append(v)
    return {p: _comparacion(reales[p], viajes_de[p]) for p in pids}


def comparacion(pid: int) -> dict:
    return comparaciones([pid])[pid]


def _comparacion(real: dict[str, float], del_proyecto: list[dict]) -> dict:
    previsto: dict[str, float] = {}
    for v in del_proyecto:
        for linea in db.de_json(v["presupuesto_detalle"], []) or []:
            previsto[linea["grupo"]] = previsto.get(linea["grupo"], 0) + linea["valor"]
    filas = [{"clave": c, "nombre": config.CATEGORIAS[c], "previsto": round(previsto.get(c, 0), 2), "real": round(real.get(c) or 0, 2)}
             for c in COMPRAS if previsto.get(c) or real.get(c)]
    en_destino = round(sum(t or 0 for c, t in real.items() if c not in COMPRAS), 2)
    previsto_destino = round(sum(v for g, v in previsto.items() if g not in COMPRAS), 2)
    if previsto_destino or en_destino:
        filas.append({"clave": "viaticos", "nombre": "Viáticos y gastos en destino", "previsto": previsto_destino, "real": en_destino})
    return {"filas": filas, "viajes": del_proyecto,
            "faltantes": [f["nombre"] for f in filas if f["previsto"] and not f["real"]],
            "tot_previsto": round(sum(f["previsto"] for f in filas), 2), "tot_real": round(sum(f["real"] for f in filas), 2)}


def en_revision(pid: int) -> int:
    return db.uno("select count(*) n from gastos where proyecto_id=:i and estado='revision'", i=pid)["n"]


def gastos(pid: int) -> list[dict]:
    """Todos los gastos del proyecto, por fecha, con el nombre de quien viaja."""
    return db.todos("""select g.*, v.nombre viajero, vj.creado viaje_creado from gastos g
                       left join viajeros v on v.id=g.viajero_id left join viajes vj on vj.id=g.viaje_id
                       where g.proyecto_id=:i order by g.fecha""", i=pid)


def csv_gastos(pid: int) -> str:
    filas = db.todos("""select g.id, g.fecha, g.comercio, g.categoria, g.total, g.moneda, g.total_usd, g.estado, g.metodo_pago,
                                g.origen_dato, v.nombre viajero, vj.id viaje_id, vj.creado viaje_creado
                         from gastos g left join viajeros v on v.id=g.viajero_id left join viajes vj on vj.id=g.viaje_id
                         where g.proyecto_id=:i order by g.fecha""", i=pid)
    for f in filas:
        f["viaje"] = viajes.codigo_viaje({"id": f["viaje_id"], "creado": f["viaje_creado"]}) if f["viaje_id"] else None
    return exportacion.csv_de(filas, COLUMNAS_CSV)
