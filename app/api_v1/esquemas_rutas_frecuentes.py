"""Modelos de salida de «Rutas frecuentes y precios» en la API v1. Son el contrato que publica `contracts/openapi-v1.json`.

Todos los importes son USD. Las cifras describen lo visto; la señal es orientativa y no promete el precio futuro.
"""
from typing import Literal

from pydantic import BaseModel, Field


class TendenciaRuta(BaseModel):
    cambio_pct: float = Field(description="Cambio de la mediana entre la primera y la segunda mitad del historial diario.")
    sentido: Literal["sube", "baja", "estable"]


class PrimaFlexibilidad(BaseModel):
    usd: float | None
    pct: float | None
    pares: int = Field(description="Itinerarios con tarifa básica y flexible a la vez: sobre cuántos se calcula.")


class AerolineaFrenteAgencia(BaseModel):
    aerolinea: float | None
    agencia: float | None
    diferencia_usd: float | None = Field(description="Agencia menos aerolínea en el mismo itinerario (mediana).")
    pares: int


class SenalPrecio(BaseModel):
    valor: Literal["por debajo", "dentro", "por encima", "sin datos"]
    referencia: str | None = Field(None, description="Rango propio (p25–p75) o rango típico de Google.")
    rango: list[float | None] | None = None
    precio: float | None = Field(None, description="Mediana de lo visto el último día con datos.")


class RutaFrecuente(BaseModel):
    ruta: str
    origen: str
    destino: str
    cotizaciones: int
    viajes: int
    observaciones: int
    por_anticipacion: dict[str, float | None] = Field(description="Mediana por tramo de días de anticipación: 0-7, 8-21, 22-45 y 46+.")
    mediana: float | None
    volatilidad: float | None = Field(description="Desviación absoluta mediana, en USD.")
    tendencia: TendenciaRuta | None
    prima_flexibilidad: PrimaFlexibilidad | None
    aerolinea_agencia: AerolineaFrenteAgencia | None
    senal: SenalPrecio


class ErrorPrecioEsperado(BaseModel):
    filas: int
    mae: float | None
    mape: float | None


class ErrorPrecioPorRuta(ErrorPrecioEsperado):
    ruta: str


class ErrorPrecioPorMes(ErrorPrecioEsperado):
    mes: str


class ExactitudModelo(ErrorPrecioEsperado):
    mensaje: str | None = Field(description="«sin datos todavía» cuando no hay decisiones con precio esperado.")
    por_ruta: list[ErrorPrecioPorRuta]
    por_mes: list[ErrorPrecioPorMes]
    contra_pagado: ErrorPrecioEsperado | None = Field(description="Frente a lo pagado, cuando hay compras registradas.")


class RutasFrecuentes(BaseModel):
    dias: int = Field(description="Ventana de cotizaciones y viajes con que se ordenan las rutas.")
    rutas: list[RutaFrecuente]
    exactitud: ExactitudModelo
    tarifas_vistas: int = Field(description="Filas de `ofertas_tarifa` útiles tras la limpieza.")
    pocos_datos: bool = Field(description="Verdadero si las cifras son demostrativas por falta de volumen.")
    aviso: str
