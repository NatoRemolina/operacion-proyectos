"""Indicadores del tablero de analítica. Todo sale de datos registrados; nada es simulado."""
from collections import Counter, defaultdict
from datetime import date, timedelta

from .. import db
from . import modelo


def _semana(fecha_iso: str) -> str:
    d = date.fromisoformat(fecha_iso[:10])
    return (d - timedelta(days=d.weekday())).isoformat()


def resumen() -> dict:
    sols = db.todos("""select s.*, v.nombre viajero, p.nombre proyecto from solicitudes s
                       left join viajeros v on v.id=s.viajero_id left join proyectos p on p.id=s.proyecto_id order by s.id""")
    decs = db.todos("select * from decisiones order by id")
    vigentes = list({d["solicitud_id"]: d for d in decs}.values())

    por_semana, por_ruta, por_viajero, por_persona = Counter(), Counter(), Counter(), Counter()
    anticipaciones = []
    for s in sols:
        por_semana[_semana(s["creado"])] += 1
        por_ruta[f"{s['origen']} → {s['destino']}"] += 1
        por_viajero[s["viajero"] or "—"] += 1
        por_persona[s["solicitado_por"] or "sin nombre"] += 1
        anticipaciones.append((date.fromisoformat(s["ida"]) - date.fromisoformat(s["creado"][:10])).days)

    potencial = [s for s in sols if s["ahorro_potencial"] is not None]
    ahorro_potencial = round(sum(s["ahorro_potencial"] for s in potencial), 2)
    capturado = 0.0
    for d in vigentes:
        capturado += (db.de_json(d["desglose"], {}) or {}).get("ahorro") or 0

    # Historial de precio de las rutas consultadas: cuánto costaba en su mejor momento
    historiales = []
    for s in sols:
        clave = f"{s['origen']}_{s['destino']}_{s['ida']}_{s['regreso']}"
        filas = db.todos("select fecha, precio from historial_ruta where busqueda=:b order by fecha", b=clave)
        if filas and not any(h["clave"] == clave for h in historiales):
            precios = [f["precio"] for f in filas]
            historiales.append({"clave": clave, "ruta": f"{s['origen']} → {s['destino']} ({s['ida']})",
                                "fechas": [f["fecha"] for f in filas], "precios": precios,
                                "minimo": min(precios), "actual": precios[-1], "sobre_minimo": round(precios[-1] - min(precios), 2)})

    obs = db.uno("select count(*) n, count(distinct busqueda) b, count(distinct origen || '-' || destino) r, min(capturado) desde from observaciones")
    por_aerolinea = db.todos("""select aerolinea, count(*) n, avg(precio) medio, avg(escalas) escalas from observaciones
                                group by aerolinea having count(*) >= 2 order by n desc limit 10""")

    g = db.uno("""select count(*) n, sum(case when estado='aprobado_auto' then 1 else 0 end) auto,
                  sum(case when estado='aprobado' then 1 else 0 end) manual,
                  sum(case when estado='revision' then 1 else 0 end) revision from gastos""")
    motivos = Counter()
    for fila in db.todos("select detalle from eventos where paso='enviado a revisión'"):
        texto = fila["detalle"] or ""
        for clave, nombre in (("duplicado", "Posible duplicado"), ("Falta", "Campo faltante"), ("Confianza", "Lectura poco confiable"),
                              ("fuera del proyecto", "Fecha fuera del proyecto"), ("no coincide", "Total no cuadra"),
                              ("Sin proyecto", "Sin proyecto"), ("tasa de cambio", "Moneda sin tasa")):
            if clave in texto:
                motivos[nombre] += 1

    semanas = sorted(por_semana)
    return {
        "desde": sols[0]["creado"][:10] if sols else None,
        "consultas": len(sols), "decisiones": len(vigentes),
        "semanas": {"etiquetas": semanas, "valores": [por_semana[s] for s in semanas]},
        "por_ruta": por_ruta.most_common(8), "por_viajero": por_viajero.most_common(8), "por_persona": por_persona.most_common(8),
        "anticipacion_media": round(sum(anticipaciones) / len(anticipaciones)) if anticipaciones else None,
        "ahorro_potencial": ahorro_potencial, "consultas_con_ahorro": sum(1 for s in potencial if s["ahorro_potencial"] > 0),
        "ahorro_capturado": round(capturado, 2),
        "detalle_ahorro": [{"id": s["id"], "ruta": f"{s['origen']} → {s['destino']}", "ida": s["ida"], "por": s["solicitado_por"],
                            "precio_min": s["precio_min_buscador"], "costo_mas_barato": s["costo_mas_barato"],
                            "costo_mejor": s["costo_mejor"], "ahorro": s["ahorro_potencial"], "estado": s["estado"]} for s in potencial],
        "historiales": historiales[:4],
        "observaciones": obs, "por_aerolinea": por_aerolinea,
        "modelo": modelo.ficha(), "modelo_utilizable": modelo.utilizable(),
        "gastos": {"n": g["n"] or 0, "auto": g["auto"] or 0, "manual": g["manual"] or 0, "revision": g["revision"] or 0,
                   "motivos": motivos.most_common()},
    }
