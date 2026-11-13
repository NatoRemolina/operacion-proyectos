"""Fidelización: las millas solo restan con membresía y los programas de hotel cambian el costo del hotel."""
import pytest


@pytest.fixture()
def cat(cliente):
    from app.servicios import costo
    return costo.catalogo()


def _vuelo(aerolinea="Delta", precio=400.0):
    return {"aerolinea": aerolinea, "numeros": ["DL 9"], "sale": "2027-01-12 08:00", "llega": "2027-01-12 15:10",
            "desde": "MIA", "hasta": "LAS", "escalas": 0, "duracion_min": 430, "precio": precio, "notas": []}


def _tarifa(precio=400.0, nombre="Main Cabin"):
    return {"nombre": nombre, "precio": precio, "mano": 0, "maleta": 0, "permite_cambio": True, "cargo_cambio": 0}


def _sol():
    return {"baterias_n": 0, "baterias_wh": 0, "maleta": 0, "prob_cambio": 0, "llegar_antes": None, "carro_dia": 0,
            "origen_lugar": None, "destino_lugar": None}


def _socio(entidad="Delta", programa="SkyMiles", estatus=""):
    return {"viajero_id": 1, "programa": programa, "entidad": entidad, "estatus": estatus}


def _empresa(entidad="Delta"):
    return {"viajero_id": None, "programa": "Cuenta de empresa", "entidad": entidad, "estatus": ""}


def _millas(ev):
    return [l for l in ev["lineas"] if l["concepto"].startswith("Millas")]


# ---------- pieza 1: millas solo con membresía ----------
def test_sin_membresia_las_millas_no_restan_y_se_ofrece_inscribirse(cat):
    from app.servicios import costo
    ev = costo.evaluar(_vuelo(), _tarifa(), _sol(), [], cat)
    assert not _millas(ev)
    assert ev["total"] == 400.0
    assert "Inscribirse en SkyMiles es gratis y acumularía ~2.000 millas (≈ 24 USD)." in ev["avisos"]


def test_con_membresia_del_viajero_las_millas_restan(cat):
    from app.servicios import costo
    ev = costo.evaluar(_vuelo(), _tarifa(), _sol(), [_socio()], cat)
    assert [(l["concepto"], l["valor"]) for l in _millas(ev)] == [("Millas del viajero (5 por USD a 0.012 USD)", -24.0)]
    assert ev["total"] == 376.0
    assert not any(a.startswith("Inscribirse") for a in ev["avisos"])


def test_la_membresia_de_otra_aerolinea_no_cuenta(cat):
    from app.servicios import costo
    ev = costo.evaluar(_vuelo(), _tarifa(), _sol(), [_socio("American", "AAdvantage", "Gold")], cat)
    assert not _millas(ev) and ev["total"] == 400.0


def test_solo_con_la_cuenta_de_empresa_resta_lo_de_la_empresa(cat):
    from app.servicios import costo
    ev = costo.evaluar(_vuelo(), _tarifa(), _sol(), [_empresa()], cat)
    assert [(l["concepto"], l["valor"]) for l in _millas(ev)] == [("Millas de la cuenta de empresa (1 por USD a 0.012 USD)", -4.8)]
    assert ev["total"] == 395.2
    # el viajero sigue sin ser socio: la oportunidad se muestra igual
    assert any(a.startswith("Inscribirse en SkyMiles es gratis") for a in ev["avisos"])


def test_viajero_y_empresa_suman(cat):
    from app.servicios import costo
    ev = costo.evaluar(_vuelo(), _tarifa(), _sol(), [_socio(), _empresa()], cat)
    assert [(l["concepto"], l["valor"]) for l in _millas(ev)] == [
        ("Millas del viajero y de la cuenta de empresa (6 por USD a 0.012 USD)", -28.8)]
    assert ev["total"] == 371.2


def test_tarifa_basica_que_no_acumula_no_ofrece_inscribirse(cat):
    from app.servicios import costo
    ev = costo.evaluar(_vuelo(), _tarifa(nombre="Basic Economy"), _sol(), [], cat)
    assert not _millas(ev)
    assert "La tarifa básica de esta aerolínea no acumula millas." in ev["avisos"]
    assert not any(a.startswith("Inscribirse") for a in ev["avisos"])


