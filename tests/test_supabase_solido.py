"""Supabase sólido (A11): la migración en PostgreSQL es una sola transacción que revierte entera, lo que se cree después
no hereda permisos para los roles públicos, las vistas analíticas corren con los permisos de quien consulta y se crean y
protegen a la vez, la conexión fuera de local va cifrada y `comprobar_supabase` revisa también las tablas de hoy."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, Table, inspect
from sqlalchemy.exc import DBAPIError

from app import config, db

RAIZ = Path(__file__).resolve().parents[1]
ROLES = ("anon", "authenticated")
SOLO_PG = pytest.mark.skipif(config.ES_SQLITE, reason="transacción de DDL, roles y permisos: solo PostgreSQL")
TABLAS_DE_HOY = ("compras", "capturas", "ofertas_tarifa", "ofertas_origenes", "claves_servicio", "avisos_salientes")


@pytest.fixture
def roles_publicos():
    """Los roles públicos de Supabase. En un PostgreSQL desechable se crean para la prueba y al final se quitan con
    todo lo que se les haya concedido (también los privilegios por omisión)."""
    creados = [r for r in ROLES if not db.uno("select 1 from pg_roles where rolname=:r", r=r)]
    for rol in creados:
        db.ejecutar(f"create role {rol} nologin")
    yield
    for rol in ROLES:
        for clase in ("tables", "sequences", "functions"):
            db.ejecutar(f"alter default privileges in schema public revoke all on {clase} from {rol}")
    for rol in creados:
        db.ejecutar(f"drop owned by {rol}")
        db.ejecutar(f"drop role {rol}")


def _privilegios_por_omision() -> list[dict]:
    """Lo que el rol de la aplicación concede por omisión a los roles públicos sobre lo que cree en `public`."""
    return db.todos("""select d.defaclobjtype tipo, r.rolname rol, a.privilege_type privilegio
                       from pg_default_acl d join pg_namespace n on n.oid=d.defaclnamespace
                       cross join lateral aclexplode(d.defaclacl) a join pg_roles r on r.oid=a.grantee
                       where n.nspname='public' and d.defaclrole=current_user::regrole and r.rolname in ('anon','authenticated')""")


def _existe(relacion: str) -> bool:
    return bool(db.uno("select to_regclass(:r) r", r=f"public.{relacion}")["r"])


# ---------- 1. la migración en una transacción ----------
@SOLO_PG
def test_en_postgresql_la_migracion_revierte_entera_si_un_paso_falla(monkeypatch):
    from datos import migracion, recolectar
    db.ejecutar("drop index if exists ix_gastos_viaje")
    db.ejecutar("delete from reglas where ambito='supuesto' and clave='recoleccion_busquedas_dia'")

    def falla():
        raise RuntimeError("un paso que falla al final")

    monkeypatch.setattr(migracion, "_restricciones_postgres", falla)
    with pytest.raises(RuntimeError, match="al final"):
        migracion.migrar()
    # el índice (`_indices`) y la regla (`recolectar.asegurar_regla`) se hicieron antes del fallo: nada quedó
    assert not _existe("ix_gastos_viaje")
    assert not db.uno("select id from reglas where ambito='supuesto' and clave='recoleccion_busquedas_dia'")
    monkeypatch.undo()
    migracion.migrar()   # se repite y termina
    assert _existe("ix_gastos_viaje")
    assert db.uno("select valor from reglas where ambito='supuesto' and clave='recoleccion_busquedas_dia'")["valor"] == str(recolectar.TOPE_DIA)


def test_crear_tablas_se_une_a_la_transaccion_en_curso():
    """La migración crea las tablas que falten dentro de su transacción: si algo falla después, tampoco quedan."""
    sonda = Table("zz_sonda_transaccion", db.meta, Column("id", Integer, primary_key=True))
    try:
        with pytest.raises(RuntimeError, match="después"), db.transaccion():
            db.crear_tablas()
            assert db.uno("select count(*) n from zz_sonda_transaccion")["n"] == 0   # dentro de la transacción ya existe
            raise RuntimeError("algo falla después")
        assert "zz_sonda_transaccion" not in inspect(db.motor).get_table_names()
    finally:
        db.meta.remove(sonda)
        db.ejecutar("drop table if exists zz_sonda_transaccion")


def _foto_del_esquema() -> dict:
    """Lo que la migración decide del esquema: tablas, columnas, índices, restricciones, seguridad por filas y permisos."""
    if config.ES_SQLITE:
        return {f["name"]: f["sql"] for f in db.todos("select name, sql from sqlite_master where name not like 'sqlite_%'")}
    return {
        "columnas": db.todos("""select table_name, column_name, is_nullable, column_default from information_schema.columns
                                where table_schema='public' order by 1, 2"""),
        "indices": db.todos("select indexname, indexdef from pg_indexes where schemaname='public' order by 1"),
        "restricciones": db.todos("""select conname, pg_get_constraintdef(c.oid) d from pg_constraint c
                                     join pg_namespace n on n.oid=c.connamespace where n.nspname='public' order by 1"""),
        "relaciones": db.todos("""select c.relname, c.relkind, c.relrowsecurity, c.reloptions::text o, c.relacl::text acl
                                  from pg_class c join pg_namespace n on n.oid=c.relnamespace
                                  where n.nspname='public' and c.relkind in ('r','p','v','m','S') order by 1"""),
        "por_omision": db.todos("select defaclobjtype, defaclacl::text acl from pg_default_acl order by 1, 2"),
    }


def test_migrar_dos_veces_deja_el_mismo_esquema():
    from datos import migracion
    migracion.migrar()
    antes = _foto_del_esquema()
    assert migracion.migrar()["columnas_alineadas"] == []
    assert _foto_del_esquema() == antes


# ---------- 2. privilegios por omisión ----------
@SOLO_PG
def test_lo_que_se_cree_despues_de_migrar_no_da_permisos_a_los_roles_publicos(roles_publicos):
    from datos import migracion
    for clase in ("tables", "sequences", "functions"):   # como deja Supabase el esquema `public`
        db.ejecutar(f"alter default privileges in schema public grant all on {clase} to anon, authenticated")
    secuencia = db.uno("select pg_get_serial_sequence('gastos', 'id') s")["s"]   # una que ya existía, con permisos dados
    db.ejecutar(f"grant usage, select on sequence {secuencia} to anon")
    assert _privilegios_por_omision()
    migracion.migrar()
    assert _privilegios_por_omision() == []
    assert db.uno("select has_sequence_privilege('anon', :s, 'usage') v", s=secuencia)["v"] is False
    db.ejecutar("create table zz_sonda_permisos (id serial primary key)")
    try:
        for rol in ROLES:
            for p in ("select", "insert", "update", "delete"):
                assert db.uno("select has_table_privilege(:r, 'zz_sonda_permisos', :p) v", r=rol, p=p)["v"] is False, (rol, p)
            assert db.uno("select has_sequence_privilege(:r, 'zz_sonda_permisos_id_seq', 'usage') v", r=rol)["v"] is False
    finally:
        db.ejecutar("drop table if exists zz_sonda_permisos")


# ---------- 3. vistas con los permisos de quien consulta ----------
@SOLO_PG
def test_las_vistas_corren_con_los_permisos_de_quien_consulta_y_nacen_sin_permisos_publicos(roles_publicos):
    from datos import semilla
    db.ejecutar("alter default privileges in schema public grant select on tables to anon, authenticated")
    semilla.crear_vistas()
    for vista in semilla.VISTAS:
        opciones = db.uno("select reloptions::text o from pg_class where relname=:v and relkind='v'", v=vista)["o"]
        assert "security_invoker=on" in (opciones or ""), vista
        for rol in ROLES:
            assert db.uno("select has_table_privilege(:r, :v, 'select') v", r=rol, v=vista)["v"] is False, (vista, rol)


def test_las_vistas_se_recrean_y_protegen_en_una_sola_transaccion(monkeypatch):
    """Si una vista falla, quedan las de antes: ninguna a medio crear y ninguna sin retirarle los permisos."""
    from datos import semilla
    originales = dict(semilla.VISTAS)
    monkeypatch.setattr(semilla, "VISTAS", {"v_h_zz_sonda": "select 1 as uno", **originales, "v_h_zz_rota": "select * from"})
    try:
        with pytest.raises(DBAPIError):
            semilla.crear_vistas()
        vistas = set(inspect(db.motor).get_view_names())
        assert "v_h_zz_sonda" not in vistas and set(originales) <= vistas
    finally:
        db.ejecutar("drop view if exists v_h_zz_sonda")


# ---------- 4. conexión cifrada fuera de local ----------
def test_fuera_de_local_postgresql_exige_ssl_salvo_que_la_cadena_diga_otro():
    """Decide el servidor de la cadena, no dónde corre la aplicación: la migración que corre el guion desde el equipo
    contra Supabase también va cifrada."""
    remota = "postgresql://usr@db.ejemplo.invalid:5432/x"
    assert db._url(remota).query["sslmode"] == "require"
    assert db._url("postgres://usr@db.ejemplo.invalid/x").query["sslmode"] == "require"
    assert db._url(remota + "?sslmode=verify-full").query["sslmode"] == "verify-full"
    for servidor in ("localhost", "127.0.0.1", "db", "host.docker.internal"):   # el contenedor de Compose no usa SSL
        assert "sslmode" not in db._url(f"postgresql://usr@{servidor}:5433/x").query, servidor
    assert db._url(remota).drivername == "postgresql+psycopg"
    assert str(db._url("sqlite:///x.db")) == "sqlite:///x.db"


def test_desde_el_equipo_la_conexion_a_supabase_tambien_exige_ssl():
    entorno = {k: v for k, v in os.environ.items() if k not in ("PREPARAR_BASE_LOCAL", "DATABASE_URL", "ENTORNO", "SECRETO_ARN")}
    entorno.update(DATABASE_URL="postgresql://usr@aws-1-us-east-1.pooler.ejemplo.invalid:5432/postgres")
    salida = subprocess.run(  # noqa: S603  comando fijo: el intérprete actual con un texto constante
        [sys.executable, "-c", "from app import config, db; print(config.LOCAL, db.motor.url.query.get('sslmode'))"],
        cwd=RAIZ, env=entorno, capture_output=True, text=True, check=True)
    assert salida.stdout.strip() == "True require"


def test_el_motor_de_la_nube_conecta_con_ssl():
    """El motor real, importado como en la nube (no conecta al crearse): sin `sslmode` en la cadena, va `require`."""
    entorno = {k: v for k, v in os.environ.items() if k not in ("PREPARAR_BASE_LOCAL", "DATABASE_URL", "ENTORNO", "SECRETO_ARN")}
    entorno.update(ENTORNO="nube", DATABASE_URL="postgresql://usr@db.ejemplo.invalid:5432/x", ORIGEN_SECRETO="x",
                   SUPABASE_URL="https://ejemplo.invalid", SUPABASE_SERVICE_KEY="x")
    salida = subprocess.run(  # noqa: S603  comando fijo: el intérprete actual con un texto constante
        [sys.executable, "-c", "from app import db; print(db.motor.url.query.get('sslmode'))"],
        cwd=RAIZ, env=entorno, capture_output=True, text=True, check=True)
    assert salida.stdout.strip() == "require"


# ---------- 5. comprobar_supabase revisa las tablas de hoy ----------
def test_comprobar_supabase_espera_las_tablas_de_hoy():
    from datos import comprobar_supabase
    assert set(TABLAS_DE_HOY) <= set(comprobar_supabase.TABLAS)


@SOLO_PG
def test_comprobar_supabase_informa_tablas_de_hoy_vistas_y_privilegios_por_omision(roles_publicos, capsys):
    from datos import comprobar_supabase, migracion, semilla
    migracion.migrar()
    semilla.crear_vistas()

    def informe() -> dict:
        comprobar_supabase.main({"DATABASE_URL": os.environ["DATABASE_URL"]})
        return json.loads(capsys.readouterr().out)

    limpio = informe()
    assert all(limpio["tablas"][t] for t in TABLAS_DE_HOY)
    assert not set(TABLAS_DE_HOY) & set(limpio["tablas_sin_seguridad_por_filas"])
    assert limpio["vistas_sin_security_invoker"] == [] and limpio["privilegios_por_omision_publicos"] == {}
    db.ejecutar("alter table avisos_salientes disable row level security")
    db.ejecutar("grant select on claves_servicio to anon")
    db.ejecutar("alter default privileges in schema public grant select on tables to authenticated")
    db.ejecutar("create view v_h_zz_sin_invoker as select 1 as uno")
    try:
        sucio = informe()
        assert not sucio["en_orden"]
        assert "avisos_salientes" in sucio["tablas_sin_seguridad_por_filas"]
        assert sucio["permisos_publicos"]["anon"]["claves_servicio"] == ["SELECT"]
        assert sucio["privilegios_por_omision_publicos"] == {"authenticated": {"tablas": ["SELECT"]}}
        assert sucio["vistas_sin_security_invoker"] == ["v_h_zz_sin_invoker"]
    finally:
        db.ejecutar("drop view if exists v_h_zz_sin_invoker")
        db.ejecutar("revoke all on claves_servicio from anon")
        db.ejecutar("alter table avisos_salientes enable row level security")


# ---------- 6. la siembra completa es atómica (el punto de entrada real: `python -m datos.semilla`) ----------
def _sonda_de_siembra():
    return Table("zz_sonda_siembra", db.meta, Column("id", Integer, primary_key=True))


def _sin_sonda():
    db.meta.remove(db.meta.tables["zz_sonda_siembra"])
    db.ejecutar("drop table if exists zz_sonda_siembra")


def _falla():
    raise RuntimeError("un paso que falla después de crear las tablas")


def test_la_siembra_atomica_retira_los_privilegios_antes_de_crear_y_revierte_entera(monkeypatch):
    """El orden y la reversión, también comprobables en SQLite (que hace transaccional el DDL): se fuerza el camino de
    PostgreSQL y se registra qué pasa dentro de la transacción."""
    from app.servicios import precios
    from datos import migracion, semilla
    orden = []
    crear = db.crear_tablas
    monkeypatch.setattr(semilla, "_atomica", lambda: True)
    monkeypatch.setattr(migracion, "privilegios_por_omision", lambda: orden.append(("privilegios", db._en_transaccion.get() is not None)))
    monkeypatch.setattr(db, "crear_tablas", lambda: orden.append(("tablas", db._en_transaccion.get() is not None)) or crear())
    monkeypatch.setattr(precios, "cargar_respaldos", _falla)
    _sonda_de_siembra()
    try:
        with pytest.raises(RuntimeError, match="después de crear"):
            semilla.sembrar()
        assert orden == [("privilegios", True), ("tablas", True)]   # primero se retiran los privilegios, todo en la transacción
        assert "zz_sonda_siembra" not in inspect(db.motor).get_table_names()   # la tabla nueva no quedó
    finally:
        _sin_sonda()


def test_en_sqlite_la_siembra_sigue_en_pasos():
    from datos import semilla
    assert semilla._atomica() is (not config.ES_SQLITE)


@SOLO_PG
def test_en_postgresql_un_fallo_en_la_siembra_no_deja_tablas_ni_permisos_publicos(roles_publicos, monkeypatch):
    from app.servicios import precios
    from datos import semilla
    for clase in ("tables", "sequences", "functions"):   # como deja Supabase el esquema `public`
        db.ejecutar(f"alter default privileges in schema public grant all on {clase} to anon, authenticated")
    monkeypatch.setattr(precios, "cargar_respaldos", _falla)
    _sonda_de_siembra()
    try:
        with pytest.raises(RuntimeError, match="después de crear"):
            semilla.sembrar()
        assert not _existe("zz_sonda_siembra")                   # ninguna tabla nueva
        monkeypatch.undo()
        semilla.sembrar()                                         # se repite y termina
        assert _existe("zz_sonda_siembra") and _privilegios_por_omision() == []
        for rol in ROLES:   # lo creado en la siembra nació sin permisos públicos: se retiraron antes de crearlo
            for p in ("select", "insert", "update", "delete"):
                assert db.uno("select has_table_privilege(:r, 'zz_sonda_siembra', :p) v", r=rol, p=p)["v"] is False, (rol, p)
    finally:
        _sin_sonda()
