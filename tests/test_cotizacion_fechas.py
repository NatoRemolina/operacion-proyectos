"""Una ida pasada no se cotiza: el buscador la rechazaría y la consulta se perdería."""
from datetime import date, timedelta

import pytest

from app.servicios import cotizacion


def test_la_ida_pasada_se_rechaza_antes_de_buscar(monkeypatch):
    llamadas = []
    monkeypatch.setattr(cotizacion.precios, "buscar_vuelos", lambda *a, **k: llamadas.append(a) or ([], "en vivo", None))
    monkeypatch.setattr(cotizacion, "primer_dia_posible", lambda: date(2026, 11, 12))
    with pytest.raises(cotizacion.CotizacionInvalida) as e:
        cotizacion.crear({"id": 1, "rol": "admin", "viajero_id": 1}, proyecto_id=1, ida="2026-11-11", regreso="2026-11-24",
                         origen="MIA", destino="LAS")
    assert e.value.campo == "ida" and "ya pasó" in str(e.value)
    assert llamadas == []


def test_el_primer_dia_posible_tolera_el_huso_de_america():
    hoy_utc = date.today()
    assert cotizacion.primer_dia_posible() in (hoy_utc, hoy_utc - timedelta(days=1))
