"""Recolecta precios reales de varias rutas y anticipaciones para entrenar el modelo.

Uso:  python -m datos.recolectar --max 40        (gasta una consulta del buscador por búsqueda nueva)
      python -m datos.recolectar --simular       (muestra qué buscaría, sin gastar nada)
No repite búsquedas que ya están guardadas en datos/respaldo/.
"""
import argparse
import time
from datetime import date, timedelta

from app import config, db
from app.servicios import precios

RUTAS = [
    ("MIA", "LAS"), ("JFK", "LAX"), ("LAX", "LAS"), ("DFW", "DEN"), ("ATL", "ORD"), ("MIA", "JFK"),
    ("MAD", "LIS"), ("MAD", "BCN"), ("LHR", "MAD"), ("CDG", "FCO"),
]
ANTICIPACIONES = [7, 21, 45, 75]
NOCHES = 3


def plan() -> list[tuple[str, str, str, str]]:
    hoy = date.today()
    busquedas = []
    for dias in ANTICIPACIONES:  # por anticipación primero: si se corta, todas las rutas quedan cubiertas
        for origen, destino in RUTAS:
            ida = hoy + timedelta(days=dias)
            busquedas.append((origen, destino, ida.isoformat(), (ida + timedelta(days=NOCHES)).isoformat()))
    return busquedas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40, help="tope de consultas nuevas")
    ap.add_argument("--simular", action="store_true")
    args = ap.parse_args()
    db.crear_tablas()
    pendientes = [b for b in plan() if not (config.DIR_RESPALDO / f"vuelos_{b[0]}_{b[1]}_{b[2]}_{b[3]}.json").is_file()]
    print(f"{len(pendientes)} búsquedas nuevas posibles; tope {args.max}.")
    if args.simular:
        for b in pendientes[:args.max]:
            print("  ", *b)
        return
    if not config.SERPAPI_KEY:
        raise SystemExit("Falta SERPAPI_KEY en .env")
    hechas = 0
    for origen, destino, ida, regreso in pendientes[:args.max]:
        vuelos, origen_dato, _ = precios.buscar_vuelos(origen, destino, ida, regreso)
        hechas += origen_dato == "en vivo"
        print(f"  {origen}-{destino} {ida}: {len(vuelos)} vuelos ({origen_dato})")
        time.sleep(1)
    total = db.uno("select count(*) n, count(distinct busqueda) b from observaciones")
    print(f"Consultas gastadas: {hechas}. Conjunto de datos: {total['n']} filas de {total['b']} búsquedas.")


if __name__ == "__main__":
    main()
