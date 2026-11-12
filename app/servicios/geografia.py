"""Datos geográficos del mundo: aeropuertos con servicio regular, lugares y países.

Los archivos vienen de `datos/geografia/` (preparados con `python -m datos.geografia`) y la semilla los carga.
Cada carga, también la que no cambia nada, queda en `cargas_datos` con la huella del archivo.
"""
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Column, Float, Index, Integer, Text

from .. import config, db
from . import eventos

aeropuertos_mundo = db._tabla(
    "aeropuertos_mundo",  # solo con código IATA y servicio regular; `grande` marca los que suelen tener más vuelos
    Column("iata", Text, unique=True), Column("nombre", Text), Column("municipio", Text), Column("pais", Text),
    Column("region", Text), Column("lat", Float), Column("lon", Float), Column("grande", Integer),
    Column("buscable", Text),  # nombre y municipio normalizados
    Index("ix_aeropuertos_mundo_lat", "lat"),
)
lugares = db._tabla(
    "lugares",  # ciudades y pueblos de más de 1.000 habitantes; `id` es el de GeoNames
    Column("nombre", Text), Column("buscable", Text), Column("pais", Text), Column("region", Text),
    Column("lat", Float), Column("lon", Float), Column("poblacion", Integer),
    # Sin índice por población a propósito: con él, ordenar las coincidencias obliga a recorrer toda la tabla por saltos
    Index("ix_lugares_buscable", "buscable"),
)
paises = db._tabla(
    "paises",
    Column("codigo", Text, unique=True), Column("nombre_es", Text), Column("nombre_en", Text),
)
aeropuertos_google = db._tabla(
    "aeropuertos_google",  # aeropuertos que solo conoce el autocompletado de Google: se pueden elegir aunque no estén en los datos locales
    Column("iata", Text, unique=True), Column("nombre", Text), Column("ciudad", Text), Column("kgmid", Text),
    Column("consulta", Text), Column("visto", Text),
)
cargas_datos = db._tabla(
    "cargas_datos",  # una fila por archivo en cada carga, también si no cambió nada: de dónde salió cada dato de referencia
    Column("fuente", Text), Column("archivo", Text), Column("url", Text), Column("huella", Text),
    Column("filas", Integer), Column("resultado", Text), Column("momento", Text), Column("quien", Text),
)

DIRECTORIO = config.RAIZ / "datos" / "geografia"

OURAIRPORTS = "https://davidmegginson.github.io/ourairports-data/"
GEONAMES = "https://download.geonames.org/export/dump/"
# archivo: (fuente, url de origen)
URLS = {
    "aeropuertos.csv": ("OurAirports (dominio público)", OURAIRPORTS + "airports.csv"),
    "paises.csv": ("OurAirports (dominio público) y nombres ICU", OURAIRPORTS + "countries.csv"),
    "regiones.csv": ("GeoNames (CC BY 4.0)", GEONAMES + "admin1CodesASCII.txt"),
    "lugares.csv.gz": ("GeoNames (CC BY 4.0)", GEONAMES + "cities1000.zip"),
}


