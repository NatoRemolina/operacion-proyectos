"""Entrenamiento ampliado: rasgos de tarifa opcionales, limpieza contada en la ficha, versión, prima de flexibilidad por ruta
y el modelo vigente se conserva si el nuevo no mejora. Escribe en una carpeta temporal, nunca en datos/modelo/."""
import json

import numpy as np

from app.servicios import modelo
from datos import entrenar


def test_entrena_con_ficha_completa_y_prima(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(entrenar, "DIR", tmp_path)
    entrenar.main()
    ficha = json.loads((tmp_path / "ficha.json").read_text())
    assert ficha["version"] == 1 and ficha["filas"] > 0 and ficha["entrenado"]
    assert set(modelo.RASGOS_TARIFA) <= set(ficha["variables"]) and ficha["rasgos_opcionales"] == modelo.RASGOS_TARIFA
    assert {"modelo", "linea_base"} == set(ficha["metricas"]) and "mae" in ficha["metricas"]["linea_base"]
    assert {"observaciones", "ofertas"} == set(ficha["limpieza"]) and "descartes" in ficha["limpieza"]["observaciones"]
    assert ficha["fuentes"]["observaciones"] + ficha["fuentes"]["ofertas"] == ficha["filas"]
    assert ficha["utilizable"] == (ficha["supera_linea_base"] and ficha["filas"] >= entrenar.MINIMO_FILAS)
    assert ficha["reemplaza"] is True and (tmp_path / "precio.json").is_file()
    prima = json.loads((tmp_path / "prima_flexibilidad.json").read_text())
    assert "rutas" in prima and "general" in prima
    assert "Importancia" in capsys.readouterr().out


def test_no_reemplaza_un_modelo_que_no_mejora(tmp_path, monkeypatch):
    monkeypatch.setattr(entrenar, "DIR", tmp_path)
    (tmp_path / "precio.json").write_text("modelo vigente")
    vigente = {"version": 4, "metricas": {"modelo": {"mae": 0.01, "mape": 0.1}, "linea_base": {"mae": 1, "mape": 1}}}
    (tmp_path / "ficha.json").write_text(json.dumps(vigente))
    entrenar.main()
    assert (tmp_path / "precio.json").read_text() == "modelo vigente"
    assert json.loads((tmp_path / "ficha.json").read_text()) == vigente
    candidata = json.loads((tmp_path / "ficha_candidata.json").read_text())
    assert candidata["version"] == 5 and candidata["reemplaza"] is False and (tmp_path / "precio_candidato.json").is_file()


def test_una_ficha_anterior_sin_rasgos_de_tarifa_sigue_sirviendo():
    anterior = {"ruta": ["MIA-LAS"], "aerolinea": ["American"]}       # categorías de un modelo entrenado antes de esta pieza
    X = modelo.codificar([{"ruta": "MIA-LAS", "aerolinea": "Delta", "escalas": 0}], anterior, modelo.VARIABLES_BASE)
    assert X.shape == (1, len(modelo.VARIABLES_BASE)) and X[0][0] == 0 and X[0][1] == -1 and np.isnan(X[0][3])
    con_tarifa = modelo.codificar([{"ruta": "MIA-LAS", "tarifa": "basica", "cambio_gratis": 0}], anterior)
    assert con_tarifa.shape == (1, len(modelo.VARIABLES)) and con_tarifa[0][modelo.VARIABLES.index("tarifa")] == -1


def test_prima_esperada_por_ruta(tmp_path):
    (tmp_path / "prima_flexibilidad.json").write_text(json.dumps(
        {"rutas": {"MIA-LAS": {"usd": 90.0, "pct": 19.0, "pares": 3}}, "general": {"usd": 70.0, "pct": 15.0, "pares": 9}}))
    assert modelo.prima_esperada("MIA", "LAS", tmp_path)["usd"] == 90.0
    assert modelo.prima_esperada("JFK", "LAX", tmp_path) == {"usd": 70.0, "pct": 15.0, "pares": 9, "alcance": "general"}
    assert modelo.prima_esperada("JFK", "LAX", tmp_path / "no-existe") is None
