"""Cotizar por la API v1: el servicio de cotización y sus endpoints. Contrato en `contracts/api-v1.md`.

El buscador nunca sale a internet: se usan las respuestas guardadas (Miami → Las Vegas, Miami → Moab) o un doble.
"""
import json

import pytest

from app import db
from app.servicios import acceso, cotizacion, viajes

MOAB = {"nombre": "Moab", "region": "Utah", "pais": "Estados Unidos", "lat": 38.57332, "lon": -109.54984}


def _cuenta(correo: str) -> dict:
    return db.uno("select * from usuarios where correo=:c", c=correo)


def _datos(**cambios) -> dict:
    """Miami → Las Vegas del 8 al 11 de diciembre de 2026: tiene respuesta guardada."""
    return {"proyecto_id": 1, "viajero_id": 1, "origen": "Miami (MIA)", "destino": "las vegas", "ida": "2026-12-08",
            "regreso": "2026-12-11", "llegar_antes": "2026-12-08T18:00", "baterias_n": 4, "baterias_wh": 77, "maleta": True,
            "prob_cambio": 25, "carro_dia": 65, "para_otra_persona": True, **cambios}


# ---------- pieza 1: el servicio que comparten las pantallas y la API ----------
def test_el_servicio_crea_busca_compara_y_decide(cliente):
    admin = _cuenta("admin@demo.local")
    sid = cotizacion.crear(admin, **_datos())
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["origen"], s["destino"], s["estado"], s["usuario_id"]) == ("MIA", "LAS", "comparando", admin["id"])
    ev = db.uno("select fuente from eventos where entidad='solicitud' and entidad_id=:i and paso='solicitud recibida'", i=sid)
    assert ev["fuente"] == f"formulario · {admin['nombre']}"
    c = cotizacion.comparacion(sid)
    assert c["vuelos"] and c["mas_barato"] and c["hoteles"]
    assert [v["ev"]["total"] for v in c["vuelos"]] == sorted(v["ev"]["total"] for v in c["vuelos"])
    r = cotizacion.decidir(admin, sid, c["vuelos"][0]["id"], c["hoteles"][0]["id"], "", ["costo_total"])
    assert not r["repetida"] and r["viaje"]["estado"] == "pendiente_aprobacion"
    assert viajes.de_solicitud(sid)["id"] == r["viaje"]["id"]
    # el mismo envío otra vez no duplica la decisión
    otra = cotizacion.decidir(admin, sid, c["vuelos"][0]["id"], c["hoteles"][0]["id"], "", ["costo_total"])
    assert otra["repetida"] and otra["decision_id"] == r["decision_id"]
    assert db.uno("select count(*) n from decisiones where solicitud_id=:s", s=sid)["n"] == 1


def test_el_servicio_dice_que_dato_falla(cliente):
    admin = _cuenta("admin@demo.local")
    antes = db.uno("select count(*) n from solicitudes")["n"]
    casos = [(dict(destino="Moab", destino_aeropuertos="ZZZ"), "destino", 'No reconozco "ZZZ"'),
             (dict(origen="xyz123"), "origen", "No reconozco"),
             (dict(ida="no-es-fecha"), "ida", "Las fechas no son válidas."),
             (dict(regreso="2026-12-01"), "regreso", "El regreso debe ser posterior a la ida."),
             (dict(viajero_id=0), "viajero_id", "Elige quién viaja.")]
    for cambios, campo, texto in casos:
        with pytest.raises(cotizacion.CotizacionInvalida) as e:
            cotizacion.crear(admin, **_datos(**cambios))
        assert e.value.campo == campo and str(e.value).startswith(texto), cambios
    assert db.uno("select count(*) n from solicitudes")["n"] == antes


def test_el_servicio_acepta_el_lugar_como_objeto(cliente):
    """La API manda el lugar ya armado; el formulario, como texto JSON. Los dos llegan igual a la base."""
    admin = _cuenta("admin@demo.local")
    sid = cotizacion.crear(admin, **_datos(destino="Moab", destino_aeropuertos="SLC,CNY,GJT", destino_lugar=MOAB))
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["destino"], s["destino_aeropuertos"], s["ciudad"]) == ("CNY", "CNY,GJT,SLC", "Moab")
    assert db.de_json(s["destino_lugar"]) == MOAB
    assert cotizacion.lugar({"nombre": "Moab", "lat": 999, "lon": 0}) is None   # coordenadas imposibles
    assert cotizacion.lugar(json.dumps(MOAB)) == MOAB


def test_el_servicio_explica_por_que_no_guarda_la_decision(cliente):
    admin = _cuenta("admin@demo.local")
    sid = cotizacion.crear(admin, **_datos())
    vuelos = cotizacion.comparacion(sid)["vuelos"]
    with pytest.raises(cotizacion.DecisionInvalida) as e:
        cotizacion.decidir(admin, sid, 0)
    assert e.value.campo == "vuelo_id"
    with pytest.raises(cotizacion.DecisionInvalida) as e:
        cotizacion.decidir(admin, sid, vuelos[1]["id"], motivo="no")
    assert e.value.campo == "motivo" and "distinta a la recomendada" in str(e.value)
    assert not db.uno("select id from decisiones where solicitud_id=:s", s=sid)
    # con el presupuesto aprobado, la decisión ya no cambia sin reabrir el viaje
    v = cotizacion.decidir(admin, sid, vuelos[0]["id"])["viaje"]
    db.actualizar("viajes", v["id"], estado="aprobado")
    with pytest.raises(cotizacion.DecisionBloqueada) as e:
        cotizacion.decidir(admin, sid, vuelos[1]["id"], motivo="Prefiero el horario de la tarde")
    assert v["codigo"] in str(e.value)
    with pytest.raises(LookupError):
        cotizacion.decidir(admin, 10**9, 1)


def test_las_pantallas_usan_el_servicio():
    from app.rutas import cotizaciones
    assert cotizaciones._comparacion is cotizacion.comparacion
    assert cotizaciones._completar_ahorros is cotizacion.completar_ahorros
    assert acceso.es_admin(_cuenta("admin@demo.local"))