def test_aerolinea_sin_programa_conocido(cat):
    from app.servicios import costo
    ev = costo.evaluar(_vuelo("Aerolínea Inventada"), _tarifa(), _sol(), [], cat)
    assert any(a.startswith("Inscribirse en el programa de Aerolínea Inventada es gratis") for a in ev["avisos"])


# ---------- pieza 2: programas de hotel con efecto en el costo ----------
def _hotel(nombre, total, calificacion=4.0):
    return {"nombre": nombre, "total": total, "noche": round(total / 3, 2), "calificacion": calificacion, "clase": 3}


def _miembro(programa="Hilton Honors", viajero_id=1):
    return {"viajero_id": viajero_id, "programa": programa, "entidad": programa, "estatus": "Member"}


def test_reconoce_la_marca_sin_mayusculas_ni_tildes(cat):
    from app.servicios import costo
    p = costo.programa_hotel("Tru by Hilton Denver Downtown Convention Center", cat)
    assert (p["nombre"], p["puntos_por_usd"], p["valor_punto_usd"], p["descuento_miembro"]) == ("Hilton Honors", 10, 0.005, 0.05)
    assert p["confianza"] == "supuesto" and p["fuente"].startswith("https://") and p["verificado"]
    assert "Hampton" in p["marcas"] and "Waldorf" in p["marcas"]
    casos = {"COURTYARD BY MARRIOTT DENVER CHERRY CREEK": "Marriott Bonvoy", "AC Hotel Miami Beach": "Marriott Bonvoy",
             "W Barcelona": "Marriott Bonvoy", "Hyatt Place Denver/Cherry Creek": "World of Hyatt",
             "Holiday Inn Express Denver Downtown by IHG": "IHG One Rewards", "avid hotel Denver": "IHG One Rewards",
             "Swissôtel Zürich": "ALL Accor", "Swissotel Lima": "ALL Accor", "ibis Styles Lisboa": "ALL Accor",
             "Embassy Suites by Hilton": "Hilton Honors",
             "Holiday Inn Fairfield": "IHG One Rewards"}   # con dos marcas en el nombre manda la primera
    assert {n: costo.programa_hotel(n, cat)["nombre"] for n in casos} == casos
    # una marca corta no se reconoce dentro de otra palabra, y un hotel independiente no tiene programa
    assert costo.programa_hotel("Wynn Las Vegas", cat) is None
    assert costo.programa_hotel("LoHi Apartment w/ Patio: 1 Mi to Downtown Denver!", cat) is None
    assert costo.programa_hotel("Hotel York House Lisboa", cat) is None


def test_marcas_que_tambien_son_ciudades_solo_cuentan_al_inicio(cat):
    from app.servicios import costo
    casos = {"Fairfield Inn & Suites Denver Downtown": "Marriott Bonvoy",
             "Fairfield by Marriott Inn & Suites Lisboa": "Marriott Bonvoy",
             "Renaissance Denver Downtown City Center Hotel": "Marriott Bonvoy",
             "Pullman Paris Tour Eiffel": "ALL Accor", "Fairmont Royal York": "ALL Accor",
             "The Fairmont San Francisco": "ALL Accor",
             "Hampton Inn Pullman": "Hilton Honors"}   # en la ciudad de Pullman, el hotel es de su marca
    assert {n: (costo.programa_hotel(n, cat) or {}).get("nombre") for n in casos} == casos
    # la ciudad o un hotel independiente con ese nombre no son la marca
    for nombre in ("Best Western Plus Fairfield Inn", "Quality Inn Paradise Creek Pullman", "Comfort Inn Fairmont",
                   "Hotel Boutique Renaissance", "Comfort Suites Fairfield"):
        assert costo.programa_hotel(nombre, cat) is None, nombre
    # el catálogo muestra la marca limpia; la condición queda aparte
    accor = next(p for p in costo.programas_hotel(cat) if p["nombre"] == "ALL Accor")
    assert "Pullman" in accor["marcas"] and "Pullman" in accor["al_inicio"] and "Novotel" not in accor["al_inicio"]


