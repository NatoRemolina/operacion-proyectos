"""API v1 de administración: resumen y cambio de estado de un viaje. Contrato en `contracts/api-v1.md`.

Solo administración ve el resumen y mueve el estado; nadie aprueba lo suyo, tampoco por la API.
"""
import re
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from app import api_v1, db
from app.servicios import acceso, eventos, metricas, viajes

V1 = "/api/v1"
DINERO = re.compile(r"^-?\d+\.\d{2}$")
NOTA = "Presupuesto disponible = aprobado − gastos aprobados. Las reservas de tiquetes se sumarán cuando existan."


@pytest.fixture(scope="module", autouse=True)
def _cerrar_lo_creado():
    """Los viajes que dejan estas pruebas se cierran al final: no deben recibir los gastos de otras pruebas."""
    desde = db.uno("select coalesce(max(id), 0) m from viajes")["m"]
    yield
    db.ejecutar("update viajes set estado='cerrado' where id>:d", d=desde)


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _error(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"] and cuerpo["request_id"]
    return cuerpo["error"]


def _estado(c: TestClient, vid: int, accion: str, **extra):
    return c.post(f"{V1}/viajes/{vid}/estado", json={"accion": accion, **extra}, headers=_csrf(c))


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


def _viaje_propio_del_admin(cliente: TestClient) -> dict:
    """Administración cotiza para sí misma: el viaje queda a su nombre y pendiente."""
    from conftest import FORM_VIAJE

    from app.main import _comparacion
    datos = {k: v for k, v in FORM_VIAJE.items() if k not in ("viajero_id", "para_otra_persona", "solicitado_por")}
    r = cliente.post("/viajes", data=datos, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1])
    cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": _comparacion(sid)["vuelos"][0]["id"], "razones": ["costo_total"]})
    v = viajes.de_solicitud(sid)
    assert v["usuario_id"] == _admin()["id"] and v["estado"] == "pendiente_aprobacion"
    return v


# ---------- resumen ----------
def test_el_resumen_tiene_la_forma_del_contrato(cliente, viaje_aprobado):
    r = cliente.get(f"{V1}/resumen")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"presupuesto_aprobado_usd", "gastado_usd", "disponible_usd", "en_revision_usd", "ejecucion_pct",
                           "viajes_por_aprobar", "gastos_en_revision", "pendientes", "revision", "actividad", "nota",
                           "datos_demostracion"}
    for campo in ("presupuesto_aprobado_usd", "gastado_usd", "disponible_usd", "en_revision_usd"):
        assert DINERO.match(cuerpo[campo]), (campo, cuerpo[campo])
    assert cuerpo["nota"] == NOTA
    assert isinstance(cuerpo["datos_demostracion"], bool)


def test_el_resumen_usa_las_mismas_cifras_que_las_metricas(cliente, viaje_aprobado):
    cuerpo = cliente.get(f"{V1}/resumen").json()
    v, g = metricas.viajes({}), metricas.gastos({})
    assert Decimal(cuerpo["presupuesto_aprobado_usd"]) == Decimal(str(v["presupuesto_aprobado"])).quantize(Decimal("0.01"))
    assert Decimal(cuerpo["gastado_usd"]) == Decimal(str(v["gastado"])).quantize(Decimal("0.01"))
    assert Decimal(cuerpo["disponible_usd"]) == Decimal(cuerpo["presupuesto_aprobado_usd"]) - Decimal(cuerpo["gastado_usd"])
    assert cuerpo["viajes_por_aprobar"] == v["pendientes"]
    assert cuerpo["gastos_en_revision"] == g["pendientes"]
    assert cuerpo["ejecucion_pct"] == (round(v["ejecucion"]) if v["ejecucion"] is not None else None)


def test_el_resumen_lista_pendientes_revision_y_actividad_reciente(cliente, piloto, nuevo_viaje, ejemplos):
    pendiente = nuevo_viaje(aprobar=False)
    aprobado = nuevo_viaje()
    foto = (ejemplos / "recibo_lisboa.png").read_bytes()
    enviado = piloto.post(f"{V1}/gastos", files={"archivo": ("lisboa.png", foto, "image/png")},
                          data={"viaje_id": str(aprobado["id"])}, headers=_csrf(piloto))
    assert enviado.status_code == 201, enviado.text
    cuerpo = cliente.get(f"{V1}/resumen").json()

    assert pendiente["id"] in {v["id"] for v in cuerpo["pendientes"]}
    assert next(v for v in cuerpo["pendientes"] if v["id"] == pendiente["id"])["propio"] is False
    assert all(v["estado"] == "pendiente_aprobacion" for v in cuerpo["pendientes"]) and len(cuerpo["pendientes"]) <= 5
    assert all(g["estado"] == "revision" for g in cuerpo["revision"]) and len(cuerpo["revision"]) <= 5

    assert 1 <= len(cuerpo["actividad"]) <= 10
    ultimo = cuerpo["actividad"][0]
    assert set(ultimo) == {"gasto_id", "comercio", "persona", "viaje", "total", "moneda", "total_usd", "estado", "estado_texto",
                           "creado"}
    assert ultimo["gasto_id"] == enviado.json()["id"]
    assert ultimo["viaje"] == {"id": aprobado["id"], "codigo": aprobado["codigo"]}
    piloto_db = db.uno("select id, nombre from usuarios where correo='piloto@demo.local'")
    assert ultimo["persona"] == {"id": piloto_db["id"], "codigo": f"P-{piloto_db['id']:04d}", "nombre": piloto_db["nombre"]}
    ids = [a["gasto_id"] for a in cuerpo["actividad"]]
    assert ids == sorted(ids, reverse=True)


