"""Acceso a datos. El mismo código sirve para Postgres (Supabase) y para SQLite local.

Para que las consultas sean idénticas en los dos motores, las fechas se guardan como
texto ISO y los campos compuestos como texto JSON.
"""
import json
import time
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Column, Float, ForeignKey, Integer, MetaData, Table, Text, create_engine, event, inspect, text

from . import config


def _url() -> str:
    url = config.DATABASE_URL
    if not url:
        (config.RAIZ / "datos").mkdir(exist_ok=True)
        return f"sqlite:///{config.RAIZ / 'datos' / 'local.db'}"
    if url.startswith("sqlite"):
        return url
    for prefijo in ("postgresql://", "postgres://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


_args = {}
if not config.ES_SQLITE:
    # El agrupador de conexiones no admite sentencias preparadas. Autocommit: cada consulta es un solo viaje de red.
    _args = {"connect_args": {"prepare_threshold": None}, "isolation_level": "AUTOCOMMIT"}
    if config.LOCAL:
        _args.update(pool_size=5, pool_recycle=240)
    else:
        # En la nube cada instancia mantiene pocas conexiones y las comprueba al reanudar tras una pausa
        _args.update(pool_size=2, max_overflow=2, pool_recycle=120, pool_pre_ping=True)
motor = create_engine(_url(), **_args)

if config.ES_SQLITE:
    @event.listens_for(motor, "connect")
    def _claves_foraneas(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")  # SQLite no las hace cumplir si no se le pide

meta = MetaData()


def _tabla(nombre, *columnas):
    return Table(nombre, meta, Column("id", Integer, primary_key=True, autoincrement=True), *columnas)


def _ref(tabla: str, columna: str, destino: str) -> Column:
    """Columna que apunta a otra tabla. El nombre de la restricción es fijo para que la migración sepa si ya existe."""
    return Column(columna, Integer, ForeignKey(f"{destino}.id", name=f"fk_{tabla}_{columna}"))


proyectos = _tabla(
    "proyectos",
    Column("nombre", Text, nullable=False), Column("cliente", Text), Column("ciudad", Text),
    Column("fecha_inicio", Text), Column("fecha_fin", Text), Column("moneda", Text),
)
viajeros = _tabla("viajeros", Column("nombre", Text, nullable=False), Column("base", Text), Column("rol", Text))
membresias = _tabla(
    "membresias",
    _ref("membresias", "viajero_id", "viajeros"),  # vacío = cuenta de la empresa
    Column("programa", Text), Column("entidad", Text), Column("estatus", Text),
)
solicitudes = _tabla(
    "solicitudes",
    _ref("solicitudes", "proyecto_id", "proyectos"), _ref("solicitudes", "viajero_id", "viajeros"),
    Column("origen", Text), Column("destino", Text), Column("ciudad", Text),
    Column("ida", Text), Column("regreso", Text), Column("llegar_antes", Text),
    Column("baterias_n", Integer), Column("baterias_wh", Float), Column("maleta", Integer),
    Column("prob_cambio", Float), Column("carro_dia", Float),
    Column("estado", Text), Column("creado", Text), Column("solicitado_por", Text), _ref("solicitudes", "usuario_id", "usuarios"),
    # Se calculan al registrar la consulta y alimentan la analítica
    Column("precio_min_buscador", Float), Column("costo_mas_barato", Float),
    Column("costo_mejor", Float), Column("ahorro_potencial", Float),
    # Buscador mundial: el lugar elegido (JSON con nombre, región, país y coordenadas) y los aeropuertos marcados
    # (códigos ordenados, separados por coma). `origen` y `destino` siguen guardando un solo código
    Column("origen_lugar", Text), Column("destino_lugar", Text),
    Column("origen_aeropuertos", Text), Column("destino_aeropuertos", Text),
)
opciones = _tabla(
    "opciones",
    _ref("opciones", "solicitud_id", "solicitudes"), Column("tipo", Text), Column("titulo", Text),
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
    _ref("decisiones", "solicitud_id", "solicitudes"), _ref("decisiones", "proyecto_id", "proyectos"),
    Column("vuelo_id", Integer), Column("hotel_id", Integer), Column("tarifa", Text),
    Column("desglose", Text), Column("total", Float), Column("motivo", Text),
    Column("aprobado_por", Text), Column("creado", Text), _ref("decisiones", "usuario_id", "usuarios"),
    # Qué recomendó el sistema y por qué eligió la persona: base del acuerdo y del futuro modelo de decisión
    Column("razones", Text), Column("recomendado_id", Integer), Column("siguio_recomendacion", Integer),
    Column("posicion_elegida", Integer),
)
elecciones = _tabla(
    "elecciones",  # una fila por opción mostrada al decidir, con la marca de cuál se eligió: conjunto etiquetado
    _ref("elecciones", "decision_id", "decisiones"), _ref("elecciones", "solicitud_id", "solicitudes"), Column("opcion_id", Integer), Column("tipo", Text),
    Column("posicion", Integer), Column("elegida", Integer), Column("recomendada", Integer), Column("descartada", Integer),
    Column("precio", Float), Column("costo_esperado", Float), Column("rasgos", Text), Column("creado", Text),
)
errores = _tabla(
    "errores",
    Column("momento", Text), Column("peticion", Text), Column("usuario_id", Integer), Column("ruta", Text),
    Column("tipo", Text), Column("mensaje", Text), Column("traza", Text),
)
documentos = _tabla(
    "documentos",
    Column("nombre", Text), Column("mime", Text), Column("canal", Text),
    Column("ruta", Text), Column("huella", Text), Column("creado", Text), _ref("documentos", "usuario_id", "usuarios"),
    # tipo: soporte (origina un gasto), audio o nota (evidencias del viaje que no originan gasto)
    _ref("documentos", "viaje_id", "viajes"), Column("tipo", Text), Column("texto", Text),
)
gastos = _tabla(
    "gastos",
    _ref("gastos", "documento_id", "documentos"), _ref("gastos", "proyecto_id", "proyectos"), _ref("gastos", "viajero_id", "viajeros"),
    Column("comercio", Text), Column("fecha", Text), Column("categoria", Text),
    Column("subtotal", Float), Column("impuesto", Float), Column("propina", Float),
    Column("total", Float), Column("moneda", Text), Column("total_usd", Float),
    Column("metodo_pago", Text), Column("canal_reserva", Text),
    Column("confianza", Float), Column("estado", Text), Column("alertas", Text),
    Column("origen_dato", Text), Column("creado", Text),
    _ref("gastos", "usuario_id", "usuarios"), _ref("gastos", "revisado_por", "usuarios"),
    Column("motivos", Text),  # códigos de las alertas, para contar por qué se revisa sin buscar en el texto
    Column("extraido", Text),  # lectura original del modelo, intacta, para medir cuánto se corrige
    _ref("gastos", "viaje_id", "viajes"),
)
eventos = _tabla(
    "eventos",
    Column("momento", Text), Column("entidad", Text), Column("entidad_id", Integer),
    Column("paso", Text), Column("detalle", Text), Column("fuente", Text), Column("duracion_ms", Integer),
    Column("usuario_id", Integer),
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

cargos = _tabla(
    "cargos",  # qué hace la persona en la empresa; no da permisos. Con personas asignadas no se borra, se desactiva
    Column("nombre", Text, nullable=False, unique=True), Column("activo", Integer), Column("creado", Text),
)
usuarios = _tabla(
    "usuarios",
    Column("correo", Text, unique=True), Column("nombre", Text), Column("rol", Text), Column("activo", Integer),
    Column("clave_hash", Text), _ref("usuarios", "viajero_id", "viajeros"), Column("fallos", Integer),
    Column("bloqueado_hasta", Text), Column("creado", Text),
    Column("telegram_chat_id", BigInteger), Column("telegram_usuario", Text),
    Column("viaje_activo_id", Integer),  # viaje que la persona fijó a mano para sus próximos gastos
    _ref("usuarios", "cargo_id", "cargos"),   # opcional
    CheckConstraint("rol in ('colaborador','gestor','admin')", name="ck_usuarios_rol"),
)
proyecto_miembros = _tabla(
    "proyecto_miembros",  # qué proyectos ve un gestor
    _ref("proyecto_miembros", "usuario_id", "usuarios"), _ref("proyecto_miembros", "proyecto_id", "proyectos"),
    Column("papel", Text), Column("creado", Text),
)
viajes = _tabla(
    "viajes",  # el eje: nace de una decisión, lo aprueba administración y agrupa gastos y evidencias
    Column("solicitud_id", Integer, ForeignKey("solicitudes.id", name="fk_viajes_solicitud_id"), unique=True),
    _ref("viajes", "decision_id", "decisiones"), _ref("viajes", "proyecto_id", "proyectos"),
    _ref("viajes", "usuario_id", "usuarios"),  # titular: quien viaja y reporta los gastos
    _ref("viajes", "viajero_id", "viajeros"),
    Column("ida", Text), Column("regreso", Text), Column("presupuesto_usd", Float), Column("presupuesto_detalle", Text),
    Column("estado", Text, nullable=False), _ref("viajes", "aprobado_por", "usuarios"), Column("aprobado_en", Text),
    Column("motivo", Text), Column("creado", Text),
    CheckConstraint("estado in ('pendiente_aprobacion','aprobado','rechazado','cerrado')", name="ck_viajes_estado"),
)
vinculos_telegram = _tabla(
    "vinculos_telegram",  # códigos de un solo uso para unir un chat con una cuenta; solo se guarda la huella
    _ref("vinculos_telegram", "usuario_id", "usuarios"), Column("huella", Text, unique=True),
    Column("expira", Text), Column("usado", Text),
)
telegram_mensajes = _tabla(
    "telegram_mensajes",  # todo lo recibido por el chat; update_id único evita procesar dos veces la misma entrega
    Column("update_id", BigInteger, unique=True), Column("chat_id", BigInteger), Column("usuario_id", Integer),
    Column("tipo", Text), Column("texto", Text), Column("documento_id", Integer), Column("gasto_id", Integer),
    Column("viaje_id", Integer), Column("estado", Text), Column("momento", Text),
)
sesiones = _tabla(
    "sesiones",  # solo la huella del token: la tabla no sirve para suplantar a nadie
    Column("huella", Text, unique=True), _ref("sesiones", "usuario_id", "usuarios"),
    Column("creada", Text), Column("ultima", Text), Column("expira", Text),
)
busquedas = _tabla(
    "busquedas",  # respuestas del buscador de precios, compartidas entre instancias
    Column("clave", Text), Column("cuerpo", Text), Column("creado", Text),
)

llamadas_modelo = _tabla(
    "llamadas_modelo",  # una fila por llamada al modelo de lenguaje: base del monitoreo de uso y costo
    Column("momento", Text), Column("uso", Text), Column("entidad_id", Integer), Column("modelo", Text),
    Column("tokens_entrada", Integer), Column("tokens_salida", Integer), Column("latencia_ms", Integer),
    Column("estado_http", Integer), Column("motivo_parada", Text), Column("error", Text),
)

# Vista viva del registro: una tabla declarada en el módulo de su servicio con `_tabla(...)` aparece aquí al importarse
TABLAS = meta.tables


def ahora() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def crear_tablas():
    """Crea las tablas que falten y añade las columnas nuevas a las que ya existen."""
    import importlib
    import pkgutil

    from . import servicios
    for m in pkgutil.iter_modules(servicios.__path__):   # cada servicio puede declarar sus propias tablas
        importlib.import_module(f"{servicios.__name__}.{m.name}")
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
    return {k: json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else v for k, v in valores.items()}


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
