"""Cotizar desde y hacia cualquier lugar del mundo: formulario, varios aeropuertos y traslado por carretera."""
import json

from conftest import FORM_VIAJE

from app import db

MOAB = {"nombre": "Moab", "region": "Utah", "pais": "Estados Unidos", "lat": 38.57332, "lon": -109.54984}


def _cotizar(cliente, **cambios) -> tuple:
    r = cliente.post("/viajes", data={**FORM_VIAJE, **cambios}, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1]) if r.headers.get("location", "").startswith("/viajes/") and \
        r.headers["location"].rsplit("/", 1)[1].isdigit() else None
    return r, sid


# ---------- tarea 7: el formulario ----------
def test_cotizar_hacia_un_pueblo_guarda_lugar_y_aeropuertos(cliente):
    r, sid = _cotizar(cliente, destino="Moab, Utah, Estados Unidos", destino_aeropuertos="SLC,CNY,GJT",
                      destino_lugar=json.dumps(MOAB))
    assert r.status_code == 303 and sid
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert s["destino_aeropuertos"] == "CNY,GJT,SLC"
    assert s["destino"] == "CNY"                   # el marcado más cercano al lugar
    assert db.de_json(s["destino_lugar"]) == MOAB
    assert s["origen"] == "MIA" and s["origen_aeropuertos"] is None and s["origen_lugar"] is None
    assert s["ciudad"] == "Moab"                   # el hotel se busca en el lugar, no en la ciudad del aeropuerto
    # trazabilidad: el evento de la solicitud dice qué lugar y qué aeropuertos se eligieron
    ev = db.uno("select detalle from eventos where entidad='solicitud' and entidad_id=:i and paso='solicitud recibida'", i=sid)
    assert "Moab, Utah, Estados Unidos" in ev["detalle"] and "CNY, GJT, SLC" in ev["detalle"]


def test_sin_lugar_el_destino_es_el_primer_marcado(cliente):
    _, sid = _cotizar(cliente, destino="Portugal", destino_aeropuertos="OPO,LIS")
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["destino"], s["destino_aeropuertos"], s["destino_lugar"]) == ("OPO", "LIS,OPO", None)
    assert s["ciudad"] == "Porto"                  # sin lugar, la ciudad del primer aeropuerto marcado


def test_origen_desde_un_pueblo(cliente):
    villa = {"nombre": "Villa de Leyva", "region": "Boyacá", "pais": "Colombia", "lat": 5.63413, "lon": -73.52438}
    _, sid = _cotizar(cliente, origen="Villa de Leyva", origen_aeropuertos="MDE,BOG", origen_lugar=json.dumps(villa))
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["origen"], s["origen_aeropuertos"]) == ("BOG", "BOG,MDE")
    assert db.de_json(s["origen_lugar"])["nombre"] == "Villa de Leyva"
    ev = db.uno("select detalle from eventos where entidad='solicitud' and entidad_id=:i and paso='solicitud recibida'", i=sid)
    assert "Villa de Leyva, Boyacá, Colombia" in ev["detalle"] and "BOG, MDE" in ev["detalle"]


def test_formulario_antiguo_sigue_funcionando(cliente):
    r, sid = _cotizar(cliente)   # origen «Miami (MIA)» y destino «las vegas», sin los campos nuevos
    assert r.status_code == 303 and sid
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["origen"], s["destino"], s["ciudad"]) == ("MIA", "LAS", "Las Vegas")
    assert s["origen_aeropuertos"] is None and s["destino_lugar"] is None
    assert db.uno("select count(*) n from opciones where solicitud_id=:i and tipo='vuelo'", i=sid)["n"] > 0


def test_codigos_invalidos_se_rechazan(cliente):
    antes = db.uno("select count(*) n from solicitudes")["n"]
    r, _ = _cotizar(cliente, destino="Moab", destino_aeropuertos="ZZZ")
    assert r.status_code == 303 and r.headers["location"].startswith("/viajes/nuevo?error=")
    assert "ZZZ" in r.headers["location"] and "No+reconozco" in r.headers["location"]
    r, _ = _cotizar(cliente, destino="Moab", destino_aeropuertos="CNY,<b>")
    assert r.headers["location"].startswith("/viajes/nuevo?error=")
    assert db.uno("select count(*) n from solicitudes")["n"] == antes


def test_un_lugar_mal_formado_no_se_guarda(cliente):
    _, sid = _cotizar(cliente, destino="Moab", destino_aeropuertos="CNY", destino_lugar='{"nombre": "Moab", "lat": "x"}')
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert s["destino"] == "CNY" and s["destino_lugar"] is None


def test_un_aeropuerto_que_solo_conoce_google_se_puede_elegir(cliente):
    if not db.uno("select id from aeropuertos_google where iata='ICN'"):
        db.insertar("aeropuertos_google", iata="ICN", nombre="Incheon International Airport", ciudad="Seoul",
                    kgmid="/m/0hsqf", consulta="seul", visto=db.ahora())
    _, sid = _cotizar(cliente, destino="Seoul, South Korea", destino_aeropuertos="ICN")
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["destino"], s["ciudad"]) == ("ICN", "Seoul")


def test_el_formulario_trae_el_buscador(cliente):
    html = cliente.get("/viajes/nuevo").text
    assert "/static/buscador_lugares.js" in html
    assert 'role="combobox"' in html and 'name="destino_aeropuertos"' in html and 'name="origen_lugar"' in html
    assert "Lugares: GeoNames (CC BY 4.0). Aeropuertos: OurAirports." in html
    js = cliente.get("/static/buscador_lugares.js")
    assert js.status_code == 200 and "aria-activedescendant" in js.text and "/lugares/buscar" in js.text
