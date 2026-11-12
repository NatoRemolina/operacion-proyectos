"""Comportamientos comunes a toda la plataforma: seguridad de las respuestas, errores legibles y cifras coherentes."""
from app import db
from app.main import _indicadores
from app.servicios import viajes


def test_toda_respuesta_lleva_cabeceras_de_seguridad(cliente, anonimo):
    for r in (cliente.get("/"), anonimo.get("/entrar"), cliente.get("/api/viajes"), cliente.get("/viaje/999999")):
        assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in r.headers["Content-Security-Policy"] and r.headers.get("X-Peticion") or r.status_code == 200


def test_los_errores_son_paginas_legibles(cliente, piloto):
    perdido = cliente.get("/viaje/999999")
    assert perdido.status_code == 404 and "Volver al inicio" in perdido.text
    vedado = piloto.get("/admin/viajes")
    assert vedado.status_code == 403 and "administración" in vedado.text and "Volver al inicio" in vedado.text
    assert piloto.get("/api/viajes").status_code == 403 and piloto.get("/api/viajes").json()["error"]


def test_el_menu_depende_del_rol(cliente, piloto, gestor):
    assert "Monitoreo" in cliente.get("/").text and "Usuarios y roles" in cliente.get("/").text
    for quien in (piloto, gestor):
        pagina = quien.get("/").text
        assert "Mis viajes" in pagina and "Monitoreo" not in pagina and "Usuarios y roles" not in pagina


def test_cada_persona_cambia_su_propia_clave(cliente, anonimo):
    cliente.post("/admin/usuarios", data={"correo": "clave@demo.local", "nombre": "Cambia Clave", "rol": "piloto", "clave": "clave-inicial-1"})
    anonimo.post("/entrar", data={"correo": "clave@demo.local", "clave": "clave-inicial-1"})
    assert "no+coincide" in anonimo.post("/mi-cuenta/clave", data={"actual": "otra", "nueva": "clave-nueva-123"}, follow_redirects=False).headers["location"]
    assert "10+caracteres" in anonimo.post("/mi-cuenta/clave", data={"actual": "clave-inicial-1", "nueva": "corta"}, follow_redirects=False).headers["location"]
    anonimo.post("/mi-cuenta/clave", data={"actual": "clave-inicial-1", "nueva": "clave-nueva-123"})
    assert anonimo.get("/mi-cuenta").status_code == 200                      # la sesión propia sigue viva
    anonimo.post("/salir")
    assert anonimo.post("/entrar", data={"correo": "clave@demo.local", "clave": "clave-inicial-1"}, follow_redirects=False).headers["location"] != "/"
    assert anonimo.post("/entrar", data={"correo": "clave@demo.local", "clave": "clave-nueva-123"}, follow_redirects=False).headers["location"] == "/"


def test_el_previsto_es_una_sola_cifra(cliente, viaje_aprobado):
    """Inicio, tablero de proyecto y viajes deben sumar lo mismo: el presupuesto de los viajes."""
    aprobados = viajes.lista("v.estado in ('aprobado','cerrado')")
    assert round(_indicadores()["previsto"], 2) == round(sum(v["presupuesto_usd"] or 0 for v in aprobados), 2)
    del_proyecto = viajes.lista("v.proyecto_id=1 and v.estado<>'rechazado'")
    total = round(sum(v["presupuesto_usd"] or 0 for v in del_proyecto), 2)
    assert f"{total:,.2f} USD" in cliente.get("/proyectos/1").text


def test_los_proyectos_se_crean_y_editan_desde_la_plataforma(cliente, piloto):
    campos = dict(nombre="Torre Norte (aéreo)", cliente="Constructora de prueba", ciudad="Denver", fecha_inicio="2026-12-15", fecha_fin="2026-12-18", moneda="usd")
    assert piloto.post("/admin/proyectos", data=campos).status_code == 403
    assert "aviso=" in cliente.post("/admin/proyectos", data={**campos, "fecha_fin": "2026-12-01"}, follow_redirects=False).headers["location"]
    assert not db.uno("select id from proyectos where nombre=:n", n=campos["nombre"])          # fechas al revés: no se crea
    cliente.post("/admin/proyectos", data=campos)
    p = db.uno("select * from proyectos where nombre=:n", n=campos["nombre"])
    assert p["moneda"] == "USD" and p["ciudad"] == "Denver"
    assert campos["nombre"] in cliente.get("/viajes/nuevo").text                               # ya se puede cotizar para él
    cliente.post(f"/admin/proyectos/{p['id']}", data={**campos, "ciudad": "Boulder"})
    assert db.uno("select ciudad from proyectos where id=:i", i=p["id"])["ciudad"] == "Boulder"
    assert db.uno("select count(*) n from eventos where entidad='proyecto' and entidad_id=:i", i=p["id"])["n"] == 2
