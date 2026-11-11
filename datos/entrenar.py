"""Entrena el modelo de precio esperado de un vuelo y publica sus métricas.

Uso:  python -m datos.entrenar
Lee la tabla `observaciones` y escribe datos/modelo/precio.json y datos/modelo/ficha.json.

Validación: cada búsqueda completa queda en entrenamiento o en prueba, nunca partida,
porque los vuelos de una misma búsqueda se parecen entre sí y partirla inflaría el resultado.
El modelo se compara con una línea base: la mediana de precio de la ruta.
"""
import json

import numpy as np
import pandas as pd
import xgboost as xgb

from app import config, db
from app.servicios.modelo import CATEGORICAS, VARIABLES, codificar

DIR = config.RAIZ / "datos" / "modelo"
MINIMO_FILAS = 200
PARAMETROS = {"objective": "reg:squarederror", "max_depth": 4, "eta": 0.08, "subsample": 0.85,
              "colsample_bytree": 0.85, "min_child_weight": 3, "seed": 7}
RONDAS = 250
PLIEGUES = 5


def _errores(real, estimado) -> dict:
    return {"mae": round(float(np.mean(np.abs(real - estimado))), 2),
            "mape": round(float(np.mean(np.abs(real - estimado) / real)) * 100, 1)}


def main():
    db.crear_tablas()
    df = pd.DataFrame(db.todos("select * from observaciones"))
    if df.empty:
        raise SystemExit("No hay observaciones. Ejecuta primero: python -m datos.recolectar")
    df["ruta"] = df["origen"] + "-" + df["destino"]
    categorias = {c: sorted(df[c].dropna().unique().tolist()) for c in CATEGORICAS}
    X = codificar(df, categorias)
    y = np.log(df["precio"].to_numpy())
    grupos = df["busqueda"].to_numpy()

    # Validación cruzada por grupos
    unicos = np.random.default_rng(7).permutation(np.unique(grupos))
    k = min(PLIEGUES, len(unicos))
    pred_modelo, pred_base = np.zeros(len(df)), np.zeros(len(df))
    if k >= 2:
        for i in range(k):
            prueba = np.isin(grupos, unicos[i::k])
            entren = ~prueba
            m = xgb.train(PARAMETROS, xgb.DMatrix(X[entren], label=y[entren], feature_names=VARIABLES), RONDAS)
            pred_modelo[prueba] = np.exp(m.predict(xgb.DMatrix(X[prueba], feature_names=VARIABLES)))
            medianas = df[entren].groupby("ruta")["precio"].median()
            pred_base[prueba] = df[prueba]["ruta"].map(medianas).fillna(df[entren]["precio"].median()).to_numpy()
        precio = df["precio"].to_numpy()
        metricas = {"modelo": _errores(precio, pred_modelo), "linea_base": _errores(precio, pred_base)}
    else:
        metricas = {"modelo": None, "linea_base": None}

    final = xgb.train(PARAMETROS, xgb.DMatrix(X, label=y, feature_names=VARIABLES), RONDAS)
    ganancia = final.get_score(importance_type="gain")
    suma = sum(ganancia.values()) or 1
    supera = bool(metricas["modelo"] and metricas["modelo"]["mae"] < metricas["linea_base"]["mae"])
    suficiente = len(df) >= MINIMO_FILAS
    ficha = {
        "entrenado": db.ahora(), "filas": int(len(df)), "busquedas": int(len(unicos)), "rutas": int(df["ruta"].nunique()),
        "capturas": sorted(df["capturado"].unique().tolist()), "variables": VARIABLES, "categorias": categorias,
        "metricas": metricas, "supera_linea_base": supera, "datos_suficientes": suficiente,
        "utilizable": supera and suficiente,
        "importancia": sorted(({"variable": v, "peso": round(g / suma, 3)} for v, g in ganancia.items()),
                              key=lambda d: -d["peso"]),
        "validacion": f"{k} pliegues por búsqueda completa", "minimo_filas": MINIMO_FILAS,
    }
    DIR.mkdir(parents=True, exist_ok=True)
    final.save_model(DIR / "precio.json")
    (DIR / "ficha.json").write_text(json.dumps(ficha, ensure_ascii=False, indent=2))
    print(json.dumps({k: ficha[k] for k in ("filas", "busquedas", "rutas", "metricas", "supera_linea_base",
                                             "datos_suficientes", "utilizable")}, ensure_ascii=False, indent=2))
    print("Importancia:", ", ".join(f"{d['variable']} {d['peso']:.0%}" for d in ficha["importancia"][:6]))


if __name__ == "__main__":
    main()
