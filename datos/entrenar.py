"""Entrena el modelo de precio esperado de un vuelo y publica sus métricas.

Uso:  python -m datos.entrenar
Lee `observaciones` (un precio por vuelo visto en el buscador) y `ofertas_tarifa` (un precio por tarifa vista, con su tipo,
vendedor, maleta y cambios), las depura al cargarlas (`ofertas.depurar`: nada se borra de la base) y escribe en
datos/modelo/ el modelo (precio.json), su ficha (ficha.json) y la prima de flexibilidad por ruta (prima_flexibilidad.json).

Validación: cada búsqueda completa queda en entrenamiento o en prueba, nunca partida,
porque los vuelos de una misma búsqueda se parecen entre sí y partirla inflaría el resultado.
El modelo se compara con una línea base: la mediana de precio de la ruta.
Si el modelo nuevo no mejora al vigente, el vigente se conserva y el nuevo queda como candidato (precio_candidato.json).
"""
import json

import numpy as np
import pandas as pd
import xgboost as xgb

from app import config, db
from app.servicios import ofertas, rutas_frecuentes
from app.servicios.modelo import CATEGORICAS, RASGOS_TARIFA, VARIABLES, codificar

DIR = config.RAIZ / "datos" / "modelo"
MINIMO_FILAS = 200
PARAMETROS = {"objective": "reg:squarederror", "max_depth": 4, "eta": 0.08, "subsample": 0.85,
              "colsample_bytree": 0.85, "min_child_weight": 3, "seed": 7}
RONDAS = 250
PLIEGUES = 5


def _errores(real, estimado) -> dict:
    return {"mae": round(float(np.mean(np.abs(real - estimado))), 2),
            "mape": round(float(np.mean(np.abs(real - estimado) / real)) * 100, 1)}


def _si_no(valor) -> int | None:
    return None if valor is None else int(bool(valor))


def cargar() -> tuple[pd.DataFrame, dict]:
    """Filas de entrenamiento de las dos fuentes, ya depuradas, y el informe de lo descartado en cada una."""
    obs, informe_obs = ofertas.depurar(db.todos("select * from observaciones"), clave_repetida=("id",),
                                       grupo_atipico=("origen", "destino"))
    filas = [{**{v: o.get(v) for v in VARIABLES}, "ruta": f"{o['origen']}-{o['destino']}", "precio": o["precio"],
              "grupo": f"busqueda:{o['busqueda']}", "capturado": o["capturado"], "fuente": "observaciones"} for o in obs]
    tarifas, informe_tar = ofertas.limpias()
    for t in tarifas:
        filas.append({"ruta": f"{t['origen']}-{t['destino']}", "aerolinea": t["aerolinea"], "dia_semana": t["dia_semana"],
                      "anticipacion": t["anticipacion_dias"], "noches": t["noches"], "tarifa": t["tarifa_normalizada"],
                      "es_aerolinea": t["es_aerolinea"],
                      "incluye_maleta": None if t["maleta_usd"] is None else _si_no(t["maleta_usd"] == 0),
                      "cambio_gratis": None if t["cambios"] is None else _si_no(t["cambios"] == "gratis"),
                      "precio": t["precio"], "grupo": t["origen_fila"], "capturado": (t["momento"] or "")[:10], "fuente": "ofertas"})
    return pd.DataFrame(filas, columns=[*VARIABLES, "precio", "grupo", "capturado", "fuente"]), {
        "observaciones": informe_obs, "ofertas": informe_tar}


def primas(tarifas: list[dict]) -> dict:
    """Tabla simple de la prima de flexibilidad esperada: por ruta y en general (mediana de pares del mismo itinerario)."""
    por_ruta: dict[str, list[dict]] = {}
    for t in tarifas:
        por_ruta.setdefault(f"{t['origen']}-{t['destino']}", []).append(t)
    rutas = {r: p for r, ts in por_ruta.items() if (p := rutas_frecuentes.prima_flexibilidad(ts))}
    return {"entrenado": db.ahora(), "rutas": rutas, "general": rutas_frecuentes.prima_flexibilidad(tarifas),
            "definicion": "Tarifa más barata con cambio gratis o maleta incluida menos la básica más barata del mismo itinerario"}


def _anterior() -> dict | None:
    archivo = DIR / "ficha.json"
    try:
        return json.loads(archivo.read_text()) if archivo.is_file() else None
    except ValueError:
        return None


