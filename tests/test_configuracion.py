"""Configuración escrita a mano (app/validar_config.py): se valida al arrancar y al poblar el secreto, sin mostrar valores.

El 13 nov la versión del agente quedó mal pegada en el secreto de producción: el asesor falló en cada pregunta durante
ocho horas, el asistente respondió con otra vía y ninguna alarma lo vio. Estas pruebas cubren lo que lo habría avisado.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import validar_config
from app.servicios import tablero

RAIZ = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("valores,esperado", [
    ({"ASESOR_AGENTE_VERSION": "6"}, []),
    ({"ASESOR_AGENTE_VERSION": ""}, []),
    ({"ASESOR_AGENTE_VERSION": "6\nASESOR_CABECERAS={}"}, [validar_config.VERSION_INVALIDA]),
    ({"ASESOR_AGENTE_VERSION": "-1"}, [validar_config.VERSION_INVALIDA]),
    ({"ASESOR_CABECERAS": '{"x-version": "v1"}', "MODELO_CABECERAS": {"x": "1"}}, []),
    ({"ASESOR_CABECERAS": "x-version: v1"}, ["ASESOR_CABECERAS no es un objeto JSON"]),
    ({"MODELO_CABECERAS": '"texto"'}, ["MODELO_CABECERAS no es un objeto JSON"]),
])
def test_reglas_de_forma(valores, esperado):
    assert validar_config.problemas(valores) == esperado


def test_las_reglas_de_produccion_no_molestan_en_local():
    local = {"URL_PUBLICA": "http://localhost:8000", "N8N_WEBHOOK_SECRETO": "corto"}
    assert validar_config.problemas(local) == []
    assert len(validar_config.problemas(local, produccion=True)) == 2


def _arrancar(**extra) -> subprocess.CompletedProcess:
    """Importa la aplicación en un proceso aparte, con el entorno de las pruebas más `extra`."""
    return subprocess.run([sys.executable, "-c", "import app.main"], cwd=RAIZ, env={**os.environ, **extra},  # noqa: S603  orden fija
                          capture_output=True, text=True, timeout=120)


def test_una_version_mal_escrita_queda_como_error_al_arrancar_sin_mostrar_el_valor():
    p = _arrancar(ASESOR_AGENTE_VERSION="6ValorPegadoDeMas")
    assert p.returncode == 0, p.stderr   # arranca igual: la variable es opcional
    assert "ERROR peticion=arranque" in p.stdout and "ASESOR_AGENTE_VERSION" in p.stdout   # la alarma lo cuenta
    assert "ValorPegadoDeMas" not in p.stdout + p.stderr


def test_bien_configurada_no_deja_errores_al_arrancar():
    p = _arrancar(ASESOR_AGENTE_VERSION="6")
    assert p.returncode == 0, p.stderr
    assert "ERROR peticion=arranque" not in p.stdout


# ---------- Monitoreo: qué vía respondió ----------
def test_monitoreo_dice_cuantas_respondio_el_asesor_y_la_ultima_caida():
    from app import db
    admin = db.uno("select id from usuarios where correo='admin@demo.local'")["id"]
    for modo in ("asesor", "modelo", "modelo", "determinista", "tope", "fallida"):
        db.insertar("asistente_consultas", usuario_id=admin, pregunta="¿?", modo=modo, momento="1999-01-10 10:00:00")
    db.insertar("eventos", momento="1999-01-10 10:05:00", entidad="asistente", paso="asesor sin respuesta",
                detalle="falló (ConnectError) · sesión — · 0 herramientas", fuente="asesor")
    f = {"proyecto_id": None, "desde": "1999-01-01", "hasta": "1999-01-31"}
    p = tablero.pestana_monitoreo("modelo", f)
    cifra = next(c for c in p["cifras"] if c["etiqueta"] == "Respondió el asesor")
    assert cifra["valor"] == 25 and cifra["unidad"] == "%"   # 1 de 4 respondidas: tope y fallida no son respuestas
    assert "1 de 4 preguntas respondidas · 3 por otra vía" in cifra["pie"]
    assert "asesor apagado: sin configurar" in cifra["pie"] and "última caída 1999-01-10 10:05" in cifra["pie"]


def test_la_pantalla_de_monitoreo_muestra_la_misma_cifra(cliente):
    html = cliente.get("/admin/monitoreo", params={"pestana": "modelo"}).text
    assert "Respondió el asesor" in html
