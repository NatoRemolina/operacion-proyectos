"""Un solo «día» y una sola zona: los topes por día, «hoy» y los periodos se cuentan en la zona de la empresa
(`config.ZONA_EMPRESA`, America/Bogota) con `tiempo.inicio_del_dia()` y `tiempo.hoy()`. En UTC, desde las 19:00 de
Bogotá ya sería el día siguiente: los topes se reiniciarían a media tarde y un viaje terminaría antes de tiempo.

El reloj se fija en marzo de 2031, lejos de hoy, y lo que se inserta se borra al terminar.
"""
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app import config, db
from app.servicios import acceso, analizador, asesor, asistente, contable, cotizacion, kpis, rutas_frecuentes, tiempo, viajes

NOCHE = datetime(2031, 3, 10, 3, 0, tzinfo=UTC)    # domingo 9 de marzo, 22:00 en Bogotá; en UTC ya es lunes 10
INICIO = "2031-03-09 05:00:00"                      # medianoche del 9 en Bogotá
AYER = "2031-03-09 04:30:00"                        # 23:30 del 8 en Bogotá: es de ayer
HOY = "2031-03-09 23:00:00"                         # 18:00 del 9 en Bogotá: es de hoy


@pytest.fixture
def reloj(monkeypatch):
    monkeypatch.setattr(tiempo, "ahora", lambda: NOCHE)
    return NOCHE


@pytest.fixture
def persona():
    """Una cuenta nueva, para contar solo lo suyo; al final se borra todo lo que quedó a su nombre."""
    uid = acceso.crear_usuario(f"dia-{uuid.uuid4().hex[:8]}@demo.local", "Persona del día", "colaborador", "clave-del-dia-2031")
    yield db.uno("select * from usuarios where id=:i", i=uid)
    for tabla in ("solicitudes", "consultas_buscador", "asistente_dictados", "asistente_consultas", "cupos_buscador", "viajes"):
        db.ejecutar(f"delete from {tabla} where usuario_id=:u", u=uid)  # noqa: S608
    db.ejecutar("delete from llamadas_modelo where uso='asesor' and momento>='2031-01-01'")
    db.ejecutar("delete from sesiones where usuario_id=:u", u=uid)
    db.ejecutar("delete from usuarios where id=:u", u=uid)


def test_la_zona_y_el_dia_de_la_empresa():
    assert str(config.ZONA_EMPRESA) == "America/Bogota"
    assert tiempo.hoy(NOCHE) == date(2031, 3, 9)
    assert tiempo.inicio_del_dia(NOCHE) == INICIO
    assert tiempo.inicio_del_dia(datetime(2031, 3, 10, 6, 0, tzinfo=UTC)) == "2031-03-10 05:00:00"
    assert tiempo.inicio_del_mes(datetime(2031, 4, 1, 4, 30, tzinfo=UTC)) == "2031-03-01 05:00:00"   # 31 de marzo en Bogotá


def test_el_tope_de_cotizaciones_cuenta_el_dia_de_la_empresa(reloj, persona):
    for creado in (AYER, HOY):
        db.insertar("solicitudes", usuario_id=persona["id"], estado="comparando", creado=creado)
    assert cotizacion.cotizaciones_de_hoy(persona) == 1


def test_el_tope_de_decisiones_en_vivo_cuenta_el_dia_de_la_empresa(reloj, persona):
    for momento in (AYER, HOY):
        db.insertar("consultas_buscador", usuario_id=persona["id"], tipo="regreso", origen="en vivo", momento=momento)
    assert cotizacion.decisiones_en_vivo_hoy(persona) == 1


def test_los_topes_del_asistente_y_del_dictado_cuentan_el_dia_de_la_empresa(reloj, persona):
    for momento in (AYER, HOY):
        db.insertar("asistente_dictados", usuario_id=persona["id"], momento=momento)
        db.insertar("asistente_consultas", usuario_id=persona["id"], momento=momento)
    assert asistente.dictados_hoy(persona["id"]) == 1
    assert asistente.usadas_hoy(persona["id"]) == 1


