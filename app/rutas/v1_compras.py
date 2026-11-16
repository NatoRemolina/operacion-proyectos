"""API v1: la bandeja de compras de administración. Contrato en `contracts/api-v1.md`, sección «Compras».

Solo administración (403 para las demás personas), y nadie decide la compra de su propio viaje (403 `SELF_APPROVAL`).
Cada cambio lleva la versión que se vio. La lógica está en `app/servicios/compras.py`.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Path, Query, Request

from .. import db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, formas, persona
from ..api_v1.esquemas_compras import CambioEstadoCompra, Compra, CompraDetalle, ListaCompras, RegistroCompra, errores_compras
from ..servicios import acceso, analizador, compras, consultas, cotizacion, enlaces

router = APIRouter(prefix=PREFIJO + "/compras", tags=["compras"])
ENTERO_MAXIMO = 2**31 - 1


def _admin(yo: dict) -> dict:
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "La bandeja de compras es solo de administración.")
    return yo


def admin(yo: dict = Depends(persona)) -> dict:
    return _admin(yo)


def admin_escritura(yo: dict = Depends(escritura)) -> dict:
    return _admin(yo)


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _forma(c: dict) -> dict:
    pagado, cotizado = c["precio_pagado"], c["precio_cotizado"]
    frente = None
    if pagado is not None:
        frente = {"presupuesto_usd": consultas.dinero(c["presupuesto_usd"]), "cotizado_usd": consultas.dinero(cotizado),
                  "diferencia_usd": consultas.dinero(Decimal(str(pagado)) - Decimal(str(cotizado))) if cotizado is not None else None}
    return {"id": c["id"], "estado": c["estado"], "estado_texto": c["estado_texto"], "version": c["version"],
            "viaje": {"id": c["viaje_id"], "codigo": c["viaje_codigo"], "estado": c["viaje_estado"],
                      "presupuesto_usd": consultas.dinero(c["presupuesto_usd"])},
            "solicitud_id": c["solicitud_id"], "solicitada_por": c["solicitada_por_nombre"], "motivo": c["motivo"],
            "vendedor": c["vendedor"], "localizador": c["localizador"], "precio_pagado_usd": consultas.dinero(pagado),
            "precio_cotizado_usd": consultas.dinero(cotizado), "anticipacion_dias": c["anticipacion_dias"],
            "creado": consultas.instante(c["creado"]), "decidido": consultas.instante(c["decidido"]),
            "comprada": consultas.instante(c["comprada"]), "frente_presupuesto": frente, "aviso": c["aviso"]}


def _detalle(c: dict, sesion: str) -> dict:
    o = cotizacion.opcion(c["opcion_id"]) if c["opcion_id"] else None
    vuelo = None
    if o:
        v = db.de_json(o["datos"], {}) or {}
        sol = cotizacion.solicitud(c["solicitud_id"])
        vuelo = {"opcion_id": o["id"], "numeros": v.get("numeros") or [], "aerolinea": v.get("aerolinea"), "sale": v.get("sale"),
                 "llega": v.get("llega"), "precio_usd": consultas.dinero(v.get("precio")),
                 "vendedor_url": enlaces.url_vendedor(sesion, c["solicitud_id"], o["id"]),
                 "fuente_url": cotizacion.fuente_vuelo(sol, v) if sol else None}
    lectura = None
    if o:
        try:
            a = analizador.ultimo(c["solicitud_id"], o["id"])
        except LookupError:
            a = None
        lectura = formas.analisis(c["solicitud_id"], o["id"], {**a, "reutilizado": True}, sesion) if a else None
    return {**_forma(c), "vuelo": vuelo, "analisis": lectura, "evidencia": formas.evidencia(c["solicitud_id"]),
            "clics": [{**k, "momento": consultas.instante(k["momento"])} for k in compras.clics(c)]}


def _uno(id: int) -> dict:
    c = compras.uno(id)
    if not c:
        raise _no_encontrado()
    return c


Id = Path(ge=1, le=ENTERO_MAXIMO)


@router.get("", response_model=ListaCompras, responses=errores_compras(401, 403, 422))
def lista(estado: str | None = Query(None, pattern=r"^(solicitada|en_analisis|se_comprara|no_se_comprara|comprada|cancelada)$"),
          yo: dict = Depends(admin)):
    """Las compras activas, la más reciente primero (hasta 200)."""
    return {"items": [_forma(c) for c in compras.lista(estado)]}


@router.get("/{id}", response_model=CompraDetalle, responses=errores_compras(401, 403, 404, 422))
def detalle(request: Request, id: int = Id, yo: dict = Depends(admin)):
    """La compra con su vuelo, el enlace a la página oficial, los clics a las fuentes y la última lectura de la página."""
    return _detalle(_uno(id), request.cookies.get(acceso.COOKIE) or "")


def _errores(funcion):
    try:
        return funcion()
    except LookupError as e:
        raise _no_encontrado() from e
    except compras.CompraImpedida as e:
        raise ErrorApi(403, "SELF_APPROVAL", str(e)) from e
    except compras.ConflictoVersion as e:
        raise ErrorApi(409, "EDIT_CONFLICT", str(e)) from e
    except compras.EstadoInvalido as e:
        raise ErrorApi(409, "INVALID_STATE", str(e)) from e
    except compras.CampoInvalido as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {e.campo: str(e)}) from e


@router.post("/{id}/estado", response_model=Compra, responses=errores_compras(401, 403, 404, 409, 422))
def cambiar_estado(datos: CambioEstadoCompra, id: int = Id, yo: dict = Depends(admin_escritura)):
    """«En análisis», «Se va a comprar» (exige el viaje aprobado), «No se va a comprar» o «Cancelada» (con motivo).
    Avisa al viajero en la bitácora de su viaje."""
    return _forma(_errores(lambda: compras.cambiar_estado(id, datos.accion, datos.version, datos.motivo, yo)))


@router.post("/{id}/registro", response_model=Compra, responses=errores_compras(401, 403, 404, 409, 422))
def registrar(datos: RegistroCompra, id: int = Id, yo: dict = Depends(admin_escritura)):
    """Registra la compra hecha: localizador, precio pagado y vendedor. Responde con la diferencia frente a lo cotizado."""
    return _forma(_errores(lambda: compras.registrar_compra(id, datos.version, datos.localizador, Decimal(datos.precio_pagado),
                                                            datos.vendedor, yo)))


@router.post("/{id}/analisis", responses=errores_compras(401, 403, 404, 422))
def analizar(id: int = Id, yo: dict = Depends(admin_escritura)) -> dict:
    """Pide (o reutiliza) la lectura de la página del vuelo de la compra. Misma forma que `AnalisisVuelo`."""
    c = _uno(id)
    if not c["opcion_id"]:
        raise _no_encontrado()
    return formas.analisis(c["solicitud_id"], c["opcion_id"], analizador.solicitar(yo, c["solicitud_id"], c["opcion_id"]))
