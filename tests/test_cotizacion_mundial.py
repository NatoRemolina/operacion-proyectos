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
    # CNY y GJT: ninguna respuesta guardada para esa combinación, ni en otras fechas
    r, sid = _cotizar(cliente, destino="Moab, Utah, Estados Unidos", destino_aeropuertos="CNY,GJT",
                      destino_lugar=json.dumps(MOAB), ida="2027-02-01", regreso="2027-02-04", llegar_antes="")
    assert r.status_code == 303 and r.headers["location"] == f"/viajes/{sid}" and llamadas == []
    pagina = cliente.get(f"/viajes/{sid}")
    assert pagina.status_code == 200 and "No hay vuelos para esta ruta y fechas" in pagina.text
    fila = db.uno("select * from consultas_buscador where solicitud_id=:i and tipo='vuelos'", i=sid)
    assert fila["origen"] == "fallida" and fila["clave"] == "vuelos_MIA_CNY-GJT_2027-02-01_2027-02-04.json"
    # con los tres aeropuertos sí hay una respuesta guardada de otras fechas: se usa y se dice
    _, otra = _cotizar(cliente, destino="Moab", destino_aeropuertos="CNY,GJT,SLC", destino_lugar=json.dumps(MOAB),
                       ida="2027-02-01", regreso="2027-02-04", llegar_antes="")
    assert db.uno("select origen from consultas_buscador where solicitud_id=:i and tipo='vuelos'", i=otra)["origen"] == "guardado (otras fechas)"


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


# ---------- tarea 9: el traslado por carretera en el costo ----------
def _aeropuerto(iata):
    from app.servicios import geografia
    return geografia.aeropuerto(iata)


def _sol(**cambios):
    base = {"baterias_n": 0, "baterias_wh": 0, "maleta": 0, "prob_cambio": 0, "llegar_antes": None, "carro_dia": 0,
            "origen_lugar": None, "destino_lugar": json.dumps(MOAB)}
    return {**base, **cambios}


def _vuelo_simple(hasta="SLC", llega="2027-01-12 15:10", **extra):
    return {"aerolinea": "Delta", "numeros": ["DL 9"], "sale": "2027-01-12 08:00", "llega": llega, "desde": "MIA",
            "hasta": hasta, "escalas": 0, "duracion_min": 430, "precio": 400.0, "notas": [], **extra}


def test_traslado_suma_y_cambia_el_orden(cliente, monkeypatch, tmp_path):
    from app.main import _comparacion
    _buscador(monkeypatch, tmp_path)   # SLC 120 USD más barato que CNY
    _, sid = _cotizar(cliente, destino="Moab, Utah, Estados Unidos", destino_aeropuertos="CNY,GJT,SLC",
                      destino_lugar=json.dumps(MOAB), ida="2027-04-06", regreso="2027-04-09", llegar_antes="",
                      carro_dia=0, prob_cambio=0, baterias_n=0, maleta="")
    c = _comparacion(sid)
    assert [v["v"]["hasta"] for v in c["vuelos"]] == ["CNY", "SLC"]
    assert c["mas_barato"]["v"]["hasta"] == "SLC"
    slc = c["vuelos"][1]["ev"]["lineas"]
    linea = next(l for l in slc if l["concepto"].startswith("Traslado por carretera desde SLC"))
    assert linea["origen"] == "supuesto" and linea["grupo"] == "traslados"
    assert 410 < linea["calculo"]["km_carretera"] < 430 and 280 < linea["valor"] < 300   # unos 420 km x 0,35 x 2
    assert "(419 km, unas 6 h)" in linea["concepto"]
    # trazabilidad: de dónde sale la línea
    assert linea["calculo"]["factor"] == 1.3 and linea["calculo"]["usd_km"] == 0.35 and linea["calculo"]["velocidad_kmh"] == 70
    assert linea["calculo"]["ida_y_vuelta"] is True and 315 < linea["calculo"]["km_linea_recta"] < 330
    # CNY está a menos de 30 km de Moab: sin línea de traslado
    assert not any("Traslado" in l["concepto"] for l in c["vuelos"][0]["ev"]["lineas"])
    pagina = cliente.get(f"/viajes/{sid}").text
    assert "Traslado por carretera desde SLC" in pagina


