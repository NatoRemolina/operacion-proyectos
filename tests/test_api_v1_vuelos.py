"""API v1 del estado de los vuelos: tramos del día con su origen y «Actualizar ahora» con los topes. Contrato en `contracts/api-v1.md`.

Sin clave del buscador (como en estas pruebas) el estado sale de la respuesta guardada de ejemplo del repositorio
(IB 5634, Madrid → Lisboa, 13 de diciembre de 2026): la API lo marca «Estado de ejemplo».
"""
import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso

V1 = "/api/v1/vuelos"
MAD_LIS = dict(numero="IB 5634", desde="MAD", hasta="LIS", fecha="2026-12-13", aerolinea="Iberia",
               sale_programada="2026-12-13 09:05", llega_programada="2026-12-13 09:30")


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    return cuerpo["error"]


@pytest.fixture()
def tramo(nuevo_viaje, monkeypatch):
    """Un tramo del 13 de diciembre en un viaje aprobado, con el reloj dentro de su ventana y sin clave del buscador."""
    monkeypatch.setenv("MONITOREO_AHORA", "2026-12-13T06:00")
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    v = nuevo_viaje()
    tid = db.insertar("tramos_vuelo", viaje_id=v["id"], sentido="ida", orden=9, estado="programado", consultas=0, **MAD_LIS)
    yield db.uno("select * from tramos_vuelo where id=:i", i=tid)
    db.ejecutar("delete from tramos_vuelo where id=:i", i=tid)


def _del_tramo(cuerpo: dict, tid: int) -> dict:
    return next(t for t in cuerpo["tramos"] if t["id"] == tid)


def test_los_vuelos_del_dia_traen_estado_terminal_puerta_y_origen_de_ejemplo(cliente, tramo):
    r = cliente.get(V1, params={"fecha": "2026-12-13"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["fecha"] == "2026-12-13" and cuerpo["hoy"] == "2026-12-13"
    t = _del_tramo(cuerpo, tramo["id"])
    assert t["numero"] == "IB 5634" and t["codigo"].startswith("V-")
    # Dentro de la ventana el tablero consulta: la respuesta guardada trae el retraso, la terminal y la puerta
    assert t["estado"] == "retrasado" and t["retraso"] == 20 and t["puerta"] == "J58"
    assert t["origen"] == "guardado" and t["origen_texto"] == "Estado de ejemplo"
    assert t["consultas"] == 1


def test_sin_fecha_son_los_de_hoy_y_una_fecha_mala_se_ignora(cliente, tramo):
    assert tramo["id"] in {t["id"] for t in cliente.get(V1).json()["tramos"]}
    assert cliente.get(V1, params={"fecha": "13/12/2026"}).json()["fecha"] is None


def test_el_refresco_respeta_la_cache(cliente, tramo):
    cliente.get(V1)
    cliente.get(V1)
    assert db.uno("select consultas from tramos_vuelo where id=:i", i=tramo["id"])["consultas"] == 1


def test_actualizar_salta_la_cache_pero_no_dos_veces_en_el_mismo_minuto(cliente, tramo):
    r = cliente.post(f"{V1}/{tramo['id']}/actualizar", headers=_csrf(cliente))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["consultado"] is True and cuerpo["motivo"] is None and "estado actualizado" in cuerpo["mensaje"]
    assert cuerpo["tramo"]["id"] == tramo["id"] and cuerpo["tramo"]["origen_texto"] == "Estado de ejemplo"
    otra = cliente.post(f"{V1}/{tramo['id']}/actualizar", headers=_csrf(cliente)).json()
    assert otra["consultado"] is False and "hace menos de 1 min" in otra["motivo"]


def test_actualizar_fuera_de_la_ventana_no_consulta(cliente, tramo, monkeypatch):
    monkeypatch.setenv("MONITOREO_AHORA", "2026-12-12T06:00")
    r = cliente.post(f"{V1}/{tramo['id']}/actualizar", headers=_csrf(cliente)).json()
    assert r["consultado"] is False and r["motivo"] == "fuera de la ventana"
    assert db.uno("select consultas from tramos_vuelo where id=:i", i=tramo["id"])["consultas"] == 0


def test_actualizar_respeta_el_tope_del_tramo(cliente, tramo):
    db.actualizar("tramos_vuelo", tramo["id"], consultas=99)
    r = cliente.post(f"{V1}/{tramo['id']}/actualizar", headers=_csrf(cliente)).json()
    assert r["consultado"] is False and r["motivo"].startswith("tope de")


def test_actualizar_exige_csrf_y_un_tramo_que_exista(cliente, tramo):
    _error(cliente.post(f"{V1}/{tramo['id']}/actualizar"), 403, "CSRF_INVALID")
    _error(cliente.post(f"{V1}/999999/actualizar", headers=_csrf(cliente)), 404, "NOT_FOUND")


def test_vuelos_es_solo_de_administracion(piloto, gestor, anonimo, tramo):
    # Ni siquiera quien viaja: el tablero es de administración, como hoy
    _error(piloto.get(V1), 403, "FORBIDDEN")
    _error(gestor.get(V1), 403, "FORBIDDEN")
    _error(anonimo.get(V1), 401, "UNAUTHENTICATED")
    _error(piloto.post(f"{V1}/{tramo['id']}/actualizar", headers=_csrf(piloto)), 403, "FORBIDDEN")
    _error(anonimo.post(f"{V1}/{tramo['id']}/actualizar"), 401, "UNAUTHENTICATED")
    assert db.uno("select consultas from tramos_vuelo where id=:i", i=tramo["id"])["consultas"] == 0
