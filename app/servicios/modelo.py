"""Precio esperado de un vuelo según el modelo entrenado con las observaciones registradas.

El modelo solo se usa si su ficha dice que es utilizable: suficientes filas y mejor que la
línea base. Si no, las pantallas no muestran precio esperado.
"""
import json
from functools import lru_cache
from statistics import mean

import numpy as np
from sqlalchemy import inspect

from .. import config, db

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


# ---------- exactitud como indicador ----------
SIN_DATOS = "sin datos todavía"


def _esperado(precio, rasgos: dict) -> float | None:
    """El precio esperado que se mostró al decidir. Si la opción solo guardó «frente_esperado» (diferencia en % redondeada),
    se reconstruye desde el precio: el error de ese redondeo es de medio punto como mucho."""
    if rasgos.get("esperado"):
        return float(rasgos["esperado"])
    frente = rasgos.get("frente_esperado")
    return round(float(precio) / (1 + frente / 100), 2) if frente is not None and precio and frente > -100 else None


def _errores(pares: list[tuple[float, float]]) -> dict:
    if not pares:
        return {"filas": 0, "mae": None, "mape": None}
    return {"filas": len(pares), "mae": round(mean(abs(r - e) for r, e in pares), 2),
            "mape": round(mean(abs(r - e) / r for r, e in pares) * 100, 1)}


def _pagados() -> dict[int, float]:
    """Precio pagado por viaje, si ya existe la tabla de compras (la crea el frente de compras)."""
    if not inspect(db.motor).has_table("compras"):
        return {}
    columnas = {c["name"] for c in inspect(db.motor).get_columns("compras")}
    if not {"viaje_id", "precio_pagado"} <= columnas:
        return {}
    return {r["viaje_id"]: float(r["precio_pagado"])
            for r in db.todos("select viaje_id, precio_pagado from compras where precio_pagado is not null and viaje_id is not null")}


def exactitud(f: dict | None = None) -> dict:
    """MAE y MAPE del precio esperado frente al precio del buscador al decidir (cada vuelo mostrado) y, si hay compras,
    frente a lo pagado (el vuelo elegido). En total, por ruta y por mes. Filtros: proyecto, desde y hasta."""
    f = f or {}
    cond, par = ["e.tipo='vuelo'", "e.precio is not null"], {}
    if f.get("proyecto_id"):
        cond.append("s.proyecto_id=:p"); par["p"] = int(f["proyecto_id"])
    if f.get("desde"):
        cond.append("e.creado>=:desde"); par["desde"] = f["desde"]
    if f.get("hasta"):
        cond.append("e.creado<=:hasta"); par["hasta"] = f["hasta"] + " 99"
    filas = db.todos(f"""select e.precio, e.rasgos, e.creado, e.elegida, s.origen, s.destino,
                                (select v.id from viajes v where v.decision_id=e.decision_id) viaje_id
                         from elecciones e join solicitudes s on s.id=e.solicitud_id where {' and '.join(cond)}""", **par)
    pagados = _pagados()
    pares, por_ruta, por_mes, contra_pagado = [], {}, {}, []
    for r in filas:
        esperado = _esperado(r["precio"], db.de_json(r["rasgos"], {}) or {})
        if not esperado:
            continue
        par_ = (float(r["precio"]), esperado)
        pares.append(par_)
        por_ruta.setdefault(f"{r['origen']} → {r['destino']}", []).append(par_)
        por_mes.setdefault((r["creado"] or "")[:7], []).append(par_)
        if r["elegida"] and r["viaje_id"] in pagados:
            contra_pagado.append((pagados[r["viaje_id"]], esperado))
    return {**_errores(pares), "mensaje": None if pares else SIN_DATOS,
            "por_ruta": sorted(({"ruta": k, **_errores(v)} for k, v in por_ruta.items()), key=lambda x: (-x["filas"], x["ruta"])),
            "por_mes": [{"mes": k, **_errores(v)} for k, v in sorted(por_mes.items())],
            "contra_pagado": _errores(contra_pagado) if contra_pagado else None}
