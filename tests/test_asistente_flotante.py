"""Asistente flotante: aparece solo a administración y pide a /admin/asistente la respuesta en JSON, sin la página.

Las pruebas corren sin asesor ni modelo (ver conftest): la vía que responde es la de consultas directas.
"""
import pytest

from app import db
from app.servicios import asistente, viajes

JSON = {"X-Envio": "pagina"}
CLAVES = {"texto", "modo", "modo_texto", "modo_clase", "fuentes", "herramientas", "duracion_ms", "usadas", "tope"}


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


@pytest.fixture(scope="module")
def andres(nuevo_viaje):
    """El piloto de demostración con un viaje propio de estas pruebas y un gasto en revisión."""
    v = nuevo_viaje(viajero_id=1)
    uid = db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]
    gid = db.insertar("gastos", usuario_id=uid, viaje_id=v["id"], proyecto_id=v["proyecto_id"], viajero_id=v["viajero_id"],
                      comercio="Parador Flotante", fecha="2026-12-09", categoria="comida", total=23.45, moneda="USD",
                      total_usd=23.45, estado="revision", confianza=0.95, creado=db.ahora())
    return {"id": uid, "viaje": v, "gasto": gid}


# ---------- dónde aparece ----------
@pytest.mark.parametrize("ruta", ["/", "/gastos"])
def test_administracion_ve_la_burbuja_con_su_guion(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code == 200
    assert 'id="asistente-flotante"' in r.text and 'aria-controls="af-panel"' in r.text
    assert '<script src="/static/asistente_flotante.js?v=' in r.text


def test_otros_permisos_no_ven_la_burbuja(piloto, gestor):
    for c in (piloto, gestor):
        r = c.get("/")
        assert r.status_code == 200 and "asistente-flotante" not in r.text


def test_la_pagina_del_asistente_no_repite_la_burbuja(cliente):
    r = cliente.get("/admin/asistente")
    assert r.status_code == 200 and 'id="asistente-flotante"' not in r.text


def test_el_guion_se_sirve(anonimo):
    r = anonimo.get("/static/asistente_flotante.js")
    assert r.status_code == 200 and "X-Envio" in r.text


# ---------- respuesta en JSON ----------
def test_responde_json_con_fuentes_y_cuenta_de_preguntas(cliente, andres):
    antes = asistente.usadas_hoy(_admin()["id"])
    r = cliente.post("/admin/asistente", data={"pregunta": f"¿Qué ha reportado {viajes.codigo_persona(andres['id'])} en su viaje?"},
                     headers=JSON)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    d = r.json()
    assert set(d) == CLAVES
    assert d["modo"] == "determinista" and d["modo_texto"] == "Sin modelo: consultas directas" and d["modo_clase"] == "azul"
    assert f"Gasto #{andres['gasto']}" in d["texto"] and "23.45 USD" in d["texto"]
    assert {"codigo": f"gasto #{andres['gasto']}", "enlace": f"/gastos/{andres['gasto']}"} in d["fuentes"]
    assert all(f["enlace"] is None or (f["enlace"].startswith("/") and not f["enlace"].startswith("//")) for f in d["fuentes"])
    assert d["usadas"] == antes + 1 and d["tope"] == asistente.tope_diario()
    fila = db.uno("select modo, usuario_id from asistente_consultas order by id desc limit 1")
    assert fila["modo"] == "determinista" and fila["usuario_id"] == _admin()["id"]


def test_pregunta_vacia_responde_sin_chip(cliente):
    d = cliente.post("/admin/asistente", data={"pregunta": "   "}, headers=JSON).json()
    assert d["texto"] == "Escribe una pregunta." and d["modo"] == "" and d["modo_texto"] == ""


def test_sin_la_cabecera_sigue_siendo_la_pagina(cliente):
    r = cliente.post("/admin/asistente", data={"pregunta": "¿Cuál es el gasto real aprobado?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Sin modelo: consultas directas" in r.text


def test_el_tope_diario_se_presenta_como_aviso(cliente):
    asistente.asegurar_regla()
    regla = db.uno("select id, valor from reglas where clave='asistente_preguntas_dia'")
    db.actualizar("reglas", regla["id"], valor=str(asistente.usadas_hoy(_admin()["id"])))
    try:
        d = cliente.post("/admin/asistente", data={"pregunta": "¿Cuál es el gasto real aprobado?"}, headers=JSON).json()
        assert d["modo"] == "tope" and d["modo_texto"] == "Tope diario alcanzado" and d["modo_clase"] == "aviso"
    finally:
        db.actualizar("reglas", regla["id"], valor=regla["valor"])


# ---------- bordes ----------
def test_sesion_vencida_responde_json_para_la_burbuja(anonimo):
    r = anonimo.post("/admin/asistente", data={"pregunta": "¿Hola?"}, headers=JSON)
    assert r.status_code == 401 and r.json()["sesion"] == "vencida"


def test_otros_permisos_no_pueden_preguntar(piloto, gestor):
    for c in (piloto, gestor):
        assert c.post("/admin/asistente", data={"pregunta": "¿Qué gastos hay?"}, headers=JSON).status_code == 403


def test_desde_otro_sitio_se_rechaza(cliente):
    for cabecera in ({"Origin": "https://sitio-ajeno.example"}, {"Sec-Fetch-Site": "cross-site"}):
        r = cliente.post("/admin/asistente", data={"pregunta": "¿Qué gastos hay?"}, headers={**JSON, **cabecera})
        assert r.status_code == 403
