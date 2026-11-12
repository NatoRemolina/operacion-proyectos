"""Todas las cuentas viajan y nadie aprueba lo suyo: ni el presupuesto de su viaje ni sus propios gastos."""
from urllib.parse import unquote_plus

import pytest
from starlette.testclient import TestClient

from app import db
from app.main import _comparacion, app
from app.servicios import acceso, viajes

FORM = dict(proyecto_id=1, origen="Miami (MIA)", destino="las vegas", ciudad="", ida="2026-12-08", regreso="2026-12-11",
            llegar_antes="2026-12-08T18:00", baterias_n=4, baterias_wh=77, maleta="on", prob_cambio=25, carro_dia=65)
NO_PRESUPUESTO = "Nadie aprueba ni rechaza su propio presupuesto: debe hacerlo otra persona de administración."
NO_GASTO = "Nadie revisa sus propios gastos: debe hacerlo otra persona de administración."


@pytest.fixture(scope="module", autouse=True)
def _cerrar_lo_creado():
    """Los viajes propios que dejan estas pruebas se cierran al final: no deben recibir los gastos de otras pruebas."""
    desde = db.uno("select coalesce(max(id), 0) m from viajes")["m"]
    yield
    db.ejecutar("update viajes set estado='cerrado' where id>:d", d=desde)


def _cuenta(correo: str) -> dict:
    return db.uno("select * from usuarios where correo=:c", c=correo)


def _entrar(correo: str, clave: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/entrar", data={"correo": correo, "clave": clave}, follow_redirects=False).headers["location"] == "/"
    return c


def _cotizar_y_decidir(c: TestClient, **cambios) -> dict:
    r = c.post("/viajes", data={**FORM, **cambios}, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1])
    c.post(f"/viajes/{sid}/decidir", data={"vuelo_id": _comparacion(sid)["vuelos"][0]["id"], "razones": ["costo_total"]})
    return viajes.de_solicitud(sid)


def test_un_gestor_cotiza_y_el_viaje_queda_a_su_nombre(gestor):
    yo = _cuenta("gestor@demo.local")
    v = _cotizar_y_decidir(gestor)   # no elige viajero: viaja quien cotiza
    assert v["usuario_id"] == yo["id"] and v["viajero_id"] == yo["viajero_id"]
    # Aunque el formulario traiga otro viajero, sin marcar «para otra persona» el viaje es de quien cotiza
    v2 = _cotizar_y_decidir(gestor, viajero_id=2)
    assert v2["usuario_id"] == yo["id"] and v2["viajero_id"] == yo["viajero_id"]


def test_admin_no_aprueba_su_propio_presupuesto(cliente):
    yo = _cuenta("admin@demo.local")
    v = _cotizar_y_decidir(cliente)
    assert v["usuario_id"] == yo["id"] and v["estado"] == "pendiente_aprobacion"

    for accion, motivo in (("aprobar", ""), ("rechazar", "No me convence el hotel")):
        r = cliente.post(f"/admin/viajes/{v['id']}", data={"accion": accion, "motivo": motivo}, follow_redirects=False)
        assert NO_PRESUPUESTO in unquote_plus(r.headers["location"])
        assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"
    assert NO_PRESUPUESTO in cliente.get(r.headers["location"]).text

    # El servicio lo impide aunque se llame sin pasar por la pantalla, y cada intento queda registrado
    assert viajes.cambiar_estado(v["id"], "aprobar", "", yo) == (False, NO_PRESUPUESTO)
    intentos = db.todos("""select * from eventos where entidad='viaje' and entidad_id=:i and paso='autoaprobación impedida'
                           order by id""", i=v["id"])
    assert len(intentos) == 3
    assert all(e["fuente"] == yo["nombre"] and v["codigo"] in e["detalle"] for e in intentos)
    assert "aprobar" in intentos[0]["detalle"] and "rechazar" in intentos[1]["detalle"]
    assert intentos[0]["usuario_id"] == yo["id"]

    # Otra persona de administración sí lo aprueba
    acceso.crear_usuario("admin2-autoaprobacion@demo.local", "Segunda administración", "admin", "clave-admin-dos-2026")
    try:
        otra = _entrar("admin2-autoaprobacion@demo.local", "clave-admin-dos-2026")
        otra.post(f"/admin/viajes/{v['id']}", data={"accion": "aprobar"})
        aprobado = viajes.uno(v["id"])
        assert aprobado["estado"] == "aprobado" and aprobado["aprobado_por"] == _cuenta("admin2-autoaprobacion@demo.local")["id"]
    finally:
        db.ejecutar("update usuarios set activo=0 where correo='admin2-autoaprobacion@demo.local'")


def test_admin_no_revisa_su_propio_gasto(cliente, ejemplos):
    yo = _cuenta("admin@demo.local")
    gid = cliente.post("/gastos/cargar", data={"proyecto_id": 1, "viajero_id": yo["viajero_id"], "canal": "web"},
                       headers={"X-Envio": "pagina"},
                       files={"archivos": ("p.png", (ejemplos / "recibo_parqueo_borroso.png").read_bytes(), "image/png")}).json()["gastos"][0]
    antes = db.uno("select * from gastos where id=:i", i=gid)
    assert antes["usuario_id"] == yo["id"] and antes["estado"] == "revision"

    for accion in ("aprobar", "rechazar", "excepcion"):
        r = cliente.post(f"/gastos/{gid}", data={"accion": accion, "total": "12", "moneda": "USD",
                                                 "motivo_excepcion": "Parqueo de la grabación"}, follow_redirects=False)
        assert NO_GASTO in unquote_plus(r.headers["location"])
        assert db.uno("select estado, revisado_por from gastos where id=:i", i=gid) == {"estado": "revision", "revisado_por": None}
    pagina = cliente.get(f"/gastos/{gid}").text
    assert NO_GASTO in pagina and 'value="aprobar"' not in pagina   # la pantalla tampoco ofrece aprobarlo
    intentos = db.todos("select * from eventos where entidad='gasto' and entidad_id=:i and paso='autoaprobación impedida'", i=gid)
    assert len(intentos) == 3 and all(e["fuente"] == yo["nombre"] for e in intentos)


def test_con_un_solo_admin_se_explica_en_pantalla(cliente):
    otros = db.todos("select id from usuarios where rol='admin' and activo=1 and correo<>'admin@demo.local'")
    db.ejecutar("update usuarios set activo=0 where rol='admin' and correo<>'admin@demo.local'")
    try:
        v = _cotizar_y_decidir(cliente)
        assert v["estado"] == "pendiente_aprobacion"
        pagina = cliente.get("/admin/viajes").text
        assert "Hace falta otra persona de administración para aprobarlo" in pagina
        assert f'action="/admin/viajes/{v["id"]}"' not in pagina   # sin botones de aprobar para lo propio
        assert "Hace falta otra persona de administración para aprobarlo" in cliente.get(f"/viaje/{v['id']}").text
    finally:
        for o in otros:
            db.actualizar("usuarios", o["id"], activo=1)


def test_admin_cotiza_para_otra_persona_como_hoy(cliente):
    laura = _cuenta("piloto2@demo.local")
    v = _cotizar_y_decidir(cliente, para_otra_persona="1", viajero_id=laura["viajero_id"])
    assert v["viajero_id"] == laura["viajero_id"] and v["usuario_id"] == laura["id"]
    # Lo de otra persona sí lo aprueba administración
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "aprobar"})
    assert viajes.uno(v["id"])["estado"] == "aprobado"
