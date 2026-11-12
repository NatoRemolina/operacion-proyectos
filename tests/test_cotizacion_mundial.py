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


# ---------- tarea 8: una búsqueda para varios aeropuertos (buscador simulado: nunca sale a internet) ----------
def _vuelo_falso(numero, llega_a, precio, llega="2027-01-12 15:10", aerolinea="Delta", sale="2027-01-12 08:00", **extra):
    return {"flights": [{"airline": aerolinea, "flight_number": numero, "departure_airport": {"id": "MIA", "time": sale},
                         "arrival_airport": {"id": llega_a, "time": llega}}],
            "total_duration": 430, "price": precio, "departure_token": f"token-{numero}", **extra}


def _respuesta_vuelos(vuelos, llegadas=("CNY", "SLC")):
    return {"search_metadata": {"created_at": "2026-11-12 10:00:00 UTC"}, "best_flights": vuelos, "other_flights": [],
            "price_insights": {"lowest_price": min(v["price"] for v in vuelos), "price_level": "typical",
                               "typical_price_range": [300, 500]},
            "airports": [{"departure": [{"airport": {"id": "MIA", "name": "Miami"}}],
                          "arrival": [{"airport": {"id": c, "name": c}} for c in llegadas]}]}


class _Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def json(self):
        return self.datos


def _buscador(monkeypatch, tmp_path, vuelos=None, clave="clave-de-prueba"):
    """Simula el buscador de vuelos y de hoteles; devuelve la lista de parámetros de cada llamada."""
    from app import config
    from app.servicios import precios
    llamadas = []
    respuesta = vuelos or _respuesta_vuelos([_vuelo_falso("DL 1", "CNY", 520), _vuelo_falso("DL 2", "SLC", 400)])

    def get(url, params=None, **k):
        llamadas.append(params)
        return _Respuesta(respuesta if params["engine"] == "google_flights" else {"properties": []})
    monkeypatch.setattr(config, "SERPAPI_KEY", clave)
    monkeypatch.setattr(config, "DIR_RESPALDO_ESCRITURA", tmp_path)   # las respuestas simuladas no quedan en el repositorio
    monkeypatch.setattr(precios.httpx, "get", get)
    return llamadas


def _vuelos(llamadas):
    return [p for p in llamadas if p["engine"] == "google_flights"]


def test_varios_aeropuertos_una_sola_consulta(cliente, monkeypatch, tmp_path):
    llamadas = _buscador(monkeypatch, tmp_path)
    r, sid = _cotizar(cliente, destino="Moab, Utah, Estados Unidos", destino_aeropuertos="CNY,GJT,SLC",
                      destino_lugar=json.dumps(MOAB), ida="2027-01-12", regreso="2027-01-15", llegar_antes="")
    assert r.status_code == 303 and sid
    vuelos = _vuelos(llamadas)
    assert len(vuelos) == 1                                         # una sola búsqueda del plan
    assert (vuelos[0]["departure_id"], vuelos[0]["arrival_id"]) == ("MIA", "CNY,GJT,SLC")
    hoteles = [p for p in llamadas if p["engine"] == "google_hotels"]
    assert hoteles and hoteles[0]["q"] == "Moab hotels"             # el hotel, en el lugar y no en la ciudad del aeropuerto
    filas = db.todos("select * from consultas_buscador where solicitud_id=:i and tipo='vuelos'", i=sid)
    assert len(filas) == 1 and filas[0]["origen"] == "en vivo"
    assert filas[0]["clave"] == "vuelos_MIA_CNY-GJT-SLC_2027-01-12_2027-01-15.json"
    # trazabilidad: el evento de la consulta dice qué códigos se consultaron
    ev = db.uno("select detalle from eventos where entidad='solicitud' and entidad_id=:i and paso='consulta externa' and detalle like 'vuelos%'", i=sid)
    assert "MIA" in ev["detalle"] and "CNY,GJT,SLC" in ev["detalle"]
    # el buscador no devolvió nada para GJT: queda dicho
    ignorado = db.uno("select detalle from eventos where entidad='solicitud' and entidad_id=:i and paso='aeropuertos ignorados por el buscador'", i=sid)
    assert ignorado and ignorado["detalle"].startswith("GJT: sin resultados")
    # cada vuelo conserva su aeropuerto real y las observaciones del modelo también
    opciones = [db.de_json(o["datos"]) for o in db.todos("select datos from opciones where solicitud_id=:i and tipo='vuelo'", i=sid)]
    assert sorted(o["hasta"] for o in opciones) == ["CNY", "SLC"]
    obs = db.todos("select origen, destino from observaciones where busqueda='MIA_CNY-GJT-SLC_2027-01-12_2027-01-15'")
    assert sorted(o["destino"] for o in obs) == ["CNY", "SLC"] and {o["origen"] for o in obs} == {"MIA"}
    pagina = cliente.get(f"/viajes/{sid}")
    assert pagina.status_code == 200 and "CNY · GJT · SLC" in pagina.text and "Va a Moab, Utah, Estados Unidos" in pagina.text


