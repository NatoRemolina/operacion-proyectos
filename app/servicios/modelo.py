"""Precio esperado de un vuelo según el modelo entrenado con las observaciones registradas.

El modelo solo se usa si su ficha dice que es utilizable: suficientes filas y mejor que la
línea base. Si no, las pantallas no muestran precio esperado.
"""
import json
from functools import lru_cache

import numpy as np

from .. import config

DIR = config.RAIZ / "datos" / "modelo"
CATEGORICAS = ["ruta", "aerolinea"]
VARIABLES = ["ruta", "aerolinea", "escalas", "duracion_min", "hora_salida", "dia_semana", "anticipacion",
             "noches", "tipico_min", "tipico_max"]


def codificar(filas, categorias: dict) -> np.ndarray:
    """Convierte filas (DataFrame o lista de dict) en la matriz del modelo. Categoría desconocida = -1."""
    registros = filas.to_dict("records") if hasattr(filas, "to_dict") else filas
    matriz = []
    for r in registros:
        fila = []
        for v in VARIABLES:
            valor = r.get(v)
            if v in CATEGORICAS:
                fila.append(categorias[v].index(valor) if valor in categorias[v] else -1)
            else:
                fila.append(np.nan if valor is None else float(valor))
        matriz.append(fila)
    return np.array(matriz, dtype=float)


@lru_cache(maxsize=1)
def ficha() -> dict | None:
    archivo = DIR / "ficha.json"
    return json.loads(archivo.read_text()) if archivo.is_file() else None


@lru_cache(maxsize=1)
def _modelo():
    import xgboost as xgb
    m = xgb.Booster()
    m.load_model(DIR / "precio.json")
    return m


def utilizable() -> bool:
    f = ficha()
    return bool(f and f.get("utilizable") and (DIR / "precio.json").is_file())


def precios_esperados(filas: list[dict]) -> list[float | None]:
    """Precio esperado en USD para cada fila con las variables del modelo."""
    if not filas or not utilizable():
        return [None] * len(filas)
    import xgboost as xgb
    X = codificar(filas, ficha()["categorias"])
    return [round(float(p), 2) for p in np.exp(_modelo().predict(xgb.DMatrix(X, feature_names=VARIABLES)))]