def test_el_gasto_del_asesor_cuenta_el_dia_de_la_empresa(reloj, persona):
    db.insertar("llamadas_modelo", uso="asesor", momento=AYER, costo_usd="1.25")
    db.insertar("llamadas_modelo", uso="asesor", momento=HOY, costo_usd="0.75")
    assert asesor.gasto_hoy() == Decimal("0.75")


def test_el_cupo_del_analizador_cuenta_el_dia_de_la_empresa(reloj, persona):
    tope = analizador.tope_enlace_vendedor()
    db.insertar("cupos_buscador", usuario_id=persona["id"], tipo="enlace_vendedor", clave="ayer", unidades=tope, creado=AYER)
    assert analizador.reservar_cupo(persona, "hoy", 1)   # lo de ayer ya no cuenta


def test_un_viaje_sigue_en_curso_hasta_el_fin_del_dia_de_la_empresa(reloj, persona):
    # Regreso el 7 más 2 días de margen: el 9 en Bogotá sigue en curso, aunque en UTC ya sea el 10
    termina = {"estado": "aprobado", "ida": "2031-03-05", "regreso": "2031-03-07"}
    assert viajes.en_curso(termina)
    # El gasto va al viaje en curso hoy (en Bogotá), no al primero de los aprobados
    for ida, regreso in (("2031-03-01", "2031-03-02"), ("2031-03-05", "2031-03-07")):
        db.insertar("viajes", usuario_id=persona["id"], estado="aprobado", ida=ida, regreso=regreso, creado=HOY)
    viaje, _ = viajes.resolver_para_gasto(persona)
    assert viaje and viaje["ida"] == "2031-03-05"


def test_el_periodo_del_libro_contable_es_el_de_la_empresa(monkeypatch):
    # 1 de abril, 04:30 UTC: en Bogotá todavía es el 31 de marzo (en Nueva York ya sería abril)
    monkeypatch.setattr(tiempo, "ahora", lambda: datetime(2031, 4, 1, 4, 30, tzinfo=UTC))
    assert contable.mes_en_curso() == ("2031-03-01", "2031-03-31")
    assert contable.anio_en_curso() == ("2031-01-01", "2031-12-31")


def test_la_tendencia_de_los_kpis_termina_en_la_semana_de_la_empresa(reloj):
    # Domingo 9 en Bogotá: la última semana empieza el lunes 3 (en UTC, el lunes 10 ya sería otra semana)
    assert kpis.tendencia({}, semanas=2)["semanas"] == ["2031-02-24", "2031-03-03"]


def test_las_rutas_frecuentes_cuentan_desde_el_dia_de_la_empresa(reloj, monkeypatch):
    pedidos = []
    monkeypatch.setattr(rutas_frecuentes, "_cuentas", lambda desde: pedidos.append(desde) or {})
    rutas_frecuentes.top()
    assert pedidos == [(date(2031, 3, 9) - timedelta(days=rutas_frecuentes.DIAS)).isoformat()]


# Formas de calcular «hoy» fuera de `tiempo`: en UTC o con la hora del equipo, y zonas propias de la empresa
OTRA_FORMA = re.compile(r"date\.today\(\)|ahora\(\)\[:10\]|ZoneInfo\(\"America/|"
                        r"datetime\.now\([^)]*\)\.(?:date\(\)|strftime\(\"%Y-%m-(?:%d|01)\"\)|astimezone)")


def test_nadie_calcula_hoy_por_su_cuenta():
    raiz = Path(config.RAIZ)
    propios = {raiz / "app" / "config.py", raiz / "app" / "servicios" / "tiempo.py"}
    hallados = [f"{p.relative_to(raiz)}:{n}" for carpeta in ("app", "datos") for p in sorted((raiz / carpeta).rglob("*.py"))
                if p not in propios for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if OTRA_FORMA.search(linea)]
    assert hallados == []
