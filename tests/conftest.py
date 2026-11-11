"""Arnés de pruebas: base SQLite temporal y ninguna clave real.

Las variables se fijan ANTES de importar la aplicación: `app.config` carga `.env`, y sin esto
las pruebas escribirían en la base real y gastarían cupo del buscador y del modelo.
"""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="pruebas_"))
os.environ.update({
    "ENTORNO": "local", "DATABASE_URL": f"sqlite:///{_tmp / 'pruebas.db'}",
    "SERPAPI_KEY": "", "MODELO_API_URL": "", "MODELO_API_KEY": "", "MODELO_NOMBRE": "",
    "SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": "", "APP_CLAVE": "", "SECRETO_ARN": "",
})

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402

config.DIR_ARCHIVOS = _tmp / "archivos"

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def cliente():
    return TestClient(app)


@pytest.fixture(scope="session")
def ejemplos():
    return config.DIR_EJEMPLOS
