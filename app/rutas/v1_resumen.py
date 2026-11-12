"""API v1: resumen de administración (indicadores, pendientes y actividad reciente). Contrato en `contracts/api-v1.md`.

Las cifras salen del catálogo de métricas, la misma definición que usan los tableros y los KPI.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends

from .. import db
from ..api_v1 import PREFIJO, datos_demostracion, solo_admin
from ..api_v1.esquemas import ResumenAdmin, errores
from ..servicios import consultas, metricas, viajes
from .v1_gastos import marcar_propios
from .v1_viajes import con_decision

router = APIRouter(prefix=PREFIJO + "/resumen", tags=["administracion"])

NOTA = "Presupuesto disponible = aprobado − gastos aprobados. Las reservas de tiquetes se sumarán cuando existan."


def _actividad(yo: dict) -> list[dict]:
    """Los últimos gastos con la persona a la que pertenecen (el titular de su viaje o, sin viaje, quien lo cargó)."""
    items = consultas.lista_gastos(yo, limite=10)["items"]
    if not items:
        return []
    ids = ",".join(str(int(g["id"])) for g in items)
    duenos = {f["gasto_id"]: f for f in db.todos(f"""select g.id gasto_id, u.id, u.nombre from gastos g
                                                      join usuarios u on u.id={metricas.dueno('g')} where g.id in ({ids})""")}
    salida = []
    for g in items:
        d = duenos.get(g["id"])
        salida.append({"gasto_id": g["id"], "comercio": g["comercio"], "viaje": g["viaje"], "total": g["total"],
                       "moneda": g["moneda"], "total_usd": g["total_usd"], "estado": g["estado"],
                       "estado_texto": g["estado_texto"], "creado": g["creado"],
                       "persona": {"id": d["id"], "codigo": viajes.codigo_persona(d["id"]), "nombre": d["nombre"]} if d else None})
    return salida


@router.get("", response_model=ResumenAdmin, responses=errores(401, 403))
def resumen(yo: dict = Depends(solo_admin)):
    """Solo administración. Indicadores del momento, lo que espera decisión y la actividad reciente."""
    with metricas.una_lectura():
        v = metricas.viajes({})
        en_revision = metricas.valor("pendientes_revision", {})["valor"]
    aprobado, gastado = v["presupuesto_aprobado"], v["gastado"]
    en_revision_usd = db.uno("select coalesce(sum(total_usd), 0) t from gastos where estado='revision'")["t"]
    pendientes = con_decision(consultas.lista_viajes(yo, "pendiente_aprobacion", 5)["items"], yo)
    return {
        "presupuesto_aprobado_usd": consultas.dinero(aprobado), "gastado_usd": consultas.dinero(gastado),
        "disponible_usd": consultas.dinero(Decimal(str(aprobado)) - Decimal(str(gastado))), "en_revision_usd": consultas.dinero(en_revision_usd),
        "ejecucion_pct": v["ejecucion"], "viajes_por_aprobar": v["pendientes"], "gastos_en_revision": en_revision,
        "pendientes": pendientes, "revision": marcar_propios(consultas.lista_gastos(yo, estado="revision", limite=5)["items"], yo),
        "actividad": _actividad(yo), "nota": NOTA,
        "datos_demostracion": datos_demostracion(),
    }
