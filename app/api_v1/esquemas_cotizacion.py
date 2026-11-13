"""Modelos de entrada y salida de la cotización en la API v1 (lugares, cotizar, comparar y decidir).

Son parte del contrato que publica `contracts/openapi-v1.json`; los comunes (dinero, errores) vienen de `esquemas.py`.
"""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .esquemas import Dinero, EstadoViaje, Referencia, RespuestaError

ENTERO_MAXIMO = 2**31 - 1   # los ids son enteros de 32 bits en la base: uno mayor no existe y no debe romper la consulta

# ---------- lugares ----------
OrigenSugerencia = Literal["local", "google"]


class AeropuertoSugerido(BaseModel):
    iata: str
    nombre: str | None
    municipio: str | None
    km: float | None = Field(description="Distancia en línea recta al lugar; null si no se conoce (por ejemplo, en un país).")
    horas: float | None = Field(description="Horas estimadas por carretera desde el lugar.")
    grande: bool = Field(description="Aeropuerto con muchos vuelos.")


class LugarSugerido(BaseModel):
    tipo: Literal["lugar", "aeropuerto", "pais"]
    id: str
    nombre: str
    region: str
    pais: str
    lat: float | None
    lon: float | None
    tambien: str | None = Field(description="Otro nombre con que se conoce, si coincidió por él.")
    aviso: str | None = Field(description="Por qué no trae aeropuertos, cuando no los trae.")
    origen: OrigenSugerencia = Field(description="`local` (datos propios) o `google` (autocompletado de Google Flights).")
    aeropuertos: list[AeropuertoSugerido] = Field(description="Los aeropuertos cercanos que se proponen comparar.")


class ReglasCarretera(BaseModel):
    factor: float = Field(description="Kilómetros por carretera por cada kilómetro en línea recta.")
    velocidad_kmh: float


class ListaLugares(BaseModel):
    resultados: list[LugarSugerido]
    aviso_google: str | None = Field(description="Por qué no hay sugerencias de Google (sin clave, tope alcanzado...).")
    carretera: ReglasCarretera = Field(description="Para estimar las horas de un aeropuerto agregado a mano.")


# ---------- formulario ----------
class ProyectoOpcion(BaseModel):
    id: int
    nombre: str
    ciudad: str | None
    inicio: str | None
    fin: str | None
    para_otra_persona: bool = Field(description="Se puede cotizar aquí para otra persona: administración en todos; "
                                                "el gestor, en los proyectos que gestiona.")


class ViajeroOpcion(BaseModel):
    id: int
    nombre: str
    base: str | None
    soy_yo: bool


class Razon(BaseModel):
    clave: str
    texto: str


class FormularioCotizacion(BaseModel):
    proyectos: list[ProyectoOpcion]
    viajeros: list[ViajeroOpcion] = Field(description="Quién puede viajar en esta cotización según el permiso de la persona.")
    viajero_propio_id: int | None = Field(description="El perfil de viajero de la persona; null si no viaja.")
    elige_viajero: bool = Field(description="Gestión y administración pueden cotizar para otra persona.")
    razones: list[Razon] = Field(description="Razones que se pueden marcar al decidir.")
    precios_en_vivo: bool = Field(description="false: sin clave del buscador, solo hay precios para las rutas guardadas.")


# ---------- entrada ----------
Codigo = Annotated[str, Field(pattern=r"^[A-Za-z]{3}$")]


class Lugar(BaseModel):
    """El lugar elegido en el buscador. El traslado por carretera se calcula hasta aquí."""
    nombre: str = Field(min_length=1, max_length=80)
    region: str = Field("", max_length=80)
    pais: str = Field("", max_length=80)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class LadoPedido(BaseModel):
    """Origen o destino: los aeropuertos que se comparan (con el lugar, si lo hay) o un texto con ciudad o código."""
    model_config = ConfigDict(extra="forbid")
    texto: str = Field("", max_length=120, description="Ciudad o código de aeropuerto. Se usa si no hay `aeropuertos`.")
    aeropuertos: list[Codigo] = Field(default_factory=list, max_length=8,
                                      description="Códigos IATA marcados; se comparan todos en una sola búsqueda.")
    lugar: Lugar | None = None


