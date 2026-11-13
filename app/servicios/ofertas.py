"""Tarifas vistas: una fila por tarifa de un vuelo, del buscador o de la página de Google Flights.

Es el conjunto de datos para predecir precios por tarifa, medir la prima de flexibilidad y comparar la aerolínea con
las agencias. Solo se añaden filas: un precio visto no se corrige, se vuelve a ver. La misma tarifa de la misma fuente y
del mismo origen (una respuesta del buscador o una lectura de la página) no se repite.
"""
from sqlalchemy import CheckConstraint, Column, Float, Integer, Text

from .. import db

FUENTES = ("buscador", "pagina")
TARIFAS = ("basica", "estandar", "flexible", "premium")
CAMBIOS = ("gratis", "cargo", "no")
REEMBOLSOS = ("total", "parcial", "no")
ASIENTOS = ("incluido", "cargo")


def _valores(columna: str, valores: tuple) -> CheckConstraint:
    return CheckConstraint(f"{columna} in ({', '.join(repr(v) for v in valores)})", name=f"ck_ofertas_tarifa_{columna}")


ofertas_tarifa = db._tabla(
    "ofertas_tarifa",
    Column("momento", Text, nullable=False), Column("fuente", Text, nullable=False),
    # De dónde sale la fila: «busqueda:<clave>» o «analisis:<id>». Con la fuente, el vuelo, el vendedor y la tarifa la hace única
    Column("origen_fila", Text, nullable=False),
    # Sin claves foráneas: la fila es un hecho histórico y sobrevive a la limpieza de cotizaciones o lecturas
    Column("solicitud_id", Integer), Column("opcion_id", Integer), Column("analisis_id", Integer), Column("busqueda_clave", Text),
    Column("origen", Text), Column("destino", Text), Column("ida", Text), Column("regreso", Text),
    Column("vuelos", Text, nullable=False),        # números de vuelo sin espacios, unidos por coma: «AA1851,AA1597»
    Column("aerolinea", Text), Column("vendedor", Text, nullable=False), Column("es_aerolinea", Integer),
    Column("tarifa", Text, nullable=False),        # nombre original: «Basic Economy»
    Column("tarifa_normalizada", Text), Column("precio", Float), Column("moneda", Text),
    Column("equipaje_mano", Integer),              # 1 incluido, 0 con cargo o sin él, vacío si no se informa
    Column("maleta_usd", Float),                   # primera maleta facturada; 0 si va incluida
    Column("cambios", Text), Column("reembolso", Text), Column("asiento", Text),
    Column("anticipacion_dias", Integer), Column("dia_semana", Integer), Column("noches", Integer),
    # La tarifa tal como llegó (JSON): si la normalización mejora, se rehace desde aquí sin volver a buscar
    Column("crudo", Text),
    _valores("fuente", FUENTES), _valores("tarifa_normalizada", TARIFAS), _valores("cambios", CAMBIOS),
    _valores("reembolso", REEMBOLSOS), _valores("asiento", ASIENTOS),
)

INDICES = [  # nombre, columnas, único
    ("ix_ofertas_tarifa_ruta_ida", "origen, destino, ida", False),
    ("ix_ofertas_tarifa_ida", "ida", False),
    ("ux_ofertas_tarifa_unica", "fuente, origen_fila, vuelos, vendedor, tarifa", True),
]