def test_la_semilla_actualiza_las_marcas_que_nadie_edito(cliente):
    from app import db
    from datos import semilla

    def marcas(entidad):
        return db.uno("select id, valor from reglas where ambito='hotel' and entidad=:e and clave='marcas'", e=entidad)
    accor = marcas("ALL Accor")["valor"]
    try:
        db.actualizar("reglas", marcas("Marriott Bonvoy")["id"], valor=semilla.MARCAS_HOTEL_ANTERIORES["Marriott Bonvoy"])
        db.actualizar("reglas", marcas("ALL Accor")["id"], valor="Novotel, Ibis")   # editada a mano: se respeta
        db.ejecutar("update reglas set nota=:n where ambito='hotel' and clave='marcas'", n=semilla.NOTA_MARCAS_ANTERIOR)
        semilla.asegurar_fidelizacion_hotel()
        assert "Fairfield Inn (al inicio)" in marcas("Marriott Bonvoy")["valor"]
        assert marcas("ALL Accor")["valor"] == "Novotel, Ibis"
        # la nota que explica «(al inicio)» llega a todos los programas
        assert {r["nota"] for r in db.todos("select nota from reglas where ambito='hotel' and clave='marcas'")} == {
            semilla.NOTAS_HOTEL["marcas"]}
    finally:
        db.actualizar("reglas", marcas("ALL Accor")["id"], valor=accor)


def test_hotel_con_membresia_tarifa_de_miembro_y_puntos(cat):
    from app.servicios import costo
    ev = costo.evaluar_hotel(_hotel("Tru by Hilton Denver", 243.0), [_miembro()], cat, 3)
    assert [(l["concepto"], l["valor"]) for l in ev["lineas"]] == [
        ("Tarifa total (3 noches)", 243.0), ("Tarifa de miembro (−5 %)", -12.15),
        ("Puntos del programa (10 por USD a 0.005 USD)", -11.54)]
    assert ev["total"] == 219.31 and ev["programa"] == "Hilton Honors" and ev["socio"]
    assert "Acumula solo con reserva directa." in ev["avisos"]
    assert not any(a.startswith("Inscribirse") for a in ev["avisos"])


def test_hotel_sin_membresia_solo_la_oportunidad(cat):
    from app.servicios import costo
    ev = costo.evaluar_hotel(_hotel("Tru by Hilton Denver", 243.0), [_miembro("Marriott Bonvoy")], cat, 3)
    assert [l["concepto"] for l in ev["lineas"]] == ["Tarifa total (3 noches)"] and ev["total"] == 243.0
    assert not ev["socio"]
    assert any(a.startswith("Inscribirse en Hilton Honors es gratis: tarifa de miembro (−5 %) y ~2.308 puntos")
               for a in ev["avisos"])
    assert "Acumula solo con reserva directa." in ev["avisos"]


def test_inscripcion_gratis_supuesta_aplica_la_tarifa_de_miembro(cat):
    from app.servicios import costo
    con_supuesto = {**cat, ("supuesto", "", "", "inscripcion_gratis_hotel"): {"valor": "sí"}}
    ev = costo.evaluar_hotel(_hotel("Tru by Hilton Denver", 243.0), [], con_supuesto, 3)
    assert ev["total"] == 219.31 and not ev["socio"]
    assert any("se inscribe gratis en Hilton Honors" in a for a in ev["avisos"])
    assert not any(a.startswith("Inscribirse") for a in ev["avisos"])


@pytest.mark.parametrize("calificacion, descartado", [
    ("3.2", "Calificación 3.2, por debajo del mínimo de 3.5."), ("4.1", None), ("n/a", None), ("", None), (None, None)])
def test_la_calificacion_que_llega_como_texto(cat, calificacion, descartado):
    from app.servicios import costo
    ev = costo.evaluar_hotel(_hotel("Independiente Centro", 225.0, calificacion=calificacion), [], cat, 3)
    assert ev["descartado"] == descartado


def test_hotel_sin_programa(cat):
    from app.servicios import costo
    ev = costo.evaluar_hotel(_hotel("The Artesian", 294.0), [_miembro()], cat, 3)
    assert [(l["concepto"], l["valor"], l["origen"]) for l in ev["lineas"]] == [("Tarifa total (3 noches)", 294.0, "buscador")]
    assert ev["total"] == 294.0 and ev["programa"] is None and ev["avisos"] == []


