"""Recorrido de viajes con los precios reales guardados: nunca llama al buscador."""
from app import db
from app.aeropuertos import resolver
from app.main import _comparacion

FORM = dict(proyecto_id=1, viajero_id=1, origen="Miami (MIA)", destino="las vegas", ciudad="", ida="2026-12-08",
            regreso="2026-12-11", llegar_antes="2026-12-08T18:00", baterias_n=4, baterias_wh=77, maleta="on",
            prob_cambio=25, carro_dia=65, solicitado_por="Pruebas")


def _crear(cliente, **cambios):
    r = cliente.post("/viajes", data={**FORM, **cambios}, follow_redirects=False)
    destino = r.headers["location"]
    return int(destino.rsplit("/", 1)[1]) if destino.startswith("/viajes/") and "error" not in destino else destino


def test_caso_guardado_recomienda_por_costo_total(cliente):
    sid = _crear(cliente)
    c = _comparacion(sid)
    assert c["vuelos"] and c["descartados"] and c["hoteles"]
    assert c["vuelos"][0]["ev"]["total"] <= c["vuelos"][-1]["ev"]["total"]
    assert c["mas_barato"]["v"]["precio"] == 279 and c["vuelos"][0]["v"]["numeros"] == ["AA 1851"]
    assert db.uno("select ahorro_potencial a from solicitudes where id=:i", i=sid)["a"] is not None
    assert cliente.get(f"/viajes/{sid}").status_code == 200


def test_hora_limite_sigue_a_la_fecha_de_ida(cliente):
    """Cambiar solo las fechas no debe descartar todos los vuelos por una hora límite de otro día."""
    sid = _crear(cliente, ida="2026-12-09", regreso="2026-12-12", llegar_antes="2026-12-08T18:00")
    assert db.uno("select llegar_antes l from solicitudes where id=:i", i=sid)["l"] == "2026-12-09T18:00"


def test_entradas_invalidas_no_crean_solicitud(cliente):
    for cambios in (dict(ida="no-es-fecha"), dict(regreso="2026-12-01"), dict(origen="xyz123")):
        assert "error" in str(_crear(cliente, **cambios)), cambios


def test_decidir_sin_hotel_y_ficha(cliente):
    sid = _crear(cliente, origen="LIM", destino="SCL", ciudad="Ciudad sin datos")   # ruta sin respaldo: sin vuelos ni hoteles
    assert _comparacion(sid)["vuelos"] == []
    assert cliente.post(f"/viajes/{sid}/decidir", data={}, follow_redirects=False).status_code == 303   # no rompe
    assert cliente.get("/analitica").status_code == 200

    sid = _crear(cliente)
    vuelo = _comparacion(sid)["vuelos"][0]["id"]
    r = cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": vuelo, "motivo": "Sin hotel"}, follow_redirects=True)
    assert r.status_code == 200 and "Sin hotel en esta decisión" in r.text


def test_aeropuertos():
    assert resolver("Lisboa (LIS)") == ("LIS", "Lisboa") and resolver("medellin")[0] == "MDE"
    assert resolver("SMF")[0] == "SMF" and resolver("xyz123") is None
