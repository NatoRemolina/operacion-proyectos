"""Modelos de la API v1 del buzón de correo simulado. Contrato en `contracts/api-v1.md`, sección «Buzón de correo (simulado)»."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .esquemas import GastoResumen


class MensajeBuzon(BaseModel):
    nombre: str
    formato: Literal["correo", "html"] = Field(description="`correo`: un .eml; `html`: una confirmación guardada como página.")
    remitente: str | None
    asunto: str | None


class LecturaBuzon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombres: list[str] = Field(min_length=1, max_length=20, description="Los `nombre` del buzón que se leen.")
    viaje_id: int | None = Field(None, ge=1, description="Opcional: el viaje al que se cargan (define proyecto y persona). "
                                                         "Sin él, quedan a nombre de quien lee y sin viaje.")


class ErrorBuzon(BaseModel):
    nombre: str
    mensaje: str


class ResultadoBuzon(BaseModel):
    leidos: list[GastoResumen] = Field(description="Un gasto por correo leído, con su estado real (`aprobado_auto` o `revision`).")
    errores: list[ErrorBuzon]
