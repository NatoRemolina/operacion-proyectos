"""Arreglos de la auditoría de seguridad previa a la publicación."""
from fastapi import Response

from app import config, db
from app.servicios import acceso
from tests.conftest import _con_sesion


def test_un_gestor_que_pasa_a_colaborador_deja_de_ver_su_proyecto(cliente):
    uid = acceso.crear_usuario("gestor-temporal@demo.local", "Gestor temporal", "gestor", "clave-temporal-2026")
    db.insertar("proyecto_miembros", usuario_id=uid, proyecto_id=1, papel="gestor", creado=db.ahora())
    try:
        antes = _con_sesion("gestor-temporal@demo.local", "clave-temporal-2026")
        assert antes.get("/proyectos/1").status_code == 200
        cliente.post(f"/admin/usuarios/{uid}", data={"accion": "rol", "rol": "colaborador"})
        assert not db.uno("select 1 from proyecto_miembros where usuario_id=:u", u=uid)   # pierde la pertenencia
        despues = _con_sesion("gestor-temporal@demo.local", "clave-temporal-2026")
        assert despues.get("/proyectos/1").status_code == 404
        assert despues.get("/proyectos/1/exportar.csv").status_code == 404
    finally:
        db.ejecutar("delete from proyecto_miembros where usuario_id=:u", u=uid)
        db.ejecutar("delete from sesiones where usuario_id=:u", u=uid)
        db.ejecutar("update usuarios set activo=0 where id=:u", u=uid)


def test_la_pertenencia_sola_no_abre_el_tablero_a_quien_no_es_gestor(cliente):
    uid = acceso.crear_usuario("colaborador-miembro@demo.local", "Colaborador miembro", "colaborador", "clave-temporal-2026")
    db.insertar("proyecto_miembros", usuario_id=uid, proyecto_id=1, papel="gestor", creado=db.ahora())
    try:
        assert _con_sesion("colaborador-miembro@demo.local", "clave-temporal-2026").get("/proyectos/1").status_code == 404
    finally:
        db.ejecutar("delete from proyecto_miembros where usuario_id=:u", u=uid)
        db.ejecutar("delete from sesiones where usuario_id=:u", u=uid)
        db.ejecutar("update usuarios set activo=0 where id=:u", u=uid)


def test_cerrar_sesion_borra_la_cookie_segura_en_el_navegador(monkeypatch):
    monkeypatch.setattr(config, "LOCAL", False)
    monkeypatch.setattr(acceso, "COOKIE", "__Host-sesion")
    cabecera = acceso.cerrar_sesion(Response(), None).headers["set-cookie"]
    # Un navegador solo acepta borrar una cookie __Host- si la orden también es Secure y con Path=/
    assert cabecera.startswith("__Host-sesion=") and "Secure" in cabecera and "Path=/" in cabecera and "Max-Age=0" in cabecera


def test_no_hay_redoc(cliente, piloto):
    assert piloto.get("/redoc").status_code == 404
    assert cliente.get("/redoc").status_code == 404


def test_las_cuentas_de_demostracion_no_se_crean_en_una_base_remota(monkeypatch):
    from datos import semilla
    creadas = []
    monkeypatch.setattr(semilla.db, "uno", lambda *a, **k: None)   # como si la base no tuviera usuarios
    monkeypatch.setattr(semilla.db, "insertar", lambda *a, **k: 0)   # la pertenencia del gestor de ejemplo
    monkeypatch.setattr(acceso, "crear_usuario", lambda *a, **k: creadas.append(a[0]) or 0)
    monkeypatch.setattr(config, "LOCAL", True)
    monkeypatch.setattr(config, "ES_SQLITE", False)
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://postgres.proyecto:x" + "@aws-0-us-east-1.pooler.supabase.com:5432/postgres")
    monkeypatch.setenv("CUENTAS_DEMO", "1")
    monkeypatch.delenv("ADMIN_INICIAL_CORREO", raising=False)
    semilla.sembrar_cuentas()
    assert not [c for c in creadas if c.endswith("@demo.local")]
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://operacion:operacion-local" + "@db:5432/operacion")
    semilla.sembrar_cuentas()   # la base de Docker sí es local
    assert "admin@demo.local" in creadas
