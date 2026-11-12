"""Permiso y cargo son cosas distintas: el permiso dice qué se puede hacer; el cargo, qué hace la persona en la empresa."""
import re

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from app import db
from app.main import app
from app.servicios import acceso
from datos import migracion

CARGOS_INICIALES = {"Pilotaje de dron", "Edición de video", "Desarrollo de software", "Ingeniería de datos", "Producción"}


def _cargo_de(correo: str) -> str | None:
    fila = db.uno("select c.nombre from usuarios u left join cargos c on c.id=u.cargo_id where u.correo=:c", c=correo)
    return fila["nombre"] if fila else None


def _id_cargo(nombre: str) -> int:
    return db.uno("select id from cargos where nombre=:n", n=nombre)["id"]


def _formulario_de_creacion(html: str) -> str:
    return re.search(r'<form[^>]*id="crear-cuenta".*?</form>', html, re.S).group(0)


def test_la_migracion_pasa_piloto_a_colaborador_con_su_cargo():
    # Se simula una base anterior: la restricción solo admite «piloto», sin cargos y sin perfil para gestión y administración
    migracion._rehacer_usuarios_sqlite(("piloto", "gestor", "admin"), {"colaborador": "piloto"})
    db.ejecutar("update usuarios set cargo_id=null where correo in ('piloto@demo.local','piloto2@demo.local')")
    assert db.uno("select rol from usuarios where correo='piloto@demo.local'")["rol"] == "piloto"
    antes = db.uno("select count(*) n from eventos where paso='permiso migrado'")["n"]

    migracion.migrar()

    piloto = db.uno("select id, rol from usuarios where correo='piloto@demo.local'")
    assert piloto["rol"] == "colaborador" and _cargo_de("piloto@demo.local") == "Pilotaje de dron"
    assert _cargo_de("piloto2@demo.local") == "Pilotaje de dron"
    assert not db.todos("select id from usuarios where rol='piloto'")
    assert CARGOS_INICIALES <= {c["nombre"] for c in db.todos("select nombre from cargos")}
    migrados = db.uno("select count(*) n from eventos where paso='permiso migrado'")["n"] - antes
    assert migrados >= 2                                                  # un evento por cuenta migrada
    assert db.todos("select id from eventos where paso='permiso migrado' and entidad='usuario' and entidad_id=:i", i=piloto["id"])

    # Una segunda ejecución no cambia nada
    foto = (db.todos("select id, rol, cargo_id, viajero_id from usuarios order by id"), db.todos("select * from cargos order by id"),
            db.uno("select count(*) n from eventos")["n"], db.uno("select count(*) n from viajeros")["n"])
    migracion.migrar()
    assert foto == (db.todos("select id, rol, cargo_id, viajero_id from usuarios order by id"), db.todos("select * from cargos order by id"),
                    db.uno("select count(*) n from eventos")["n"], db.uno("select count(*) n from viajeros")["n"])
    # La restricción sigue rechazando un permiso que no existe
    with pytest.raises(IntegrityError):
        db.ejecutar("update usuarios set rol='piloto' where correo='piloto@demo.local'")
    assert db.uno("select rol from usuarios where correo='piloto@demo.local'")["rol"] == "colaborador"


def test_toda_cuenta_tiene_perfil_de_viajero():
    db.ejecutar("update usuarios set viajero_id=null where correo in ('gestor@demo.local','admin@demo.local')")
    migracion.migrar()
    for correo in ("gestor@demo.local", "admin@demo.local"):
        u = db.uno("select viajero_id from usuarios where correo=:c", c=correo)
        assert u["viajero_id"], correo
        assert db.todos("select id from eventos where entidad='viajero' and entidad_id=:v and paso='perfil de viajero creado'", v=u["viajero_id"])
    uid = acceso.crear_usuario("gestora-cargo@demo.local", "Gestora con perfil", "gestor", "clave-de-gestora-1", cargo_id=_id_cargo("Producción"))
    u = db.uno("select viajero_id, cargo_id from usuarios where id=:i", i=uid)
    assert u["viajero_id"] and u["cargo_id"] == _id_cargo("Producción")
    assert db.uno("select rol from viajeros where id=:i", i=u["viajero_id"])["rol"] == "Producción"
    sin_cargo = acceso.crear_usuario("admin-sin-cargo@demo.local", "Admin sin cargo", "admin", "clave-de-admin-1")
    v = db.uno("select v.rol from usuarios u join viajeros v on v.id=u.viajero_id where u.id=:i", i=sin_cargo)
    assert v["rol"] == "Viajero"


