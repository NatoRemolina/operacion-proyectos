"""Revalidación de gastos aprobados sin intervención con las reglas vigentes."""
from app import db
from datos import revalidar_gastos


def _gasto_aprobado_auto(viaje_id: int | None, proyecto_id: int = 1) -> int:
    return db.insertar("gastos", comercio="Diner de prueba", fecha="2026-12-09", categoria="comida", total=20.0,
                       moneda="USD", total_usd=20.0, confianza=0.97, estado="aprobado_auto", alertas=[], motivos=[],
                       proyecto_id=proyecto_id, viaje_id=viaje_id, creado=db.ahora())


def test_un_gasto_aprobado_solo_en_un_viaje_sin_aprobar_pasa_a_revision(nuevo_viaje):
    pendiente = nuevo_viaje(aprobar=False)
    gid = _gasto_aprobado_auto(pendiente["id"])
    cambios = {c["id"]: c for c in revalidar_gastos.candidatos()}
    assert "viaje_no_aprobado" in cambios[gid]["motivos"]
    assert db.uno("select estado from gastos where id=:i", i=gid)["estado"] == "aprobado_auto"   # sin --aplicar no escribe
    revalidar_gastos.main(["--aplicar"])
    fila = db.uno("select estado, motivos from gastos where id=:i", i=gid)
    assert fila["estado"] == "revision" and "viaje_no_aprobado" in fila["motivos"]
    assert db.uno("select 1 as x from eventos where entidad='gasto' and entidad_id=:i and paso='revalidado: pasa a revisión'", i=gid)


def test_un_gasto_sin_viaje_pasa_a_revision_y_uno_que_cumple_no_se_toca(viaje_aprobado):
    sin_viaje = _gasto_aprobado_auto(None)
    revalidar_gastos.main(["--aplicar"])
    assert db.uno("select estado from gastos where id=:i", i=sin_viaje)["estado"] == "revision"
    # lo que aprobó una persona nunca se toca
    humano = _gasto_aprobado_auto(None)
    db.actualizar("gastos", humano, estado="aprobado")
    revalidar_gastos.main(["--aplicar"])
    assert db.uno("select estado from gastos where id=:i", i=humano)["estado"] == "aprobado"
