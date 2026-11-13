"""Recolector de rutas frecuentes: listo y apagado. Ninguna prueba gasta búsquedas: el buscador es siempre un doble."""
import pytest

from app import config, db
from app.servicios import costo, precios, rutas_frecuentes
from datos import recolectar
from infra import poblar_secreto

RUTAS = [{"origen": "ZRA", "destino": "ZRB"}, {"origen": "ZRC", "destino": "ZRD"}, {"origen": "ZRE", "destino": "ZRF"}]


@pytest.fixture()
def sin_gasto(monkeypatch):
    """El buscador falla si alguien lo llama; las rutas frecuentes son tres inventadas."""
    def prohibido(*_a, **_k):
        raise AssertionError("se intentó una búsqueda paga")
    monkeypatch.setattr(precios, "buscar_vuelos", prohibido)
    monkeypatch.setattr(rutas_frecuentes, "top", lambda n=5, **_: RUTAS[:n])
    db.ejecutar("delete from eventos where entidad='recolector'")


def test_apagado_por_omision_y_en_el_secreto():
    assert config.RECOLECTOR == "apagado"
    assert "RECOLECTOR" in poblar_secreto.CLAVES


def test_apagado_no_busca(sin_gasto, capsys):
    with pytest.raises(SystemExit) as fin:
        recolectar.main(["--frecuentes"])
    assert "apagado" in str(fin.value)


def test_simular_muestra_el_plan_sin_gastar(sin_gasto, capsys):
    recolectar.main(["--frecuentes", "--simular"])
    salida = capsys.readouterr().out
    assert "ZRA ZRB" in salida and "ZRE ZRF" in salida
    assert len([linea for linea in salida.splitlines() if linea.startswith("   Z")]) == 10   # tope por omisión


def test_el_tope_es_una_regla_editable(sin_gasto):
    recolectar.asegurar_regla()
    assert costo.supuesto(costo.catalogo(), "recoleccion_busquedas_dia", 0) == 10
    db.ejecutar("update reglas set valor='3' where ambito='supuesto' and clave='recoleccion_busquedas_dia'")
    try:
        assert len(recolectar.plan_frecuentes()) == 3
    finally:
        db.ejecutar("update reglas set valor='10' where ambito='supuesto' and clave='recoleccion_busquedas_dia'")


def test_encendido_respeta_el_tope_del_dia(sin_gasto, monkeypatch):
    hechas = []
    monkeypatch.setattr(precios, "buscar_vuelos", lambda o, d, i, r: hechas.append((o, d, i, r)) or ([], "en vivo", {}))
    monkeypatch.setattr(config, "RECOLECTOR", "encendido")
    monkeypatch.setattr(config, "SERPAPI_KEY", "doble-sin-uso")
    monkeypatch.setattr(recolectar.time, "sleep", lambda _: None)
    recolectar.main(["--frecuentes"])
    assert len(hechas) == 10 and {h[0] for h in hechas} == {"ZRA", "ZRC", "ZRE"}
    assert db.uno("select count(*) n from eventos where entidad='recolector' and paso='búsqueda recolectada'")["n"] == 10
    recolectar.main(["--frecuentes"])          # el mismo día ya no queda cupo
    assert len(hechas) == 10
