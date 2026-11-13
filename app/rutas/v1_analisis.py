"""API v1: leer la página de un vuelo en Google Flights al abrir su desglose. Contrato en `contracts/api-v1.md`.

La lectura la hace el analizador (`app/servicios/analizador.py`); aquí solo el permiso y la forma. La pide y la ve
quien ve la cotización (`acceso.puede_ver`); lo demás responde 404.
"""
from fastapi import APIRouter, Depends, Path
from fastapi.responses import Response

from .. import db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, persona
from ..api_v1.esquemas_cotizacion import ENTERO_MAXIMO, AnalisisVuelo, errores_cotizacion
from ..servicios import acceso, analizador, consultas

router = APIRouter(prefix=PREFIJO, tags=["cotizaciones"])


def Id():  # noqa: N802 (un `Path` por parámetro: compartido, FastAPI le pone a todos el nombre del primero)
    return Path(ge=1, le=ENTERO_MAXIMO)


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _visible(yo: dict, sid: int):
    if not acceso.puede_ver(yo, db.uno("select usuario_id, viajero_id, proyecto_id from solicitudes where id=:i", i=sid)):
        raise _no_encontrado()


def _forma(sid: int, opcion_id: int, a: dict) -> dict:
    precio = (db.uno("select precio from opciones where id=:o", o=opcion_id) or {}).get("precio")
    return {"id": a["id"], "opcion_id": opcion_id, "estado": a["estado"], "motivo": a["motivo"], "url": a["url"],
            "leido": consultas.instante(a["terminado"]) if a.get("terminado") else None, "duracion_ms": a["duracion_ms"],
            "reutilizado": bool(a.get("reutilizado")), "precio_buscador_usd": consultas.dinero(precio),
            "aviso_precio": analizador.aviso_precio(a, precio) if a["estado"] == "listo" else None,
            "datos": a["datos"] if a["estado"] == "listo" else None,
            "extracto": (a["datos"] or {}).get("extracto") if a["estado"] == "fallido" else None,
            "captura_url": f"{PREFIJO}/cotizaciones/{sid}/analisis/{a['id']}/captura" if a.get("captura") else None}


@router.post("/cotizaciones/{id}/vuelos/{opcion_id}/analisis", response_model=AnalisisVuelo,
             responses=errores_cotizacion(401, 403, 404, 422))
def pedir(id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(escritura)):
    """Lee la página del vuelo en Google Flights (tarda unos segundos) o devuelve la lectura de menos de 60 minutos.

    Tarifas y qué incluye cada una, equipaje, cambios y reembolso, escalas, precio por vendedor y una captura. Con los
    topes del día alcanzados, apagado o sin analizador: `estado: no_disponible` y el motivo, sin leer nada."""
    _visible(yo, id)
    try:
        return _forma(id, opcion_id, analizador.solicitar(yo, id, opcion_id))
    except LookupError as e:
        raise _no_encontrado() from e


@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/analisis", response_model=AnalisisVuelo,
            responses=errores_cotizacion(401, 404, 422))
def ver(id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona)):
    """La última lectura del vuelo (para seguir una en curso). 404 si nunca se leyó."""
    _visible(yo, id)
    if not db.uno("select id from opciones where id=:o and solicitud_id=:s and tipo='vuelo'", o=opcion_id, s=id):
        raise _no_encontrado()
    a = analizador.ultimo(opcion_id)
    if not a:
        raise _no_encontrado()
    return _forma(id, opcion_id, {**a, "reutilizado": True})


@router.get("/cotizaciones/{id}/analisis/{analisis_id}/captura", response_class=Response, responses={
    **errores_cotizacion(401, 404, 422), 200: {"description": "La captura de la página leída", "content": {"image/png": {}}}})
def captura(id: int = Id(), analisis_id: int = Id(), yo: dict = Depends(persona)):
    _visible(yo, id)
    a = db.uno("select * from analisis_vuelo where id=:a and solicitud_id=:s", a=analisis_id, s=id)
    contenido = analizador.captura(a) if a else None
    if contenido is None:
        raise _no_encontrado()
    return Response(contenido, media_type="image/png",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