def test_el_resumen_es_solo_de_administracion(piloto, gestor, anonimo):
    _error(piloto.get(f"{V1}/resumen"), 403, "FORBIDDEN")
    _error(gestor.get(f"{V1}/resumen"), 403, "FORBIDDEN")
    _error(anonimo.get(f"{V1}/resumen"), 401, "UNAUTHENTICATED")


# ---------- cambio de estado ----------
def test_administracion_aprueba_el_viaje_de_otra_persona(cliente, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    r = _estado(cliente, v["id"], "aprobar")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"viaje", "mensaje"}
    assert cuerpo["viaje"]["id"] == v["id"] and cuerpo["viaje"]["estado"] == "aprobado"
    assert cuerpo["viaje"]["aprobado_en"]
    assert v["codigo"] in cuerpo["mensaje"] and "presupuesto aprobado" in cuerpo["mensaje"]
    # Sin clave del buscador no se reconfirma el precio: se aprueba con el aviso
    assert "Precio no reconfirmado" in cuerpo["mensaje"]
    assert viajes.uno(v["id"])["aprobado_por"] == _admin()["id"]


def test_rechazar_exige_motivo_y_se_puede_reabrir(cliente, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    error = _error(_estado(cliente, v["id"], "rechazar", motivo="no"), 422, "VALIDATION_ERROR")
    assert "motivo" in error["fields"]
    assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"

    r = _estado(cliente, v["id"], "rechazar", motivo="El hotel está lejos del set")
    assert r.status_code == 200, r.text
    assert r.json()["viaje"]["estado"] == "rechazado" and r.json()["viaje"]["motivo"] == "El hotel está lejos del set"

    r = _estado(cliente, v["id"], "reabrir")
    assert r.status_code == 200 and r.json()["viaje"]["estado"] == "pendiente_aprobacion"


def test_cerrar_un_viaje_aprobado(cliente, nuevo_viaje):
    v = nuevo_viaje()
    r = _estado(cliente, v["id"], "cerrar")
    assert r.status_code == 200 and r.json()["viaje"]["estado"] == "cerrado"


def test_una_transicion_invalida_responde_409(cliente, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    error = _error(_estado(cliente, v["id"], "cerrar"), 409, "INVALID_STATE")
    assert v["codigo"] in error["message"]
    assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"


def test_colaborador_y_gestor_no_cambian_el_estado(piloto, gestor, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)   # del piloto, en el proyecto 1 (el del gestor)
    for c in (piloto, gestor):
        for accion in ("aprobar", "rechazar", "reabrir", "cerrar"):
            _error(_estado(c, v["id"], accion, motivo="Motivo suficiente"), 403, "FORBIDDEN")
    assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"


def test_nadie_aprueba_lo_suyo_por_la_api_y_queda_el_evento(cliente):
    v = _viaje_propio_del_admin(cliente)
    for accion, motivo in (("aprobar", ""), ("rechazar", "No me convence el hotel")):
        error = _error(_estado(cliente, v["id"], accion, motivo=motivo), 403, "SELF_APPROVAL")
        assert error["message"] == viajes.NO_AUTOAPROBAR
    assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"
    intentos = db.todos("""select detalle from eventos where entidad='viaje' and entidad_id=:i
                           and paso='autoaprobación impedida' order by id""", i=v["id"])
    assert len(intentos) == 2 and "aprobar" in intentos[0]["detalle"] and "rechazar" in intentos[1]["detalle"]


def test_la_lista_dice_si_el_viaje_es_propio(cliente, nuevo_viaje):
    propio, ajeno = _viaje_propio_del_admin(cliente), nuevo_viaje(aprobar=False)
    items = {v["id"]: v for v in cliente.get(f"{V1}/viajes", params={"estado": "pendiente_aprobacion", "limite": 100}).json()["items"]}
    assert items[propio["id"]]["propio"] is True and items[ajeno["id"]]["propio"] is False
    assert cliente.get(f"{V1}/viajes/{propio['id']}").json()["propio"] is True


def test_con_precio_pendiente_hay_que_confirmarlo(cliente, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    cambio = f"antes 410.00 USD, ahora 451.00 USD (+10.0%); {viajes.SUPERA_TOLERANCIA} de 5%"
    eventos.registrar("viaje", v["id"], "precio cambió", cambio, "SerpApi (en vivo)")

    # El aviso se ve antes de aprobar, en la lista y en el detalle
    items = {x["id"]: x for x in cliente.get(f"{V1}/viajes", params={"estado": "pendiente_aprobacion", "limite": 100}).json()["items"]}
    assert items[v["id"]]["precio_por_confirmar"] == cambio
    assert cliente.get(f"{V1}/viajes/{v['id']}").json()["precio_por_confirmar"] == cambio

    error = _error(_estado(cliente, v["id"], "aprobar"), 409, "PRICE_CONFIRMATION_REQUIRED")
    assert "451" in error["message"] and error["fields"]["precio"] == cambio
    assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"

    r = _estado(cliente, v["id"], "aprobar", confirmar_precio=True)
    assert r.status_code == 200, r.text
    assert r.json()["viaje"]["estado"] == "aprobado" and r.json()["viaje"]["precio_por_confirmar"] is None


def test_el_cambio_de_estado_exige_csrf_y_valida_la_accion(cliente, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    _error(cliente.post(f"{V1}/viajes/{v['id']}/estado", json={"accion": "aprobar"}), 403, "CSRF_INVALID")
    _error(_estado(cliente, v["id"], "borrar"), 422, "VALIDATION_ERROR")
    _error(cliente.post(f"{V1}/viajes/{v['id']}/estado", json={"accion": "aprobar", "rol": "admin"}, headers=_csrf(cliente)),
           422, "VALIDATION_ERROR")
    _error(_estado(cliente, 999999, "aprobar"), 404, "NOT_FOUND")
    assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"
