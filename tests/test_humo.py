"""Prueba de humo: cada página de lectura responde para cada rol con un código esperado, nunca con un error interno.

Una plantilla rota o una consulta mal escrita aparece aquí como 500 en la ruta y el rol exactos.
"""
import re

import pytest

from app import db, web
from app.main import app
from app.servicios import acceso

EXCLUIDAS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect", "/salud"}
RUTAS_GET = sorted(r.path for r in app.routes
                   if "GET" in getattr(r, "methods", set()) and r.path not in EXCLUIDAS and not r.path.startswith("/api/v1"))
EXTRA = {"/admin/monitoreo/exportar.csv": "?vista=v_h_gasto"}


@pytest.fixture(scope="module")
def ids(cliente, viaje_aprobado, ejemplos):
    """Un identificador real para cada parámetro de ruta, todos del piloto de demostración y del proyecto 1."""
    cliente.post("/gastos/cargar", data={"canal": "web", "viaje_id": viaje_aprobado["id"]}, headers={"X-Envio": "pagina"},
                 files={"archivos": ("r.png", (ejemplos / "recibo_gasolina.png").read_bytes(), "image/png")})
    gasto = db.uno("select id from gastos where viaje_id=:v order by id desc", v=viaje_aprobado["id"])
    cliente.post(f"/gastos/{gasto['id']}/justificacion", data={"texto": "Gasolina del carro de alquiler para llegar al set"})
    piloto = db.uno("select id from usuarios where correo='piloto@demo.local'")
    return {"sid": viaje_aprobado["solicitud_id"], "vid": viaje_aprobado["id"], "gid": gasto["id"], "pid": 1,
            "uid": piloto["id"], "doc": 999999, "jid": 999999}


@pytest.mark.parametrize("rol", ["cliente", "piloto", "gestor"])
@pytest.mark.parametrize("ruta", RUTAS_GET)
def test_cada_pagina_responde_segun_el_rol(ruta, rol, ids, request):
    quien = request.getfixturevalue(rol)
    url = re.sub(r"\{(\w+)\}", lambda m: str(ids[m[1]]), ruta) + EXTRA.get(ruta, "")
    r = quien.get(url, follow_redirects=False)
    assert r.status_code != 500, (rol, url, r.text[:300])
    if acceso.nivel(ruta) == "admin" and rol != "cliente":
        assert r.status_code == 403, (rol, url, r.status_code)
    else:
        assert r.status_code in (200, 303, 404), (rol, url, r.status_code)


def test_toda_entrada_de_menu_de_administracion_esta_protegida_por_su_ruta():
    """El menú oculta el enlace, pero quien protege es el control de acceso: una entrada de administración
    con una ruta fuera de los prefijos reservados quedaría abierta a cualquier cuenta."""
    for entrada in web.MENU:
        if entrada.get("rol") == "admin":
            assert acceso.nivel(entrada["href"]) == "admin", entrada
