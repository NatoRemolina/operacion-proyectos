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
    ("/gastos/10/soporte", "/gastos/10"), ("/mi-cuenta", "/mi-cuenta"), ("/algo-viejo", "/"),
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


# ---------- punto A15: decisión de la responsable (mixto) ----------
# /admin/asistente se retira (la web tiene el asistente flotante); /analitica y /flujo siguen en admin.software. con
# su propio ingreso: /entrar y /salir se siguen sirviendo allí.
def test_el_estado_de_los_vuelos_de_la_bandeja_lleva_a_vuelos(retirada):
    assert interfaz.destino("/admin/viajes/vuelos") == WEB + "/vuelos"
    assert interfaz.destino("/admin/viajes/vuelos/3") == WEB + "/vuelos"
    assert interfaz.destino("/admin/viajes/7") == WEB + "/viajes"


def test_la_pantalla_del_asistente_se_retira_pero_su_envio_sigue(retirada):
    assert interfaz.destino("/admin/asistente") == WEB + "/"
    # el asistente flotante de las pantallas que siguen (analítica y flujo) envía aquí sus preguntas
    assert interfaz.destino("/admin/asistente", "POST") is None


@pytest.mark.parametrize("ruta", ["/analitica", "/flujo", "/entrar", "/salir"])
def test_la_analitica_y_el_flujo_siguen_con_su_propio_ingreso(retirada, ruta):
    assert interfaz.destino(ruta) is None


def test_con_la_interfaz_retirada_se_entra_y_se_llega_a_la_analitica(retirada, anonimo):
    r = anonimo.post("/entrar", data={"correo": "admin@demo.local", "clave": "demo-admin-2026"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/analitica"
    assert anonimo.get("/analitica", follow_redirects=False).status_code == 200
    assert anonimo.get("/flujo", follow_redirects=False).status_code == 200
    assert anonimo.get("/admin/asistente", follow_redirects=False).headers["location"] == WEB + "/"


def test_en_la_nube_la_interfaz_anterior_siempre_redirige():
    import os
    import subprocess
    import sys
    entorno = {**os.environ, "ENTORNO": "nube", "DATABASE_URL": "postgresql://db.invalid:5432/x", "SUPABASE_URL": "https://x.invalid",
               "SUPABASE_SERVICE_KEY": "k", "INTERFAZ_ANTIGUA": "", "SECRETO_ARN": ""}
    salida = subprocess.run([sys.executable, "-c", "from app import config; print(config.INTERFAZ_ANTIGUA)"], env=entorno,  # noqa: S603
                            capture_output=True, text=True, cwd=config.RAIZ, check=True).stdout
    assert salida.strip() == "redirige"
