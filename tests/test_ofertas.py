"""Tarifas vistas (`ofertas_tarifa`): una fila por tarifa, solo se añaden filas y la misma tarifa no se repite."""
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import config, db
from app.servicios import ofertas
from datos import migracion


def _fila(**otros) -> dict:
    return {"momento": db.ahora(), "fuente": "buscador", "origen_fila": "busqueda:prueba-unica", "origen": "MIA", "destino": "LAS",
            "ida": "2026-12-08", "regreso": "2026-12-11", "vuelos": "AA1851", "vendedor": "American", "es_aerolinea": 1,
            "tarifa": "Basic Economy", "tarifa_normalizada": "basica", "precio": 458.0, "moneda": "USD", **otros}


def test_la_tabla_existe_con_sus_indices():
    columnas = {c["name"] for c in inspect(db.motor).get_columns("ofertas_tarifa")}
    assert {"momento", "fuente", "solicitud_id", "opcion_id", "analisis_id", "busqueda_clave", "origen", "destino", "ida",
            "regreso", "vuelos", "aerolinea", "vendedor", "es_aerolinea", "tarifa", "tarifa_normalizada", "precio", "moneda",
            "equipaje_mano", "maleta_usd", "cambios", "reembolso", "asiento", "anticipacion_dias", "dia_semana",
            "noches", "crudo"} <= columnas
    indices = {i["name"] for i in inspect(db.motor).get_indexes("ofertas_tarifa")}
    assert {"ix_ofertas_tarifa_ruta_ida", "ux_ofertas_tarifa_unica"} <= indices


def test_la_misma_tarifa_de_la_misma_fuente_no_se_repite():
    db.insertar("ofertas_tarifa", **_fila())
    with pytest.raises(IntegrityError):
        db.insertar("ofertas_tarifa", **_fila(precio=460.0))
    db.insertar("ofertas_tarifa", **_fila(fuente="pagina"))          # la misma tarifa leída en la página es otra fila
    db.insertar("ofertas_tarifa", **_fila(tarifa="Main Cabin", tarifa_normalizada="estandar", precio=588.0))
    assert db.uno("select count(*) n from ofertas_tarifa where origen_fila='busqueda:prueba-unica'")["n"] == 3


def test_la_migracion_de_la_tabla_se_puede_repetir():
    hechos = migracion._tablas_modelo()
    assert hechos == migracion._tablas_modelo()
    assert "ofertas_tarifa" in hechos["tablas_modelo"]


@pytest.mark.skipif(config.ES_SQLITE, reason="RLS solo existe en PostgreSQL")
def test_la_tabla_tiene_rls():
    assert db.uno("select relrowsecurity r from pg_class where relname='ofertas_tarifa'")["r"]


def test_solo_valores_conocidos():
    assert set(ofertas.TARIFAS) == {"basica", "estandar", "flexible", "premium"}
    assert set(ofertas.CAMBIOS) == {"gratis", "cargo", "no"} and set(ofertas.REEMBOLSOS) == {"total", "parcial", "no"}
    assert set(ofertas.ASIENTOS) == {"incluido", "cargo"} and set(ofertas.FUENTES) == {"buscador", "pagina"}
