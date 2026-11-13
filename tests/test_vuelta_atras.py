"""La vuelta atrás de docs/respaldo.md (H-33): antes de restaurar se borran las vistas del código y las tablas que la
versión nueva añadió (no están en el manifiesto de la copia), y la copia se restaura en una sola transacción.

Las primeras pruebas no necesitan nada. La última repite el caso de la auditoría en PostgreSQL de verdad: necesita
Docker y PRUEBAS_POSTGRES_SERVIDOR, la dirección de un servidor desechable donde pueda crear y borrar la base
`pruebas_infra` (por ejemplo el de docker-compose.yml, con su base `postgres`).
"""
import json
import os
import shutil
from pathlib import Path

import psycopg
import pytest

from datos import respaldar
from datos.semilla import VISTAS


def _copia(tmp_path: Path, tablas: dict) -> Path:
    carpeta = tmp_path / "copia"
    carpeta.mkdir()
    (carpeta / "base.dump").write_bytes(b"copia")
    archivos = {"base.dump": {"bytes": 5, "sha256": respaldar._sha(carpeta / "base.dump")}}
    (carpeta / "manifiesto.json").write_text(json.dumps({"filas": tablas, "archivos": archivos}))
    return carpeta


def test_borra_las_tablas_del_codigo_que_no_estan_en_la_copia(tmp_path):
    sql = respaldar.vuelta_atras(_copia(tmp_path, {"usuarios": 2, "gastos": 5, "viajes": 1}))
    for tabla in ("envios_soporte", "envios_cotizacion", "tramos_vuelo", "cargos"):
        assert f'drop table if exists public."{tabla}" cascade;' in sql
    for tabla in ("usuarios", "gastos", "viajes"):
        assert f'"{tabla}"' not in sql   # lo que trae la copia lo reemplaza la propia restauración


def test_borra_las_vistas_del_codigo(tmp_path):
    sql = respaldar.vuelta_atras(_copia(tmp_path, {"usuarios": 1}))
    for vista in VISTAS:
        assert f'drop view if exists public."{vista}" cascade;' in sql
    assert sql.index("drop view") < sql.index("drop table")


def test_no_sigue_si_la_copia_esta_alterada(tmp_path):
    carpeta = _copia(tmp_path, {"usuarios": 1})
    (carpeta / "base.dump").write_bytes(b"otra cosa")
    with pytest.raises(SystemExit, match="huella"):
        respaldar.vuelta_atras(carpeta)


def test_la_orden_imprime_el_sql(tmp_path, capsys):
    carpeta = _copia(tmp_path, {"usuarios": 1})
    assert respaldar.main(["vuelta-atras", "--respaldo", str(carpeta)]) == 0
    assert capsys.readouterr().out == respaldar.vuelta_atras(carpeta)


# ---------- en PostgreSQL ----------
SERVIDOR = os.getenv("PRUEBAS_POSTGRES_SERVIDOR", "")
BASE = "pruebas_infra"

