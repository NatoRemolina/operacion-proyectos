"""Tarifas vistas: una fila por tarifa de un vuelo, del buscador o de la página de Google Flights.

Es el conjunto de datos para predecir precios por tarifa, medir la prima de flexibilidad y comparar la aerolínea con
las agencias. Solo se añaden filas: un precio visto no se corrige, se vuelve a ver. La misma tarifa de la misma fuente y
del mismo origen (una respuesta del buscador o una lectura de la página) no se repite.
"""
import json
import re
import time
from datetime import date

from sqlalchemy import CheckConstraint, Column, Float, Integer, Text, inspect

from .. import config, db
from . import eventos

FUENTES = ("buscador", "pagina")
TARIFAS = ("basica", "estandar", "flexible", "premium")
CAMBIOS = ("gratis", "cargo", "no")
REEMBOLSOS = ("total", "parcial", "no")
ASIENTOS = ("incluido", "cargo")
TRAMOS = ("ida_vuelta", "ida", "regreso")   # la tarifa cubre el viaje completo, o solo la ida o el regreso (boletos separados)


def _valores(columna: str, valores: tuple) -> CheckConstraint:
    return CheckConstraint(f"{columna} in ({', '.join(repr(v) for v in valores)})", name=f"ck_ofertas_tarifa_{columna}")


ofertas_tarifa = db._tabla(
    "ofertas_tarifa",
    Column("momento", Text, nullable=False), Column("fuente", Text, nullable=False),
    # De dónde sale la fila: «busqueda:<id de busquedas>», «archivo:<nombre>» (respaldo local) o «analisis:<id>». Cada
    # respuesta guardada es un momento distinto: la misma tarifa vista otro día es otra fila
    Column("origen_fila", Text, nullable=False),
    # Sin claves foráneas: la fila es un hecho histórico y sobrevive a la limpieza de cotizaciones o lecturas
    Column("solicitud_id", Integer), Column("opcion_id", Integer), Column("analisis_id", Integer), Column("busqueda_clave", Text),
    Column("origen", Text), Column("destino", Text), Column("ida", Text), Column("regreso", Text),
    # Posición de la opción dentro de su respuesta o lectura (desde 0) y qué parte del viaje cubre
    Column("ordinal", Integer, nullable=False, server_default="0"),
    Column("tramo", Text, nullable=False, server_default="ida_vuelta"),
    Column("vuelos", Text, nullable=False),        # números de vuelo de la ida, juntos y sin espacios como en las claves: «AA1851»
    Column("aerolinea", Text), Column("vendedor", Text, nullable=False), Column("es_aerolinea", Integer),
    Column("tarifa", Text, nullable=False),        # nombre original: «Basic Economy»
    Column("tarifa_normalizada", Text), Column("precio", Float), Column("moneda", Text),
    Column("equipaje_mano", Integer),              # 1 incluido, 0 con cargo o sin él, vacío si no se informa
    Column("maleta_usd", Float),                   # primera maleta facturada; 0 si va incluida
    Column("cambios", Text), Column("reembolso", Text), Column("asiento", Text),
    Column("anticipacion_dias", Integer), Column("dia_semana", Integer), Column("noches", Integer),
    # La tarifa tal como llegó (JSON): si la normalización mejora, se rehace desde aquí sin volver a buscar
    Column("crudo", Text),
    # Lo que no se pudo clasificar (JSON con las líneas y la tarifa sin tipo) y si la lectura fue completa o parcial
    Column("sin_reconocer", Text), Column("normalizacion", Text),
    _valores("fuente", FUENTES), _valores("tarifa_normalizada", TARIFAS), _valores("cambios", CAMBIOS),
    _valores("reembolso", REEMBOLSOS), _valores("asiento", ASIENTOS), _valores("tramo", TRAMOS),
    _valores("normalizacion", ("completa", "parcial")),
)

INDICES = [  # nombre, columnas, único
    ("ix_ofertas_tarifa_ruta_ida", "origen, destino, ida", False),
    ("ix_ofertas_tarifa_ida", "ida", False),
    ("ux_ofertas_tarifa_origen", "fuente, origen_fila, ordinal, tramo, vuelos, vendedor, tarifa", True),
]
INDICES_RETIRADOS = ("ux_ofertas_tarifa_unica",)   # sin ordinal ni tramo rechazaba filas legítimas