def test_la_semilla_trae_el_catalogo_de_hotel_y_la_membresia_de_ejemplo(cliente):
    from app import db
    from datos import semilla
    programas = {r["entidad"] for r in db.todos("select entidad from reglas where ambito='hotel' and clave='marcas'")}
    assert programas == {"Marriott Bonvoy", "Hilton Honors", "World of Hyatt", "IHG One Rewards", "ALL Accor"}
    hilton = db.todos("select * from membresias where entidad='Hilton Honors'")
    assert len(hilton) == 1 and hilton[0]["viajero_id"] == 1 and hilton[0]["programa"] == "Hilton Honors"
    antes = db.uno("select count(*) n from reglas")["n"], db.uno("select count(*) n from membresias")["n"]
    semilla.asegurar_fidelizacion_hotel()
    assert (db.uno("select count(*) n from reglas")["n"], db.uno("select count(*) n from membresias")["n"]) == antes


# ---------- pieza 3: hotel recomendado y descartes ----------
def _cotizacion_con_hoteles(cliente, hoteles, viajero_id=1, **cambios):
    """Cotización guardada de Miami a Las Vegas cuyos hoteles se cambian por los de la prueba."""
    from conftest import FORM_VIAJE

    from app import db
    r = cliente.post("/viajes", data={**FORM_VIAJE, "viajero_id": viajero_id, **cambios}, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1])
    db.ejecutar("delete from opciones where solicitud_id=:i and tipo='hotel'", i=sid)
    for h in hoteles:
        db.insertar("opciones", solicitud_id=sid, tipo="hotel", titulo=h["nombre"], precio=h["total"], moneda="USD",
                    datos=h, tarifas=None, origen_dato="guardado", capturado=db.ahora())
    return sid


def test_el_mas_barato_por_tarifa_pierde_contra_el_del_programa(cliente):
    from app.servicios import cotizacion
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Independiente Centro", 225.0), _hotel("Tru by Hilton Las Vegas", 243.0)])
    c = cotizacion.comparacion(sid)
    assert [h["h"]["nombre"] for h in c["hoteles"]] == ["Tru by Hilton Las Vegas", "Independiente Centro"]
    assert [h["ev"]["total"] for h in c["hoteles"]] == [219.31, 225.0]
    assert c["hotel_recomendado"]["h"]["nombre"] == "Tru by Hilton Las Vegas" and c["hoteles"][0]["recomendado"]
    assert c["hotel_mas_barato"]["h"]["nombre"] == "Independiente Centro" and c["hoteles"][1]["mas_barato"]
    # sin la membresía (Laura no es socia de Hilton Honors) gana la tarifa
    sin = cotizacion.comparacion(_cotizacion_con_hoteles(cliente, [_hotel("Independiente Centro", 225.0),
                                                                   _hotel("Tru by Hilton Las Vegas", 243.0)], viajero_id=2))
    assert sin["hotel_recomendado"]["h"]["nombre"] == "Independiente Centro" and sin["hotel_mas_barato"] is None


def test_calificacion_baja_descarta_con_su_razon(cliente):
    from app.servicios import cotizacion
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Barato y mal calificado", 150.0, calificacion=3.3),
                                            _hotel("Sin calificación", 260.0, calificacion=None),
                                            _hotel("Bien calificado", 280.0, calificacion=4.4)])
    c = cotizacion.comparacion(sid)
    assert [h["h"]["nombre"] for h in c["hoteles"]] == ["Sin calificación", "Bien calificado"]
    assert [(h["h"]["nombre"], h["ev"]["descartado"]) for h in c["hoteles_descartados"]] == [
        ("Barato y mal calificado", "Calificación 3.3, por debajo del mínimo de 3.5.")]
    # el más barato que se compara es el más barato de los que sirven
    assert c["hotel_recomendado"]["h"]["nombre"] == "Sin calificación" and c["hotel_mas_barato"] is None


def test_la_calificacion_en_texto_no_rompe_la_pagina_ni_la_api(cliente):
    from app.servicios import cotizacion
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Independiente Centro", 225.0, calificacion="4.1"),
                                            _hotel("Independiente Norte", 230.0, calificacion="n/a")])
    c = cotizacion.comparacion(sid)
    assert [h["h"]["calificacion"] for h in c["hoteles"]] == [4.1, None] and c["hoteles_descartados"] == []
    pagina = cliente.get(f"/viajes/{sid}")
    assert pagina.status_code == 200 and "<td>4.1</td>" in pagina.text
    api = cliente.get(f"/api/v1/cotizaciones/{sid}")
    assert api.status_code == 200 and [h["calificacion"] for h in api.json()["hoteles"]] == [4.1, None]


