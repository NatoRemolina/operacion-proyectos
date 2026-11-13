"""Exactitud de la lectura: el guion compara la lectura real con `esperados.json`. Aquí el modelo es un doble que
responde la lectura esperada con errores puestos a propósito; nunca se llama a un servicio externo."""
import json
from datetime import UTC, datetime

import pytest

from app import config, db
from app.servicios import llm
from datos import medir_exactitud as medir

ESPERADOS = json.loads((config.DIR_EJEMPLOS / "esperados.json").read_text())
ORDEN = sorted(ESPERADOS)


@pytest.fixture()
def con_clave(monkeypatch):
    for nombre, valor in (("MODELO_API_URL", "http://modelo.test"), ("MODELO_API_KEY", "clave-de-prueba"),
                          ("MODELO_NOMBRE", "modelo-de-prueba"), ("MODELO_FORMATO", "gemini")):
        monkeypatch.setattr(config, nombre, valor)


@pytest.fixture()
def doble(monkeypatch, con_clave):
    """Responde, en el orden del guion, la lectura esperada con los cambios de `errores` y registra cada llamada
    en `llamadas_modelo` con 1.000 tokens de entrada y 200 de salida, como lo haría el cliente real."""
    estado = {"errores": {}, "pedidos": [], "siguiente": iter(ORDEN)}

    def generar(contenidos, **opciones):
        nombre = next(estado["siguiente"])
        estado["pedidos"].append((nombre, opciones))
        lectura = {**ESPERADOS[nombre], **estado["errores"].get(nombre, {})}
        cuerpo = {"usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200},
                  "candidates": [{"finishReason": "STOP"}]}
        llm._registrar(opciones["uso"], opciones.get("entidad_id"), cuerpo, 5, 200)
        return {"content": {"parts": [{"text": json.dumps(lectura)}]}, "finishReason": "STOP"}

    monkeypatch.setattr(llm, "generar", generar)
    yield estado
    db.ejecutar("delete from llamadas_modelo where uso=:u", u=medir.USO)


def test_sin_clave_no_se_mide_ni_se_escribe_el_informe(tmp_path):
    destino = tmp_path / "exactitud.md"
    with pytest.raises(SystemExit) as salida:
        medir.main(["--destino", str(destino)])
    assert "sin clave: no se mide" in str(salida.value)
    assert not destino.exists()


def test_compara_campo_por_campo_con_tolerancia_de_un_centavo():
    assert medir.comparar("total", 31.56, 31.55) is True
    assert medir.comparar("total", 31.57, 31.55) is False
    assert medir.comparar("total", None, None) is True            # ilegible esperado y no inventado
    assert medir.comparar("total", 25.0, None) is False           # inventar un total ilegible es un error
    assert medir.comparar("impuesto", 2.0, None) is None          # sin impuesto esperado, no se mide
    assert medir.comparar("comercio", "DESERT CAB CO", "Desert Cab Co.") is True
    assert medir.comparar("moneda", "usd", "USD") is True
    assert medir.comparar("fecha", "2026-09-12", "2026-12-09") is False
    assert medir.comparar("categoria", "comida", "comida") is True


def test_con_un_doble_mide_cada_soporte_y_escribe_el_informe(doble, tmp_path):
    doble["errores"] = {"recibo_diner.png": {"total": 31.56},              # dentro de la tolerancia: acierto
                        "recibo_lisboa.png": {"fecha": "2026-14-12"},       # fecha mal leída: error
                        "recibo_taxi.png": {"categoria": "otros"}}          # categoría equivocada: error
    destino = tmp_path / "exactitud.md"
    assert medir.main(["--destino", str(destino)]) == 0
    assert [n for n, _ in doble["pedidos"]] == ORDEN
    assert all(o["uso"] == medir.USO for _, o in doble["pedidos"])

    texto = destino.read_text()
    assert "pendiente de corrida" not in texto
    assert "modelo-de-prueba" in texto and datetime.now(UTC).date().isoformat() in texto
    medidos = sum(5 + (ESPERADOS[n]["impuesto"] is not None) for n in ORDEN)
    assert f"{medidos - 2} de {medidos} campos" in texto
    assert f"{(medidos - 2) / medidos:.1%}".replace(".", ",") in texto
    for nombre in ORDEN:
        assert f"| `{nombre}` |" in texto
    assert "leyó 2026-14-12" in texto and "leyó otros" in texto
    # 13 llamadas × (1.000 tokens de entrada a 0,5 USD/M + 200 de salida a 3 USD/M) = 0,0143 USD
    assert "0,0143 USD" in texto and "13 llamadas" in texto


def test_el_tope_de_gasto_detiene_la_corrida(doble, tmp_path):
    destino = tmp_path / "exactitud.md"
    assert medir.main(["--destino", str(destino), "--tope-usd", "0.002"]) == 0
    assert len(doble["pedidos"]) == 2           # cada lectura cuesta 0,0011 USD: la tercera ya superaría el tope
    texto = destino.read_text()
    assert "tope" in texto and "no medido" in texto


def test_el_informe_versionado_tiene_la_estructura_y_espera_la_corrida():
    versionado = (config.RAIZ / "docs" / "exactitud-lectura.md").read_text()
    assert versionado == medir.informe(None)
    assert "pendiente de corrida" in versionado
    for nombre in ORDEN:
        assert f"| `{nombre}` |" in versionado
