"""La forma en que la API v1 entrega la lectura de la página de un vuelo y la evidencia guardada de la decisión.

La usan la cotización (`rutas/v1_analisis.py`) y la bandeja de compras (`rutas/v1_compras.py`): las rutas no se
importan entre sí. Los datos los traen los servicios.
"""
from ..servicios import analizador, capturas, consultas, cotizacion, enlaces
from . import PREFIJO


def con_enlaces(tarifas: list, sesion: str, sid: int, opcion_id: int) -> list:
    """Cada tarifa con su «Ir a…» firmado para esta sesión (sin sesión, sin enlace)."""
    return [{**t, "ir_url": enlaces.url_ir(sesion, sid, opcion_id, str(t.get("vendedor") or ""), str(t.get("nombre") or ""))
             if sesion and t.get("vendedor") and t.get("nombre") else None} for t in tarifas if isinstance(t, dict)]


def analisis(sid: int, opcion_id: int, a: dict, sesion: str = "") -> dict:
    """La lectura de la página de un vuelo como la entrega la API (`AnalisisVuelo`)."""
    precio = cotizacion.precio_de_opcion(opcion_id)
    return {"id": a["id"], "opcion_id": opcion_id, "estado": a["estado"], "motivo": a["motivo"], "url": a["url"],
            "leido": consultas.instante(a["terminado"]) if a.get("terminado") else None, "duracion_ms": a["duracion_ms"],
            "reutilizado": bool(a.get("reutilizado")), "precio_buscador_usd": consultas.dinero(precio),
            "aviso_precio": analizador.aviso_precio(a, precio) if a["estado"] == "listo" else None,
            "datos": {**a["datos"], "tarifas": con_enlaces(a["datos"].get("tarifas") or [], sesion, sid, opcion_id)}
            if a["estado"] == "listo" and isinstance(a.get("datos"), dict) else None,
            "extracto": (a["datos"] or {}).get("extracto") if a["estado"] == "fallido" else None,
            "captura_url": f"{PREFIJO}/cotizaciones/{sid}/analisis/{a['id']}/captura" if a.get("captura") else None}


def evidencia(sid: int) -> dict:
    """Las capturas de la decisión vigente (al decidir, el seguimiento y la compra) y la línea de precios del vuelo."""
    filas = capturas.de_la_decision_vigente(sid)
    base = f"{PREFIJO}/cotizaciones/{sid}/evidencia"
    lista = [{"id": f["id"], "tipo": f["tipo"], "motivo": f["motivo"], "estado": f["estado"], "fallo": f["fallo"],
              "intentos": f["intentos"], "creado": consultas.instante(f["creado"]), "terminado": consultas.instante(f["terminado"]),
              "datos": f["datos"] if f["estado"] == "lista" else None,
              "imagenes": [f"{base}/{f['id']}/imagen/{n}" for n in range(len(f["imagenes"]))] if f["estado"] == "lista" else [],
              "texto_url": f"{base}/{f['id']}/texto" if f["estado"] == "lista" and f["texto"] else None} for f in filas]
    listas = [c for c in lista if c["estado"] == "lista"]
    seguimiento = [{"momento": c["terminado"], "motivo": c["motivo"],
                    "precio_google_usd": consultas.dinero(((c["datos"] or {}).get("google") or {}).get("precio_total")),
                    "total_aerolinea_usd": consultas.dinero(((c["datos"] or {}).get("aerolinea") or {}).get("total"))}
                   for c in listas if c["tipo"] == "vuelo"]
    estado = "guardando" if any(c["estado"] in ("pendiente", "en_curso") for c in lista) else \
        "guardada" if listas else "sin_evidencia"
    return {"estado": estado, "guardada": max((c["terminado"] for c in listas if c["terminado"]), default=None),
            "capturas": lista, "seguimiento": sorted(seguimiento, key=lambda p: p["momento"] or "")}