def test_la_decision_lleva_el_hotel_evaluado(cliente):
    from app import db
    from app.servicios import cotizacion, viajes
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Independiente Centro", 225.0), _hotel("Tru by Hilton Las Vegas", 243.0)])
    c = cotizacion.comparacion(sid)
    tru = c["hotel_recomendado"]
    cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": c["vuelos"][0]["id"], "hotel_id": tru["id"], "razones": ["costo_total"]})
    d = db.uno("select * from decisiones where solicitud_id=:i order by id desc", i=sid)
    desglose = db.de_json(d["desglose"], {})
    hotel = [(l["concepto"], l["valor"], l["origen"]) for l in desglose["lineas"] if l["grupo"] == "hotel"]
    assert hotel == [("Hotel: Tru by Hilton Las Vegas (3 noches)", 243.0, "buscador"),
                     ("Hotel: tarifa de miembro Hilton Honors (−5 %)", -12.15, "supuesto"),
                     ("Hotel: puntos de Hilton Honors (10 por USD a 0.005 USD)", -11.54, "supuesto")]
    # los puntos son valor esperado, como las millas: están en el total de la decisión pero no en el presupuesto
    assert desglose["hotel_evaluado"]["total"] == 219.31
    assert any(l["concepto"].startswith("Puntos del programa") for l in desglose["hotel_evaluado"]["lineas"])
    detalle = viajes.de_solicitud(sid)["presupuesto_detalle"]
    detalle = db.de_json(detalle) if isinstance(detalle, str) else detalle
    assert sum(l["valor"] for l in detalle if l["grupo"] == "hotel") == 230.85
    # la foto de lo mostrado guarda el costo evaluado y cuál era el recomendado
    fotos = db.todos("select * from elecciones where decision_id=:d and tipo='hotel' order by posicion", d=d["id"])
    assert [(f["opcion_id"], f["recomendada"], f["costo_esperado"]) for f in fotos] == [
        (tru["id"], 1, 219.31), (c["hoteles"][1]["id"], 0, 225.0)]


@pytest.mark.parametrize("carro_dia", [0, 65])
def test_el_total_de_la_decision_es_el_de_la_comparacion(cliente, carro_dia):
    from app import db
    from app.servicios import cotizacion, viajes
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Tru by Hilton Las Vegas", 243.0)], carro_dia=carro_dia)
    c = cotizacion.comparacion(sid)
    vuelo = c["vuelos"][0]
    cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": vuelo["id"], "hotel_id": c["hotel_recomendado"]["id"],
                                                 "razones": ["costo_total"]})
    d = db.uno("select * from decisiones where solicitud_id=:i order by id desc", i=sid)
    # el carro de alquiler no está en «Total con el hotel recomendado» (vuelo + hotel): se suma aparte
    assert d["total"] == round(vuelo["total_con_hotel"] + c["carro"], 2)
    # el presupuesto es lo que se paga: la tarifa con el descuento de miembro, sin los puntos
    detalle = viajes.de_solicitud(sid)["presupuesto_detalle"]
    detalle = db.de_json(detalle) if isinstance(detalle, str) else detalle
    assert [(l["concepto"], l["valor"]) for l in detalle if l["grupo"] == "hotel"] == [
        ("Hotel: Tru by Hilton Las Vegas (3 noches)", 243.0), ("Hotel: tarifa de miembro Hilton Honors (−5 %)", -12.15)]


# ---------- pieza 4: total del viaje visible ----------
def test_cada_vuelo_suma_el_hotel_recomendado(cliente):
    from app.servicios import cotizacion
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Independiente Centro", 225.0), _hotel("Tru by Hilton Las Vegas", 243.0)])
    c = cotizacion.comparacion(sid)
    assert all(v["total_con_hotel"] == round(v["ev"]["total"] + 219.31, 2) for v in c["vuelos"])
    assert all(v.get("total_con_hotel") is None for v in c["descartados"])
    pagina = cliente.get(f"/viajes/{sid}").text
    assert "Total con el hotel recomendado" in pagina and "Tarifa de miembro (−5 %)" in pagina
    assert "El más barato" in pagina and "Recomendado" in pagina


