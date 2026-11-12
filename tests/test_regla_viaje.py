"""La regla de negocio de punta a punta: persona -> cotización -> decisión -> viaje aprobado -> gastos."""
import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.main import _comparacion
from app.servicios import viajes


def _subir(cliente, ejemplos, archivo, **campos):
    r = cliente.post("/gastos/cargar", data={"canal": "web", **campos}, headers={"X-Envio": "pagina"},
                     files={"archivos": (archivo, (ejemplos / archivo).read_bytes(),
                                         "application/pdf" if archivo.endswith(".pdf") else "image/png")})
    return db.uno("select * from gastos where id=:i", i=r.json()["gastos"][0])


def _motivos(g):
    return db.de_json(g["motivos"], [])


def test_la_decision_crea_el_viaje_asignado_a_quien_viaja(nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    piloto = db.uno("select id from usuarios where correo='piloto@demo.local'")["id"]
    assert v["estado"] == "pendiente_aprobacion" and v["codigo"] == f"V-{v['creado'][:4]}-{v['id']:04d}"
    assert v["usuario_id"] == piloto                      # cotizó administración, pero el titular es quien viaja
    conceptos = " ".join(l["concepto"] for l in db.de_json(v["presupuesto_detalle"], []))
    assert "Viáticos" in conceptos and "cambio" not in conceptos.lower()   # desembolsos, no valor esperado
    assert v["presupuesto_usd"] == round(sum(l["valor"] for l in db.de_json(v["presupuesto_detalle"], [])), 2)


def test_una_cotizacion_un_viaje_y_aprobado_no_se_cambia(cliente, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    sid = v["solicitud_id"]
    otro = _comparacion(sid)["vuelos"][1]["id"]
    cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": otro, "motivo": "Cambio de horario"})
    assert db.uno("select count(*) n from viajes where solicitud_id=:s", s=sid)["n"] == 1
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "aprobar"})
    antes = db.uno("select count(*) n from decisiones where solicitud_id=:s", s=sid)["n"]
    r = cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": otro, "motivo": "Otro cambio"}, follow_redirects=False)
    assert "aviso=" in r.headers["location"]
    assert db.uno("select count(*) n from decisiones where solicitud_id=:s", s=sid)["n"] == antes


def test_solo_administracion_mueve_el_estado(cliente, piloto, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    ruta = f"/admin/viajes/{v['id']}"
    assert piloto.post(ruta, data={"accion": "aprobar"}).status_code == 403
    cliente.post(ruta, data={"accion": "rechazar", "motivo": ""})
    assert viajes.uno(v["id"])["estado"] == "pendiente_aprobacion"          # rechazar exige motivo
    cliente.post(ruta, data={"accion": "rechazar", "motivo": "Supera lo acordado con el cliente"})
    assert viajes.uno(v["id"])["estado"] == "rechazado"
    cliente.post(ruta, data={"accion": "cerrar"})
    assert viajes.uno(v["id"])["estado"] == "rechazado"                     # transición que no existe
    cliente.post(ruta, data={"accion": "reabrir"})
    cliente.post(ruta, data={"accion": "aprobar"})
    aprobado = viajes.uno(v["id"])
    assert aprobado["estado"] == "aprobado" and aprobado["aprobado_por"] and aprobado["aprobado_en"]
    pasos = [e["paso"] for e in db.todos("select paso from eventos where entidad='viaje' and entidad_id=:i order by id", i=v["id"])]
    # al decidir se registran los tramos; al aprobar sin clave del buscador el precio queda sin reconfirmar, y se dice
    assert pasos == ["viaje creado", "tramos registrados", "presupuesto rechazado", "viaje reabierto", "precio no reconfirmado",
                     "presupuesto aprobado"]


def test_cada_gasto_responde_al_estado_de_su_viaje(cliente, ejemplos, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    g = _subir(cliente, ejemplos, "factura_alquiler_carro.pdf", viaje_id=v["id"])   # soporte que no usa ninguna otra prueba
    assert g["estado"] == "revision" and "viaje_no_aprobado" in _motivos(g) and g["viaje_id"] == v["id"]
    assert g["proyecto_id"] == v["proyecto_id"] and g["viajero_id"] == v["viajero_id"]   # el viaje define proyecto y persona

    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "aprobar"})
    db.actualizar("viajes", v["id"], presupuesto_usd=1)                      # mucho menos que la factura
    campos = dict(comercio=g["comercio"], fecha=g["fecha"], categoria=g["categoria"], total=str(g["total"]), moneda=g["moneda"])
    cliente.post(f"/gastos/{g['id']}", data={**campos, "accion": "aprobar"})
    g = db.uno("select * from gastos where id=:i", i=g["id"])
    assert g["estado"] == "revision" and "presupuesto_superado" in _motivos(g)

    db.actualizar("viajes", v["id"], presupuesto_usd=50000)
    cliente.post(f"/gastos/{g['id']}", data={**campos, "accion": "aprobar"})
    assert db.uno("select estado from gastos where id=:i", i=g["id"])["estado"] == "aprobado"
    assert viajes.resumen(v["id"])["gastado"] == g["total_usd"] > 0

    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "cerrar"})
    tarde = _subir(cliente, ejemplos, "recibo_diner.png", viaje_id=v["id"])
    assert tarde["estado"] == "revision" and "viaje_cerrado" in _motivos(tarde)


