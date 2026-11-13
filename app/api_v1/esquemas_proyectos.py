"""Modelos de la API v1 de proyectos. Contrato en `contracts/api-v1.md`, sección «Proyectos»."""
from pydantic import BaseModel, ConfigDict, Field

from .esquemas import Dinero, GastoResumen, ViajeResumen


class DatosProyecto(BaseModel):
    """Alta o edición de un proyecto. Quién lo hace sale de la sesión."""
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(max_length=200, description="3 caracteres o más; se guardan hasta 120.")
    cliente: str = Field("", max_length=200, description="Opcional; vacío se guarda como null.")
    ciudad: str = Field("", max_length=200, description="Opcional; vacío se guarda como null.")
    fecha_inicio: str = Field(max_length=10, description="AAAA-MM-DD")
    fecha_fin: str = Field(max_length=10, description="AAAA-MM-DD; no antes de `fecha_inicio`.")
    moneda: str = Field("USD", max_length=3, description="Código de tres letras (USD, EUR...); se guarda en mayúsculas.")


class ProyectoResumen(BaseModel):
    id: int
    nombre: str
    cliente: str | None
    ciudad: str | None
    fecha_inicio: str
    fecha_fin: str
    moneda: str
    viajes: int = Field(description="Viajes del proyecto, en cualquier estado.")
    gastos: int = Field(description="Gastos del proyecto, en cualquier estado.")
    previsto_usd: Dinero = Field(description="Presupuesto de los viajes del proyecto que no se rechazaron.")
    real_usd: Dinero = Field(description="Gastos aprobados del proyecto.")
    diferencia_usd: Dinero = Field(description="Real menos previsto: positivo es sobrecosto.")


class ListaProyectos(BaseModel):
    items: list[ProyectoResumen]
    siguiente: str | None


class CategoriaProyecto(BaseModel):
    clave: str = Field(description="vuelo, hotel, alquiler_carro o viaticos (todo lo que se paga en el viaje).")
    nombre: str
    previsto_usd: Dinero
    real_usd: Dinero
    diferencia_usd: Dinero


class GastoDelProyecto(GastoResumen):
    viajero: str | None = Field(description="Nombre de quien viaja, si el gasto lo tiene.")


class PeriodoContable(BaseModel):
    desde: str = Field(description="Primer día del mes en curso (hora de Nueva York): lo que propone el Excel contable.")
    hasta: str


class TableroProyecto(BaseModel):
    proyecto: ProyectoResumen
    categorias: list[CategoriaProyecto] = Field(description="Solo las que tienen previsto o real.")
    previsto_usd: Dinero
    real_usd: Dinero
    diferencia_usd: Dinero
    en_revision: int = Field(description="Gastos del proyecto que esperan revisión.")
    faltantes: list[str] = Field(description="Categorías con previsto y sin ningún gasto aprobado todavía.")
    viajes: list[ViajeResumen] = Field(description="Viajes del proyecto que no se rechazaron.")
    gastos: list[GastoDelProyecto] = Field(description="Todos los gastos del proyecto, por fecha del recibo.")
    periodo_contable: PeriodoContable
