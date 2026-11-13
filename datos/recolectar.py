"""Recolecta precios reales de varias rutas y anticipaciones para entrenar el modelo.

Uso:  python -m datos.recolectar --max 40                 (gasta una consulta del buscador por búsqueda nueva)
      python -m datos.recolectar --simular                (muestra qué buscaría, sin gastar nada)
      python -m datos.recolectar --frecuentes             (las 5 rutas más cotizadas; tope diario y solo si RECOLECTOR=encendido)
      python -m datos.recolectar --frecuentes --simular   (el plan del día, sin gastar nada, aunque esté apagado)
No repite búsquedas que ya están guardadas (carpeta datos/respaldo/ o tabla `busquedas`).
La programación diaria y su costo están en docs/datos-para-modelos.md.
"""
import argparse
import time
from datetime import date, timedelta

from app import config, db
from app.servicios import costo, eventos, precios, rutas_frecuentes

RUTAS = [
    ("MIA", "LAS"), ("JFK", "LAX"), ("LAX", "LAS"), ("DFW", "DEN"), ("ATL", "ORD"), ("MIA", "JFK"),
    ("MAD", "LIS"), ("MAD", "BCN"), ("LHR", "MAD"), ("CDG", "FCO"),
]
ANTICIPACIONES = [7, 21, 45, 75]
NOCHES = 3
RUTAS_FRECUENTES = 5
TOPE_DIA = 10   # valor inicial de la regla editable `recoleccion_busquedas_dia`


def plan(rutas=RUTAS, hoy: date | None = None) -> list[tuple[str, str, str, str]]:
    hoy = hoy or date.today()
    busquedas = []
    for dias in ANTICIPACIONES:  # por anticipación primero: si se corta, todas las rutas quedan cubiertas
        for origen, destino in rutas:
            ida = hoy + timedelta(days=dias)
            busquedas.append((origen, destino, ida.isoformat(), (ida + timedelta(days=NOCHES)).isoformat()))
    return busquedas


def _guardada(b: tuple) -> bool:
    nombre = f"vuelos_{b[0]}_{b[1]}_{b[2]}_{b[3]}.json"
    return (config.DIR_RESPALDO / nombre).is_file() or bool(db.uno("select id from busquedas where clave=:c limit 1", c=nombre))


def asegurar_regla():
    """El tope diario del recolector, editable en Reglas. Nunca pisa un valor editado."""
    if not db.uno("select id from reglas where ambito='supuesto' and clave='recoleccion_busquedas_dia'"):
        db.insertar("reglas", ambito="supuesto", entidad="", tarifa="", clave="recoleccion_busquedas_dia", valor=str(TOPE_DIA),
                    nota="Búsquedas pagas que el recolector de rutas frecuentes puede gastar al día (unas 300 al mes con 10).",
                    fuente="Supuesto editable", confianza="supuesto", verificado=db.ahora()[:10])


def hechas_hoy() -> int:
    return db.uno("select count(*) n from eventos where entidad='recolector' and paso='búsqueda recolectada' and momento>=:d",
                  d=db.ahora()[:10])["n"]


def plan_frecuentes(hoy: date | None = None) -> list[tuple[str, str, str, str]]:
    """Las búsquedas que tocan hoy: las rutas más cotizadas, sin las ya guardadas y hasta el tope del día."""
    asegurar_regla()
    tope = int(costo.supuesto(costo.catalogo(), "recoleccion_busquedas_dia", TOPE_DIA))
    rutas = [(r["origen"], r["destino"]) for r in rutas_frecuentes.top(n=RUTAS_FRECUENTES)]
    return [b for b in plan(rutas, hoy) if not _guardada(b)][:max(tope - hechas_hoy(), 0)]


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=40, help="tope de consultas nuevas")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--frecuentes", action="store_true", help="rutas más cotizadas con el tope diario de Reglas")
    args = ap.parse_args(argv)
    db.crear_tablas()
    if args.frecuentes:
        pendientes = plan_frecuentes()
        print(f"Rutas frecuentes: {len(pendientes)} búsquedas para hoy (ya hechas hoy: {hechas_hoy()}).")
    else:
        pendientes = [b for b in plan() if not _guardada(b)][:args.max]
        print(f"{len(pendientes)} búsquedas nuevas posibles; tope {args.max}.")
    if args.simular:
        for b in pendientes:
            print("  ", *b)
        return
    if args.frecuentes and config.RECOLECTOR != "encendido":
        raise SystemExit("El recolector está apagado (RECOLECTOR=apagado): no se gastó ninguna búsqueda. "
                         "Usa --simular para ver el plan.")
    if not config.SERPAPI_KEY:
        raise SystemExit("Falta SERPAPI_KEY en .env")
    hechas = 0
    for origen, destino, ida, regreso in pendientes:
        vuelos, origen_dato, _ = precios.buscar_vuelos(origen, destino, ida, regreso)
        hechas += origen_dato == "en vivo"
        eventos.registrar("recolector", None, "búsqueda recolectada",
                          f"{origen}-{destino} {ida} a {regreso}: {len(vuelos)} vuelos ({origen_dato})", "recolector")
        print(f"  {origen}-{destino} {ida}: {len(vuelos)} vuelos ({origen_dato})")
        time.sleep(1)
    total = db.uno("select count(*) n, count(distinct busqueda) b from observaciones")
    print(f"Consultas gastadas: {hechas}. Conjunto de datos: {total['n']} filas de {total['b']} búsquedas.")


if __name__ == "__main__":
    main()