# ---------- normalización del texto de Google (en inglés: la página se pide siempre en inglés y en dólares) ----------
def _bajo(lineas) -> list[str]:
    return [str(x).strip().lower() for x in lineas or [] if x]


def _importe(linea: str) -> float | None:
    m = re.search(r"\$?\s*(\d+(?:[.,]\d+)?)\s*$", linea) or re.search(r":\s*\$?\s*(\d+(?:[.,]\d+)?)", linea)
    return float(m.group(1).replace(",", "")) if m else None


_ORDINAL = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b")


def _sin_incluir(t: str) -> bool:
    return t.startswith(("no ", "0 ")) or "not included" in t


def equipaje(lineas) -> tuple[int | None, float | None]:
    """(equipaje de mano: 1 incluido, 0 no; primera maleta facturada en USD: 0 si va incluida). Vacío si no se dice o si
    no está incluida y no se informa el precio. Solo cuenta la línea de la primera maleta («1st» o sin ordinal)."""
    mano, maleta, primera_vista = None, None, False
    for t in _bajo(lineas):
        if "carry-on" in t:
            if _sin_incluir(t):     # «no» y «not included» antes que «free» o «included»
                mano = 0
            elif "free" in t or "included" in t:
                mano = 1
            elif _importe(t) is not None:
                mano = 0
        elif "checked bag" in t and not primera_vista:
            ordinal = _ORDINAL.search(t)
            if ordinal and ordinal.group(1) != "1":
                continue           # la segunda maleta no dice nada de la primera
            primera_vista = True
            if _sin_incluir(t):
                maleta = None
            elif "free" in t or "included" in t:
                maleta = 0.0
            else:
                maleta = _importe(t)
    return mano, maleta


def cambios(lineas) -> str | None:
    for t in _bajo(lineas):
        if "change" not in t:
            continue
        if re.search(r"free (ticket )?changes?|no change fee", t):
            return "gratis"
        if t.startswith("no ") or "not allowed" in t or re.search(r"non-?changeable", t):
            return "no"
        if "fee" in t or _importe(t) is not None:
            return "cargo"
    return None


def reembolso(lineas) -> str | None:
    for t in _bajo(lineas):
        if "refund" not in t:
            continue
        if t.startswith("no ") or re.search(r"non-?refundable|not refundable", t):
            return "no"
        if "partial" in t or "fee" in t:
            return "parcial"
        if "full" in t or "fully" in t or t in ("refundable", "refunds"):
            return "total"
    return None


def asiento(lineas) -> str | None:
    for t in _bajo(lineas):
        if "seat selection" not in t:
            continue
        if "fee" in t or "paid" in t or _importe(t) is not None:
            return "cargo"
        if "free" in t or "included" in t:
            return "incluido"
    return None


_PREMIUM = re.compile(r"business|first|premium|polaris|suite|upper class|delta one|\bmint\b|club world")
_FLEXIBLE = re.compile(r"flex|refundable")
_BASICA = re.compile(r"\bbasic\b|\blight\b|\blite\b|saver|hand baggage|no bag")
_ESTANDAR = re.compile(r"\bmain\b|economy|standard|classic|coach|\bvalue\b|regular|\bsmart\b|\bplus\b|comfort")


def tarifa_normalizada(nombre: str | None, cambios_: str | None, reembolso_: str | None) -> str | None:
    """basica | estandar | flexible | premium, o vacía si no se reconoce (queda marcada en `sin_reconocer`). Primero el
    nombre de la tarifa; si no lo dice, sus condiciones."""
    n = (nombre or "").lower()
    if _PREMIUM.search(n):
        return "premium"
    if _FLEXIBLE.search(n) or reembolso_ == "total":
        return "flexible"
    if _BASICA.search(n) or cambios_ == "no":
        return "basica"
    if _ESTANDAR.search(n):
        return "estandar"
    return None


