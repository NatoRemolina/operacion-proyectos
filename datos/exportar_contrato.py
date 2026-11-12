"""Escribe `contracts/openapi-v1.json` con las rutas de la API v1 (y solo esas).

Uso: python -m datos.exportar_contrato

Monta únicamente los módulos `app/rutas/v1_*.py`: no arranca la aplicación completa, no siembra la base ni la toca.
Una prueba comprueba que el archivo versionado coincide con lo que genera este guion.
"""
import importlib
import json
import pkgutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app import rutas
from app.api_v1 import PREFIJO

DESTINO = Path(__file__).resolve().parent.parent / "contracts" / "openapi-v1.json"


def contrato() -> dict:
    app = FastAPI()
    for m in sorted(m.name for m in pkgutil.iter_modules(rutas.__path__) if m.name.startswith("v1_")):
        app.include_router(importlib.import_module(f"{rutas.__name__}.{m}").router)
    return get_openapi(title="API v1 · Operación de proyectos", version="1.0.0",
                       description="Recorrido mínimo: ingreso, viajes, gastos y envío de recibos. Ver `contracts/api-v1.md`.",
                       routes=[r for r in app.routes if getattr(r, "path", "").startswith(PREFIJO)])


def texto() -> str:
    return json.dumps(contrato(), ensure_ascii=False, indent=2, sort_keys=False) + "\n"


if __name__ == "__main__":
    DESTINO.write_text(texto(), encoding="utf-8")
    print(f"Contrato escrito en {DESTINO.relative_to(DESTINO.parent.parent)}")