def test_sin_hoteles_no_hay_total_con_hotel(cliente):
    from app.servicios import cotizacion
    c = cotizacion.comparacion(_cotizacion_con_hoteles(cliente, []))
    assert c["hotel_recomendado"] is None and all(v["total_con_hotel"] is None for v in c["vuelos"])


def test_la_api_expone_los_hoteles_evaluados(cliente):
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Barato y mal calificado", 150.0, calificacion=3.3),
                                            _hotel("Independiente Centro", 225.0), _hotel("Tru by Hilton Las Vegas", 243.0)])
    api = cliente.get(f"/api/v1/cotizaciones/{sid}").json()
    tru, indep = api["hoteles"]
    assert (tru["nombre"], tru["recomendada"], tru["mas_barata"], tru["socio"], tru["programa"]) == (
        "Tru by Hilton Las Vegas", True, False, True, "Hilton Honors")
    assert tru["total_usd"] == "243.00" and tru["costo_total_usd"] == "219.31"
    assert [(l["tipo"], l["valor_usd"]) for l in tru["lineas"]] == [("tarifa", "243.00"), ("tarifa_miembro", "-12.15"),
                                                                    ("puntos", "-11.54")]
    assert "Acumula solo con reserva directa." in tru["avisos"] and tru["descartado"] is None
    assert indep["mas_barata"] and not indep["recomendada"] and indep["costo_total_usd"] == "225.00"
    assert api["hotel_recomendado_id"] == tru["id"]
    assert [(h["nombre"], h["descartado"]) for h in api["hoteles_descartados"]] == [
        ("Barato y mal calificado", "Calificación 3.3, por debajo del mínimo de 3.5.")]
    v = api["vuelos"][0]
    assert v["total_con_hotel_usd"] == f"{float(v['costo_total_usd']) + 219.31:.2f}"


# ---------- pieza 5: rótulos de dato de ejemplo ----------
def test_las_membresias_sembradas_llevan_el_rotulo(cliente):
    from app import db
    from datos import semilla
    filas = db.todos("select m.programa, m.ejemplo, v.nombre from membresias m left join viajeros v on v.id=m.viajero_id")
    sembradas = {(f["nombre"], f["programa"]) for f in filas if f["ejemplo"]}
    assert {("Andrés Molina", "AAdvantage"), ("Laura Pérez", "Miles & More"),
            (None, "Cuenta de empresa (AAdvantage Business)"), ("Andrés Molina", "Hilton Honors")} <= sembradas
    # una membresía real (no sembrada) no se marca
    real = db.insertar("membresias", viajero_id=2, programa="SkyMiles", entidad="Delta", estatus="")
    semilla.asegurar_fidelizacion_hotel()
    assert db.uno("select ejemplo from membresias where id=:i", i=real)["ejemplo"] is None
    pagina = cliente.get("/reglas").text
    assert pagina.count('<span class="chip aviso">Dato de ejemplo</span>') == len(sembradas)
    db.ejecutar("delete from membresias where id=:i", i=real)


def test_el_socio_de_ejemplo_se_rotula_en_hoteles(cliente):
    sid = _cotizacion_con_hoteles(cliente, [_hotel("Tru by Hilton Las Vegas", 243.0)])
    api = cliente.get(f"/api/v1/cotizaciones/{sid}").json()
    assert api["hoteles"][0]["socio"] and api["hoteles"][0]["membresia_de_ejemplo"]
    assert "socio · dato de ejemplo" in cliente.get(f"/viajes/{sid}").text


def test_el_tramo_de_la_demostracion_lleva_estado_de_ejemplo(cliente, monkeypatch):
    from app import config, db
    from datos import demo_monitoreo
    monkeypatch.setattr(config, "PREPARAR_BASE_LOCAL", True)
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    r = demo_monitoreo.preparar()
    tramo = db.uno("select * from tramos_vuelo where viaje_id=:v", v=r["viaje_id"])
    assert tramo["aerolinea"] == "Iberia · Estado de ejemplo"
    monkeypatch.setenv("MONITOREO_AHORA", demo_monitoreo.AHORA)   # el tablero muestra los tramos del día de ese ahora
    assert "Iberia · Estado de ejemplo" in cliente.get("/admin/viajes").text
