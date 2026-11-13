"""Modelos de salida de Monitoreo en la API v1. Son el contrato que publica `contracts/openapi-v1.json`.

Cada pestaña llega como cifras y tablas ya armadas (las mismas de la pantalla de administración), para que la web
las muestre sin repetir reglas. Las cifras son números en su `unidad`; los importes, en dólares.
"""
from typing import Literal

from pydantic import BaseModel, Field

from .esquemas_kpis import Filtros, Opcion

Pestana = Literal["viajes", "gastos", "busquedas", "modelo", "cupos", "auditoria", "calidad"]


class Enlace(BaseModel):
    texto: str
    href: str = Field(description="Ruta de la web, por ejemplo `/viajes/7`.")


Celda = Enlace | float | int | str | None


class Cifra(BaseModel):
    etiqueta: str
    valor: float | str | None = Field(description="Null si no hay datos.")
    unidad: str | None = Field(description="`%`, `USD`, `h`, `s`... o null si es un conteo.")
    pie: str


class Columna(BaseModel):
    texto: str
    unidad: str | None = Field(description="`USD` o `%` si la columna es una cifra con unidad.")
    fin: bool = Field(description="Cifra: se alinea a la derecha.")


class Tabla(BaseModel):
    titulo: str
    columnas: list[Columna]
    filas: list[list[Celda]]
    vacio: str = Field(description="Qué decir si no hay filas.")
    nota: str | None
    barras: bool = Field(description="La segunda columna se puede dibujar como barra (embudo, categorías).")


class PestanaDisponible(BaseModel):
    clave: Pestana
    titulo: str


class VistaExportable(BaseModel):
    vista: str = Field(description="Valor de `vista` para `GET /monitoreo/exportar.csv`.")
    texto: str


class PestanaMonitoreo(BaseModel):
    pestana: Pestana
    titulo: str
    nota: str | None
    pestanas: list[PestanaDisponible]
    filtros: Filtros
    proyectos: list[Opcion]
    cifras: list[Cifra]
    tablas: list[Tabla]
    exportar: list[VistaExportable]
