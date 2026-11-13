"""Datos propios de una factura en la lectura: número, identificación tributaria del proveedor y líneas de detalle.

No son columnas de `gastos`: viajan en la lectura original (`gastos.extraido`) y en el aviso a n8n. La lectura usa un
doble del modelo: ninguna prueba llama a un servicio externo.
"""
import json

import pytest

from app import config
from app.servicios import extraccion, llm

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def modelo(monkeypatch):
    """Doble del modelo que responde la lectura fijada en `respuesta` y guarda lo que se le pidió."""
    for nombre, valor in (("MODELO_API_URL", "http://modelo.test"), ("MODELO_API_KEY", "clave-de-prueba"),
                          ("MODELO_NOMBRE", "modelo-de-prueba"), ("MODELO_FORMATO", "gemini")):
        monkeypatch.setattr(config, nombre, valor)
    doble = {"pedidos": [], "respuesta": {}}

    def generar(contenidos, **opciones):
        doble["pedidos"].append(opciones)
        lectura = {"comercio": "Hotel Andino", "fecha": "2026-12-10", "categoria": "hotel", "total": 119.0, "moneda": "USD",
                   "confianza": 0.95, "dudas": [], **doble["respuesta"]}
        return {"content": {"parts": [{"text": json.dumps(lectura)}]}, "finishReason": "STOP"}

    monkeypatch.setattr(llm, "generar", generar)
    return doble


def test_la_instruccion_y_el_esquema_piden_los_datos_de_factura():
    for campo in extraccion.CAMPOS_FACTURA:
        assert campo in extraccion.INSTRUCCION and campo in extraccion.ESQUEMA["properties"]
        assert campo not in extraccion.ESQUEMA["required"]   # una boleta sin número no es un error de lectura
        assert campo not in extraccion.CAMPOS                # no son columnas de gastos
    assert "NIT" in extraccion.INSTRUCCION and str(extraccion.MAX_LINEAS) in extraccion.INSTRUCCION


def test_lee_numero_identificacion_y_lineas(modelo):
    modelo["respuesta"] = {"numero_factura": "  FE-4471 ", "id_fiscal": "900.123.456-7",
                           "lineas": [{"descripcion": "Noche estándar", "cantidad": 2, "total": "200.004"},
                                      {"descripcion": "Desayuno", "cantidad": None, "total": 19}]}
    x = extraccion.extraer(PNG, "image/png", "factura.png")
    assert x["origen_dato"] == "en vivo"
    assert x["numero_factura"] == "FE-4471" and x["id_fiscal"] == "900.123.456-7"
    assert x["lineas"] == [{"descripcion": "Noche estándar", "cantidad": 2.0, "total": 200.0},
                           {"descripcion": "Desayuno", "cantidad": None, "total": 19.0}]
    assert modelo["pedidos"][0]["esquema"] is extraccion.ESQUEMA


def test_lo_que_no_tiene_forma_se_descarta_y_se_recorta(modelo):
    modelo["respuesta"] = {"numero_factura": "X" * 200, "id_fiscal": 12345, "lineas": [
        "texto suelto", {"descripcion": None, "total": None}, {"descripcion": "Inf", "total": "inf"},
        {"descripcion": "D" * 300, "cantidad": "uno", "total": float("nan")}, *[{"descripcion": f"L{i}", "total": i} for i in range(40)]]}
    x = extraccion.extraer(PNG, "image/png", "factura.png")
    assert len(x["numero_factura"]) == 60 and x["id_fiscal"] == "12345"
    assert len(x["lineas"]) == extraccion.MAX_LINEAS
    assert x["lineas"][0] == {"descripcion": "Inf", "cantidad": None, "total": None}       # infinito no es un importe
    assert x["lineas"][1]["descripcion"] == "D" * 120 and x["lineas"][1]["total"] is None  # NaN tampoco
    assert all(isinstance(linea, dict) for linea in x["lineas"])


def test_sin_datos_de_factura_quedan_vacios(modelo):
    x = extraccion.extraer(PNG, "image/png", "boleta.png")
    assert x["numero_factura"] is None and x["id_fiscal"] is None and x["lineas"] == []


def test_sin_lectura_los_datos_de_factura_existen_vacios():
    x = extraccion.extraer(PNG + b"sin-lectura", "image/png", "nada.png")   # en pruebas no hay modelo ni lectura guardada
    assert x["error"] and x["numero_factura"] is None and x["lineas"] == []
