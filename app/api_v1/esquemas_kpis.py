"""Modelos de salida de los KPIs en la API v1. Son el contrato que publica `contracts/openapi-v1.json`.

Los valores de los indicadores son números (no cadenas de dinero): cada uno trae su `unidad` (%, USD, h, días, ms...).
"""
from typing import Literal

from pydantic import BaseModel, Field

EstadoKpi = Literal["verde", "ambar", "rojo", "sin datos", "fuera de rango"]


class Filtros(BaseModel):
    proyecto_id: int | None = None
    desde: str | None = Field(None, description="AAAA-MM-DD")
    hasta: str | None = Field(None, description="AAAA-MM-DD")


class Opcion(BaseModel):
    id: int
    nombre: str


class Reto(BaseModel):
    reto: int
    nombre: str


class Kpi(BaseModel):
    nombre: str = Field(description="Nombre estable del indicador, el mismo de `/api/metricas`.")
    titulo: str
    unidad: str
    para_que: str
    formula: str
    sentido: Literal["mayor", "menor"] = Field(description="Hacia dónde es mejor.")
    meta: float
    alerta: float = Field(description="Umbral de alerta: pasado este valor el semáforo está en rojo.")
    responsable: str
    reto: int
    principal: bool
    valor: float | None = Field(description="Null si no hay datos: entonces no hay color.")
    estado: EstadoKpi
    estado_texto: str


class ResumenEstados(BaseModel):
    verde: int
    ambar: int
    rojo: int
    sin_datos: int
    fuera_de_rango: int = Field(description="Valores imposibles para el indicador (por ejemplo, días negativos): un dato malo, no un logro.")


class PuntoTendencia(BaseModel):
    valor: float | None
    estado: EstadoKpi


class FilaTendencia(BaseModel):
    nombre: str
    titulo: str
    unidad: str
    puntos: list[PuntoTendencia]


class Tendencia(BaseModel):
    semanas: list[str] = Field(description="Lunes de cada semana, de la más antigua a la más reciente.")
    filas: list[FilaTendencia]


class Par(BaseModel):
    etiqueta: str | None
    valor: float | None


class FallaBuscador(BaseModel):
    momento: str | None
    tipo: str | None
    error: str | None


class Cupo(BaseModel):
    plan: str | None = None
    mensual: int | None = None
    usadas: int | None = None
    restantes: int | None = None


class DetalleCotizacion(BaseModel):
    cotizaciones_por_persona: list[Par]
    cotizaciones_por_ruta: list[Par]
    consultas_por_origen: list[Par]
    consultas_por_tipo: list[Par]
    consultas_por_persona: list[Par]
    consultas_por_ruta: list[Par]
    errores_buscador: list[FallaBuscador]
    cupo: Cupo | None = Field(description="Null sin clave del buscador configurada.")


class EjecucionViaje(BaseModel):
    id: int
    codigo: str
    titular: str | None
    ruta: str | None
    ida: str | None
    estado: str
    presupuesto: float | None
    gastado: float | None
    en_revision: float | None
    pct: float | None


class EjecucionGrupo(BaseModel):
    nombre: str | None
    presupuesto: float | None
    gastado: float | None
    pct: float | None


class GastoPorMoneda(BaseModel):
    moneda: str | None
    gastos: int
    total: float | None
    total_usd: float | None


class RevisionAntigua(BaseModel):
    id: int
    comercio: str | None
    persona: str | None
    total_usd: float | None
    dias: float | None


class DetalleGastos(BaseModel):
    por_viaje: list[EjecucionViaje]
    por_proyecto: list[EjecucionGrupo]
    por_categoria: list[EjecucionGrupo]
    por_moneda: list[GastoPorMoneda]
    revision_antiguas: list[RevisionAntigua]
    real_total: float | None


class FilaPersona(BaseModel):
    id: int
    codigo: str
    nombre: str
    rol: str
    rol_texto: str
    activo: bool
    cotizaciones: int
    viajes: int
    presupuesto: float
    gastado: float
    en_revision: float
    ejecucion: float | None
    gastos: int
    gastos_revision: int


class FilaCargo(BaseModel):
    cargo: str
    viajes: int
    gasto_usd: float
    en_revision: float


class TableroKpis(BaseModel):
    filtros: Filtros
    retos: list[Reto]
    proyectos: list[Opcion] = Field(description="Para el filtro de proyecto.")
    kpis: list[Kpi]
    resumen: ResumenEstados
    tendencia: Tendencia
    cotizacion: DetalleCotizacion
    gastos: DetalleGastos
    personas: list[FilaPersona]
    por_cargo: list[FilaCargo]


# ---------- ficha ----------
class UsuarioFicha(BaseModel):
    id: int
    codigo: str
    nombre: str
    correo: str
    rol: str
    rol_texto: str
    activo: bool
    creado: str | None
    cargo: str | None
    viajero: str | None
    base: str | None


class TotalesPersona(BaseModel):
    presupuesto: float
    gastado: float
    en_revision: float


class CotizacionPersona(BaseModel):
    id: int
    origen: str | None
    destino: str | None
    ida: str | None
    regreso: str | None
    estado: str | None
    creado: str | None
    proyecto: str | None
    viaje: str | None = Field(description="Código del viaje que nació de la cotización, si lo hay.")


class ViajePersona(BaseModel):
    id: int
    codigo: str
    origen: str | None
    destino: str | None
    ida: str | None
    regreso: str | None
    estado: str
    estado_texto: str
    proyecto: str | None
    presupuesto_usd: float | None
    gastado: float | None
    en_revision: float | None
    pct: float | None


class GastoPersona(BaseModel):
    id: int
    comercio: str | None
    fecha: str | None
    categoria: str | None
    total: float | None
    moneda: str | None
    total_usd: float | None
    estado: str
    creado: str | None
    canal: str | None
    viaje: str | None


class EvidenciaPersona(BaseModel):
    id: int
    tipo: str | None
    canal: str | None
    nombre: str | None
    creado: str | None
    viaje: str | None


class EventoPersona(BaseModel):
    momento: str
    entidad: str | None
    entidad_id: int | None
    paso: str
    detalle: str | None
    fuente: str | None
    quien: str | None


class FichaPersona(BaseModel):
    usuario: UsuarioFicha
    totales: TotalesPersona
    indicadores: list[Kpi]
    cotizaciones: list[CotizacionPersona]
    viajes: list[ViajePersona]
    gastos: list[GastoPersona]
    evidencias: list[EvidenciaPersona]
    eventos: list[EventoPersona] = Field(description="Línea de tiempo: los hechos sobre lo suyo, del más reciente al más antiguo (200 como máximo).")
    gastos_por_estado: list[Par]
    gastos_por_canal: list[Par]
