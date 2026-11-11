"""Acceso a datos. El mismo código sirve para Postgres (Supabase) y para SQLite local.

Para que las consultas sean idénticas en los dos motores, las fechas se guardan como
texto ISO y los campos compuestos como texto JSON.
"""
import json
import time
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Float, Integer, MetaData, Table, Text, create_engine, inspect, text

from . import config


def _url() -> str:
    url = config.DATABASE_URL
    if not url:
        (config.RAIZ / "datos").mkdir(exist_ok=True)
        return f"sqlite:///{config.RAIZ / 'datos' / 'local.db'}"
    for prefijo in ("postgresql://", "postgres://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


_args = {}
if config.DATABASE_URL:
    # El agrupador de conexiones de Supabase no admite sentencias preparadas
    # Autocommit y sin comprobación previa: cada consulta es un solo viaje de red hasta la base
    _args = {"connect_args": {"prepare_threshold": None}, "pool_recycle": 240, "pool_size": 5,
             "isolation_level": "AUTOCOMMIT"}
motor = create_engine(_url(), **_args)

meta = MetaData()


def _tabla(nombre, *columnas):
    return Table(nombre, meta, Column("id", Integer, primary_key=True, autoincrement=True), *columnas)


proyectos = _tabla(
    "proyectos",
    Column("nombre", Text, nullable=False), Column("cliente", Text), Column("ciudad", Text),
    Column("fecha_inicio", Text), Column("fecha_fin", Text), Column("moneda", Text),
)
viajeros = _tabla("viajeros", Column("nombre", Text, nullable=False), Column("base", Text), Column("rol", Text))
membresias = _tabla(
    "membresias",
    Column("viajero_id", Integer),  # vacío = cuenta de la empresa
    Column("programa", Text), Column("entidad", Text), Column("estatus", Text),
)
solicitudes = _tabla(
    "solicitudes",
    Column("proyecto_id", Integer), Column("viajero_id", Integer),
    Column("origen", Text), Column("destino", Text), Column("ciudad", Text),
    Column("ida", Text), Column("regreso", Text), Column("llegar_antes", Text),
    Column("baterias_n", Integer), Column("baterias_wh", Float), Column("maleta", Integer),
    Column("prob_cambio", Float), Column("carro_dia", Float),
    Column("estado", Text), Column("creado", Text), Column("solicitado_por", Text),
    # Se calculan al registrar la consulta y alimentan la analítica
    Column("precio_min_buscador", Float), Column("costo_mas_barato", Float),
    Column("costo_mejor", Float), Column("ahorro_potencial", Float),
)
opciones = _tabla(
    "opciones",
    Column("solicitud_id", Integer), Column("tipo", Text), Column("titulo", Text),
    Column("precio", Float), Column("moneda", Text), Column("datos", Text),
    Column("tarifas", Text), Column("origen_dato", Text), Column("capturado", Text),
)
reglas = _tabla(
    "reglas",
    Column("ambito", Text), Column("entidad", Text), Column("tarifa", Text), Column("clave", Text),
    Column("valor", Text), Column("nota", Text), Column("fuente", Text),
    Column("confianza", Text), Column("verificado", Text),
)
decisiones = _tabla(
    "decisiones",
    Column("solicitud_id", Integer), Column("proyecto_id", Integer),
    Column("vuelo_id", Integer), Column("hotel_id", Integer), Column("tarifa", Text),
    Column("desglose", Text), Column("total", Float), Column("motivo", Text),
    Column("aprobado_por", Text), Column("creado", Text),
)
documentos = _tabla(
    "documentos",
    Column("nombre", Text), Column("mime", Text), Column("canal", Text),
    Column("ruta", Text), Column("huella", Text), Column("creado", Text),
)
gastos = _tabla(
    "gastos",
    Column("documento_id", Integer), Column("proyecto_id", Integer), Column("viajero_id", Integer),
    Column("comercio", Text), Column("fecha", Text), Column("categoria", Text),
    Column("subtotal", Float), Column("impuesto", Float), Column("propina", Float),
    Column("total", Float), Column("moneda", Text), Column("total_usd", Float),
    Column("metodo_pago", Text), Column("canal_reserva", Text),
    Column("confianza", Float), Column("estado", Text), Column("alertas", Text),
    Column("origen_dato", Text), Column("creado", Text),
)
eventos = _tabla(
    "eventos",
    Column("momento", Text), Column("entidad", Text), Column("entidad_id", Integer),
    Column("paso", Text), Column("detalle", Text), Column("fuente", Text), Column("duracion_ms", Integer),
)

observaciones = _tabla(
    "observaciones",  # una fila por vuelo visto en una búsqueda: es el conjunto de datos del modelo
    Column("busqueda", Text), Column("origen", Text), Column("destino", Text), Column("ida", Text), Column("regreso", Text),
    Column("aerolinea", Text), Column("escalas", Integer), Column("duracion_min", Float), Column("hora_salida", Float),
    Column("dia_semana", Integer), Column("anticipacion", Integer), Column("noches", Integer), Column("precio", Float),
    Column("nivel_ruta", Text), Column("tipico_min", Float), Column("tipico_max", Float),
    Column("capturado", Text), Column("fuente", Text),
)
historial_ruta = _tabla(
    "historial_ruta",  # precio diario más bajo de un viaje concreto durante los 60 días previos
    Column("busqueda", Text), Column("origen", Text), Column("destino", Text), Column("fecha", Text), Column("precio", Float),
)

TABLAS = {t.name: t for t in meta.sorted_tables}


def ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def crear_tablas():
    """Crea las tablas que falten y añade las columnas nuevas a las que ya existen."""
    meta.create_all(motor)
    existentes = inspect(motor)
    with motor.begin() as c:
        for t in meta.sorted_tables:
            presentes = {col["name"] for col in existentes.get_columns(t.name)}
            for col in t.columns:
                if col.name not in presentes:
                    c.execute(text(f"alter table {t.name} add column {col.name} {col.type.compile(motor.dialect)}"))


def todos(sql: str, **p) -> list[dict]:
    with motor.connect() as c:
        # Postgres devuelve sumas y promedios como Decimal; se pasan a float para que todo sea serializable
        return [{k: float(v) if isinstance(v, Decimal) else v for k, v in f._mapping.items()} for f in c.execute(text(sql), p)]


_cache: dict = {}


def todos_cache(sql: str, **p) -> list[dict]:
    """Lectura con memoria corta para tablas que casi no cambian (catálogos). Cualquier escritura la vacía."""
    clave = (sql, tuple(sorted(p.items())))
    guardado = _cache.get(clave)
    if guardado and time.monotonic() - guardado[0] < 60:
        return guardado[1]
    filas = todos(sql, **p)
    _cache[clave] = (time.monotonic(), filas)
    return filas


def uno(sql: str, **p) -> dict | None:
    filas = todos(sql, **p)
    return filas[0] if filas else None


def ejecutar(sql: str, **p):
    _cache.clear()
    with motor.begin() as c:
        c.execute(text(sql), p)


def _plano(valores: dict) -> dict:
    return {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in valores.items()}


def insertar(tabla: str, **valores) -> int:
    t = TABLAS[tabla]
    if tabla not in ("eventos", "opciones", "observaciones"):
        _cache.clear()
    with motor.begin() as c:
        return c.execute(t.insert().values(**_plano(valores)).returning(t.c.id)).scalar_one()


def insertar_varios(tabla: str, filas: list[dict]):
    if filas:
        with motor.begin() as c:
            c.execute(TABLAS[tabla].insert(), [_plano(f) for f in filas])


def actualizar(tabla: str, id_: int, **valores):
    t = TABLAS[tabla]
    if tabla not in ("solicitudes", "opciones", "gastos"):
        _cache.clear()
    with motor.begin() as c:
        c.execute(t.update().where(t.c.id == id_).values(**_plano(valores)))


def de_json(valor, defecto=None):
    if not valor:
        return defecto
    try:
        return json.loads(valor)
    except (TypeError, json.JSONDecodeError):
        return defecto
