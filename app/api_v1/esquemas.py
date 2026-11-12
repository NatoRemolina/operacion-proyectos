"""Modelos de entrada y salida de la API v1. Son el contrato que publica `contracts/openapi-v1.json`.

Las salidas se validan contra estos modelos: un campo que no está aquí (por ejemplo, la huella de la contraseña) nunca sale.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Rol = Literal["colaborador", "gestor", "admin"]
EstadoViaje = Literal["pendiente_aprobacion", "aprobado", "rechazado", "cerrado"]
EstadoGasto = Literal["procesando", "revision", "aprobado_auto", "aprobado", "rechazado"]
Dinero = str | None   # "54.00"; null si no se pudo leer


# ---------- entrada ----------
class Ingreso(BaseModel):
    """Solo correo y contraseña. Cualquier otro campo (rol, usuario_id...) se ignora."""
    correo: str = Field(min_length=3, max_length=200)
    clave: str = Field(min_length=1, max_length=200)


class CambioEstadoViaje(BaseModel):
    """Lo que decide administración sobre un viaje. Quién decide sale de la sesión, nunca del cuerpo."""
    model_config = ConfigDict(extra="forbid")
    accion: Literal["aprobar", "rechazar", "reabrir", "cerrar"] = Field(
        description="`aprobar` y `rechazar` solo desde pendiente; `reabrir` desde aprobado, rechazado o cerrado; `cerrar` desde aprobado.")
    motivo: str = Field("", max_length=300, description="Obligatorio para rechazar (5 caracteres o más). La persona lo verá.")
    confirmar_precio: bool = Field(False, description="Aprueba con el precio nuevo cuando el del vuelo subió más que la tolerancia.")


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
    cargo: str | None = Field(description="Qué hace la persona en la empresa (por ejemplo, «Pilotaje de dron»). No da permisos.")


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
    propio: bool = Field(False, description="Es de la persona de la sesión (titular o viajero): nadie aprueba lo suyo.")
    precio_por_confirmar: str | None = Field(
        None, description="Pendiente de aprobación cuyo precio de vuelo subió más que la tolerancia: hay que confirmarlo al aprobar.")


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


class ResultadoCambioEstado(BaseModel):
    viaje: ViajeDetalle
    mensaje: str = Field(description="Lo que pasó, en lenguaje claro (incluye el aviso de precio si lo hubo).")


class ActividadGasto(BaseModel):
    gasto_id: int
    comercio: str | None
    persona: Titular | None = Field(description="De quién es el gasto: el titular de su viaje o, sin viaje, quien lo cargó.")
    viaje: ViajeCodigo | None
    total: Dinero
    moneda: str | None
    total_usd: Dinero
    estado: EstadoGasto
    estado_texto: str
    creado: str


class ResumenAdmin(BaseModel):
    presupuesto_aprobado_usd: Dinero = Field(description="Presupuesto de los viajes aprobados y cerrados.")
    gastado_usd: Dinero = Field(description="Gastos aprobados de esos viajes.")
    disponible_usd: Dinero = Field(description="Aprobado menos gastado.")
    en_revision_usd: Dinero = Field(description="Total en dólares de los gastos que esperan revisión.")
    ejecucion_pct: int | None
    viajes_por_aprobar: int
    gastos_en_revision: int
    pendientes: list[ViajeResumen] = Field(description="Hasta 5 viajes pendientes de aprobación, el más reciente primero.")
    revision: list[GastoResumen] = Field(description="Hasta 5 gastos en revisión, el más reciente primero.")
    actividad: list[ActividadGasto] = Field(description="Los 10 gastos más recientes.")
    nota: str
    datos_demostracion: bool = Field(description="La plataforma corre en local con las cuentas de demostración.")


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
    401: "Sin sesión, sesión vencida o credenciales incorrectas",
    403: "Token CSRF ausente o inválido, origen no permitido, operación de otro permiso o aprobación de lo propio",
    404: "No existe o no es visible para la persona",
    409: "Conflicto: Idempotency-Key repetida con otro contenido, cambio ajeno o estado que no admite la acción",
    413: "Archivo de más de 4,5 MB", 415: "El contenido no es JPG, PNG, WebP, PDF ni correo",
    422: "Campos inválidos; detalle por campo en `fields`", 429: "Demasiados intentos de ingreso",
}


def errores(*estados: int) -> dict:
    """Respuestas de error que documenta un endpoint, todas con el formato común."""
    return {e: {"model": RespuestaError, "description": DESCRIPCION_ERROR[e]} for e in estados}