class NuevaCotizacion(BaseModel):
    """Un pedido de cotización. Quien cotiza sale de la sesión; nunca del cuerpo."""
    model_config = ConfigDict(extra="forbid")
    proyecto_id: int = Field(ge=1, le=ENTERO_MAXIMO)
    viajero_id: int | None = Field(None, ge=1, le=ENTERO_MAXIMO, description="Quién viaja. Omitido, quien cotiza. Otra persona: "
                                   "administración, o el gestor en los proyectos que gestiona.")
    origen: LadoPedido
    destino: LadoPedido
    ida: date
    regreso: date
    hora_limite: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
                                    description="Hora a la que debe estar en el destino el día de ida, como \"18:00\".")
    ciudad_hotel: str = Field("", max_length=80, description="Vacío: el lugar de destino.")
    baterias_n: int = Field(0, ge=0, le=50, description="Baterías de repuesto del dron.")
    baterias_wh: float = Field(0, ge=0, le=1000, description="Capacidad de cada batería.")
    maleta: bool = Field(False, description="Lleva maleta facturada.")
    prob_cambio_pct: int = Field(0, ge=0, le=100, description="Probabilidad de que cambie la fecha, en porcentaje.")
    carro_dia_usd: str = Field("0", pattern=r"^\d{1,4}(\.\d{1,2})?$", description="Carro de alquiler por día; \"0\" sin carro.")


class NuevaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vuelo_id: int = Field(ge=1, le=ENTERO_MAXIMO)
    hotel_id: int | None = Field(None, ge=1, le=ENTERO_MAXIMO, description="Opcional: puede no haber hoteles para el lugar.")
    motivo: str = Field("", max_length=300, description="Obligatorio (5 caracteres o más) si el vuelo no es el recomendado.")
    razones: list[str] = Field(default_factory=list, max_length=10, description="Claves de `razones` del formulario.")


# ---------- salida ----------
class LadoCotizacion(BaseModel):
    codigo: str = Field(description="El aeropuerto principal; tras decidir, el del vuelo elegido.")
    aeropuertos: list[str] = Field(description="Los aeropuertos comparados.")
    lugar: Lugar | None


TipoLinea = Literal["precio", "equipaje", "riesgo_cambio", "millas", "traslado", "otro"]


class LineaCosto(BaseModel):
    concepto: str
    valor_usd: Dinero
    origen: str = Field(description="De dónde sale: `buscador`, `regla` o `supuesto`.")
    tipo: TipoLinea


class Desglose(BaseModel):
    """El costo total esperado por partes. Las millas restan."""
    precio_usd: Dinero
    equipaje_usd: Dinero
    riesgo_cambio_usd: Dinero
    millas_usd: Dinero
    traslado_usd: Dinero


class Tarifa(BaseModel):
    nombre: str
    permite_cambio: bool
    reales: bool = Field(description="false: tarifa supuesta por reglas; true: tarifas reales del buscador.")


class OpcionVuelo(BaseModel):
    id: int
    aerolinea: str
    numeros: list[str]
    desde: str | None
    hasta: str | None
    sale: str = Field(description="Hora local de salida, \"2026-12-08 09:15\".")
    llega: str = Field(description="Hora local de llegada.")
    escalas: int
    duracion_min: int | None
    precio_usd: Dinero = Field(description="Precio del buscador.")
    tarifa: Tarifa
    costo_total_usd: Dinero = Field(description="Costo total esperado: precio + equipaje + riesgo de cambio − millas + traslado.")
    desglose: Desglose
    lineas: list[LineaCosto]
    avisos: list[str]
    descartada: str | None = Field(description="Por qué no sirve (llega tarde, el equipo no cabe...); null si sirve.")
    recomendada: bool
    mas_barata: bool = Field(description="La de menor precio entre las que sirven; una descartada más barata no cuenta.")
    origen_dato: str | None = Field(description="`en vivo`, `guardado` o `guardado (otras fechas)`.")
    esperado_usd: Dinero = Field(description="Precio esperado según el modelo, si hay uno utilizable.")
    frente_esperado_pct: int | None
    total_con_hotel_usd: Dinero = Field(description="Costo total esperado del vuelo más el del hotel recomendado (una suma, no "
                                                    "todas las combinaciones); null sin hotel o si el vuelo está descartado.")


class LineaHotel(BaseModel):
    concepto: str
    valor_usd: Dinero
    origen: str = Field(description="De dónde sale: `buscador` o `supuesto`.")
    tipo: Literal["tarifa", "tarifa_miembro", "puntos"]


