"""Modelos de la API v1 de compras (solo administración). Contrato en `contracts/api-v1.md`, sección «Compras»."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .esquemas import Dinero, RespuestaError
from .esquemas_cotizacion import Evidencia

EstadoCompra = Literal["solicitada", "en_analisis", "se_comprara", "no_se_comprara", "comprada", "cancelada"]


class CambioEstadoCompra(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accion: Literal["en_analisis", "se_comprara", "no_se_comprara", "cancelada"] = Field(
        description="`se_comprara` exige el viaje aprobado; `no_se_comprara` y `cancelada` exigen motivo.")
    version: int = Field(ge=1, description="La versión que se vio: si otra persona la cambió, 409 `EDIT_CONFLICT`.")
    motivo: str = Field("", max_length=300, description="La persona que viaja lo verá.")


class RegistroCompra(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    localizador: str = Field(min_length=5, max_length=8, pattern=r"^[A-Za-z0-9]+$", description="Como lo da la aerolínea.")
    precio_pagado: str = Field(pattern=r"^\d{1,5}(\.\d{1,2})?$", description="USD, como \"461.30\".")
    vendedor: str = Field(min_length=1, max_length=60, description="A quién se le compró: la aerolínea o la agencia.")


class FrentePresupuesto(BaseModel):
    presupuesto_usd: Dinero = Field(description="Presupuesto aprobado del viaje completo.")
    cotizado_usd: Dinero = Field(description="Precio del tiquete que dio el buscador al decidir.")
    diferencia_usd: Dinero = Field(description="Pagado − cotizado (positivo: costó más).")


class VueloCompra(BaseModel):
    opcion_id: int | None
    numeros: list[str]
    aerolinea: str | None
    sale: str | None
    llega: str | None
    precio_usd: Dinero
    vendedor_url: str | None = Field(description="El mismo enlace a la página oficial del vendedor que usa «Ver desglose».")
    fuente_url: str | None


class ViajeCompra(BaseModel):
    id: int
    codigo: str
    estado: str
    presupuesto_usd: Dinero


class ClicFuente(BaseModel):
    destino: Literal["google_flights", "google_hotels", "vendedor", "hotel_oficial"]
    dominio: str | None
    momento: str | None
    opcion_id: int | None
    usuario: str | None


class Compra(BaseModel):
    id: int
    estado: EstadoCompra
    estado_texto: str
    version: int
    viaje: ViajeCompra
    solicitud_id: int | None
    solicitada_por: str | None
    motivo: str | None
    vendedor: str | None
    localizador: str | None
    precio_pagado_usd: Dinero
    precio_cotizado_usd: Dinero
    anticipacion_dias: int | None
    creado: str | None
    decidido: str | None
    comprada: str | None
    frente_presupuesto: FrentePresupuesto | None = Field(description="Solo con la compra registrada.")


class CompraDetalle(Compra):
    vuelo: VueloCompra | None
    clics: list[ClicFuente]
    analisis: dict | None = Field(description="La última lectura de la página del vuelo (forma de `AnalisisVuelo`).")
    evidencia: Evidencia | None = Field(None, description="La evidencia guardada de la decisión (forma de `Evidencia`).")


class ListaCompras(BaseModel):
    items: list[Compra]


_DESCRIPCION = {401: "Sin sesión o sesión vencida", 403: "Fuera de administración, sin CSRF, o la compra es del propio viaje "
                "(`SELF_APPROVAL`)", 404: "No existe", 409: "Versión vieja (`EDIT_CONFLICT`) o cambio no permitido (`INVALID_STATE`)",
                422: "Campos inválidos; detalle por campo en `fields`"}


def errores_compras(*estados: int) -> dict:
    return {e: {"model": RespuestaError, "description": _DESCRIPCION[e]} for e in estados}
