"""Ronda 1: el asesor (agente alojado) puede pedir los viajes y los gastos de un proyecto.

Las herramientas del asistente ya filtran por proyecto; faltaba ofrecerlo en los esquemas que conoce el agente y decir
en sus instrucciones cuándo usarlo. Aquí no se publica nada en el servicio del asesor: lo sincroniza quien integra.
"""
from app import db
from app.servicios import asesor, asistente


def _esquema(nombre: str) -> dict:
    return next(e for e in asesor.ESQUEMAS if e["name"] == nombre)["input_schema"]


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


def test_viajes_de_y_gastos_de_ofrecen_proyecto_opcional():
    for nombre in ("viajes_de", "gastos_de"):
        esquema = _esquema(nombre)
        assert esquema["properties"]["proyecto"]["type"] == "string"
        assert "proyecto" not in esquema.get("required", [])
    # Con el proyecto basta: la persona deja de ser obligatoria en viajes_de
    assert _esquema("viajes_de").get("required", []) == []


def test_las_instrucciones_dicen_cuando_pedir_por_proyecto():
    lineas = [linea for linea in asesor.SISTEMA.splitlines() if "proyecto" in linea and ("viajes_de" in linea or "gastos_de" in linea)]
    assert lineas, "las instrucciones deben decir que viajes_de y gastos_de aceptan un proyecto"


def test_el_proyecto_llega_a_la_herramienta():
    r = asistente.Rastro(_admin())
    viajes = asesor.despachar(r, "viajes_de", {"proyecto": "1"}, _admin())
    gastos = asesor.despachar(r, "gastos_de", {"proyecto": "1"}, _admin())
    assert "proyecto" in viajes and "viajes" in viajes, viajes
    assert "gastos" in gastos and "error" not in gastos, gastos