def test_gasto_sin_viaje_se_guarda_y_va_a_revision(cliente, ejemplos):
    g = _subir(cliente, ejemplos, "recibo_lisboa.png", proyecto_id=2, viajero_id=2)   # administración no tiene viajes propios
    assert g["id"] and g["estado"] == "revision" and "sin_viaje" in _motivos(g) and g["viaje_id"] is None


def test_la_base_rechaza_referencias_a_lo_que_no_existe():
    with pytest.raises(IntegrityError):
        db.insertar("gastos", proyecto_id=987654, estado="revision", creado=db.ahora())
    with pytest.raises(IntegrityError):
        db.insertar("viajes", solicitud_id=987654, estado="aprobado", creado=db.ahora())
    with pytest.raises(IntegrityError):
        db.insertar("viajes", estado="inventado", creado=db.ahora())


def test_cada_rol_ve_lo_que_le_corresponde(cliente, piloto, gestor, anonimo, viaje_aprobado):
    vid, sid = viaje_aprobado["id"], viaje_aprobado["solicitud_id"]
    for quien in (cliente, piloto, gestor):
        pagina = quien.get("/mi-cuenta")
        assert pagina.status_code == 200 and "P-000" in pagina.text and viaje_aprobado["codigo"] in pagina.text
        assert quien.get(f"/viaje/{vid}").status_code == 200
    assert gestor.get("/admin/viajes").status_code == 403 and cliente.get("/admin/viajes").status_code == 200
    vuelo = _comparacion(sid)["vuelos"][0]["id"]
    assert gestor.post(f"/viajes/{sid}/decidir", data={"vuelo_id": vuelo}).status_code == 404   # ve, no decide
    # Una cuenta nueva no ve viajes ajenos; un gestor no ve proyectos que no gestiona
    cliente.post("/admin/usuarios", data={"correo": "otra@demo.local", "nombre": "Otra Persona", "rol": "colaborador", "clave": "clave-de-otra-1"})
    anonimo.post("/entrar", data={"correo": "otra@demo.local", "clave": "clave-de-otra-1"})
    assert anonimo.get(f"/viaje/{vid}").status_code == 404
    assert viaje_aprobado["codigo"] not in anonimo.get("/mi-cuenta").text
    otra = db.uno("select viajero_id from usuarios where correo='otra@demo.local'")
    assert otra["viajero_id"]                                                # la cuenta de piloto nace con su perfil
    cliente.get("/api/viajes").json()


def test_la_migracion_se_puede_repetir():
    from datos.semilla import sembrar
    antes = db.uno("select count(*) n from viajes")["n"]
    assert sembrar()["viajes_creados"] == 0 and sembrar()["gastos_enlazados"] == 0
    assert db.uno("select count(*) n from viajes")["n"] == antes


def test_ver_un_viaje_no_basta_para_cargarle_gastos(gestor, ejemplos, viaje_aprobado):
    """El gestor ve los viajes de su proyecto, pero un gasto suyo no puede ir al presupuesto de otra persona."""
    g = _subir(gestor, ejemplos, "recibo_lisboa.png", viaje_id=viaje_aprobado["id"])
    assert g["viaje_id"] is None and "sin_viaje" in _motivos(g)


def test_ver_una_cotizacion_no_basta_para_gastar_consultas(gestor, viaje_aprobado):
    oid = db.uno("select id from opciones where solicitud_id=:s and tipo='vuelo' limit 1", s=viaje_aprobado["solicitud_id"])["id"]
    assert gestor.post(f"/viajes/{viaje_aprobado['solicitud_id']}/tarifas/{oid}").status_code == 404
