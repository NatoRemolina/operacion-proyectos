"""El enlace de los gastos anteriores a su viaje (datos/migracion.py, H-32): una sola vez por base, solo con la fecha
dentro del viaje, subiendo la versión y dejando evento. Repetir la migración no deshace lo que decidió administración."""
import itertools

import pytest

from app import db
from datos import migracion

_n = itertools.count(1)


def _viaje(ida="2026-12-08", regreso="2026-12-11") -> dict:
    """Un viajero y un proyecto propios con un único viaje: así el enlace no depende de lo que dejen otras pruebas."""
    n = next(_n)
    proyecto = db.insertar("proyectos", nombre=f"Proyecto de la migración {n}")
    viajero = db.insertar("viajeros", nombre=f"Viajero de la migración {n}")
    viaje = db.insertar("viajes", proyecto_id=proyecto, viajero_id=viajero, ida=ida, regreso=regreso, estado="aprobado",
                        creado=db.ahora())
    return {"id": viaje, "proyecto_id": proyecto, "viajero_id": viajero}


def _gasto(v: dict, fecha: str | None, **otros) -> int:
    return db.insertar("gastos", proyecto_id=v["proyecto_id"], viajero_id=v["viajero_id"], fecha=fecha, comercio="Prueba",
                       total=10.0, total_usd=10.0, moneda="USD", estado="aprobado", version=1, creado=db.ahora(), **otros)


def _g(gid: int) -> dict:
    return db.uno("select viaje_id, version from gastos where id=:i", i=gid)


def _eventos(gid: int) -> int:
    return db.uno("select count(*) n from eventos where entidad='gasto' and entidad_id=:i and paso='enlazado a su viaje'", i=gid)["n"]


@pytest.fixture()
def base_sin_marca():
    """Como una base que nunca pasó por este paso. Lo que la prueba enlace de otras pruebas se deja como estaba."""
    antes = {g["id"]: (g["viaje_id"], g["version"]) for g in db.todos("select id, viaje_id, version from gastos")}
    db.ejecutar("delete from eventos where entidad='migracion' and paso=:p", p=migracion.MARCA_ENLACE)
    yield
    for g in db.todos("select id, viaje_id, version from gastos"):
        if g["id"] in antes and (g["viaje_id"], g["version"]) != antes[g["id"]]:
            db.ejecutar("update gastos set viaje_id=:v, version=:n where id=:i", v=antes[g["id"]][0], n=antes[g["id"]][1], i=g["id"])
            db.ejecutar("delete from eventos where entidad='gasto' and entidad_id=:i and paso='enlazado a su viaje'", i=g["id"])
    assert db.uno("select id from eventos where entidad='migracion' and paso=:p", p=migracion.MARCA_ENLACE)


def test_un_gasto_sacado_de_su_viaje_sigue_fuera_tras_migrar_de_nuevo():
    v = _viaje()
    gid = _gasto(v, "2026-12-09", viaje_id=v["id"])
    db.actualizar("gastos", gid, viaje_id=None, version=2)   # administración lo sacó del viaje
    migracion.migrar()
    migracion.migrar()
    assert _g(gid) == {"viaje_id": None, "version": 2} and _eventos(gid) == 0


def test_la_primera_vez_enlaza_solo_los_gastos_con_fecha_dentro_del_viaje(base_sin_marca):
    v = _viaje()
    dentro, fuera, sin_fecha = _gasto(v, "2026-12-09"), _gasto(v, "2026-11-01"), _gasto(v, None)
    ultimo_dia = _gasto(v, "2026-12-11T20:15:00")
    hechos = migracion.migrar()
    assert _g(dentro) == {"viaje_id": v["id"], "version": 2} and _eventos(dentro) == 1
    assert _g(ultimo_dia)["viaje_id"] == v["id"]
    for gid in (fuera, sin_fecha):
        assert _g(gid) == {"viaje_id": None, "version": 1} and _eventos(gid) == 0
    assert hechos["gastos_enlazados"] >= 2


def test_lo_que_ya_revisó_una_persona_no_se_toca(base_sin_marca):
    v = _viaje()
    revisor = db.uno("select id from usuarios where correo='admin@demo.local'")["id"]
    gid = _gasto(v, "2026-12-09", revisado_por=revisor)
    migracion.migrar()
    assert _g(gid) == {"viaje_id": None, "version": 1}


def test_el_enlace_se_hace_una_sola_vez(base_sin_marca):
    v = _viaje()
    primero = _gasto(v, "2026-12-09")
    migracion.migrar()
    assert _g(primero)["viaje_id"] == v["id"]
    marcas = db.uno("select count(*) n from eventos where entidad='migracion' and paso=:p", p=migracion.MARCA_ENLACE)["n"]
    db.actualizar("gastos", primero, viaje_id=None)
    tardio = _gasto(v, "2026-12-10")   # entró después sin viaje: lo resuelve la plataforma o la revisión, no la migración
    assert migracion.migrar()["gastos_enlazados"] == 0
    assert _g(primero)["viaje_id"] is None and _g(tardio)["viaje_id"] is None
    assert db.uno("select count(*) n from eventos where entidad='migracion' and paso=:p", p=migracion.MARCA_ENLACE)["n"] == marcas == 1
