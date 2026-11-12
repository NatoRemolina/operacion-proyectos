"""Prepara la demostración del monitoreo del vuelo, solo en local.

Uso:
    python -m datos.demo_monitoreo          (en Docker: make demo-monitoreo)

Deja un viaje aprobado de Madrid a Lisboa del 13 al 16 de diciembre de 2026 con el tramo IB 5634 (09:05 → 09:30), el
vuelo de la respuesta guardada de ejemplo `datos/respaldo/estado_vuelo_IB5634_2026-12-13.json`. Es idempotente: si el
viaje ya existe lo reutiliza y reinicia su tramo (estado, consultas y avisos), para repetir la demostración. No hace
consultas en vivo: sin clave del buscador, el tablero lee la respuesta de ejemplo.

Después hay que fijar el «ahora» del monitoreo dentro de la ventana del vuelo (variable `MONITOREO_AHORA`, que solo
se respeta en local) y abrir «Viajes» en administración.
"""
import json
import sys

from app import config, db
from app.servicios import eventos, monitoreo_vuelos, viajes

FUENTE = "preparador de la demostración"
AHORA = "2026-12-13T06:00"   # UTC: dentro de la ventana del vuelo (05:05 a 09:30 UTC, o la llegada estimada)
IDA, REGRESO, LIMITE = "2026-12-13", "2026-12-16", "2026-12-13T12:00"   # llegar a Lisboa antes del mediodía
TRAMO = {"aerolinea": "Iberia", "numero": "IB 5634", "desde": "MAD", "hasta": "LIS",
         "sale": "2026-12-13 09:05", "llega": "2026-12-13 09:30"}
LISBOA_GEONAMES = 2267057


def _uno(sql: str, **p) -> dict | None:
    return db.uno(sql, **p)


def _cuentas() -> tuple[dict | None, dict | None]:
    """La colaboradora de demostración con base en Madrid (o, si no está, otra cuenta con perfil de viajero) y una
    cuenta de administración que apruebe: nadie aprueba lo suyo."""
    colaborador = (_uno("select * from usuarios where correo='piloto2@demo.local' and activo=1 and viajero_id is not null")
                   or _uno("select * from usuarios where rol='colaborador' and activo=1 and viajero_id is not null order by id limit 1"))
    admin = _uno("select * from usuarios where rol='admin' and activo=1 and id<>:i order by id limit 1",
                 i=colaborador["id"] if colaborador else 0)
    return colaborador, admin


def _lugar_lisboa() -> dict | None:
    l = _uno("select nombre, region, pais, lat, lon from lugares where id=:i", i=LISBOA_GEONAMES)
    return {"nombre": "Lisboa", "region": l["region"] or "", "pais": "Portugal", "lat": l["lat"], "lon": l["lon"]} if l else None


