"""Datos geográficos del mundo: aeropuertos con servicio regular, lugares y países.

Los archivos vienen de `datos/geografia/` (preparados con `python -m datos.geografia`) y la semilla los carga.
Cada carga, también la que no cambia nada, queda en `cargas_datos` con la huella del archivo.
"""
import csv
import gzip
import hashlib
import io
import os
import re
import unicodedata
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
    Index("ix_lugares_buscable", "buscable"), Index("ix_lugares_poblacion", "poblacion"),
)
paises = db._tabla(
    "paises",
    Column("codigo", Text, unique=True), Column("nombre_es", Text), Column("nombre_en", Text),
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
    _cache_aeropuertos.clear()
    eventos.registrar("datos de referencia", None, "datos de referencia cargados",
                      ", ".join(cambios) if cambios else "sin cambios", f"{directorio_.name} · {quien}")
    return conteo


_cache_aeropuertos: dict = {}
