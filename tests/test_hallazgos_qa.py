"""Hallazgos del recorrido de punta a punta del 13 de noviembre: cada prueba reproduce el caso que falló."""
from conftest import FORM_VIAJE


# ---------- I-2: los hoteles se comparan todos antes de recortar ----------
def _hotel_de_buscador(nombre, total, calificacion=4.2):
    return {"nombre": nombre, "noche": round(total / 3, 2), "noche_sin_cargos": None, "total": float(total),
            "calificacion": calificacion, "clase": 3, "vendedores": []}


def test_el_mejor_hotel_despues_del_puesto_12_se_recomienda(cliente, monkeypatch):
    from app.servicios import cotizacion, precios
    caros = [_hotel_de_buscador(f"Independiente {i}", 400 + i) for i in range(13)]
    respuesta = caros + [_hotel_de_buscador("Independiente Barato", 150), _hotel_de_buscador("Barato mal calificado", 120, 3.0)]
    monkeypatch.setattr(precios, "buscar_hoteles", lambda *a, **k: (list(respuesta), "guardado"))
    r = cliente.post("/viajes", data={**FORM_VIAJE}, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1])
    c = cotizacion.comparacion(sid)
    assert c["hotel_recomendado"]["h"]["nombre"] == "Independiente Barato"
    assert [h["h"]["nombre"] for h in c["hoteles_descartados"]] == ["Barato mal calificado"]
    # la lista se ordena por costo total y recién después se recorta
    assert len(c["hoteles"]) <= 12
    assert [h["ev"]["total"] for h in c["hoteles"]] == sorted(h["ev"]["total"] for h in c["hoteles"])


def test_las_vegas_guardado_muestra_el_descartado_por_calificacion(cliente):
    from app import db
    from app.servicios import cotizacion
    r = cliente.post("/viajes", data={**FORM_VIAJE}, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1])
    # la respuesta guardada trae 15 hoteles: se guardan todos
    assert db.uno("select count(*) n from opciones where solicitud_id=:i and tipo='hotel'", i=sid)["n"] == 15
    c = cotizacion.comparacion(sid)
    assert any(h["h"]["nombre"].startswith("OYO") for h in c["hoteles_descartados"])
