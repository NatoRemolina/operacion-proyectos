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
