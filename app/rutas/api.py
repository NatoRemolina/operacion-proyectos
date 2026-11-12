"""API de lectura en JSON, solo para administración."""

from fastapi import APIRouter
from fastapi.responses import Response

from .. import db
from ..servicios import agente, analitica
from .cotizaciones import _comparacion, _completar_ahorros

router = APIRouter()


# ---------- API en JSON (contrato para un front aparte) ----------
@router.get("/api/analitica", tags=["api"])
def api_analitica():
    _completar_ahorros()
    return analitica.resumen()


@router.get("/api/solicitudes", tags=["api"])
def api_solicitudes():
    return db.todos("select * from solicitudes order by id desc")


@router.get("/api/solicitudes/{sid}", tags=["api"])
def api_solicitud(sid: int):
    c = _comparacion(sid)
    if not c:
        return Response(status_code=404)
    quitar = lambda o: {k: v for k, v in o.items() if k != "tarifas_lista"}
    return {"solicitud": c["sol"], "aviso": c["aviso"], "equipo": c["baterias"], "vuelos": [quitar(o) for o in c["vuelos"]],
            "descartados": [quitar(o) for o in c["descartados"]], "hoteles": c["hoteles"],
            "recomendacion": agente.recomendar(c, solo_determinista=True)}


@router.get("/api/gastos", tags=["api"])
def api_gastos(proyecto_id: int = 0):
    filtro = "where proyecto_id=:p" if proyecto_id else ""
    return db.todos(f"select * from gastos {filtro} order by id desc", p=proyecto_id)


@router.get("/api/observaciones", tags=["api"])
def api_observaciones(limite: int = 1000):
    return db.todos("select * from observaciones order by id desc limit :l", l=min(limite, 5000))


@router.get("/api/eventos", tags=["api"])
def api_eventos(limite: int = 200):
    return db.todos("select * from eventos order by id desc limit :l", l=min(limite, 1000))
