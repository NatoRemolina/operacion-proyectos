"""Respaldo de la base y de los soportes, y ensayo de su restauración.

    python -m datos.respaldar respaldar --env .env.supabase-publicada [--destino CARPETA]
    python -m datos.respaldar verificar --respaldo CARPETA --env .env.supabase-pruebas --base restauracion_AAAAMMDD
    python -m datos.respaldar vuelta-atras --respaldo CARPETA > vuelta_atras.sql

`respaldar` no escribe nada en la base de origen: `pg_dump` solo lee y los conteos van en una sesión de
solo lectura. Copia el esquema `public` (estructura y datos, formato restaurable y estructura legible), descarga
los archivos del bucket de soportes con la clave de servicio y deja un `manifiesto.json` con los conteos de
filas y la huella SHA-256 de cada archivo. Nunca imprime la conexión ni las claves.

`verificar` restaura la copia en una base NUEVA (`--base`) del destino indicado y compara fila por fila los
conteos con el manifiesto. Se niega a restaurar sobre el mismo servidor y usuario de los que salió la copia
y sobre la base `postgres`: el ensayo nunca toca ni la base publicada ni la principal del proyecto de pruebas.

`vuelta-atras` escribe el SQL que deja una base migrada lista para restaurar encima la copia (docs/respaldo.md):
borra las vistas del código y las tablas que esta versión añadió y la copia no trae, con lo que depende de ellas.
Sin eso, `pg_restore --clean` no puede borrar las tablas de antes, porque las nuevas apuntan a ellas.

`pg_dump` y `pg_restore` corren en Docker (`postgres:17`, la versión del servidor), sin instalar nada.
El archivo de entorno lleva DATABASE_URL (puede traer [YOUR-PASSWORD] con DATABASE_PASSWORD aparte) y,
para los soportes, SUPABASE_URL y SUPABASE_SERVICE_KEY. Los respaldos contienen datos personales: se guardan
fuera del repositorio y cifrados (ver docs/respaldo.md).
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import httpx
import psycopg
from dotenv import dotenv_values

IMAGEN = "postgres:17"
DIR_RESPALDOS = Path.home() / "Respaldos" / "operacion-proyectos"   # fuera del repositorio: los respaldos llevan datos personales
ESQUEMA = "public"


def _entorno(archivo: str) -> dict:
    v = {k: (x or "") for k, x in dotenv_values(archivo).items()}
    url = v.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
    if "[YOUR-PASSWORD]" in url:
        url = url.replace("[YOUR-PASSWORD]", quote(v.get("DATABASE_PASSWORD", ""), safe=""))
    if not url.startswith("postgres"):
        sys.exit(f"{archivo}: falta DATABASE_URL de PostgreSQL")
    return {"url": url, "supabase_url": v.get("SUPABASE_URL", "").rstrip("/"),
            "clave_servicio": v.get("SUPABASE_SERVICE_KEY", ""), "bucket": v.get("SUPABASE_BUCKET") or "soportes"}


def _partes(url: str, base: str | None = None) -> dict:
    p = urlsplit(url)
    return {"host": p.hostname or "", "puerto": str(p.port or 5432), "usuario": unquote(p.username or ""),
            "clave": unquote(p.password or ""), "base": base or p.path.lstrip("/") or "postgres"}


def identidad(url: str) -> str:
    """Huella del servidor y el usuario, sin la contraseña: permite reconocer el origen sin guardarlo."""
    p = _partes(url)
    return hashlib.sha256(f"{p['host']}|{p['puerto']}|{p['usuario']}".encode()).hexdigest()[:16]


def _conectar(url: str, base: str | None = None, solo_lectura: bool = False):
    p = _partes(url, base)
    local = p["host"] in ("127.0.0.1", "localhost")
    c = psycopg.connect(host=p["host"], port=p["puerto"], user=p["usuario"], password=p["clave"], dbname=p["base"],
                        sslmode="prefer" if local else "require", connect_timeout=20, autocommit=True)
    if solo_lectura:
        # El agrupador de Supabase ignora las opciones de arranque: la sesión se pone en solo lectura con una orden
        # explícita y se comprueba; si no queda así, no se sigue.
        c.execute("set session characteristics as transaction read only")
        if c.execute("show transaction_read_only").fetchone()[0] != "on":
            c.close()
            sys.exit("No se pudo poner la sesión en solo lectura: no se sigue")
    return c


def conteos(url: str, base: str | None = None) -> dict:
    with _conectar(url, base, solo_lectura=True) as c:
        tablas = [r[0] for r in c.execute(
            "select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname=%s and c.relkind='r' order by 1", (ESQUEMA,)).fetchall()]
        return {t: c.execute(f'select count(*) from {ESQUEMA}."{t}"').fetchone()[0] for t in tablas}


def _docker(p: dict, argumentos: list[str], salida=None, entrada=None) -> None:
    """Ejecuta una herramienta de PostgreSQL en Docker; la conexión viaja en variables, nunca en la línea."""
    host = "host.docker.internal" if p["host"] in ("127.0.0.1", "localhost") else p["host"]
    variables = {"PGHOST": host, "PGPORT": p["puerto"], "PGUSER": p["usuario"], "PGPASSWORD": p["clave"],
                 "PGDATABASE": p["base"], "PGSSLMODE": "prefer" if host == "host.docker.internal" else "require"}
    cmd = ["docker", "run", "--rm", "-i"] + [x for k in variables for x in ("-e", k)] + [IMAGEN] + argumentos
    r = subprocess.run(cmd, env={**dict(os.environ), **variables}, stdout=salida or subprocess.PIPE,  # noqa: S603
                       stdin=entrada, stderr=subprocess.PIPE, check=False)
    if r.returncode:
        error = r.stderr.decode(errors="replace").replace(p["clave"], "<oculta>") if p["clave"] else r.stderr.decode()
        sys.exit(f"{argumentos[0]} falló: {error.strip().splitlines()[-1] if error.strip() else r.returncode}")


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def respaldar(archivo_env: str, destino: str | None) -> Path:
    e = _entorno(archivo_env)
    p = _partes(e["url"])
    momento = datetime.now(UTC)
    carpeta = Path(destino or DIR_RESPALDOS / momento.strftime("%Y-%m-%d_%H%M")).expanduser()
    carpeta.mkdir(parents=True, exist_ok=False)
    print(f"Respaldo en {carpeta}")

    filas = conteos(e["url"])
    print(f"  {len(filas)} tablas, {sum(filas.values())} filas (antes de copiar)")
    with open(carpeta / "base.dump", "wb") as f:
        _docker(p, ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", f"--schema={ESQUEMA}"], f)
    with open(carpeta / "estructura.sql", "wb") as f:
        _docker(p, ["pg_dump", "--schema-only", "--no-owner", "--no-privileges", f"--schema={ESQUEMA}"], f)
    print("  base.dump y estructura.sql listos")

    soportes = []
    if e["supabase_url"] and e["clave_servicio"]:
        cab = {"Authorization": f"Bearer {e['clave_servicio']}", "apikey": e["clave_servicio"]}
        with _conectar(e["url"], solo_lectura=True) as c:
            nombres = [r[0] for r in c.execute("select name from storage.objects where bucket_id=%s order by name",
                                               (e["bucket"],)).fetchall()]
        for nombre in nombres:
            r = httpx.get(f"{e['supabase_url']}/storage/v1/object/{e['bucket']}/{nombre}", headers=cab, timeout=60)
            if r.status_code != 200:
                sys.exit(f"No se pudo descargar un soporte ({r.status_code}): {nombre}")
            ruta = carpeta / "soportes" / nombre
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(r.content)
            soportes.append(nombre)
        print(f"  {len(soportes)} soportes descargados del bucket {e['bucket']}")
    else:
        print("  Sin SUPABASE_URL y SUPABASE_SERVICE_KEY: no se copian soportes")

    archivos = {str(x.relative_to(carpeta)): {"bytes": x.stat().st_size, "sha256": _sha(x)}
                for x in sorted(carpeta.rglob("*")) if x.is_file()}
    manifiesto = {"momento": momento.isoformat(timespec="seconds"), "origen": identidad(e["url"]),
                  "esquema": ESQUEMA, "herramienta": IMAGEN, "filas": filas, "soportes": len(soportes),
                  "archivos": archivos}
    (carpeta / "manifiesto.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1))
    print("  manifiesto.json con conteos y huellas. Cifra la carpeta antes de moverla (docs/respaldo.md).")
    return carpeta


def _manifiesto(carpeta: Path) -> dict:
    """El manifiesto de una copia, después de comprobar la huella de cada archivo."""
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text())
    for nombre, datos in manifiesto["archivos"].items():
        if _sha(carpeta / nombre) != datos["sha256"]:
            sys.exit(f"La huella de {nombre} no coincide: el respaldo está alterado o incompleto")
    return manifiesto


def _tablas_del_codigo() -> set[str]:
    """Las tablas que declara esta versión: las de app/db.py y las que cada servicio declara al importarse."""
    import importlib
    import pkgutil

    from app import db, servicios
    for m in pkgutil.iter_modules(servicios.__path__):
        importlib.import_module(f"{servicios.__name__}.{m.name}")
    return set(db.TABLAS)


def vuelta_atras(carpeta: str | Path) -> str:
    """SQL para correr antes de restaurar la copia sobre una base ya migrada. La lista sale del código y del manifiesto,
    no se escribe a mano: cada tabla nueva que se declare queda incluida sola."""
    from datos.semilla import VISTAS
    manifiesto = _manifiesto(Path(carpeta).expanduser())
    sobran = sorted(_tablas_del_codigo() - set(manifiesto["filas"]))
    lineas = [f'drop view if exists {ESQUEMA}."{v}" cascade;' for v in sorted(VISTAS)]   # la copia trae las suyas
    lineas += [f'drop table if exists {ESQUEMA}."{t}" cascade;' for t in sobran]
    return "\n".join(lineas) + "\n"


def verificar(carpeta: str, archivo_env: str, base: str) -> bool:
    carpeta = Path(carpeta).expanduser()
    manifiesto = _manifiesto(carpeta)
    e = _entorno(archivo_env)
    if identidad(e["url"]) == manifiesto["origen"]:
        sys.exit("El destino es el mismo servidor del que salió la copia: el ensayo se hace en otro proyecto")
    if base in ("postgres", "template0", "template1") or not base.replace("_", "").isalnum():
        sys.exit("Indica una base nueva y aparte para el ensayo (letras, números y _), no la principal")
    with _conectar(e["url"]) as c:
        if c.execute("select 1 from pg_database where datname=%s", (base,)).fetchone():
            sys.exit(f"La base {base} ya existe: usa otro nombre para no pisar nada")
        c.execute(f'create database "{base}"')
    # Una base nueva ya trae el esquema public vacío; la copia lo crea con su dueño original
    with _conectar(e["url"], base) as c:
        c.execute(f"drop schema {ESQUEMA}")
    p = _partes(e["url"], base)
    with open(carpeta / "base.dump", "rb") as f:
        _docker(p, ["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "-d", base], entrada=f)
    restaurado = conteos(e["url"], base)
    diferencias = {t: (n, restaurado.get(t)) for t, n in manifiesto["filas"].items() if restaurado.get(t) != n}
    print(f"Restaurado en la base {base}: {len(restaurado)} tablas, {sum(restaurado.values())} filas")
    if diferencias:
        for t, (antes, ahora) in diferencias.items():
            print(f"  DIFERENCIA {t}: respaldo {antes}, restaurado {ahora}")
        return False
    print("  Todas las tablas coinciden con el manifiesto. Las huellas de los archivos también.")
    return True


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = a.add_subparsers(dest="orden", required=True)
    r = sub.add_parser("respaldar")
    r.add_argument("--env", default=".env.supabase-publicada")
    r.add_argument("--destino")
    v = sub.add_parser("verificar")
    v.add_argument("--respaldo", required=True)
    v.add_argument("--env", default=".env.supabase-pruebas")
    v.add_argument("--base", required=True)
    b = sub.add_parser("vuelta-atras")
    b.add_argument("--respaldo", required=True)
    x = a.parse_args(argv)
    if x.orden == "respaldar":
        respaldar(x.env, x.destino)
        return 0
    if x.orden == "vuelta-atras":
        print(vuelta_atras(x.respaldo), end="")
        return 0
    return 0 if verificar(x.respaldo, x.env, x.base) else 1


if __name__ == "__main__":
    sys.exit(main())
