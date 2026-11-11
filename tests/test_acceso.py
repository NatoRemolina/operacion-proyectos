"""Quién puede qué: ingreso, roles, propiedad de los datos, origen de los formularios y revocación."""
from app import db
from app.main import app
from app.servicios import acceso
from starlette.testclient import TestClient

FORM = dict(proyecto_id=1, viajero_id=2, origen="MIA", destino="LAS", ida="2026-12-08", regreso="2026-12-11")


def test_toda_ruta_tiene_nivel_y_sin_sesion_no_se_entra(anonimo):
    rutas = sorted({r.path for r in app.routes if hasattr(r, "methods") and "GET" in r.methods})
    for ruta in rutas:
        concreta = ruta.replace("{sid}", "1").replace("{gid}", "1").replace("{pid}", "1").replace("{oid}", "1")
        r = anonimo.get(concreta, follow_redirects=False)
        if acceso.nivel(ruta) == "publica":
            assert r.status_code == 200, ruta
        else:
            assert r.status_code in (303, 401), ruta      # nunca contenido sin sesión
    assert anonimo.get("/api/gastos").status_code == 401


def test_ingreso_incorrecto_no_dice_que_fallo_y_bloquea(anonimo):
    for _ in range(6):
        r = anonimo.post("/entrar", data={"correo": "piloto@demo.local", "clave": "equivocada-123"}, follow_redirects=False)
        assert "error=" in r.headers["location"]
    r = anonimo.post("/entrar", data={"correo": "piloto@demo.local", "clave": "demo-piloto-2026"}, follow_redirects=False)
    assert "Demasiados" in r.headers["location"] or "intentos" in r.headers["location"]   # bloqueada aunque la clave sea correcta
    db.ejecutar("update usuarios set fallos=0, bloqueado_hasta=null where correo='piloto@demo.local'")


def test_usuario_no_entra_a_administracion(piloto):
    for ruta in ("/analitica", "/flujo", "/reglas", "/proyectos/1", "/admin/usuarios", "/api/gastos", "/docs"):
        assert piloto.get(ruta).status_code == 403, ruta
    assert piloto.post("/reglas/1", data={"valor": "999"}).status_code == 403
    assert piloto.post("/gastos/ejemplos", data={"nombres": ["recibo_diner.png"]}).status_code == 403


def test_usuario_solo_ve_lo_suyo_y_no_aprueba(cliente, piloto, ejemplos):
    # El administrador crea un viaje y un gasto para OTRO viajero
    sid = int(cliente.post("/viajes", data=FORM, follow_redirects=False).headers["location"].rsplit("/", 1)[1])
    gid = cliente.post("/gastos/cargar", data={"proyecto_id": 1, "viajero_id": 2, "canal": "web"}, headers={"X-Envio": "pagina"},
                       files={"archivos": ("r.png", (ejemplos / "recibo_lisboa.png").read_bytes(), "image/png")}).json()["gastos"][0]
    for ruta in (f"/viajes/{sid}", f"/viajes/{sid}/ficha", f"/gastos/{gid}", f"/gastos/{gid}/soporte"):
        assert piloto.get(ruta).status_code == 404, ruta
    assert piloto.post(f"/viajes/{sid}/decidir", data={"vuelo_id": 1}).status_code == 404
    assert str(gid) not in [str(g["id"]) for g in db.todos("select id from gastos where usuario_id=(select id from usuarios where correo='piloto@demo.local')")]

    # Lo propio sí lo ve, pero no puede aprobarlo
    propio = piloto.post("/gastos/cargar", data={"proyecto_id": 1, "viajero_id": 1, "canal": "celular"}, headers={"X-Envio": "pagina"},
                         files={"archivos": ("p.png", (ejemplos / "recibo_parqueo_borroso.png").read_bytes(), "image/png")}).json()["gastos"][0]
    assert piloto.get(f"/gastos/{propio}").status_code == 200
    assert piloto.post(f"/gastos/{propio}", data={"accion": "aprobar", "total": "24", "moneda": "USD"}).status_code == 403
    assert db.uno("select estado from gastos where id=:i", i=propio)["estado"] == "revision"
    assert "Mis gastos" in piloto.get("/").text


def test_formulario_desde_otro_sitio_se_rechaza(cliente):
    r = cliente.post("/reglas/1", data={"valor": "1"}, headers={"Origin": "https://sitio-ajeno.example"}, follow_redirects=False)
    assert r.status_code == 403
    r = cliente.post("/reglas/1", data={"valor": "1"}, headers={"Sec-Fetch-Site": "cross-site"}, follow_redirects=False)
    assert r.status_code == 403


def test_desactivar_expulsa_y_el_admin_no_se_bloquea_a_si_mismo(cliente):
    cliente.post("/admin/usuarios", data={"correo": "temporal@demo.local", "nombre": "Temporal", "rol": "usuario", "clave": "clave-temporal-1"})
    uid = db.uno("select id from usuarios where correo='temporal@demo.local'")["id"]
    temporal = TestClient(app)
    temporal.post("/entrar", data={"correo": "temporal@demo.local", "clave": "clave-temporal-1"})
    assert temporal.get("/").status_code == 200
    cliente.post(f"/admin/usuarios/{uid}", data={"accion": "estado"})
    assert temporal.get("/", follow_redirects=False).status_code == 303                 # expulsado en la siguiente petición
    yo = db.uno("select id from usuarios where correo='admin@demo.local'")["id"]
    cliente.post(f"/admin/usuarios/{yo}", data={"accion": "estado"})
    cliente.post(f"/admin/usuarios/{yo}", data={"accion": "rol", "rol": "usuario"})
    u = db.uno("select rol, activo from usuarios where id=:i", i=yo)
    assert u["rol"] == "admin" and u["activo"] == 1


def test_salir_cierra_la_sesion(ejemplos):
    c = TestClient(app)
    c.post("/entrar", data={"correo": "admin@demo.local", "clave": "demo-admin-2026"})
    assert c.get("/").status_code == 200
    c.post("/salir")
    assert c.get("/", follow_redirects=False).status_code == 303


def test_las_claves_no_se_guardan_en_claro():
    for u in db.todos("select clave_hash from usuarios"):
        assert u["clave_hash"].startswith("$argon2id$")
    assert not db.todos("select id from eventos where detalle like '%demo-admin-2026%' or detalle like '%equivocada-123%'")