def test_sin_clave_ni_respaldo_no_falla(cliente, monkeypatch, tmp_path):
    """Punto de atención 3: sin clave y sin respuesta guardada para varios códigos, la cotización muestra «sin datos»."""
    llamadas = _buscador(monkeypatch, tmp_path, clave="")
    r, sid = _cotizar(cliente, destino="Moab, Utah, Estados Unidos", destino_aeropuertos="CNY,GJT,SLC",
                      destino_lugar=json.dumps(MOAB), ida="2027-02-01", regreso="2027-02-04", llegar_antes="")
    assert r.status_code == 303 and r.headers["location"] == f"/viajes/{sid}" and llamadas == []
    pagina = cliente.get(f"/viajes/{sid}")
    assert pagina.status_code == 200 and "No hay vuelos para esta ruta y fechas" in pagina.text
    fila = db.uno("select * from consultas_buscador where solicitud_id=:i and tipo='vuelos'", i=sid)
    assert fila["origen"] == "fallida" and fila["clave"] == "vuelos_MIA_CNY-GJT-SLC_2027-02-01_2027-02-04.json"


def test_la_respuesta_guardada_de_un_solo_codigo_sigue_valiendo(cliente, monkeypatch, tmp_path):
    from app.servicios import precios
    llamadas = _buscador(monkeypatch, tmp_path)
    vuelos, origen, info = precios.buscar_vuelos("MIA", "LAS", "2026-11-18", "2026-11-21")
    assert origen == "guardado" and vuelos and llamadas == []
    # una lista de un solo código es lo mismo que el código
    assert precios.buscar_vuelos(["MIA"], ["LAS"], "2026-11-18", "2026-11-21")[1] == "guardado" and llamadas == []
    # y la cotización de siempre (Miami → Las Vegas) sigue leyendo lo guardado
    r, sid = _cotizar(cliente)
    assert _vuelos(llamadas) == []
    assert db.uno("select origen from consultas_buscador where solicitud_id=:i and tipo='vuelos'", i=sid)["origen"] == "guardado"


def test_parametros_estables_para_la_cache_del_proveedor(cliente, monkeypatch, tmp_path):
    from app.servicios import precios
    llamadas = _buscador(monkeypatch, tmp_path)
    nombre = "vuelos_MIA_CNY-GJT-SLC_2027-03-02_2027-03-05.json"
    precios.buscar_vuelos("MIA", ["GJT", "CNY", "SLC"], "2027-03-02", "2027-03-05")
    assert precios.buscar_vuelos("MIA", ["SLC", "GJT", "CNY"], "2027-03-02", "2027-03-05")[1] == "guardado"
    assert len(_vuelos(llamadas)) == 1                     # el mismo pedido en otro orden no se paga dos veces
    db.ejecutar("delete from busquedas where clave=:c", c=nombre)
    precios.buscar_vuelos("MIA", ["SLC", "GJT", "CNY"], "2027-03-02", "2027-03-05")
    primera, segunda = _vuelos(llamadas)
    assert primera == segunda and primera["arrival_id"] == "CNY,GJT,SLC"
    assert all("no_cache" not in p for p in llamadas)
    assert (tmp_path / nombre).is_file()
