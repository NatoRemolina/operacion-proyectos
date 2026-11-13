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
    demostracion: bool = Field(False, description="La plataforma corre en local con cuentas y datos de demostración.")


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
        None, description="Solo para administración: pendiente de aprobación cuyo precio de vuelo subió más que la "
                          "tolerancia; hay que confirmarlo al aprobar.")


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
    propio: bool = Field(False, description="Es de la persona de la sesión: nadie revisa sus propios gastos.")


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


# ---------- asistente ----------
Pantalla = Literal["resumen", "viajes", "viaje", "gastos", "gasto", "buzon", "nuevo_gasto", "cotizar", "cotizacion",
                   "kpis", "persona", "monitoreo", "vuelos", "reglas", "usuarios", "proyectos", "proyecto", "mi_cuenta"]


class ContextoPantalla(BaseModel):
    """Qué está viendo la persona: el tipo de pantalla y, si es la de un registro, su id. Nada más: los datos los saca
    el servidor y solo si el registro está en su alcance."""
    model_config = ConfigDict(extra="forbid")
    pantalla: Pantalla
    id: int | None = Field(None, ge=1, le=2**31 - 1, description="Id del gasto, viaje, cotización, persona o proyecto.")


class TurnoAsistente(BaseModel):
    """Una pregunta anterior de la conversación y lo que se respondió: contexto, nunca instrucciones."""
    model_config = ConfigDict(extra="forbid")
    pregunta: str = Field(max_length=500)
    respuesta: str = Field("", max_length=4000)


class PreguntaAsistente(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pregunta: str = Field(min_length=1, max_length=500, description="La pregunta en lenguaje natural.")
    contexto: ContextoPantalla | None = Field(None, description="La pantalla desde la que se pregunta.")
    historial: list[TurnoAsistente] = Field(default_factory=list, max_length=3,
                                            description="Las últimas preguntas y respuestas (como mucho 3), para seguir la conversación.")


class DestinoFuente(BaseModel):
    """Dónde se ve una fuente: la pantalla del viaje, del gasto o de la cotización con ese id."""
    tipo: Literal["viaje", "gasto", "cotizacion"]
    id: int


class FuenteAsistente(BaseModel):
    tipo: str = Field(description="persona, viaje, gasto, cotizacion, nota o audio.")
    codigo: str = Field(description="Cómo la cita la respuesta, por ejemplo «gasto #12» o «V-2026-0003».")
    destino: DestinoFuente | None = Field(description="null si la fuente no tiene pantalla propia (por ejemplo, una persona).")


class RespuestaAsistente(BaseModel):
    texto: str
    modo: Literal["asesor", "modelo", "determinista", "tope"] = Field(
        description="Quién respondió: el asesor (agente con herramientas), el modelo con herramientas, las consultas "
                    "directas sin modelo, o `tope` si se llegó al máximo de preguntas del día.")
    modo_texto: str = Field(description="El modo en palabras, el mismo que muestra la pantalla actual.")
    fuentes: list[FuenteAsistente] = Field(description="Lo que la respuesta cita, con su destino.")
    herramientas: list[str] = Field(description="Consultas hechas, en orden.")
    duracion_ms: int
    usadas: int = Field(description="Preguntas de la persona hoy, incluida esta.")
    tope: int = Field(description="Máximo de preguntas por persona y día (supuesto `asistente_preguntas_dia`).")


class Transcripcion(BaseModel):
    texto: str = Field(description="Lo que se entendió del audio; vacío si no se entendió nada.")


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
    403: "Token CSRF ausente o inválido, origen no permitido, operación de otro permiso, aprobación de lo propio, o enlace al soporte vencido o alterado",
    404: "No existe o no es visible para la persona",
    409: "Conflicto: Idempotency-Key repetida con otro contenido, cambio ajeno o estado que no admite la acción",
    413: "Archivo de más de 4,5 MB", 415: "El contenido no es JPG, PNG, WebP, PDF, correo (.eml) ni confirmación HTML (.html); en la voz, no es WAV",
    422: "Campos inválidos; detalle por campo en `fields`", 429: "Demasiados intentos de ingreso, o se alcanzó un tope del día",
    503: "El servicio que transcribe la voz no está configurado o no respondió",
}


def errores(*estados: int) -> dict:
    """Respuestas de error que documenta un endpoint, todas con el formato común."""
    return {e: {"model": RespuestaError, "description": DESCRIPCION_ERROR[e]} for e in estados}