def test_administracion_crea_renombra_y_desactiva_cargos(cliente):
    cliente.post("/admin/cargos", data={"nombre": "Fotografía"})
    foto = db.uno("select id, activo from cargos where nombre='Fotografía'")
    assert foto and foto["activo"] == 1
    assert db.todos("select id from eventos where entidad='cargo' and entidad_id=:i and paso='cargo creado' and usuario_id is not null", i=foto["id"])

    r = cliente.post("/admin/cargos", data={"nombre": "  fotografía "}, follow_redirects=False)
    assert "aviso=" in r.headers["location"] and db.uno("select count(*) n from cargos where lower(nombre)='fotografía'")["n"] == 1
    assert "Ya existe" in cliente.get(r.headers["location"]).text
    assert "aviso=" in cliente.post("/admin/cargos", data={"nombre": "ab"}, follow_redirects=False).headers["location"]

    cliente.post(f"/admin/cargos/{foto['id']}", data={"accion": "renombrar", "nombre": "Fotografía aérea"})
    assert db.uno("select nombre from cargos where id=:i", i=foto["id"])["nombre"] == "Fotografía aérea"
    assert db.todos("select id from eventos where entidad='cargo' and entidad_id=:i and paso='cargo renombrado'", i=foto["id"])

    # Se asigna a una persona y luego se desactiva: no se borra, la persona lo conserva
    uid = acceso.crear_usuario("fotografa@demo.local", "Fotógrafa", "colaborador", "clave-de-fotografa-1")
    cliente.post(f"/admin/usuarios/{uid}", data={"accion": "cargo", "cargo_id": foto["id"]})
    assert db.uno("select cargo_id from usuarios where id=:i", i=uid)["cargo_id"] == foto["id"]
    assert db.todos("select id from eventos where entidad='usuario' and entidad_id=:i and paso='cargo asignado' and usuario_id is not null", i=uid)

    cliente.post(f"/admin/cargos/{foto['id']}", data={"accion": "estado", "activo": "0"})
    assert db.uno("select activo from cargos where id=:i", i=foto["id"])["activo"] == 0
    assert db.uno("select cargo_id from usuarios where id=:i", i=uid)["cargo_id"] == foto["id"]
    assert db.todos("select id from eventos where entidad='cargo' and entidad_id=:i and paso='cargo desactivado'", i=foto["id"])
    assert {c["nombre"] for c in acceso.cargos()} >= CARGOS_INICIALES and "Fotografía aérea" not in {c["nombre"] for c in acceso.cargos()}
    todos = {c["nombre"]: c for c in acceso.cargos(solo_activos=False)}
    assert todos["Fotografía aérea"]["personas"] == 1 and todos["Fotografía aérea"]["activo"] == 0

    pagina = cliente.get("/admin/usuarios").text
    assert "Fotografía aérea" in pagina                                         # sigue en la lista de cargos y en la persona
    assert "Fotografía aérea" not in _formulario_de_creacion(pagina) and "Edición de video" in _formulario_de_creacion(pagina)
    with pytest.raises(ValueError):
        acceso.crear_usuario("otra-foto@demo.local", "Otra", "colaborador", "clave-de-otra-foto-1", cargo_id=foto["id"])


def test_el_cargo_no_da_permisos(cliente, ejemplos):
    acceso.crear_usuario("editora@demo.local", "Editora de video", "colaborador", "clave-de-editora-1", cargo_id=_id_cargo("Edición de video"))
    editora = TestClient(app)
    editora.post("/entrar", data={"correo": "editora@demo.local", "clave": "clave-de-editora-1"})
    assert editora.get("/admin/usuarios").status_code == 403
    assert editora.post("/admin/cargos", data={"nombre": "Cargo de la editora"}).status_code == 403
    ajeno = cliente.post("/gastos/cargar", data={"proyecto_id": 1, "viajero_id": 2, "canal": "web"}, headers={"X-Envio": "pagina"},
                         files={"archivos": ("r.png", (ejemplos / "recibo_lisboa.png").read_bytes(), "image/png")}).json()["gastos"][0]
    r = editora.get("/gastos")
    assert r.status_code == 200 and f'href="/gastos/{ajeno}"' not in r.text


def test_la_api_devuelve_rol_y_cargo(piloto):
    persona = piloto.get("/api/v1/auth/me").json()["persona"]
    assert persona["rol"] == "colaborador" and persona["cargo"] == "Pilotaje de dron"
    assert acceso.ROLES == ("colaborador", "gestor", "admin") and acceso.NOMBRE_ROL["colaborador"] == "colaborador"
