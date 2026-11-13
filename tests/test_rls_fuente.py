"""Ronda 2, punto 10: las tablas nuevas del frente (compras, clics a la fuente y lecturas del analizador) quedan con RLS
y sin ningún permiso para los roles públicos del proveedor (`anon` y `authenticated`). Solo en PostgreSQL."""
import pytest

from app import config, db

TABLAS = ("compras", "clics_fuente", "analisis_vuelo", "cupos_buscador", "capturas")
ROLES = ("anon", "authenticated")
PRIVILEGIOS = ("select", "insert", "update", "delete", "truncate", "references", "trigger")

pytestmark = pytest.mark.skipif(config.ES_SQLITE, reason="RLS y roles: solo PostgreSQL")


@pytest.fixture
def roles_publicos():
    """Los roles de Supabase; en un PostgreSQL desechable se crean para la prueba y se quitan al final."""
    creados = []
    for rol in ROLES:
        if not db.uno("select 1 from pg_roles where rolname=:r", r=rol):
            db.ejecutar(f"create role {rol} nologin")
            creados.append(rol)
    yield
    for rol in creados:
        for t in TABLAS:
            db.ejecutar(f"revoke all on {t} from {rol}")
        db.ejecutar(f"drop role if exists {rol}")


def test_las_tablas_nuevas_tienen_rls_y_ningun_permiso_publico(roles_publicos):
    from datos import migracion
    for t in TABLAS:   # aunque alguien les haya dado permisos, la migración los quita
        for rol in ROLES:
            db.ejecutar(f"grant select, insert on {t} to {rol}")
    migracion.migrar()
    for t in TABLAS:
        assert db.uno("select relrowsecurity r from pg_class where relname=:t and relkind='r'", t=t)["r"] is True, t
        for rol in ROLES:
            for p in PRIVILEGIOS:
                assert db.uno("select has_table_privilege(:r, :t, :p) v", r=rol, t=t, p=p)["v"] is False, (t, rol, p)
