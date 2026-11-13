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