def test_con_carro_solo_combustible(cliente):
    from app.servicios import costo
    t = costo.traslado(_aeropuerto("SLC"), MOAB, True, costo.catalogo())
    assert t["concepto"].startswith("Combustible y peajes desde SLC (") and t["grupo"] == "combustible"
    assert t["valor"] == round(t["calculo"]["km_carretera"] * 0.12 * 2, 2) and t["calculo"]["usd_km"] == 0.12
    # y al evaluar con carro_dia > 0, la línea de llegada es la de combustible
    ev = costo.evaluar(_vuelo_simple(), costo.tarifa_supuesta(_vuelo_simple(), costo.catalogo()), _sol(carro_dia=60), [], costo.catalogo())
    assert any(l["concepto"].startswith("Combustible y peajes desde SLC") and l["grupo"] == "combustible" for l in ev["lineas"])
    assert not any(l["concepto"].startswith("Traslado") for l in ev["lineas"])


def test_bajo_30_km_no_hay_linea(cliente):
    from app.servicios import costo
    cerca = {"iata": "XXX", "lat": MOAB["lat"] + 0.18, "lon": MOAB["lon"]}   # unos 20 km
    assert costo.traslado(cerca, MOAB, False, costo.catalogo()) is None
    assert costo.traslado(_aeropuerto("SLC"), None, False, costo.catalogo()) is None     # sin lugar no hay traslado
    assert costo.traslado(None, MOAB, False, costo.catalogo()) is None                   # aeropuerto sin coordenadas


def test_traslado_y_hora_limite_con_cambio_de_dia(cliente):
    """Punto de atención 4: llegada 22:40 + 3 h de traslado frente a la hora límite del día siguiente."""
    from app.servicios import costo
    slc = _aeropuerto("SLC")
    lugar = {"nombre": "A tres horas", "region": "", "pais": "", "lat": slc["lat"] + 1.452, "lon": slc["lon"]}
    cat = costo.catalogo()
    assert costo.traslado(slc, lugar, False, cat)["horas"] == 3.0
    vuelo = _vuelo_simple(llega="2027-01-12 22:40")
    tarifa = costo.tarifa_supuesta(vuelo, cat)
    llega_bien = costo.evaluar(vuelo, tarifa, _sol(destino_lugar=lugar, llegar_antes="2027-01-13T16:00"), [], cat)
    assert llega_bien["descartada"] is None
    tarde = costo.evaluar(vuelo, tarifa, _sol(destino_lugar=lugar, llegar_antes="2027-01-13T01:00"), [], cat)
    assert tarde["descartada"] == "Con el traslado llega a las 01:40, después de la hora límite."
    # sin traslado, la misma llegada cumple ese límite: lo que la descarta es el traslado
    assert costo.evaluar(vuelo, tarifa, _sol(destino_lugar=None, llegar_antes="2027-01-13T01:00"), [], cat)["descartada"] is None


def test_el_presupuesto_incluye_el_traslado(cliente, monkeypatch, tmp_path):
    from app.main import _comparacion
    from app.servicios import viajes
    _buscador(monkeypatch, tmp_path)
    _, sid = _cotizar(cliente, destino="Moab, Utah, Estados Unidos", destino_aeropuertos="CNY,GJT,SLC",
                      destino_lugar=json.dumps(MOAB), ida="2027-05-04", regreso="2027-05-07", llegar_antes="",
                      carro_dia=0, prob_cambio=0, baterias_n=0, maleta="")
    slc = next(v for v in _comparacion(sid)["vuelos"] if v["v"]["hasta"] == "SLC")
    cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": slc["id"], "motivo": "Prueba del traslado desde Salt Lake City",
                                                 "razones": ["horario"]})
    v = viajes.de_solicitud(sid)
    detalle = db.de_json(v["presupuesto_detalle"]) if isinstance(v["presupuesto_detalle"], str) else v["presupuesto_detalle"]
    traslado = [l for l in detalle if l["grupo"] == "traslados"]
    assert len(traslado) == 1 and traslado[0]["concepto"].startswith("Traslado por carretera desde SLC")
    assert v["presupuesto_usd"] == round(sum(l["valor"] for l in detalle), 2)
    # la decisión guarda el cálculo completo y deja su evento
    d = db.de_json(db.uno("select desglose from decisiones where solicitud_id=:i order by id desc", i=sid)["desglose"])
    linea = next(l for l in d["lineas"] if l["grupo"] == "traslados")
    assert linea["calculo"]["factor"] == 1.3 and linea["origen"] == "supuesto"
    ev = db.uno("select detalle from eventos where entidad='solicitud' and entidad_id=:i and paso='traslado calculado'", i=sid)
    assert ev and "SLC" in ev["detalle"] and "x 1.3" in ev["detalle"] and "0.35 USD/km" in ev["detalle"]


