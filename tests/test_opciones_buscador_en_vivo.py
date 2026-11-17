"""I-8 (QA del 16 nov): la capa del buscador sabe si vale la pena esperar la consulta en vivo.

`OpcionesBuscador.en_vivo` dice si el buscador está encendido (hay clave): entonces el mismo clic que abre el desglose lo
consulta y lo nuevo llega a esta ruta en unos segundos, y la web reintenta. Sin clave, lo guardado es todo lo que hay.
Leer la ruta nunca paga una búsqueda, con clave o sin ella.
"""
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from app import api_v1, config
from app.servicios import acceso, analizador, precios

V1 = "/api/v1"
PEDIDO = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
          "ida": "2026-12-08", "regreso": "2026-12-11"}


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


@pytest.fixture
def consultas(monkeypatch):
    """Ninguna búsqueda paga: cada consulta al buscador queda anotada y no sale."""
    llamadas = []
    monkeypatch.setattr(precios, "_consultar", lambda *a, **k: llamadas.append(a) or {})
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    return llamadas


def _rutas(piloto: TestClient) -> dict:
    """Cotiza sin clave (de lo guardado) y devuelve la ruta `…/reserva` del AA 1851 (con respaldo) y la de otro vuelo."""
    c = piloto.post(f"{V1}/cotizaciones", json=PEDIDO, headers=_csrf(piloto)).json()
    vuelos = c["vuelos"] + c["descartados"]
    ruta = lambda v: f"{V1}/cotizaciones/{c['id']}/vuelos/{v['id']}/reserva"  # noqa: E731
    return {"respaldo": ruta(next(v for v in vuelos if v["numeros"] == ["AA 1851"])),
            "sin_datos": ruta(next(v for v in vuelos if v["numeros"] != ["AA 1851"]))}


def test_sin_clave_en_vivo_es_falso(piloto, consultas):
    rutas = _rutas(piloto)
    con, sin = piloto.get(rutas["respaldo"]).json(), piloto.get(rutas["sin_datos"]).json()
    assert (con["estado"], con["consultado"], con["en_vivo"]) == ("listo", None, False)   # el respaldo, «de referencia»
    assert (sin["estado"], sin["en_vivo"]) == ("sin_datos", False)
    assert consultas == []


def test_con_clave_en_vivo_es_verdadero_y_leer_no_consulta(piloto, consultas, monkeypatch):
    rutas = _rutas(piloto)
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    con, sin = piloto.get(rutas["respaldo"]).json(), piloto.get(rutas["sin_datos"]).json()
    assert (con["estado"], con["en_vivo"]) == ("listo", True) and (sin["estado"], sin["en_vivo"]) == ("sin_datos", True)
    assert consultas == []


# ---------- ronda 1: con el cupo del día agotado, el clic no consulta: no hay nada que esperar ----------
@pytest.fixture
def cupo(piloto):
    """Reserva búsquedas del cupo diario del enlace al vendedor a nombre del piloto; al final las borra."""
    from app import db
    from app.servicios import tiempo
    uid = db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]
    marca = "prueba-en-vivo-" + str(id(piloto))

    def reservar(unidades: int, hace_minutos: float | None = None):
        creado = tiempo.inicio_del_dia() if hace_minutos is None else \
            (datetime.now(UTC) - timedelta(minutes=hace_minutos)).strftime("%Y-%m-%d %H:%M:%S")
        db.insertar("cupos_buscador", usuario_id=uid, tipo="enlace_vendedor", clave=marca, unidades=unidades, creado=creado)

    yield reservar
    db.ejecutar("delete from cupos_buscador where clave=:m", m=marca)


def test_con_el_cupo_del_dia_agotado_en_vivo_es_falso(piloto, consultas, monkeypatch, cupo):
    rutas = _rutas(piloto)
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    cupo(analizador.tope_enlace_vendedor())                           # usado desde la mañana
    con, sin = piloto.get(rutas["respaldo"]).json(), piloto.get(rutas["sin_datos"]).json()
    assert (con["en_vivo"], sin["en_vivo"]) == (False, False) and consultas == []


def test_la_reserva_de_este_clic_no_cuenta_como_cupo_agotado(piloto, consultas, monkeypatch, cupo):
    """El clic reserva su cupo antes de buscar: si con eso llegó al tope, su consulta sí sale y hay que esperarla."""
    rutas = _rutas(piloto)
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    cupo(analizador.tope_enlace_vendedor() - 1)
    cupo(1, hace_minutos=0.2)                                         # la de este clic, hace un momento
    assert piloto.get(rutas["respaldo"]).json()["en_vivo"] is True and consultas == []


def test_con_el_tope_del_dia_en_cero_en_vivo_es_falso(piloto, consultas, monkeypatch):
    from app import db
    rutas = _rutas(piloto)
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    regla = db.uno("select id, valor from reglas where ambito='supuesto' and clave='enlace_vendedor_persona_dia'")
    if regla:
        db.actualizar("reglas", regla["id"], valor="0")
    else:
        monkeypatch.setattr(analizador, "tope_enlace_vendedor", lambda: 0)
    try:
        assert piloto.get(rutas["respaldo"]).json()["en_vivo"] is False and consultas == []
    finally:
        if regla:
            db.actualizar("reglas", regla["id"], valor=regla["valor"])