def preparar() -> dict:
    """Crea o reutiliza el viaje de la demostración. Devuelve {"hecho", "mensaje", "viaje_id", "creado", "ahora"}."""
    # Igual que la siembra: en local y solo sobre SQLite o una base marcada como desechable (PREPARAR_BASE_LOCAL=1).
    # Así nunca escribe en la base publicada aunque .env apunte a ella.
    if not config.PREPARAR_BASE_LOCAL:
        return {"hecho": False, "mensaje": "Solo se prepara en local sobre una base desechable "
                                           "(SQLite o PREPARAR_BASE_LOCAL=1): no se escribió nada."}
    colaborador, admin = _cuentas()
    if not colaborador or not admin:
        return {"hecho": False, "mensaje": "Faltan las cuentas de demostración (CUENTAS_DEMO=1): no se escribió nada."}
    proyecto = _uno("select id, nombre from proyectos where ciudad='Lisboa' order by id limit 1") \
        or _uno("select id, nombre from proyectos order by id limit 1")
    previa = _uno("""select s.id solicitud_id, v.id viaje_id from solicitudes s join viajes v on v.solicitud_id=s.id
                     where s.solicitado_por=:f and s.origen='MAD' and s.destino='LIS' and s.ida=:ida order by s.id limit 1""",
                  f=FUENTE, ida=IDA)
    creado = previa is None
    if creado:
        lugar = _lugar_lisboa()
        sid = db.insertar("solicitudes", proyecto_id=proyecto["id"], viajero_id=colaborador["viajero_id"], origen="MAD",
                          destino="LIS", ciudad="Lisboa", ida=IDA, regreso=REGRESO, llegar_antes=LIMITE, baterias_n=0,
                          baterias_wh=0, maleta=0, prob_cambio=0, carro_dia=0, estado="decidido", creado=db.ahora(),
                          solicitado_por=FUENTE, usuario_id=colaborador["id"], destino_lugar=json.dumps(lugar) if lugar else None)
        sol = _uno("select * from solicitudes where id=:i", i=sid)
        # Sin tiquete comprado ni decisión: el presupuesto es el de los viáticos del viaje
        total, lineas = viajes.presupuesto_de({"desglose": {"lineas": []}}, sol)
        vid = db.insertar("viajes", solicitud_id=sid, proyecto_id=proyecto["id"], usuario_id=colaborador["id"],
                          viajero_id=colaborador["viajero_id"], ida=IDA, regreso=REGRESO, presupuesto_usd=total,
                          presupuesto_detalle=lineas, estado="aprobado", aprobado_por=admin["id"], aprobado_en=db.ahora(),
                          creado=db.ahora())
        eventos.registrar("solicitud", sid, "preparado para la demostración",
                          f"MAD → Lisboa {IDA} a {REGRESO}, llegar antes de {LIMITE[11:]} · {colaborador['nombre']}", FUENTE)
    else:
        sid, vid = previa["solicitud_id"], previa["viaje_id"]
        db.actualizar("viajes", vid, estado="aprobado", aprobado_por=admin["id"], aprobado_en=db.ahora())
    # Reemplaza el tramo: la demostración vuelve a empezar desde «programado», sin consultas ni avisos
    monitoreo_vuelos.registrar_tramos(vid, {"aerolinea": TRAMO["aerolinea"], "numeros": [TRAMO["numero"]], "sale": TRAMO["sale"],
                                            "llega": TRAMO["llega"], "desde": "MAD", "hasta": "LIS", "tramos": [TRAMO]}, None)
    v = viajes.uno(vid)
    eventos.registrar("viaje", vid, "preparado para la demostración",
                      f"{v['codigo']} · {'creado' if creado else 'reutilizado'}; tramo {TRAMO['numero']} {TRAMO['sale']} "
                      f"→ {TRAMO['llega'][11:]} reiniciado · aprobado por {admin['nombre']}", FUENTE)
    t = _uno("select * from tramos_vuelo where viaje_id=:v", v=vid)
    inicio, fin = monitoreo_vuelos.ventana(t)
    return {"hecho": True, "creado": creado, "viaje_id": vid, "codigo": v["codigo"], "ahora": AHORA,
            "mensaje": (f"Viaje {v['codigo']} {'creado' if creado else 'reutilizado'}: {colaborador['nombre']}, "
                        f"{proyecto['nombre']}, MAD → Lisboa {IDA} a {REGRESO}, llegar antes de las {LIMITE[11:]}, aprobado.\n"
                        f"Tramo {TRAMO['numero']} {TRAMO['sale']} → {TRAMO['llega'][11:]} (horas locales); ventana del monitoreo "
                        f"de {inicio:%H:%M} a {fin:%H:%M} UTC del {inicio:%d/%m/%Y}.")}


def main() -> int:
    r = preparar()
    print(r["mensaje"])
    if not r["hecho"]:
        return 1
    print(f"\nFija el «ahora» del monitoreo en la app (solo vale en local) y reiníciala:\n    MONITOREO_AHORA={r['ahora']}\n"
          "Después abre «Viajes» en administración: el tablero consulta el tramo con la respuesta de ejemplo "
          "(sin gastar búsquedas) y lo muestra retrasado 20 min, terminal 4, puerta J58.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