def no_reconocidas(lineas_equipaje, lineas_condiciones) -> list[str]:
    """Las líneas que hablan de equipaje, cambios, reembolso o elección de asiento y no se pudieron clasificar. Las que
    hablan de otra cosa (espacio para las piernas, embarque, wifi) no se clasifican y quedan solo en el crudo."""
    fuera = []
    for linea in lineas_equipaje or []:
        t = str(linea).strip().lower()
        if "carry-on" in t:
            entendida = equipaje([linea])[0] is not None
        elif "checked bag" in t:
            ordinal = _ORDINAL.search(t)
            entendida = bool(ordinal and ordinal.group(1) != "1") or _sin_incluir(t) or equipaje([linea])[1] is not None
        else:
            entendida = False
        if not entendida:
            fuera.append(str(linea))
    for linea in lineas_condiciones or []:
        t = str(linea).strip().lower()
        if ("change" in t and cambios([linea]) is None) or ("refund" in t and "change" not in t and reembolso([linea]) is None) \
                or ("seat selection" in t and asiento([linea]) is None):
            fuera.append(str(linea))
    return fuera


# ---------- extractor ----------
PREFIJOS = ("reserva_", "tarifas_", "reconfirmacion_")   # respuestas del buscador que traen `booking_options`


def _existe(tabla: str) -> bool:
    return inspect(db.motor).has_table(tabla)


