"""Prepara los datos geográficos del buscador de origen y destino.

Uso:
    python -m datos.geografia                    descarga las fuentes a una carpeta temporal y escribe datos/geografia/
    python -m datos.geografia --desde CARPETA    usa archivos ya descargados (airports.csv, countries.csv,
                                                 cities1000.zip, admin1CodesASCII.txt)
    python -m datos.geografia --mini             rehace el subconjunto de pruebas desde datos/geografia/
    python -m datos.geografia --zonas ZIP        añade la zona horaria de GeoNames a datos/geografia/lugares.csv.gz
                                                 desde un cities1000.zip descargado, sin cambiar las demás columnas

Los archivos resultantes se versionan: la demostración y la carga inicial no dependen de internet.
Fuentes: OurAirports (dominio público) y GeoNames (CC BY 4.0). Los nombres de países en español salen del
estándar ICU con `Intl.DisplayNames` de Node.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import subprocess
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.servicios.geografia import normalizar

RAIZ = Path(__file__).resolve().parent
DESTINO = RAIZ / "geografia"
MINI = RAIZ.parent / "tests" / "datos" / "geografia_mini"

DESCARGAS = {
    "airports.csv": "https://davidmegginson.github.io/ourairports-data/airports.csv",
    "countries.csv": "https://davidmegginson.github.io/ourairports-data/countries.csv",
    "cities1000.zip": "https://download.geonames.org/export/dump/cities1000.zip",
    "admin1CodesASCII.txt": "https://download.geonames.org/export/dump/admin1CodesASCII.txt",
}
TIPOS = {"large_airport", "medium_airport", "small_airport"}

# Columnas de cities1000.txt (formato de GeoNames, separado por tabuladores)
G_ID, G_NOMBRE, G_ASCII, G_ALTERNOS, G_LAT, G_LON, G_PAIS, G_ADMIN1, G_POBLACION, G_ZONA = 0, 1, 2, 3, 4, 5, 8, 10, 14, 17


def huella(archivo: Path) -> str:
    return hashlib.sha256(archivo.read_bytes()).hexdigest()


def descargar(carpeta: Path) -> None:
    for nombre, url in DESCARGAS.items():
        print(f"Descargando {url}")
        urllib.request.urlretrieve(url, carpeta / nombre)  # noqa: S310  direcciones fijas de las fuentes


def _nombres_es(codigos: list[str]) -> dict:
    """Nombre en español de cada código de país según ICU. Si Node no está, queda vacío y se usa el inglés."""
    programa = ("const c = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                "const d = new Intl.DisplayNames(['es'], {type: 'region'});"
                "const r = {}; for (const k of c) { try { r[k] = d.of(k); } catch (e) {} }"
                "process.stdout.write(JSON.stringify(r));")
    try:
        salida = subprocess.run(["node", "-e", programa], input=json.dumps(codigos), capture_output=True,  # noqa: S603, S607  programa fijo
                                text=True, check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        print("Aviso: sin Node, los países quedan con su nombre en inglés.")
        return {}
    return {k: v for k, v in json.loads(salida).items() if v and v != k}


def _alternos(nombre: str, ascii_: str, alternos: str) -> str:
    """Texto buscable: nombre, nombre ASCII y alternos en alfabeto latino de 3 a 40 letras, sin repetir."""
    vistos = []
    for n in [nombre, ascii_, *alternos.split(",")]:
        s = normalizar(n)
        if 3 <= len(s) <= 40 and s.isascii() and "http" not in s and s not in vistos:
            vistos.append(s)
    return " | ".join(vistos)


def preparar(origen: Path, destino: Path) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    # Aeropuertos con código IATA y servicio regular: sin pistas privadas, helipuertos ni bases militares
    with open(origen / "airports.csv", encoding="utf-8") as f:
        aeropuertos = [r for r in csv.DictReader(f) if r["iata_code"].strip() and r["scheduled_service"] == "yes"
                       and r["type"] in TIPOS]
    aeropuertos.sort(key=lambda r: r["iata_code"])
    with open(destino / "aeropuertos.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["iata", "nombre", "municipio", "pais", "region", "lat", "lon", "grande"])
        for r in aeropuertos:
            w.writerow([r["iata_code"].strip().upper(), r["name"], r["municipality"], r["iso_country"], r["iso_region"],
                        round(float(r["latitude_deg"]), 5), round(float(r["longitude_deg"]), 5),
                        1 if r["type"] == "large_airport" else 0])

    with open(origen / "countries.csv", encoding="utf-8") as f:
        paises = sorted(((r["code"], r["name"]) for r in csv.DictReader(f)), key=lambda p: p[0])
    es = _nombres_es([c for c, _ in paises])
    with open(destino / "paises.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["codigo", "nombre_es", "nombre_en"])
        for codigo, ingles in paises:
            w.writerow([codigo, es.get(codigo, ingles), ingles])

    with open(origen / "admin1CodesASCII.txt", encoding="utf-8") as f:
        regiones = sorted(linea.rstrip("\n").split("\t")[:2] for linea in f if "\t" in linea)
    with open(destino / "regiones.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["codigo", "nombre"])
        w.writerows(regiones)

    with zipfile.ZipFile(origen / "cities1000.zip") as z, z.open("cities1000.txt") as crudo:
        filas = [linea.rstrip("\n").split("\t") for linea in io.TextIOWrapper(crudo, encoding="utf-8")]
    filas.sort(key=lambda r: int(r[G_ID]))
    buffer = io.StringIO()
    w = csv.writer(buffer)
    w.writerow(["id", "nombre", "buscable", "pais", "region", "lat", "lon", "poblacion", "zona"])
    for r in filas:
        w.writerow([r[G_ID], r[G_NOMBRE], _alternos(r[G_NOMBRE], r[G_ASCII], r[G_ALTERNOS]), r[G_PAIS],
                    f"{r[G_PAIS]}.{r[G_ADMIN1]}" if r[G_ADMIN1] else "", round(float(r[G_LAT]), 5),
                    round(float(r[G_LON]), 5), int(r[G_POBLACION] or 0), r[G_ZONA]])
    # mtime=0: el mismo contenido produce el mismo archivo y la misma huella
    (destino / "lugares.csv.gz").write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), mtime=0))

    conteo = {"aeropuertos": len(aeropuertos), "lugares": len(filas), "paises": len(paises), "regiones": len(regiones)}
    _fuentes(origen, destino, conteo)
    return conteo


def zonas(cities1000: Path, archivo: Path = DESTINO / "lugares.csv.gz") -> int:
    """Añade (o rehace) la columna `zona` (zona horaria IANA de GeoNames) a un lugares.csv.gz ya preparado, por el id de
    cada lugar. Las demás columnas no cambian. Devuelve cuántos lugares quedaron sin zona."""
    with zipfile.ZipFile(cities1000) as z, z.open("cities1000.txt") as crudo:
        zona = {int(r[G_ID]): r[G_ZONA] for r in (linea.rstrip("\n").split("\t") for linea in io.TextIOWrapper(crudo, encoding="utf-8"))}
    with gzip.open(archivo, "rt", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    cabecera = filas[0][:8] + ["zona"]
    cuerpo = [r[:8] + [zona.get(int(r[0]), "")] for r in filas[1:]]
    buffer = io.StringIO()
    csv.writer(buffer).writerows([cabecera] + cuerpo)
    archivo.write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), mtime=0))
    return sum(1 for r in cuerpo if not r[8])


def _fuentes(origen: Path, destino: Path, conteo: dict) -> None:
    hoy = datetime.now(UTC).strftime("%Y-%m-%d")
    lineas = [
        "# Fuentes de los datos geográficos",
        "",
        f"Preparados con `python -m datos.geografia` el {hoy}. Se cargan a la base con la semilla, que registra cada carga en `cargas_datos`.",
        "",
        "- **Aeropuertos y países:** [OurAirports](https://ourairports.com/data/), dominio público. Solo aeropuertos con "
        "código IATA, servicio regular y tipo grande, mediano o pequeño.",
        "- **Lugares y regiones:** [GeoNames](https://www.geonames.org/), licencia "
        "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Ciudades y pueblos de más de 1.000 habitantes "
        "(`cities1000`). Cambios: se conservan nombre, nombres alternativos en alfabeto latino (de 3 a 40 letras), "
        "país, región, coordenadas, población y zona horaria.",
        "- **Nombres de países en español:** estándar ICU, con `Intl.DisplayNames` de Node.",
        "",
        "## Archivos descargados",
        "",
        "| Archivo | URL | Huella SHA-256 |",
        "|---|---|---|",
    ]
    for nombre, url in DESCARGAS.items():
        lineas.append(f"| `{nombre}` | {url} | `{huella(origen / nombre)}` |")
    lineas += ["", "## Archivos preparados", "", "| Archivo | Filas | Huella SHA-256 |", "|---|---|---|"]
    for archivo, clave in (("aeropuertos.csv", "aeropuertos"), ("lugares.csv.gz", "lugares"), ("paises.csv", "paises"),
                           ("regiones.csv", "regiones")):
        lineas.append(f"| `{archivo}` | {conteo[clave]} | `{huella(destino / archivo)}` |")
    (destino / "FUENTES.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


# Subconjunto de pruebas: lo justo para los casos del buscador (homónimos, lugar aislado, país, pueblo sin aeropuerto)
MINI_AEROPUERTOS = {"CNY", "GJT", "SLC", "LIS", "OPO", "FAO", "BOG", "MDE", "MIA", "LAS", "MAD", "BIO", "AMM", "AQJ", "JFK",
                    "SJO", "SJC", "NDJ", "MOB", "PNS", "ELP", "IGU"}
# Moab (Utah), Qīr Moāv y Ar Rabbah (Jordania, con «Moab» entre sus nombres), Three Rivers (Míchigan, alterno «Moab»),
# Lisboa, Oporto, Villa de Leyva, Bogotá, Miami, Las Vegas, San José (Costa Rica y California), Madrid, Nueva York,
# Portugalete y Am Timan (Chad: sin aeropuertos con vuelos regulares a menos de 400 km); para las zonas horarias cerca
# de una frontera horaria: Mobile y Pensacola (hora central), El Paso (montaña) y Foz do Iguaçu (Brasil)
MINI_LUGARES = {5543307, 250624, 250345, 5012194, 2267057, 2735943, 3666003, 3688689, 4164138, 5506956, 3621849, 5392171,
                3117735, 5128581, 3113082, 245338, 4076598, 4168228, 5520993, 3463030}


def mini(completo: Path = DESTINO, destino: Path = MINI) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    with open(completo / "aeropuertos.csv", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    with open(destino / "aeropuertos.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([filas[0]] + [r for r in filas[1:] if r[0] in MINI_AEROPUERTOS])
    with gzip.open(completo / "lugares.csv.gz", "rt", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    elegidos = [r for r in filas[1:] if int(r[0]) in MINI_LUGARES]
    buffer = io.StringIO()
    csv.writer(buffer).writerows([filas[0]] + elegidos)
    (destino / "lugares.csv.gz").write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), mtime=0))
    paises_usados = {r[3] for r in elegidos} | {"TD"}
    regiones_usadas = {r[4] for r in elegidos}
    for archivo, filtro in (("paises.csv", lambda r: r[0] in paises_usados), ("regiones.csv", lambda r: r[0] in regiones_usadas)):
        with open(completo / archivo, encoding="utf-8") as f:
            filas = list(csv.reader(f))
        with open(destino / archivo, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([filas[0]] + [r for r in filas[1:] if filtro(r)])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desde", type=Path, help="carpeta con los archivos ya descargados")
    p.add_argument("--mini", action="store_true", help="rehace el subconjunto de pruebas")
    p.add_argument("--zonas", type=Path, help="cities1000.zip descargado: añade la zona horaria a lugares.csv.gz")
    a = p.parse_args()
    if a.zonas:
        print(f"Lugares sin zona: {zonas(a.zonas)}")
    elif a.mini:
        mini()
        print(f"Subconjunto escrito en {MINI}")
    elif a.desde:
        print(preparar(a.desde, DESTINO))
    else:
        with tempfile.TemporaryDirectory(prefix="geografia_") as tmp:
            descargar(Path(tmp))
            print(preparar(Path(tmp), DESTINO))
