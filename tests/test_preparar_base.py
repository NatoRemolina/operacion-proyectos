"""Arrancar en local contra un PostgreSQL existente no lo migra ni lo siembra sin permiso explícito."""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _preparar(**variables: str) -> str:
    entorno = {k: v for k, v in os.environ.items() if k not in ("PREPARAR_BASE_LOCAL", "DATABASE_URL", "ENTORNO")}
    entorno.update(variables)
    salida = subprocess.run(  # noqa: S603  comando fijo: el intérprete actual con un texto constante
        [sys.executable, "-c", "from app import config; print(config.PREPARAR_BASE_LOCAL)"],
        cwd=RAIZ, env=entorno, capture_output=True, text=True, check=True)
    return salida.stdout.strip()


def test_sqlite_local_se_prepara_solo():
    assert _preparar(ENTORNO="local", DATABASE_URL="sqlite:///:memory:") == "True"


def test_postgres_existente_no_se_siembra_sin_permiso():
    assert _preparar(ENTORNO="local", DATABASE_URL="postgresql://x:y@127.0.0.1:1/base") == "False"


def test_postgres_local_con_permiso_explicito():
    assert _preparar(ENTORNO="local", DATABASE_URL="postgresql://x:y@127.0.0.1:1/base",
                     PREPARAR_BASE_LOCAL="1") == "True"