ANTES = """
create table usuarios (id serial primary key, correo text unique, rol text,
                       constraint ck_usuarios_rol check (rol in ('piloto','gestor','admin')));
create table viajes (id serial primary key, usuario_id integer references usuarios(id), estado text);
create table gastos (id serial primary key, usuario_id integer references usuarios(id), viaje_id integer references viajes(id), total float);
insert into usuarios (correo, rol) values ('piloto@ejemplo.com', 'piloto'), ('admin@ejemplo.com', 'admin');
insert into viajes (usuario_id, estado) values (1, 'aprobado');
insert into gastos (usuario_id, viaje_id, total) values (1, 1, 10), (1, null, 5);
"""
# Lo que hace una migración como la de datos/migracion.py: permisos nuevos y tablas nuevas que apuntan a las de antes
MIGRACION = """
alter table usuarios drop constraint ck_usuarios_rol;
update usuarios set rol='colaborador' where rol='piloto';
alter table usuarios add constraint ck_usuarios_rol check (rol in ('colaborador','gestor','admin'));
create table cargos (id serial primary key, nombre text);
alter table usuarios add column cargo_id integer references cargos(id);
create table envios_soporte (id serial primary key, usuario_id integer not null references usuarios(id), gasto_id integer references gastos(id));
create table tramos_vuelo (id serial primary key, viaje_id integer references viajes(id));
alter table gastos add column version integer not null default 1;
insert into cargos (nombre) values ('Pilotaje de dron');
update usuarios set cargo_id=1;
insert into envios_soporte (usuario_id, gasto_id) values (1, 1);
insert into tramos_vuelo (viaje_id) values (1);
insert into gastos (usuario_id, total) values (2, 99);
create view v_h_gasto as select g.*, u.correo from gastos g join usuarios u on u.id=g.usuario_id;
"""
RESTAURAR = ["pg_restore", "--no-owner", "--no-privileges", "--clean", "--if-exists", "--single-transaction",
             "--exit-on-error", "-d", BASE]


@pytest.fixture()
def base_propia(tmp_path):
    if not SERVIDOR or not shutil.which("docker"):
        pytest.skip("Necesita Docker y PRUEBAS_POSTGRES_SERVIDOR")
    with psycopg.connect(SERVIDOR, autocommit=True) as c:
        c.execute(f"drop database if exists {BASE} with (force)")
        c.execute(f"create database {BASE}")
    url = SERVIDOR.rsplit("/", 1)[0] + f"/{BASE}"
    env = tmp_path / ".env.base-propia"
    env.write_text(f"DATABASE_URL={url}\n")
    yield url, str(env)
    with psycopg.connect(SERVIDOR, autocommit=True) as c:
        c.execute(f"drop database if exists {BASE} with (force)")


def _sql(url: str, sql: str):
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(sql)


def _estado(url: str) -> dict:
    with psycopg.connect(url) as c:
        tablas = {r[0] for r in c.execute("select tablename from pg_tables where schemaname='public'")}
        vistas = {r[0] for r in c.execute("select viewname from pg_views where schemaname='public'")}
        roles = sorted(r[0] for r in c.execute("select rol from usuarios"))
    return {"tablas": tablas, "vistas": vistas, "roles": roles}


def _docker(url: str, argumentos: list[str], archivo: Path):
    with open(archivo, "rb") as f:
        respaldar._docker(respaldar._partes(url), argumentos, entrada=f)


def test_restaurar_la_copia_sobre_la_base_migrada(base_propia, tmp_path, capsys):
    url, env = base_propia
    _sql(url, ANTES)
    carpeta = respaldar.respaldar(env, str(tmp_path / "copia"))
    manifiesto = json.loads((carpeta / "manifiesto.json").read_text())
    assert manifiesto["filas"] == {"gastos": 2, "usuarios": 2, "viajes": 1}
    _sql(url, MIGRACION)
    migrada = _estado(url)

    # Sin borrar antes lo nuevo, la restauración choca con las claves foráneas; en una transacción no deja nada a medias
    with pytest.raises(SystemExit, match="pg_restore"):
        _docker(url, RESTAURAR, carpeta / "base.dump")
    assert _estado(url) == migrada

    # El procedimiento de docs/respaldo.md: borrar lo que la copia no trae y restaurar
    (tmp_path / "vuelta_atras.sql").write_text(respaldar.vuelta_atras(carpeta))
    _docker(url, ["psql", "-v", "ON_ERROR_STOP=1", "--single-transaction", "-q"], tmp_path / "vuelta_atras.sql")
    _docker(url, RESTAURAR, carpeta / "base.dump")

    assert respaldar.conteos(url) == manifiesto["filas"]
    assert _estado(url) == {"tablas": {"usuarios", "viajes", "gastos"}, "vistas": set(),
                            "roles": ["admin", "piloto"]}