class OpcionHotel(BaseModel):
    id: int
    nombre: str
    noche_usd: Dinero
    total_usd: Dinero = Field(description="Tarifa total del buscador para todas las noches.")
    costo_total_usd: Dinero = Field(description="Tarifa − tarifa de miembro − puntos del programa (estos dos, solo con membresía "
                                                "o si se supone la inscripción gratis).")
    lineas: list[LineaHotel]
    avisos: list[str] = Field(description="Entre ellos «Acumula solo con reserva directa» y la oportunidad de inscribirse.")
    calificacion: float | None
    clase: int | None
    programa: str | None = Field(description="Programa de fidelización reconocido por la marca, solo con reserva directa.")
    socio: bool = Field(description="El viajero o la empresa tiene membresía de ese programa.")
    descartado: str | None = Field(description="Por qué no sirve (calificación bajo el mínimo); null si sirve.")
    origen_dato: str | None
    recomendada: bool = Field(description="El de menor costo total entre los que sirven.")
    mas_barata: bool = Field(description="El de menor tarifa entre los que sirven, si no es el recomendado.")


class Equipo(BaseModel):
    nivel: Literal["ok", "aviso", "bloqueo"]
    texto: str


class DecisionCotizacion(BaseModel):
    id: int
    vuelo_id: int
    hotel_id: int | None
    motivo: str | None
    razones: list[str]
    total_usd: Dinero = Field(description="Costo total esperado de lo decidido (vuelo con riesgo y millas, hotel y carro).")
    siguio_recomendacion: bool
    creado: str
    aviso: str | None = Field(description="Si se decidió sin consultar en vivo por el tope del día, lo dice.")


class ViajeDeCotizacion(BaseModel):
    id: int
    codigo: str
    estado: EstadoViaje
    estado_texto: str
    presupuesto_usd: Dinero = Field(description="Lo que aprueba administración: vuelo, equipaje, hotel, carro y viáticos; "
                                                "sin el riesgo de cambio ni las millas, que solo sirven para comparar.")


class Cotizacion(BaseModel):
    id: int
    estado: Literal["buscando", "comparando", "decidido"]
    creado: str
    solicitado_por: str | None
    proyecto: Referencia | None
    viajero: Referencia | None
    origen: LadoCotizacion
    destino: LadoCotizacion
    ciudad_hotel: str | None
    ida: str
    regreso: str
    noches: int
    hora_limite: str | None
    baterias_n: int
    baterias_wh: float
    maleta: bool
    prob_cambio_pct: int
    carro_usd: Dinero = Field(description="Carro de alquiler de todo el viaje.")
    equipo: Equipo = Field(description="Si las baterías pueden viajar.")
    origen_dato: str | None = Field(description="De dónde salieron los vuelos: `en vivo`, `guardado`, `guardado (otras fechas)` o `fallida`.")
    aviso: str | None = Field(description="Cuando lo más barato no es lo mejor, la explicación.")
    fallos: list[str] = Field(description="Consultas en vivo que fallaron.")
    recomendacion: str = Field(description="Explicación de la recomendación (análisis determinista).")
    vuelos: list[OpcionVuelo] = Field(description="Los que sirven, del menor al mayor costo total esperado.")
    descartados: list[OpcionVuelo]
    hoteles: list[OpcionHotel] = Field(description="Los que sirven, del menor al mayor costo total (con la fidelización).")
    hoteles_descartados: list[OpcionHotel]
    hotel_recomendado_id: int | None
    recomendada_id: int | None
    mas_barata_id: int | None
    decision: DecisionCotizacion | None
    viaje: ViajeDeCotizacion | None
    puede_decidir: bool = Field(description="La persona puede guardar o cambiar la decisión ahora.")
    bloqueo: str | None = Field(description="Por qué la decisión ya no se puede cambiar, si es el caso.")


# ---------- errores ----------
_DESCRIPCION = {
    401: "Sin sesión o sesión vencida", 403: "Token CSRF ausente o inválido, origen no permitido, o sin permiso para esta acción",
    404: "No existe o no es visible para la persona",
    409: "Misma Idempotency-Key con otro pedido, pedido en curso, o decisión bloqueada por el viaje aprobado",
    422: "Campos inválidos; detalle por campo en `fields`", 429: "Tope de cotizaciones nuevas del día alcanzado",
}


def errores_cotizacion(*estados: int) -> dict:
    return {e: {"model": RespuestaError, "description": _DESCRIPCION[e]} for e in estados}
