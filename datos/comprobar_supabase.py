"""Comprueba la base PostgreSQL (Supabase) sin importar la aplicación, sin sembrar datos y sin migrar.

Uso: python -m datos.comprobar_supabase

Lee `DATABASE_URL` del entorno o de `.env`. Todo es lectura, salvo una tabla TEMPORAL que se escribe, se lee y se
revierte: ninguna tabla del negocio se toca. Informa en JSON:
- conexión, versión del servidor y la prueba de escritura y reversión;
- si están las tablas y columnas que espera esta versión (`envios_soporte`, `gastos.version` obligatoria...);
- las tablas del esquema `public` sin seguridad por filas;
- qué pueden hacer los roles públicos del proveedor (`anon`, `authenticated`) sobre tablas y vistas de `public`.

Nunca imprime la cadena de conexión: si algo falla, solo el tipo de error y su código SQLSTATE.
Sale con 0 si todo está en orden, 1 si la base responde pero algo no está como debe, 2 si falta configuración.
"""
import json
import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

TABLAS = ("usuarios", "sesiones", "viajes", "gastos", "documentos", "eventos", "envios_soporte")
LOCALES = ("127.0.0.1", "localhost", "::1")   # la base de `docker compose` no usa SSL; cualquier otra lo exige
ROLES_PUBLICOS = ("anon", "authenticated")
PRIVILEGIOS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")


def _cadena(entorno: dict) -> str:
    cadena = entorno.get("DATABASE_URL") or ""
    if "[YOUR-PASSWORD]" in cadena:
        cadena = cadena.replace("[YOUR-PASSWORD]", quote(entorno.get("DATABASE_PASSWORD") or "", safe=""))
    return cadena


def _motor(cadena: str):
    """Devuelve (motor, None) o (None, mensaje). Ningún mensaje incluye la cadena."""
    try:
        url = make_url(cadena)
    except Exception:
        return None, "DATABASE_URL no tiene el formato de una cadena de conexión."
    if url.get_backend_name() not in ("postgres", "postgresql"):
        return None, "La comprobación requiere PostgreSQL; SQLite no verifica Supabase."
    query = dict(url.query)
    if url.host not in LOCALES:
        query.setdefault("sslmode", "require")
        if query["sslmode"] not in ("require", "verify-ca", "verify-full"):
            return None, "La conexión a una base remota debe usar SSL (sslmode=require o con verificación de certificado)."
    motor = create_engine(url.set(drivername="postgresql+psycopg", query=query), poolclass=NullPool,
                          connect_args={"connect_timeout": 10, "prepare_threshold": None})
    return motor, None


def _revisar(conexion) -> dict:
    conexion.execute(text("set local statement_timeout = '10s'"))
    version = conexion.execute(text("show server_version")).scalar_one()
    tablas = {t: bool(conexion.execute(text("select to_regclass(:n)"), {"n": f"public.{t}"}).scalar()) for t in TABLAS}
    columnas = {f"gastos.{c}": conexion.execute(text(
        """select is_nullable from information_schema.columns
           where table_schema='public' and table_name='gastos' and column_name=:c"""), {"c": c}).scalar()
        for c in ("version", "motivo_rechazo")}
    sin_rls = conexion.execute(text(
        """select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
           where n.nspname='public' and c.relkind in ('r','p') and not c.relrowsecurity order by c.relname""")).scalars().all()
    roles = conexion.execute(text("select rolname from pg_roles where rolname = any(:r) order by 1"),
                             {"r": list(ROLES_PUBLICOS)}).scalars().all()
    permisos: dict[str, dict[str, list[str]]] = {}
    for fila in conexion.execute(text(
            """select r.rolname rol, c.relname tabla, p.privilegio
               from pg_class c join pg_namespace n on n.oid=c.relnamespace
               cross join pg_roles r cross join unnest(cast(:p as text[])) p(privilegio)
               where n.nspname='public' and c.relkind in ('r','p','v','m') and r.rolname = any(:r)
                 and has_table_privilege(r.oid, c.oid, p.privilegio)
               order by 1, 2, 3"""), {"p": list(PRIVILEGIOS), "r": list(ROLES_PUBLICOS)}):
        permisos.setdefault(fila.rol, {}).setdefault(fila.tabla, []).append(fila.privilegio)
    # Tabla TEMPORARY: ningún INSERT toca tablas del negocio. La reversión deshace toda la prueba.
    conexion.execute(text("create temporary table sonda_comprobacion (importe numeric(14,2)) on commit drop"))
    conexion.execute(text("insert into sonda_comprobacion values (:i)"), {"i": Decimal("12.34")})
    escrita = conexion.execute(text("select importe from sonda_comprobacion")).scalar_one() == Decimal("12.34")
    return {"postgresql": version, "escritura_temporal": "correcta" if escrita else "no coincide", "tablas": tablas,
            "columnas": {c: ("obligatoria" if v == "NO" else "admite vacíos" if v == "YES" else "falta") for c, v in columnas.items()},
            "tablas_sin_seguridad_por_filas": sin_rls, "roles_publicos": roles, "permisos_publicos": permisos}


def main(entorno: dict | None = None) -> int:
    if entorno is None:
        entorno = {**dotenv_values(Path(__file__).resolve().parent.parent / ".env"), **os.environ}
    cadena = _cadena(entorno)
    if not cadena:
        print("Falta DATABASE_URL en el entorno del servidor o en .env. No la publiques ni la pegues en un chat.")
        return 2
    motor, problema = _motor(cadena)
    if problema:
        print(problema)
        return 2
    try:
        with motor.connect() as conexion:
            informe = _revisar(conexion)
            conexion.rollback()
            revertida = conexion.execute(text("select to_regclass('pg_temp.sonda_comprobacion')")).scalar() is None
            conexion.rollback()
        informe = {"conexion": "correcta", **informe, "rollback_verificado": revertida}
        en_orden = (revertida and informe["escritura_temporal"] == "correcta" and all(informe["tablas"].values())
                    and set(informe["columnas"].values()) <= {"obligatoria", "admite vacíos"}
                    and informe["columnas"]["gastos.version"] == "obligatoria"
                    and not informe["tablas_sin_seguridad_por_filas"] and not informe["permisos_publicos"])
        informe["en_orden"] = en_orden
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return 0 if en_orden else 1
    except Exception as error:
        # Los mensajes del controlador pueden incluir la cadena de conexión: solo se informa el tipo y el SQLSTATE
        origen = getattr(error, "orig", error)
        print(json.dumps({"conexion": "no verificada", "tipo": type(error).__name__, "sqlstate": getattr(origen, "sqlstate", None)}))
        return 1
    finally:
        motor.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
