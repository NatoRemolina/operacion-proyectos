"""Retiro de las pantallas anteriores: con INTERFAZ_ANTIGUA=redirige llevan a la web; la API sigue igual."""
import pytest

from app import config
from app.servicios import interfaz

WEB = "https://software.ejemplo.test"


@pytest.fixture()
def retirada(monkeypatch):
    monkeypatch.setattr(config, "INTERFAZ_ANTIGUA", "redirige")
    monkeypatch.setattr(config, "ORIGENES_WEB", [WEB])


@pytest.mark.parametrize("anterior, nueva", [
    ("/", "/"), ("/admin/proyectos", "/proyectos"), ("/proyectos/7", "/proyectos/7"),
    ("/proyectos/7/exportar.csv", "/proyectos/7"), ("/admin/usuarios", "/usuarios"), ("/reglas", "/reglas"),
    ("/admin/kpis", "/kpis"), ("/admin/kpis/persona/3", "/kpis/persona/3"), ("/admin/monitoreo", "/monitoreo"),
    ("/viajes/nuevo", "/cotizar"), ("/viajes/12", "/cotizar/12"), ("/viaje/4", "/viajes/4"), ("/admin/viajes", "/viajes"),
    ("/gastos", "/gastos"), ("/gastos/cargar", "/gastos/nuevo"), ("/gastos/10", "/gastos/10"),
    ("/gastos/10/soporte", "/gastos/10"), ("/mi-cuenta", "/mi-cuenta"), ("/entrar", "/entrar"), ("/algo-viejo", "/"),
])
def test_cada_pantalla_anterior_tiene_su_equivalente(retirada, anterior, nueva):
    assert interfaz.destino(anterior) == WEB + nueva


@pytest.mark.parametrize("ruta", ["/api/v1/gastos", "/api/viajes", "/salud", "/static/estilo.css", "/telegram/webhook", "/analitica", "/flujo"])
def test_la_api_y_lo_tecnico_siguen_aqui(retirada, ruta):
    assert interfaz.destino(ruta) is None


def test_con_la_interfaz_retirada_una_pagina_redirige_y_la_api_responde(retirada, cliente):
    r = cliente.get("/admin/proyectos", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == WEB + "/proyectos"
    assert cliente.post("/reglas/1", data={}, follow_redirects=False).headers["location"] == WEB + "/reglas"
    assert cliente.get("/salud").status_code == 200
    assert cliente.get("/api/v1/auth/me").status_code == 200


def test_sin_activar_las_pantallas_anteriores_siguen(cliente):
    assert config.INTERFAZ_ANTIGUA != "redirige"
    assert cliente.get("/admin/proyectos", follow_redirects=False).status_code == 200