def directorio() -> Path:
    """Carpeta de los archivos a cargar. Las pruebas apuntan a un subconjunto pequeño con GEOGRAFIA_DIR."""
    return Path(os.getenv("GEOGRAFIA_DIR") or DIRECTORIO)


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, signos como espacios y espacios simples: «São Paulo» y «sao  paulo» coinciden."""
    sin = unicodedata.normalize("NFKD", (texto or "").lower())
    sin = "".join(c for c in sin if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w]+", " ", sin).replace("_", " ").split())


def _leer(archivo: Path) -> list[dict]:
    datos = archivo.read_bytes()
    texto = gzip.decompress(datos).decode("utf-8") if archivo.suffix == ".gz" else datos.decode("utf-8")
    return list(csv.DictReader(io.StringIO(texto)))


def _huella(archivo: Path) -> str:
    return hashlib.sha256(archivo.read_bytes()).hexdigest()


def _ultima_carga(archivo: str) -> tuple | None:
    """Huella y filas de la última carga efectiva del archivo."""
    fila = db.uno("select huella, filas from cargas_datos where archivo=:a and resultado='cargada' order by id desc limit 1", a=archivo)
    return (fila["huella"], fila["filas"]) if fila else None


def _registrar(archivo: str, huella: str, filas: int, resultado: str, quien: str):
    fuente, url = URLS.get(archivo, ("desconocida", ""))
    db.insertar("cargas_datos", fuente=fuente, archivo=archivo, url=url, huella=huella, filas=filas,
                resultado=resultado, momento=db.ahora(), quien=quien)


def _reemplazar(tabla: str, filas: list[dict]):
    db.ejecutar(f"delete from {tabla}")  # noqa: S608  nombre de tabla fijo, no viene de fuera
    for i in range(0, len(filas), 5000):   # por lotes: la carga completa de lugares cabe en segundos
        db.insertar_varios(tabla, filas[i:i + 5000])


def _aeropuertos(directorio_: Path) -> list[dict]:
    return [{"iata": r["iata"], "nombre": r["nombre"], "municipio": r["municipio"], "pais": r["pais"], "region": r["region"],
             "lat": float(r["lat"]), "lon": float(r["lon"]), "grande": int(r["grande"]),
             "buscable": normalizar(f"{r['nombre']} | {r['municipio']}")} for r in _leer(directorio_ / "aeropuertos.csv")]


def _lugares(directorio_: Path) -> list[dict]:
    regiones = {r["codigo"]: r["nombre"] for r in _leer(directorio_ / "regiones.csv")}
    return [{"id": int(r["id"]), "nombre": r["nombre"], "buscable": r["buscable"], "pais": r["pais"],
             "region": regiones.get(r["region"], ""), "lat": float(r["lat"]), "lon": float(r["lon"]),
             "poblacion": int(r["poblacion"] or 0)} for r in _leer(directorio_ / "lugares.csv.gz")]


def _paises(directorio_: Path) -> list[dict]:
    return [{"codigo": r["codigo"], "nombre_es": r["nombre_es"], "nombre_en": r["nombre_en"]}
            for r in _leer(directorio_ / "paises.csv")]


# tabla: (archivo principal, archivos de los que depende, lector)
CONJUNTOS = {
    "aeropuertos": ("aeropuertos_mundo", "aeropuertos.csv", (), _aeropuertos),
    "lugares": ("lugares", "lugares.csv.gz", ("regiones.csv",), _lugares),
    "paises": ("paises", "paises.csv", (), _paises),
}


def cargar(directorio_: Path | None = None, quien: str = "semilla") -> dict:
    """Carga los archivos a la base. Un archivo con la misma huella y el mismo número de filas no se vuelve a cargar,
    pero su carga queda registrada con el resultado «sin cambios». Devuelve las filas de cada tabla."""
    directorio_ = Path(directorio_ or directorio())
    if not (directorio_ / "aeropuertos.csv").is_file():
        return {}
    conteo, cambios = {}, []
    for clave, (tabla, archivo, dependencias, lector) in CONJUNTOS.items():
        huellas = {a: _huella(directorio_ / a) for a in (archivo, *dependencias)}
        presentes = db.uno(f"select count(*) n from {tabla}")["n"]  # noqa: S608  nombre de tabla fijo
        previas = {a: _ultima_carga(a) for a in huellas}
        sin_cambios = (presentes and previas[archivo] == (huellas[archivo], presentes)
                       and all(previas[d] and previas[d][0] == huellas[d] for d in dependencias))
        if sin_cambios:
            conteo[clave] = presentes
            for a, h in huellas.items():
                _registrar(a, h, previas[a][1], "sin cambios", quien)
            continue
        filas = lector(directorio_)
        _reemplazar(tabla, filas)
        conteo[clave] = len(filas)
        cambios.append(f"{len(filas)} {clave}")
        _registrar(archivo, huellas[archivo], len(filas), "cargada", quien)
        for d in dependencias:
            _registrar(d, huellas[d], len(_leer(directorio_ / d)), "cargada", quien)
    _memoria.clear()
    eventos.registrar("datos de referencia", None, "datos de referencia cargados",
                      ", ".join(cambios) if cambios else "sin cambios", f"{directorio_.name} · {quien}")
    return conteo


# ---------- búsqueda ----------
_memoria: dict = {}   # aeropuertos y países en memoria del proceso: son pocos y casi no cambian


def _en_memoria(clave: str, cargar_):
    guardado = _memoria.get(clave)
    if guardado and time.monotonic() - guardado[0] < 600:
        return guardado[1]
    valor = cargar_()
    _memoria[clave] = (time.monotonic(), valor)
    return valor


def _aeropuertos_por_latitud() -> tuple[list[float], list[dict]]:
    def cargar_():
        filas = sorted(db.todos("select iata, nombre, municipio, pais, lat, lon, grande, buscable from aeropuertos_mundo"),
                       key=lambda a: a["lat"])
        return [a["lat"] for a in filas], filas
    return _en_memoria("aeropuertos", cargar_)


def aeropuerto(iata: str | None) -> dict | None:
    """Un aeropuerto de los datos locales por su código (con coordenadas), o None."""
    if not iata:
        return None
    indice = _en_memoria("aeropuertos_por_codigo", lambda: {a["iata"]: a for a in _aeropuertos_por_latitud()[1]})
    return indice.get(iata.upper())


def _nombres_pais() -> dict:
    return _en_memoria("paises", lambda: {p["codigo"]: p for p in db.todos("select * from paises")})


def _regla(clave: str, defecto: float) -> float:
    from . import costo
    return costo.supuesto(costo.catalogo(), clave, defecto)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta sobre la Tierra (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(min(h, 1.0)))


def cercanos(lat: float, lon: float, radio_km: float | None = None, maximo: int | None = None) -> list[dict]:
    """Aeropuertos con servicio regular a menos del radio, del más cercano al más lejano."""
    radio = radio_km if radio_km is not None else _regla("radio_aeropuertos_km", 400)
    maximo = maximo if maximo is not None else int(_regla("maximo_aeropuertos", 4))
    lats, filas = _aeropuertos_por_latitud()
    # Recuadro primero (barato), distancia exacta después
    margen_lat = radio / 111.0
    margen_lon = radio / max(111.32 * math.cos(math.radians(lat)), 1.0)
    candidatos = []
    for a in filas[bisect.bisect_left(lats, lat - margen_lat):bisect.bisect_right(lats, lat + margen_lat)]:
        if abs((a["lon"] - lon + 540) % 360 - 180) > margen_lon:
            continue
        km = distancia_km(lat, lon, a["lat"], a["lon"])
        if km <= radio:
            candidatos.append({"iata": a["iata"], "nombre": a["nombre"], "municipio": a["municipio"], "km": round(km, 1),
                               "grande": a["grande"]})
    return sorted(candidatos, key=lambda a: a["km"])[:maximo]


def carretera() -> dict:
    """Reglas para estimar el traslado por carretera: distancia = línea recta x factor; tiempo = distancia ÷ velocidad."""
    return {"factor": _regla("factor_carretera", 1.3), "velocidad_kmh": _regla("velocidad_carretera_kmh", 70) or 70}


def _con_horas(aeropuertos: list[dict]) -> list[dict]:
    """Tiempo estimado por carretera: línea recta x factor ÷ velocidad (reglas editables)."""
    factor, velocidad = carretera().values()
    return [{**a, "horas": round(a["km"] * factor / velocidad, 1) if a.get("km") is not None else None} for a in aeropuertos]


def _aviso_sin_aeropuertos() -> str:
    return (f"Sin aeropuertos con vuelos regulares a menos de {_regla('radio_aeropuertos_km', 400):g} km. "
            "Busca un aeropuerto por nombre o código.")


def _empieza_palabra(texto: str, q: str) -> bool:
    return texto.startswith(q) or f" {q}" in texto


def _coincidencia(nombre: str, buscable: str, q: str) -> tuple[int, str | None]:
    """Qué tan bien coincide un lugar: 0 nombre exacto, 1 nombre alterno exacto, 2 inicio de palabra del nombre,
    3 inicio de palabra de un alterno. Con un alterno, devuelve cuál («Lisbon» coincide con «lisboa»)."""
    nombre = normalizar(nombre)
    if nombre == q:
        return 0, None
    alternos = buscable.split(" | ")
    if q in alternos:
        return 1, q
    if _empieza_palabra(nombre, q):
        return 2, None
    return 3, next((n for n in alternos if _empieza_palabra(n, q)), None)


def _resultado_aeropuerto(a: dict, paises_: dict) -> dict:
    return {"tipo": "aeropuerto", "id": a["iata"], "nombre": a["nombre"], "region": a["municipio"],
            "pais": paises_.get(a["pais"], {}).get("nombre_es", a["pais"]), "lat": a["lat"], "lon": a["lon"],
            "aeropuertos": _con_horas([{"iata": a["iata"], "nombre": a["nombre"], "municipio": a["municipio"], "km": 0.0,
                                        "grande": a["grande"]}]), "aviso": None, "origen": "local"}


def _locales(q: str, limite: int) -> list[dict]:
    """Sugerencias de los datos locales, en el orden del diseño: código exacto, lugares con aeropuerto, países, el resto.
    Entre lugares pesa primero cuánto coincide el nombre y después la población."""
    paises_ = _nombres_pais()
    _, aeropuertos = _aeropuertos_por_latitud()
    candidatos = []   # (orden, desempate, resultado)
    if re.fullmatch(r"[a-z]{3}", q):
        for a in aeropuertos:
            if a["iata"] == q.upper():
                candidatos.append((0, 0, _resultado_aeropuerto(a, paises_)))
    for p in paises_.values():
        nombres = (normalizar(p["nombre_es"]), normalizar(p["nombre_en"]))
        if q in nombres or any(_empieza_palabra(n, q) for n in nombres):
            grandes = sorted((a for a in aeropuertos if a["pais"] == p["codigo"] and a["grande"]), key=lambda a: a["iata"])[:6]
            candidatos.append((1 if q in nombres else 6, 0, {
                "tipo": "pais", "id": p["codigo"], "nombre": p["nombre_es"], "region": "", "pais": p["nombre_es"],
                "lat": None, "lon": None, "aviso": None if grandes else "Este país no tiene aeropuertos grandes en los datos.",
                "aeropuertos": [{"iata": a["iata"], "nombre": a["nombre"], "municipio": a["municipio"], "km": None,
                                 "grande": 1, "horas": None} for a in grandes], "origen": "local"}))
    filas = db.todos("""select id, nombre, buscable, pais, region, lat, lon, poblacion from lugares
                        where buscable like :prefijo or buscable like :palabra
                        order by poblacion desc limit 40""", prefijo=f"{q}%", palabra=f"% {q}%")
    for f in filas:
        nivel, tambien = _coincidencia(f["nombre"], f["buscable"], q)
        cerca = cercanos(f["lat"], f["lon"])
        # Un nombre alterno exacto compite con el nombre exacto, pero con un décimo de la población:
        # «londres» da Londres y Londres de Argentina; «moab», Moab (Utah) antes que un pueblo que alguna vez se llamó así
        grupo, poblacion = max(nivel - 1, 0), (f["poblacion"] or 0) / (10 if nivel == 1 else 1)
        candidatos.append((2 + grupo if cerca else 8 + grupo, -poblacion, {
            "tipo": "lugar", "id": f["id"], "nombre": f["nombre"], "region": f["region"] or "",
            "pais": paises_.get(f["pais"], {}).get("nombre_es", f["pais"]), "lat": f["lat"], "lon": f["lon"],
            "poblacion": f["poblacion"], "tambien": tambien, "aeropuertos": _con_horas(cerca),
            "aviso": None if cerca else _aviso_sin_aeropuertos(), "origen": "local"}))
    if len(q) >= 3:
        for a in aeropuertos:
            if a["iata"] != q.upper() and _empieza_palabra(a["buscable"], q):
                candidatos.append((7, 0, _resultado_aeropuerto(a, paises_)))
    candidatos.sort(key=lambda c: (c[0], c[1]))
    return [c[2] for c in candidatos[:limite]]


def aeropuertos_conocidos(codigos: list[str]) -> dict:
    """Los códigos que existen en los datos locales o que trajo el autocompletado de Google, con lo que se sabe de cada uno."""
    if not codigos:
        return {}
    marcas = {f"c{i}": c for i, c in enumerate(codigos)}
    en = ", ".join(f":{k}" for k in marcas)
    conocidos = {a["iata"]: a for a in db.todos(f"select iata, nombre, municipio, lat, lon from aeropuertos_mundo where iata in ({en})", **marcas)}  # noqa: S608
    for a in db.todos(f"select iata, nombre, ciudad from aeropuertos_google where iata in ({en})", **marcas):  # noqa: S608
        conocidos.setdefault(a["iata"], {"iata": a["iata"], "nombre": a["nombre"], "municipio": a["ciudad"], "lat": None, "lon": None})
    return conocidos


# ---------- autocompletado de Google, combinado con lo local ----------
def proveedor() -> str:
    """`local+google` (por defecto) o `local`, que apaga por completo las consultas de lugares a Google."""
    return (os.getenv("PROVEEDOR_LUGARES") or "local+google").strip().lower()


def _tope_alcanzado(usuario: dict | None) -> bool:
    gastadas = "tipo='autocompletado' and origen in ('en vivo', 'fallida')"
    mes = datetime.now(UTC).strftime("%Y-%m-01")
    if db.uno(f"select count(*) n from consultas_buscador where {gastadas} and momento>=:m", m=mes)["n"] >= _regla("tope_autocompletado_mes", 60):  # noqa: S608
        return True
    if usuario and usuario.get("id"):
        hoy = datetime.now(UTC).strftime("%Y-%m-%d")
        n = db.uno(f"select count(*) n from consultas_buscador where {gastadas} and momento>=:h and usuario_id=:u", h=hoy, u=usuario["id"])["n"]  # noqa: S608
        return n >= _regla("tope_autocompletado_persona_dia", 15)
    return False


def _km_de(distancia: str | None) -> int | None:
    m = re.match(r"\s*([\d.]+)\s*(mi|km)", distancia or "")
    if not m:
        return None
    return round(float(m.group(1)) * (1.609344 if m.group(2) == "mi" else 1))


def _anotar_aeropuertos_nuevos(datos: dict, q: str):
    """Un aeropuerto que solo trae Google queda registrado para poder elegirlo y validarlo al cotizar."""
    conocidos = {a["iata"] for a in _aeropuertos_por_latitud()[1]}
    for s in datos.get("suggestions", []):
        for a in s.get("airports") or []:
            iata = (a.get("id") or "").upper()
            if not re.fullmatch(r"[A-Z]{3}", iata) or iata in conocidos or db.uno("select id from aeropuertos_google where iata=:i", i=iata):
                continue
            db.insertar("aeropuertos_google", iata=iata, nombre=a.get("name"), ciudad=a.get("city"), kgmid=a.get("city_id"),
                        consulta=q, visto=db.ahora())
            eventos.registrar("aeropuerto", None, "aeropuerto conocido por Google", f"{iata} {a.get('name') or ''} ({a.get('city') or ''})",
                              "SerpApi (autocompletado)")


def _de_google(datos: dict) -> list[dict]:
    resultados = []
    for s in datos.get("suggestions", []):
        if s.get("type") != "city" or not s.get("airports"):
            continue   # las regiones y países ya los cubren los datos locales
        resultados.append({
            "tipo": "lugar", "id": s.get("id"), "nombre": s.get("name"), "region": s.get("description") or "", "pais": "",
            "lat": None, "lon": None, "tambien": None, "aviso": None, "origen": "google",
            "aeropuertos": [{"iata": (a.get("id") or "").upper(), "nombre": a.get("name"), "municipio": a.get("city"),
                             "km": _km_de(a.get("distance")), "grande": 0, "horas": None} for a in s["airports"]]})
    return resultados


def _google(q: str, usuario: dict | None) -> tuple[list[dict], str | None]:
    """Sugerencias de Google para el texto ya normalizado y, si no se pudo consultar, el aviso para el pie de la lista."""
    from . import precios
    if "google" not in proveedor() or len(q) < 3:
        return [], None
    clave = "autocompletado_" + q.replace(" ", "-")
    guardada = db.uno("select cuerpo from busquedas where clave=:c order by id desc limit 1", c=clave)
    if guardada:   # el mismo texto no se paga dos veces
        return _de_google(json.loads(guardada["cuerpo"])), None
    if not config.SERPAPI_KEY:
        return [], "Sin clave del buscador: solo sugerencias de los datos locales."
    if _tope_alcanzado(usuario):
        return [], "Se alcanzó el tope de sugerencias de Google de hoy o del mes: solo datos locales."
    inicio = time.perf_counter()
    try:   # solo sale el texto escrito en el campo, nunca datos de la persona
        datos = precios._consultar({"engine": "google_flights_autocomplete", "q": q}, "lugares", None, f"autocompletado «{q}»")
    except Exception as e:
        precios._anotar("autocompletado", clave, "fallida", None, inicio, error=e)
        return [], "Google no respondió: solo sugerencias de los datos locales."
    db.insertar("busquedas", clave=clave, cuerpo=json.dumps(datos, ensure_ascii=False), creado=db.ahora())
    precios._anotar("autocompletado", clave, "en vivo", None, inicio)
    _anotar_aeropuertos_nuevos(datos, q)
    return _de_google(datos), None


def sugerencias_google(q: str, usuario: dict | None = None) -> list[dict]:
    return _google(normalizar(q), usuario)[0]


def buscar_con_aviso(q: str, limite: int = 8, usuario: dict | None = None, google: bool = False) -> tuple[list[dict], str | None]:
    q = normalizar(q)
    if len(q) < 2:
        return [], None
    locales = _locales(q, limite)
    if not google:
        return locales, None
    externos, aviso = _google(q, usuario)
    vistos = {a["iata"] for r in locales for a in r["aeropuertos"]}
    # Lo que la lista local ya muestra no se repite
    nuevos = [r for r in externos if not {a["iata"] for a in r["aeropuertos"]} <= vistos]
    return locales + nuevos, aviso


def buscar(q: str, limite: int = 8, usuario: dict | None = None, google: bool = False) -> list[dict]:
    """Lugares, aeropuertos y países que coinciden con el texto. Con `google`, suma las sugerencias de Google."""
    return buscar_con_aviso(q, limite, usuario, google)[0]