def _fecha(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _calendario(ida, regreso, momento) -> dict:
    f_ida, f_reg, visto = _fecha(ida), _fecha(regreso), _fecha(momento)
    return {"anticipacion_dias": (f_ida - visto).days if f_ida and visto else None,
            "dia_semana": f_ida.weekday() if f_ida else None, "noches": (f_reg - f_ida).days if f_ida and f_reg else None}


def _fila(base: dict, nombre, precio, vendedor, es_aerolinea, lineas_equipaje, lineas_condiciones, crudo,
          ordinal: int = 0, tramo: str = "ida_vuelta") -> dict | None:
    try:
        precio = float(precio)
    except (TypeError, ValueError):
        precio = None   # se guarda igual, con su crudo: la limpieza la deja fuera al entrenar («sin precio»)
    mano, maleta = equipaje(lineas_equipaje)
    c, r = cambios(lineas_condiciones), reembolso(lineas_condiciones)
    tipo = tarifa_normalizada(nombre, c, r)
    sin = ([f"tarifa «{nombre or 'sin nombre'}»"] if tipo is None else []) + no_reconocidas(lineas_equipaje, lineas_condiciones)
    return {**base, "ordinal": ordinal, "tramo": tramo, "tarifa": nombre or "Tarifa", "vendedor": vendedor or "",
            "es_aerolinea": es_aerolinea, "precio": precio, "tarifa_normalizada": tipo, "equipaje_mano": mano, "maleta_usd": maleta,
            "cambios": c, "reembolso": r, "asiento": asiento(lineas_condiciones),
            "sin_reconocer": json.dumps(sin, ensure_ascii=False) if sin else None,
            "normalizacion": "parcial" if sin else "completa", "crudo": json.dumps(crudo, ensure_ascii=False)}


def _de_respuesta(origen_fila: str, clave: str, datos: dict, creado: str | None) -> list[dict]:
    """Filas de una respuesta del buscador con opciones de reserva (las de «Traer tarifas» guardaban también el regreso)."""
    if clave.startswith("tarifas_"):
        datos = datos.get("reserva") or {}
    if not isinstance(datos, dict) or not datos.get("booking_options"):
        return []
    p = datos.get("search_parameters") or {}
    partes = clave.removesuffix(".json").split("_")
    tramos = ((datos.get("selected_flights") or [{}])[0] or {}).get("flights") or []
    numeros = "".join((t.get("flight_number") or "").replace(" ", "") for t in tramos)
    if not numeros and len(partes) == 6:
        numeros = partes[5]
    origen = (tramos[0].get("departure_airport") or {}).get("id") if tramos else None
    destino = (tramos[-1].get("arrival_airport") or {}).get("id") if tramos else None
    ida, regreso = p.get("outbound_date") or (partes[3] if len(partes) >= 5 else None), p.get("return_date") or (partes[4] if len(partes) >= 5 else None)
    momento = ((datos.get("search_metadata") or {}).get("created_at") or creado or db.ahora())[:19]
    consulta = db.uno("select solicitud_id from consultas_buscador where clave=:c and solicitud_id is not null order by id limit 1", c=clave)
    sid = consulta["solicitud_id"] if consulta else None
    base = {"momento": momento, "fuente": "buscador", "origen_fila": origen_fila, "busqueda_clave": clave,
            "solicitud_id": sid, "opcion_id": _opcion_de(sid, numeros), "analisis_id": None,
            "origen": origen or p.get("departure_id") or (partes[1] if len(partes) >= 3 else None),
            "destino": destino or p.get("arrival_id") or (partes[2] if len(partes) >= 3 else None),
            "ida": ida, "regreso": regreso, "vuelos": numeros, "aerolinea": tramos[0].get("airline") if tramos else None,
            "moneda": p.get("currency") or "USD", **_calendario(ida, regreso, momento)}
    filas = []
    for ordinal, o in enumerate(datos["booking_options"]):
        partes = [(o[k], tramo) for k, tramo in (("together", "ida_vuelta"), ("departing", "ida"), ("returning", "regreso"))
                  if isinstance(o.get(k), dict)] or [(o, "ida_vuelta")]   # una forma desconocida se guarda entera
        for t, tramo in partes:
            f = _fila(base, t.get("option_title"), t.get("price"), t.get("book_with"), int(bool(t.get("airline"))),
                      t.get("baggage_prices"), t.get("extensions"), t, ordinal, tramo)
            filas += [f] if f else []
    return filas


def _opcion_de(sid: int | None, numeros: str) -> int | None:
    """La opción de vuelo de la cotización con esos números de vuelo."""
    if not sid or not numeros:
        return None
    for o in db.todos("select id, datos from opciones where solicitud_id=:s and tipo='vuelo'", s=sid):
        if "".join(n.replace(" ", "") for n in (db.de_json(o["datos"], {}) or {}).get("numeros") or []) == numeros:
            return o["id"]
    return None


def _de_lectura(a: dict) -> list[dict]:
    """Filas de una lectura de la página de Google Flights (`analisis_vuelo.datos`, como lo deja `analizador/lector.py`)."""
    datos = db.de_json(a["datos"], {}) or {}
    tarifas = datos.get("tarifas") or []
    if not tarifas:
        return []
    partes = (a.get("clave") or "").split("_")
    numeros = partes[0] if len(partes) == 4 else ""
    ida, regreso = (partes[2], partes[3]) if len(partes) == 4 else (None, None)
    sol = db.uno("select origen, destino, ida, regreso from solicitudes where id=:i", i=a["solicitud_id"]) if a.get("solicitud_id") else None
    tramos = datos.get("tramos") or []
    ruta = re.split(r"\s*[–-]\s*", tramos[0].get("ruta") or "") if tramos else []
    momento = (a.get("terminado") or a.get("creado") or db.ahora())[:19]
    ida, regreso = ida or (sol or {}).get("ida"), regreso or (sol or {}).get("regreso")
    base = {"momento": momento, "fuente": "pagina", "origen_fila": f"analisis:{a['id']}", "analisis_id": a["id"],
            "solicitud_id": a.get("solicitud_id"), "opcion_id": a.get("opcion_id"), "busqueda_clave": None,
            "origen": ruta[0] if len(ruta) == 2 else (sol or {}).get("origen"),
            "destino": ruta[1] if len(ruta) == 2 else (sol or {}).get("destino"),
            "ida": ida, "regreso": regreso, "vuelos": numeros, "aerolinea": tramos[0].get("aerolinea") if tramos else None,
            "moneda": "USD", **_calendario(ida, regreso, momento)}
    de_aerolinea = {v.get("vendedor"): int(bool(v.get("aerolinea"))) for v in datos.get("vendedores") or []}
    filas = []
    for ordinal, t in enumerate(tarifas):
        condiciones = (t.get("cambios") or []) + (t.get("reembolso") or []) + (t.get("otras") or [])
        f = _fila(base, t.get("nombre"), t.get("precio"), t.get("vendedor"), de_aerolinea.get(t.get("vendedor")),
                  t.get("equipaje"), condiciones, t, ordinal)
        filas += [f] if f else []
    return filas


def _insertar(filas: list[dict]) -> int:
    """Añade las filas que no estén; la misma tarifa del mismo origen se ignora (índice único). Devuelve cuántas entraron."""
    if not filas:
        return 0
    from sqlalchemy.dialects import postgresql, sqlite
    sentencia = (sqlite if config.ES_SQLITE else postgresql).insert(ofertas_tarifa).on_conflict_do_nothing()
    antes = db.uno("select count(*) n from ofertas_tarifa")["n"]
    with db.transaccion() as c:
        c.execute(sentencia, filas)
    return db.uno("select count(*) n from ofertas_tarifa")["n"] - antes


def _hechos() -> set[str]:
    return {r["origen_fila"] for r in db.todos("select distinct origen_fila from ofertas_tarifa")}


def _respuestas_nuevas(hechos: set[str]) -> list[tuple[str, str, dict, str | None]]:
    """(origen de la fila, clave, respuesta, creado) de las respuestas con opciones de reserva aún no extraídas. Cada fila de
    `busquedas` cuenta por separado (la misma clave guardada otro día es otro momento). Un archivo de la carpeta de
    respaldo solo entra si la tabla no tiene ninguna respuesta con esa clave: si la tiene, es la misma respuesta."""
    condicion = " or ".join(f"clave like '{p}%'" for p in PREFIJOS)
    salida = []
    for r in db.todos(f"select id, clave from busquedas where {condicion} order by id"):
        if f"busqueda:{r['id']}" in hechos:
            continue
        fila = db.uno("select cuerpo, creado from busquedas where id=:i", i=r["id"])
        datos = db.de_json(fila["cuerpo"], None)
        if isinstance(datos, dict):
            salida.append((f"busqueda:{r['id']}", r["clave"], datos, fila["creado"]))
    en_tabla = {r["clave"] for r in db.todos(f"select distinct clave from busquedas where {condicion}")}
    for archivo in sorted(config.DIR_RESPALDO.glob("*.json")) if config.DIR_RESPALDO.is_dir() else []:
        if archivo.name.startswith(PREFIJOS) and archivo.name not in en_tabla and f"archivo:{archivo.name}" not in hechos:
            try:
                salida.append((f"archivo:{archivo.name}", archivo.name, json.loads(archivo.read_text()), None))
            except (OSError, ValueError):
                continue
    return salida


def actualizar() -> dict:
    """Extrae a `ofertas_tarifa` lo que aún no esté: las lecturas `listo` de la página y las respuestas del buscador con
    opciones de reserva. Incremental e idempotente: repetirlo no duplica. Sin la tabla de lecturas, las omite."""
    hechos = {"filas": 0, "respuestas": 0, "lecturas": 0}
    if not _existe("ofertas_tarifa"):
        return hechos
    for origen_fila, clave, datos, creado in _respuestas_nuevas(_hechos()):
        filas = _de_respuesta(origen_fila, clave, datos, creado)
        if filas:
            hechos["respuestas"] += 1
            hechos["filas"] += _insertar(filas)
    if _existe("analisis_vuelo"):
        for a in db.todos("""select * from analisis_vuelo a where estado='listo' and not exists
                             (select 1 from ofertas_tarifa o where o.analisis_id=a.id) order by id"""):
            filas = _de_lectura(a)
            if filas:
                hechos["lecturas"] += 1
                hechos["filas"] += _insertar(filas)
    if hechos["filas"]:
        eventos.registrar("ofertas_tarifa", None, "tarifas extraídas",
                          f"{hechos['filas']} tarifas de {hechos['respuestas']} respuestas del buscador y {hechos['lecturas']} lecturas de la página",
                          "extractor")
    return hechos


_ultima: list = [None]
CADA_SEGUNDOS = 600


def actualizar_si_toca() -> dict | None:
    """Para el tablero: como mucho una vez cada 10 minutos por instancia, y nunca rompe la pantalla que lo llama."""
    if _ultima[0] is not None and time.monotonic() - _ultima[0] < CADA_SEGUNDOS:
        return None
    _ultima[0] = time.monotonic()
    try:
        return actualizar()
    except Exception as e:   # el tablero se muestra aunque la extracción falle; el fallo queda en la bitácora
        eventos.registrar("ofertas_tarifa", None, "extracción fallida", f"{type(e).__name__}: {str(e)[:200]}", "extractor")
        return None


# ---------- limpieza al cargar ----------
# La base guarda todo lo visto (trazabilidad); lo que no sirve para entrenar se descarta al leer y se cuenta por motivo,
# para que cada modelo diga con qué datos se hizo y cuántos dejó fuera.
MINIMO_GRUPO_ATIPICOS = 5      # con menos precios en la ruta y la tarifa no se juzga qué es raro
DESVIOS_ATIPICO = 5            # distancia a la mediana, en desviaciones absolutas medianas (escaladas a desviación típica)
ANTICIPACION_MAXIMA = 365


def _mediana(valores: list[float]) -> float:
    v = sorted(valores)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def depurar(filas: list[dict], clave_repetida=("fuente", "origen", "destino", "ida", "regreso", "vuelos", "vendedor", "tarifa"),
            grupo_atipico=("origen", "destino", "tarifa_normalizada")) -> tuple[list[dict], dict]:
    """(filas útiles, informe). Descarta: sin precio, otra moneda, sin ruta o fecha, anticipación imposible, la misma
    tarifa de la misma fuente repetida el mismo día (queda la más reciente) y precios atípicos dentro de su ruta y tipo de tarifa."""
    descartes: dict[str, int] = {}

    def fuera(motivo: str):
        descartes[motivo] = descartes.get(motivo, 0) + 1

    validas = []
    for f in filas:
        try:
            precio = float(f.get("precio")) if f.get("precio") is not None else None
        except (TypeError, ValueError):
            precio = None
        anticipacion = f.get("anticipacion_dias", f.get("anticipacion"))
        if not precio or precio <= 0:
            fuera("sin precio")
        elif (f.get("moneda") or "USD") != "USD":
            fuera("otra moneda")
        elif not (f.get("origen") and f.get("destino") and f.get("ida")):
            fuera("sin ruta o fecha")
        elif anticipacion is not None and not 0 <= anticipacion <= ANTICIPACION_MAXIMA:
            fuera("anticipación imposible")
        else:
            validas.append(f)
    ultimas: dict[tuple, dict] = {}
    for f in sorted(validas, key=lambda x: str(x.get("momento") or x.get("capturado") or "")):
        clave = (*(f.get(c) for c in clave_repetida), str(f.get("momento") or f.get("capturado") or "")[:10])
        if clave in ultimas:
            fuera("repetida el mismo día")
        ultimas[clave] = f
    unicas = list(ultimas.values())
    grupos: dict[tuple, list[float]] = {}
    for f in unicas:
        grupos.setdefault(tuple(f.get(c) for c in grupo_atipico), []).append(float(f["precio"]))
    limites = {}
    for g, precios in grupos.items():
        if len(precios) >= MINIMO_GRUPO_ATIPICOS:
            m = _mediana(precios)
            mad = _mediana([abs(p - m) for p in precios]) * 1.4826 or m * 0.05   # sin dispersión, un 5 % de la mediana
            limites[g] = (m - DESVIOS_ATIPICO * mad, m + DESVIOS_ATIPICO * mad)
    limpias = []
    for f in unicas:
        lim = limites.get(tuple(f.get(c) for c in grupo_atipico))
        if lim and not lim[0] <= float(f["precio"]) <= lim[1]:
            fuera("precio atípico")
        else:
            limpias.append(f)
    return limpias, {"leidas": len(filas), "utiles": len(limpias), "descartes": descartes}


def limpias() -> tuple[list[dict], dict]:
    """Las tarifas vistas listas para entrenar o medir, con el informe de lo descartado. Solo lee."""
    return depurar(db.todos("select * from ofertas_tarifa order by id"))