# ---------- sin costo de búsquedas: lo que ya traen las respuestas ----------
def test_las_condiciones_del_itinerario_corrigen_la_tarifa_supuesta(cliente):
    from app.servicios import costo
    cat = costo.catalogo()
    t = costo.tarifa_supuesta(_vuelo_simple(notas=["Free change, possible fare difference", "1 checked bag included",
                                                   "Full refund for cancellations"]), cat)
    assert t["permite_cambio"] and t["reembolsable"] and t["maleta"] == 0 and t["cargo_cambio"] == 0
    ev = costo.evaluar(_vuelo_simple(), t, _sol(maleta=1, prob_cambio=0.25), [], cat)
    maleta = next(l for l in ev["lineas"] if l["concepto"].startswith("Maleta facturada"))
    assert maleta["valor"] == 0 and maleta["origen"] == "buscador"
    con_cargo = costo.tarifa_supuesta(_vuelo_simple(notas=["Ticket changes for a fee"]), cat)
    assert con_cargo["permite_cambio"] and con_cargo["cargo_cambio"] == 75
    riesgo = next(l for l in costo.evaluar(_vuelo_simple(), con_cargo, _sol(prob_cambio=0.25), [], cat)["lineas"]
                  if l["concepto"].startswith("Riesgo de cambio"))
    assert riesgo["valor"] == round(0.25 * (60 + 75), 2) and "cargo" in riesgo["concepto"]
    sin_cambios = costo.tarifa_supuesta(_vuelo_simple(notas=["No ticket changes"]), cat)
    assert not sin_cambios["permite_cambio"]


def test_avisos_de_retraso_habitual_y_escalas(cliente):
    from app.servicios import costo
    cat = costo.catalogo()
    retrasado = _vuelo_simple(llega="2027-01-12 17:40", a_menudo_retrasado=True)
    ev = costo.evaluar(retrasado, costo.tarifa_supuesta(retrasado, cat), _sol(destino_lugar=None, llegar_antes="2027-01-12T18:00"), [], cat)
    assert ev["descartada"] is None and any("suele retrasarse" in a for a in ev["avisos"])
    holgado = costo.evaluar(retrasado, costo.tarifa_supuesta(retrasado, cat), _sol(destino_lugar=None, llegar_antes="2027-01-12T20:00"), [], cat)
    assert not any("suele retrasarse" in a for a in holgado["avisos"])
    con_escalas = _vuelo_simple(escalas_detalle=[{"aeropuerto": "DEN", "minutos": 44, "nocturna": False},
                                                 {"aeropuerto": "SFO", "minutos": 600, "nocturna": True}])
    avisos = costo.evaluar(con_escalas, costo.tarifa_supuesta(con_escalas, cat), _sol(destino_lugar=None), [], cat)["avisos"]
    assert any("Escala corta en DEN (44 min)" in a for a in avisos) and any("Escala nocturna en SFO" in a for a in avisos)


def test_un_vuelo_incompleto_no_rompe_la_lectura(cliente):
    from app.servicios import precios
    v = precios._vuelo({"flights": [{"departure_airport": {"id": "MIA", "time": "2027-01-12 08:00"},
                                     "arrival_airport": {"id": "SLC", "time": "2027-01-12 12:00"}}], "price": 300,
                        "layovers": [{"duration": 40, "id": "DEN", "overnight": True}]})
    assert v["numeros"] == ["s/n"] and v["aerolinea"] and v["escalas_detalle"][0] == {"aeropuerto": "DEN", "minutos": 40, "nocturna": True}
    assert precios._vuelo({"price": 300}) is None   # sin tramos no es un vuelo que se pueda comparar


# ---------- caso de demostración: respuesta real guardada (12 nov 2026), sin clave ni internet ----------
def test_demostracion_miami_a_moab_sin_clave(cliente):
    from app.main import _comparacion
    _, sid = _cotizar(cliente, destino="Moab, Utah, Estados Unidos", destino_aeropuertos="CNY,GJT,SLC",
                      destino_lugar=json.dumps(MOAB))   # fechas, hora límite y carro del formulario de siempre
    assert db.uno("select origen from consultas_buscador where solicitud_id=:i and tipo='vuelos'", i=sid)["origen"] == "guardado"
    c = _comparacion(sid)
    assert {v["v"]["hasta"] for v in c["vuelos"] + c["descartados"]} == {"CNY", "GJT", "SLC"}
    # lo más barato del buscador llega a Salt Lake City, pero con el traslado conviene Moab (CNY)
    assert (c["mas_barato"]["v"]["hasta"], c["mas_barato"]["v"]["precio"]) == ("SLC", 415)
    assert c["vuelos"][0]["v"]["hasta"] == "CNY"
    assert any((v["ev"]["descartada"] or "").startswith("Con el traslado llega a las") for v in c["descartados"])
    assert "Combustible y peajes desde SLC" in cliente.get(f"/viajes/{sid}").text   # el formulario trae carro de alquiler