def main():
    db.crear_tablas()
    ofertas.actualizar()   # lo último que se haya leído entra antes de entrenar
    df, limpieza = cargar()
    if df.empty:
        raise SystemExit("No hay observaciones ni tarifas. Ejecuta primero: python -m datos.recolectar")
    categorias = {c: sorted(df[c].dropna().unique().tolist()) for c in CATEGORICAS}
    X = codificar(df, categorias, VARIABLES)
    y = np.log(df["precio"].astype(float).to_numpy())
    grupos = df["grupo"].to_numpy()

    # Validación cruzada por grupos
    unicos = np.random.default_rng(7).permutation(np.unique(grupos))
    k = min(PLIEGUES, len(unicos))
    pred_modelo, pred_base = np.zeros(len(df)), np.zeros(len(df))
    precio = df["precio"].astype(float).to_numpy()
    if k >= 2:
        for i in range(k):
            prueba = np.isin(grupos, unicos[i::k])
            entren = ~prueba
            m = xgb.train(PARAMETROS, xgb.DMatrix(X[entren], label=y[entren], feature_names=VARIABLES), RONDAS)
            pred_modelo[prueba] = np.exp(m.predict(xgb.DMatrix(X[prueba], feature_names=VARIABLES)))
            medianas = df[entren].groupby("ruta")["precio"].median()
            pred_base[prueba] = df[prueba]["ruta"].map(medianas).fillna(df[entren]["precio"].median()).to_numpy()
        metricas = {"modelo": _errores(precio, pred_modelo), "linea_base": _errores(precio, pred_base)}
    else:
        metricas = {"modelo": None, "linea_base": None}

    final = xgb.train(PARAMETROS, xgb.DMatrix(X, label=y, feature_names=VARIABLES), RONDAS)
    ganancia = final.get_score(importance_type="gain")
    suma = sum(ganancia.values()) or 1
    supera = bool(metricas["modelo"] and metricas["modelo"]["mae"] < metricas["linea_base"]["mae"])
    suficiente = len(df) >= MINIMO_FILAS
    anterior = _anterior()
    mae_anterior = ((anterior or {}).get("metricas") or {}).get("modelo") or {}
    # Se reemplaza si no hay modelo vigente o si el nuevo tiene menor error. Con datos distintos la comparación es
    # aproximada; ante la duda se conserva el vigente y el nuevo queda como candidato para revisarlo
    reemplaza = not mae_anterior.get("mae") or bool(metricas["modelo"] and metricas["modelo"]["mae"] < mae_anterior["mae"])
    ficha = {
        "version": int((anterior or {}).get("version") or (1 if anterior else 0)) + 1,
        "entrenado": db.ahora(), "filas": int(len(df)), "busquedas": int(len(unicos)), "rutas": int(df["ruta"].nunique()),
        "fuentes": {f: int((df["fuente"] == f).sum()) for f in ("observaciones", "ofertas")},
        "capturas": sorted(c for c in df["capturado"].dropna().unique().tolist() if c), "variables": VARIABLES,
        "rasgos_opcionales": RASGOS_TARIFA, "categorias": categorias,
        "metricas": metricas, "supera_linea_base": supera, "datos_suficientes": suficiente,
        "utilizable": supera and suficiente, "reemplaza": reemplaza, "limpieza": limpieza,
        "importancia": sorted(({"variable": v, "peso": round(g / suma, 3)} for v, g in ganancia.items()),
                              key=lambda d: -d["peso"]),
        "validacion": f"{k} pliegues por búsqueda completa", "minimo_filas": MINIMO_FILAS,
    }
    DIR.mkdir(parents=True, exist_ok=True)
    sufijo = ("", "") if reemplaza else ("_candidato", "_candidata")
    final.save_model(DIR / f"precio{sufijo[0]}.json")
    (DIR / f"ficha{sufijo[1]}.json").write_text(json.dumps(ficha, ensure_ascii=False, indent=2))
    (DIR / "prima_flexibilidad.json").write_text(json.dumps(primas(ofertas.limpias()[0]), ensure_ascii=False, indent=2))
    print(json.dumps({k: ficha[k] for k in ("version", "filas", "fuentes", "busquedas", "rutas", "metricas", "supera_linea_base",
                                             "datos_suficientes", "utilizable", "reemplaza")}, ensure_ascii=False, indent=2))
    print("Descartados al depurar:", json.dumps({f: i["descartes"] for f, i in limpieza.items()}, ensure_ascii=False))
    if not reemplaza:
        print(f"El modelo vigente (MAE {mae_anterior['mae']}) se conserva; el nuevo quedó en precio_candidato.json.")
    print("Importancia:", ", ".join(f"{d['variable']} {d['peso']:.0%}" for d in ficha["importancia"][:6]))


if __name__ == "__main__":
    main()
