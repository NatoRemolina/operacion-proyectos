"""Modelos de salida del estado de los vuelos en la API v1. Son el contrato que publica `contracts/openapi-v1.json`.

Las horas programadas y estimadas son locales de cada aeropuerto (`AAAA-MM-DD HH:MM`); `actualizado`, en UTC.
"""
from pydantic import BaseModel, Field


class AvisoVuelo(BaseModel):
    momento: str | None = None
    texto: str | None = None
    enviado: bool | None = None
    error: str | None = None
    retraso: int | None = None


class TramoVuelo(BaseModel):
    id: int
    viaje_id: int
    codigo: str = Field(description="Código del viaje, por ejemplo V-2026-0007.")
    titular: str | None
    sentido: str = Field(description="`ida` o `regreso`.")
    orden: int | None
    aerolinea: str | None
    numero: str
    fecha: str
    desde: str | None
    hasta: str | None
    sale_programada: str | None
    llega_programada: str | None
    llega_estimada: str | None
    estado: str | None = Field(description="programado, a tiempo, retrasado, cancelado, aterrizado, desviado o sin datos.")
    estado_texto: str
    retraso: int = Field(description="Minutos: el mayor entre la salida y la llegada.")
    retraso_salida: int | None
    retraso_llegada: int | None
    terminal: str | None
    puerta: str | None
    consultas: int | None
    actualizado: str | None
    hace_min: int | None = Field(description="Minutos desde la última consulta; null si nunca se consultó.")
    llegar_antes: str | None
    en_destino: str | None = Field(description="Llegada estimada más el traslado, en el último tramo de ida.")
    no_llega: bool = Field(description="Con el retraso no llega a la hora límite de la grabación.")
    omitida: str | None = Field(description="Último motivo para no consultar (ventana, tope, caché...).")
    ultima_consulta: str | None
    aviso: AvisoVuelo | None = Field(description="Último aviso al viajero.")
    origen: str | None = Field(description="`en vivo` o `guardado`; null si nunca trajo datos.")
    origen_texto: str | None = Field(description="«En vivo» o «Estado de ejemplo» (la respuesta guardada del repositorio).")


class VuelosDelDia(BaseModel):
    fecha: str | None = Field(description="El día pedido; null es hoy más los vuelos en curso de ayer o mañana.")
    hoy: str = Field(description="Hoy en UTC.")
    tramos: list[TramoVuelo]


class ResultadoActualizacion(BaseModel):
    consultado: bool
    motivo: str | None = Field(description="Por qué no se consultó: fuera de la ventana, tope, consultado hace menos de 1 min...")
    mensaje: str
    tramo: TramoVuelo | None = Field(description="El tramo actualizado; null si su viaje ya no está aprobado.")
