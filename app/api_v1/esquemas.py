"""Modelos de entrada y salida de la API v1. Son el contrato que publica `contracts/openapi-v1.json`.

Las salidas se validan contra estos modelos: un campo que no está aquí (por ejemplo, la huella de la contraseña) nunca sale.
"""
from typing import Literal

from pydantic import BaseModel, Field

Rol = Literal["piloto", "gestor", "admin"]
EstadoViaje = Literal["pendiente_aprobacion", "aprobado", "rechazado", "cerrado"]
EstadoGasto = Literal["procesando", "revision", "aprobado_auto", "aprobado", "rechazado"]
Dinero = str | None   # "54.00"; null si no se pudo leer


# ---------- entrada ----------
class Ingreso(BaseModel):
    """Solo correo y contraseña. Cualquier otro campo (rol, usuario_id...) se ignora."""
    correo: str = Field(min_length=3, max_length=200)
    clave: str = Field(min_length=1, max_length=200)


class NuevaJustificacion(BaseModel):
    """Para qué fue el gasto, con las palabras de la persona."""
    texto: str = Field(min_length=3, max_length=2000)


# ---------- salida ----------
class Persona(BaseModel):
    id: int
    codigo: str
    nombre: str
    rol: Rol
    correo: str


class Sesion(BaseModel):
    persona: Persona
    csrf_token: str


class Referencia(BaseModel):
    id: int
    nombre: str | None


class Titular(BaseModel):
    id: int
    codigo: str
    nombre: str | None


class ViajeResumen(BaseModel):
    id: int
    codigo: str
    estado: EstadoViaje
    estado_texto: str
    en_curso: bool
    origen: str | None
    destino: str | None
    ida: str | None
    regreso: str | None
    proyecto: Referencia | None
    titular: Titular | None
    presupuesto_usd: Dinero
    gastado_usd: Dinero
    en_revision_usd: Dinero
    ejecucion_pct: int | None
    gastos: int


class LineaPresupuesto(BaseModel):
    concepto: str
    valor: Dinero
    grupo: str


class ViajeDetalle(ViajeResumen):
    presupuesto_detalle: list[LineaPresupuesto]
    motivo: str | None
    aprobado_en: str | None


class ViajeCodigo(BaseModel):
    id: int
    codigo: str


class GastoResumen(BaseModel):
    id: int
    viaje: ViajeCodigo | None
    comercio: str | None
    fecha: str | None
    categoria: str | None
    total: Dinero
    moneda: str | None
    total_usd: Dinero
    estado: EstadoGasto
    estado_texto: str
    creado: str


class Lectura(BaseModel):
    origen: str
    confianza: float | None


class Justificacion(BaseModel):
    id: int
    tipo: Literal["texto", "audio"]
    canal: str
    texto: str | None = Field(description="Lo escrito, o la transcripción de la nota de voz si ya existe.")
    transcripcion: Literal["no_aplica", "pendiente", "hecha", "fallida"]
    creado: str


class GastoDetalle(GastoResumen):
    subtotal: Dinero
    impuesto: Dinero
    propina: Dinero
    motivos: list[str]
    alertas: list[str]
    canal: str
    documento_id: int | None
    lectura: Lectura
    justificaciones: list[Justificacion]


class ListaViajes(BaseModel):
    items: list[ViajeResumen]
    siguiente: str | None


class ListaGastos(BaseModel):
    items: list[GastoResumen]
    siguiente: str | None


# ---------- errores ----------
class DetalleError(BaseModel):
    code: str
    message: str
    fields: dict[str, str]


class RespuestaError(BaseModel):
    error: DetalleError
    request_id: str


DESCRIPCION_ERROR = {
    401: "Sin sesión, sesión vencida o credenciales incorrectas", 403: "Token CSRF ausente o inválido, u origen no permitido",
    404: "No existe o no es visible para la persona", 409: "Misma Idempotency-Key con un archivo distinto",
    413: "Archivo de más de 4,5 MB", 415: "El contenido no es JPG, PNG, WebP, PDF ni correo",
    422: "Campos inválidos; detalle por campo en `fields`", 429: "Demasiados intentos de ingreso",
}


def errores(*estados: int) -> dict:
    """Respuestas de error que documenta un endpoint, todas con el formato común."""
    return {e: {"model": RespuestaError, "description": DESCRIPCION_ERROR[e]} for e in estados}
