"""Integridad del flujo de gastos: importes, duplicados, transacciones, envíos repetidos y revisión versionada."""
from datetime import UTC, datetime, timedelta

import pytest

from app import db
from app.servicios import dinero, validacion


def _sin_rastro(*ids):
    for i in ids:
        db.ejecutar("delete from eventos where entidad='gasto' and entidad_id=:i", i=i)
        db.ejecutar("delete from gastos where id=:i", i=i)


# ---------- importes y reglas ----------
@pytest.mark.parametrize("total", [-10, 0, float("nan"), float("inf"), "NaN", "0.001", "Infinity", 1e15])
def test_importe_invalido_va_a_revision_con_su_motivo(total, viaje_aprobado):
    g = {"comercio": "Sonda de importes", "fecha": viaje_aprobado["ida"], "total": total, "moneda": "USD", "confianza": 1}
    r = validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)
    assert r["estado"] == "revision" and "importe_invalido" in r["motivos"]
    assert g["total"] is total   # la lectura original no se toca: es lo que se guarda en `extraido`


def test_componente_negativo_es_importe_invalido(viaje_aprobado):
    g = {"comercio": "Sonda componentes", "fecha": viaje_aprobado["ida"], "total": 10, "subtotal": 12, "propina": -2,
         "moneda": "USD", "confianza": 1}
    assert "importe_invalido" in validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)["motivos"]


def test_dinero_rechaza_lo_que_no_es_un_importe():
    for malo in (None, True, "abc", float("nan"), float("-inf"), "1e13"):
        with pytest.raises(ValueError):
            dinero.decimal(malo)
    for malo in (0, "0.004", -1):
        with pytest.raises(ValueError):
            dinero.decimal(malo, positivo=True)
    assert str(dinero.decimal("10.005")) == "10.01" and str(dinero.decimal(0)) == "0.00"


def test_fecha_imposible_va_a_revision(viaje_aprobado):
    g = {"comercio": "Fecha imposible", "fecha": "2026-02-31", "total": 10, "moneda": "USD", "confianza": 1}
    r = validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)
    assert r["estado"] == "revision" and "fecha_invalida" in r["motivos"]


def test_fecha_futura_se_avisa():
    futura = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    hoy = datetime.now(UTC).date().isoformat()
    g = {"comercio": "Sonda futura", "fecha": futura, "total": 12.5, "moneda": "USD", "confianza": 1, "categoria": "otros"}
    assert "fecha_futura" in validacion.revisar(g, {"id": 1})["motivos"] and validacion.MOTIVOS["fecha_futura"]
    assert "fecha_futura" not in validacion.revisar({**g, "fecha": hoy}, {"id": 1})["motivos"]


def test_fecha_futura_no_bloquea_por_ahora(viaje_aprobado):
    """Decisión de la usuaria: mientras los recibos y viajes de demostración sean de diciembre, la fecha futura solo avisa."""
    if viaje_aprobado["ida"] <= datetime.now(UTC).date().isoformat():
        pytest.skip("El viaje de prueba ya no está en el futuro")
    g = {"comercio": "Sonda futura en viaje", "fecha": viaje_aprobado["ida"], "total": 12.5, "moneda": "USD",
         "confianza": 1, "categoria": "otros"}
    r = validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)
    assert "fecha_futura" in r["motivos"] and r["estado"] == "aprobado_auto"


def test_duplicado_exacto_compara_la_moneda():
    gid = db.insertar("gastos", comercio="Café Moneda", fecha="2026-10-01", total=50, moneda="USD", estado="aprobado")
    try:
        base = {"comercio": "café moneda", "fecha": "2026-10-01", "total": 50, "confianza": 1}
        assert "duplicado" in validacion.revisar({**base, "moneda": "USD"}, None)["motivos"]
        otra = validacion.revisar({**base, "moneda": "EUR"}, None)["motivos"]
        assert "duplicado" not in otra and "duplicado_aproximado" not in otra
    finally:
        _sin_rastro(gid)


def test_dos_gastos_sin_moneda_del_mismo_comercio_dia_e_importe_son_duplicado():
    gid = db.insertar("gastos", comercio="Peaje sin moneda", fecha="2026-10-02", total=7, moneda=None, estado="revision")
    try:
        r = validacion.revisar({"comercio": "Peaje sin moneda", "fecha": "2026-10-02", "total": 7, "moneda": None,
                                "confianza": 1}, None)
        assert "duplicado" in r["motivos"]
    finally:
        _sin_rastro(gid)


def test_la_tolerancia_del_diez_por_ciento_se_conserva(nuevo_viaje):
    v = nuevo_viaje()
    db.actualizar("viajes", v["id"], presupuesto_usd=100)   # se devuelve al final: otras pruebas suman los presupuestos
    v = {**v, "presupuesto_usd": 100}
    gid = db.insertar("gastos", viaje_id=v["id"], comercio="Base tolerancia", fecha=v["ida"], total=80, moneda="USD",
                      total_usd=80, estado="aprobado")
    try:
        g = {"comercio": "Sonda tolerancia", "fecha": v["ida"], "moneda": "USD", "confianza": 1, "categoria": "otros"}
        assert "presupuesto_superado" not in validacion.revisar({**g, "total": 30}, {"id": 1}, viaje=v)["motivos"]   # 110
        assert "presupuesto_superado" in validacion.revisar({**g, "total": 30.01}, {"id": 1}, viaje=v)["motivos"]
    finally:
        _sin_rastro(gid)
        db.actualizar("viajes", v["id"], estado="rechazado")


def test_la_api_no_publica_importes_no_finitos():
    from app.servicios import consultas
    assert consultas.dinero(float("nan")) is None and consultas.dinero(float("inf")) is None
    assert consultas.dinero(54) == "54.00"
