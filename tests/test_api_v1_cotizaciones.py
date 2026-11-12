"""Cotizar por la API v1: el servicio de cotización y sus endpoints. Contrato en `contracts/api-v1.md`.

El buscador nunca sale a internet: se usan las respuestas guardadas (Miami → Las Vegas, Miami → Moab) o un doble.
"""
import json
import re
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from app import api_v1, db
from app.api_v1.esquemas_cotizacion import NuevaCotizacion
from app.main import app
from app.servicios import acceso, consultas, costo, cotizacion, viajes

MOAB = {"nombre": "Moab", "region": "Utah", "pais": "Estados Unidos", "lat": 38.57332, "lon": -109.54984}


def _cuenta(correo: str) -> dict:
    return db.uno("select * from usuarios where correo=:c", c=correo)


def _datos(**cambios) -> dict:
    """Miami → Las Vegas del 8 al 11 de diciembre de 2026: tiene respuesta guardada."""
    return {"proyecto_id": 1, "viajero_id": 1, "origen": "Miami (MIA)", "destino": "las vegas", "ida": "2026-12-08",
            "regreso": "2026-12-11", "llegar_antes": "2026-12-08T18:00", "baterias_n": 4, "baterias_wh": 77, "maleta": True,
            "prob_cambio": 25, "carro_dia": 65, "para_otra_persona": True, **cambios}


# ---------- pieza 1: el servicio que comparten las pantallas y la API ----------
def test_el_servicio_crea_busca_compara_y_decide(cliente):
    admin = _cuenta("admin@demo.local")
    sid = cotizacion.crear(admin, **_datos())
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["origen"], s["destino"], s["estado"], s["usuario_id"]) == ("MIA", "LAS", "comparando", admin["id"])
    ev = db.uno("select fuente from eventos where entidad='solicitud' and entidad_id=:i and paso='solicitud recibida'", i=sid)
    assert ev["fuente"] == f"formulario · {admin['nombre']}"
    c = cotizacion.comparacion(sid)
    assert c["vuelos"] and c["mas_barato"] and c["hoteles"]
    assert [v["ev"]["total"] for v in c["vuelos"]] == sorted(v["ev"]["total"] for v in c["vuelos"])
    r = cotizacion.decidir(admin, sid, c["vuelos"][0]["id"], c["hoteles"][0]["id"], "", ["costo_total"])
    assert not r["repetida"] and r["viaje"]["estado"] == "pendiente_aprobacion"
    assert viajes.de_solicitud(sid)["id"] == r["viaje"]["id"]
    # el mismo envío otra vez no duplica la decisión
    otra = cotizacion.decidir(admin, sid, c["vuelos"][0]["id"], c["hoteles"][0]["id"], "", ["costo_total"])
    assert otra["repetida"] and otra["decision_id"] == r["decision_id"]
    assert db.uno("select count(*) n from decisiones where solicitud_id=:s", s=sid)["n"] == 1


def test_el_servicio_dice_que_dato_falla(cliente):
    admin = _cuenta("admin@demo.local")
    antes = db.uno("select count(*) n from solicitudes")["n"]
    casos = [(dict(destino="Moab", destino_aeropuertos="ZZZ"), "destino", 'No reconozco "ZZZ"'),
             (dict(origen="xyz123"), "origen", "No reconozco"),
             (dict(ida="no-es-fecha"), "ida", "Las fechas no son válidas."),
             (dict(regreso="2026-12-01"), "regreso", "El regreso debe ser posterior a la ida."),
             (dict(viajero_id=0), "viajero_id", "Elige quién viaja.")]
    for cambios, campo, texto in casos:
        with pytest.raises(cotizacion.CotizacionInvalida) as e:
            cotizacion.crear(admin, **_datos(**cambios))
        assert e.value.campo == campo and str(e.value).startswith(texto), cambios
    assert db.uno("select count(*) n from solicitudes")["n"] == antes


def test_el_servicio_acepta_el_lugar_como_objeto(cliente):
    """La API manda el lugar ya armado; el formulario, como texto JSON. Los dos llegan igual a la base."""
    admin = _cuenta("admin@demo.local")
    sid = cotizacion.crear(admin, **_datos(destino="Moab", destino_aeropuertos="SLC,CNY,GJT", destino_lugar=MOAB))
    s = db.uno("select * from solicitudes where id=:i", i=sid)
    assert (s["destino"], s["destino_aeropuertos"], s["ciudad"]) == ("CNY", "CNY,GJT,SLC", "Moab")
    assert db.de_json(s["destino_lugar"]) == MOAB
    assert cotizacion.lugar({"nombre": "Moab", "lat": 999, "lon": 0}) is None   # coordenadas imposibles
    assert cotizacion.lugar(json.dumps(MOAB)) == MOAB


def test_el_servicio_explica_por_que_no_guarda_la_decision(cliente):
    admin = _cuenta("admin@demo.local")
    sid = cotizacion.crear(admin, **_datos())
    vuelos = cotizacion.comparacion(sid)["vuelos"]
    with pytest.raises(cotizacion.DecisionInvalida) as e:
        cotizacion.decidir(admin, sid, 0)
    assert e.value.campo == "vuelo_id"
    with pytest.raises(cotizacion.DecisionInvalida) as e:
        cotizacion.decidir(admin, sid, vuelos[1]["id"], motivo="no")
    assert e.value.campo == "motivo" and "distinta a la recomendada" in str(e.value)
    assert not db.uno("select id from decisiones where solicitud_id=:s", s=sid)
    # con el presupuesto aprobado, la decisión ya no cambia sin reabrir el viaje
    v = cotizacion.decidir(admin, sid, vuelos[0]["id"])["viaje"]
    db.actualizar("viajes", v["id"], estado="aprobado")
    with pytest.raises(cotizacion.DecisionBloqueada) as e:
        cotizacion.decidir(admin, sid, vuelos[1]["id"], motivo="Prefiero el horario de la tarde")
    assert v["codigo"] in str(e.value)
    with pytest.raises(LookupError):
        cotizacion.decidir(admin, 10**9, 1)


def test_las_pantallas_usan_el_servicio():
    from app.rutas import cotizaciones
    assert cotizaciones._comparacion is cotizacion.comparacion
    assert cotizaciones._completar_ahorros is cotizacion.completar_ahorros
    assert acceso.es_admin(_cuenta("admin@demo.local"))


# ---------- pieza 2: la API v1 de cotización ----------
V1 = "/api/v1"
DINERO = re.compile(r"^-?\d+\.\d{2}$")


def _contrato(r, estado: int, codigo: str) -> dict:
    assert r.status_code == estado, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"error", "request_id"} and cuerpo["error"]["code"] == codigo and cuerpo["error"]["message"]
    assert cuerpo["request_id"] and cuerpo["request_id"] == r.headers["X-Peticion"]
    assert r.headers["Cache-Control"] == "no-store"
    return cuerpo


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _pedido(**cambios) -> dict:
    """Miami (MIA) → Moab con CNY, GJT y SLC del 8 al 11 de diciembre de 2026: respuesta real guardada."""
    return {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"},
            "destino": {"texto": "Moab, Utah, Estados Unidos", "aeropuertos": ["CNY", "GJT", "SLC"], "lugar": MOAB},
            "ida": "2026-12-08", "regreso": "2026-12-11", "hora_limite": "18:00", "baterias_n": 4, "baterias_wh": 77,
            "maleta": True, "prob_cambio_pct": 25, "carro_dia_usd": "65.00", **cambios}


def _cotizar(c: TestClient, cabeceras: dict | None = None, **cambios):
    return c.post(f"{V1}/cotizaciones", json=_pedido(**cambios), headers={**_csrf(c), **(cabeceras or {})})


def _solicitudes() -> int:
    return db.uno("select count(*) n from solicitudes")["n"]


def test_lugares_pide_sesion_y_responde_lo_mismo_que_el_buscador(piloto, anonimo):
    _contrato(anonimo.get(f"{V1}/lugares", params={"q": "moab"}), 401, "UNAUTHENTICATED")
    r = piloto.get(f"{V1}/lugares", params={"q": "moab"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"resultados", "aviso_google", "carretera"} and cuerpo["carretera"]["factor"] > 1
    moab = cuerpo["resultados"][0]
    assert (moab["tipo"], moab["nombre"], moab["origen"]) == ("lugar", "Moab", "local")
    cny = next(a for a in moab["aeropuertos"] if a["iata"] == "CNY")
    assert cny["km"] is not None and cny["km"] < 30 and isinstance(cny["grande"], bool)
    assert piloto.get(f"{V1}/lugares", params={"q": "m"}).json()["resultados"] == []
    _contrato(piloto.get(f"{V1}/lugares", params={"q": "x" * 81}), 422, "VALIDATION_ERROR")
    sin_clave = piloto.get(f"{V1}/lugares", params={"q": "moab", "google": 1}).json()
    assert sin_clave["aviso_google"] == "Sin clave del buscador: solo sugerencias de los datos locales."


def test_lugares_aplica_los_topes_del_autocompletado_por_persona(piloto, monkeypatch):
    from app import config
    from app.servicios import precios
    llamadas = []
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    monkeypatch.setattr(precios, "_consultar", lambda *a, **k: llamadas.append(a) or {"suggestions": []})
    yo = _cuenta("piloto@demo.local")
    tope = int(costo.supuesto(costo.catalogo(), "tope_autocompletado_persona_dia", 15))
    for i in range(tope):
        db.insertar("consultas_buscador", momento=db.ahora(), usuario_id=yo["id"], tipo="autocompletado", origen="en vivo",
                    clave=f"autocompletado_prueba-{i}")
    try:
        r = piloto.get(f"{V1}/lugares", params={"q": "pueblo sin cache", "google": 1})
        assert r.json()["aviso_google"].startswith("Se alcanzó el tope de sugerencias") and llamadas == []
    finally:
        db.ejecutar("delete from consultas_buscador where clave like 'autocompletado_prueba-%'")


def test_formulario_segun_el_permiso(piloto, cliente):
    propio = piloto.get(f"{V1}/cotizaciones/formulario").json()
    assert propio["viajero_propio_id"] == 1 and not propio["elige_viajero"]
    assert [(v["id"], v["soy_yo"]) for v in propio["viajeros"]] == [(1, True)]
    assert propio["proyectos"] and {"clave": "costo_total", "texto": "Menor costo total"} in propio["razones"]
    assert propio["precios_en_vivo"] is False
    admin = cliente.get(f"{V1}/cotizaciones/formulario").json()
    assert admin["elige_viajero"] and admin["viajero_propio_id"] == _cuenta("admin@demo.local")["viajero_id"]
    assert len(admin["viajeros"]) >= 2 and sum(v["soy_yo"] for v in admin["viajeros"]) == 1


def test_cotizar_miami_moab_por_la_api(piloto):
    r = _cotizar(piloto)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["estado"] == "comparando" and c["viajero"]["id"] == 1 and c["proyecto"]["id"] == 1
    assert c["destino"] == {"codigo": "CNY", "aeropuertos": ["CNY", "GJT", "SLC"], "lugar": MOAB}
    assert c["origen"] == {"codigo": "MIA", "aeropuertos": ["MIA"], "lugar": None}
    assert (c["ida"], c["regreso"], c["noches"], c["hora_limite"]) == ("2026-12-08", "2026-12-11", 3, "18:00")
    assert c["origen_dato"] == "guardado" and c["vuelos"] and c["descartados"]
    # lo más barato del buscador llega a Salt Lake City; con el traslado conviene Moab (CNY)
    assert c["recomendada_id"] == c["vuelos"][0]["id"] and c["vuelos"][0]["recomendada"] and c["vuelos"][0]["hasta"] == "CNY"
    barata = next(v for v in c["vuelos"] + c["descartados"] if v["id"] == c["mas_barata_id"])
    assert barata["mas_barata"] and (barata["hasta"], barata["precio_usd"]) == ("SLC", "415.00")
    assert c["aviso"] and "más barata" in c["aviso"]
    for v in c["vuelos"] + c["descartados"]:
        assert DINERO.match(v["costo_total_usd"]) and v["origen_dato"] == "guardado"
        assert set(v["desglose"]) == {"precio_usd", "equipaje_usd", "riesgo_cambio_usd", "millas_usd", "traslado_usd"}
        suma = sum(Decimal(x) for x in v["desglose"].values())
        assert suma == Decimal(v["costo_total_usd"]) == sum(Decimal(l["valor_usd"]) for l in v["lineas"])
    assert [v["costo_total_usd"] for v in c["vuelos"]] == sorted((v["costo_total_usd"] for v in c["vuelos"]), key=Decimal)
    assert all(v["descartada"] for v in c["descartados"])
    assert any(v["descartada"].startswith("Con el traslado llega a las") for v in c["descartados"])
    slc = next(v for v in c["vuelos"] + c["descartados"] if v["hasta"] == "SLC")
    linea = next(l for l in slc["lineas"] if l["tipo"] == "traslado")
    assert linea["concepto"].startswith("Combustible y peajes desde SLC") and linea["origen"] == "supuesto"
    assert Decimal(slc["desglose"]["traslado_usd"]) > 0
    assert c["hoteles"] == [] and c["equipo"]["nivel"] == "ok"      # Moab no tiene hoteles guardados: se decide solo con el vuelo
    assert c["decision"] is None and c["viaje"] is None and c["puede_decidir"] and c["bloqueo"] is None
    assert c["recomendacion"]
    ev = db.uno("select fuente from eventos where entidad='solicitud' and entidad_id=:i and paso='solicitud recibida'", i=c["id"])
    assert ev["fuente"] == "api v1 · Andrés Molina"
    assert piloto.get(f"{V1}/cotizaciones/{c['id']}").json() == c


def test_cada_quien_ve_solo_sus_cotizaciones(piloto, piloto2, gestor, cliente, anonimo):
    c = _cotizar(piloto).json()
    ruta = f"{V1}/cotizaciones/{c['id']}"
    _contrato(piloto2.get(ruta), 404, "NOT_FOUND")                    # otro colaborador: como si no existiera
    _contrato(anonimo.get(ruta), 401, "UNAUTHENTICATED")
    _contrato(piloto.get(f"{V1}/cotizaciones/999999"), 404, "NOT_FOUND")
    assert cliente.get(ruta).status_code == 200
    vista = gestor.get(ruta)                                           # gestiona el proyecto 1: la ve, no la decide
    assert vista.status_code == 200 and vista.json()["puede_decidir"] is False
    decision = {"vuelo_id": c["recomendada_id"]}
    _contrato(gestor.post(f"{ruta}/decision", json=decision, headers=_csrf(gestor)), 403, "FORBIDDEN")
    _contrato(piloto2.post(f"{ruta}/decision", json=decision, headers=_csrf(piloto2)), 404, "NOT_FOUND")
    assert not db.uno("select id from decisiones where solicitud_id=:s", s=c["id"])


def test_crear_valida_cada_dato_y_no_cotiza_para_otro_sin_permiso(piloto, cliente):
    antes = _solicitudes()
    _contrato(_cotizar(piloto, viajero_id=2), 403, "FORBIDDEN")       # un colaborador cotiza para sí
    casos = [(piloto, dict(destino={"aeropuertos": ["ZZZ"]}), "destino"),
             (piloto, dict(origen={"texto": ""}), "origen"),
             (piloto, dict(regreso="2026-12-08"), "regreso"),
             (piloto, dict(ida="8 de diciembre"), "ida"),
             (piloto, dict(proyecto_id=999), "proyecto_id"),
             (piloto, dict(hora_limite="6 pm"), "hora_limite"),
             (piloto, dict(rol="admin"), "rol"),
             (piloto, dict(destino={"aeropuertos": ["C1Y"]}), "destino.aeropuertos.0")]
    for c, cambios, campo in casos:
        cuerpo = _contrato(_cotizar(c, **cambios), 422, "VALIDATION_ERROR")
        assert campo in cuerpo["error"]["fields"], (cambios, cuerpo)
    _contrato(piloto.post(f"{V1}/cotizaciones", json=_pedido()), 403, "CSRF_INVALID")
    ajeno = {"Origin": "https://sitio-ajeno.example", "Sec-Fetch-Site": "cross-site"}
    _contrato(_cotizar(piloto, cabeceras=ajeno), 403, "ORIGIN_NOT_ALLOWED")
    assert _solicitudes() == antes
    otra = _cotizar(cliente, viajero_id=2)                              # administración sí cotiza para otra persona
    assert otra.status_code == 201 and otra.json()["viajero"]["id"] == 2
    assert _cotizar(cliente).json()["viajero"]["id"] == _cuenta("admin@demo.local")["viajero_id"]   # y por defecto, para sí


def test_una_cuenta_sin_perfil_de_viajero_dice_quien_viaja():
    """Las cuentas de antes del 12 nov 2026 pueden no tener perfil de viajero."""
    uid = acceso.crear_usuario("sin-perfil-api@demo.local", "Sin perfil", "colaborador", "clave-sin-perfil-2026")
    db.ejecutar("update usuarios set viajero_id=null where id=:i", i=uid)
    c = TestClient(app)
    assert c.post(f"{V1}/auth/login", json={"correo": "sin-perfil-api@demo.local", "clave": "clave-sin-perfil-2026"}).status_code == 200
    assert c.get(f"{V1}/cotizaciones/formulario").json()["viajeros"] == []
    cuerpo = _contrato(_cotizar(c), 422, "VALIDATION_ERROR")
    assert "viajero_id" in cuerpo["error"]["fields"]


def test_la_misma_clave_devuelve_la_misma_cotizacion(piloto, piloto2):
    clave = {"Idempotency-Key": "cotizacion-repetida-1"}
    primera = _cotizar(piloto, clave)
    assert primera.status_code == 201
    antes = _solicitudes()
    repetida = _cotizar(piloto, clave)
    assert repetida.status_code == 200 and repetida.json()["id"] == primera.json()["id"] and _solicitudes() == antes
    _contrato(_cotizar(piloto, clave, regreso="2026-12-12"), 409, "IDEMPOTENCY_CONFLICT")
    assert _cotizar(piloto2, clave).json()["id"] != primera.json()["id"]   # la clave es de cada persona
    # un pedido rechazado no gasta la clave: corregido, se cotiza con la misma
    otra = {"Idempotency-Key": "cotizacion-corregida-1"}
    _contrato(_cotizar(piloto, otra, destino={"aeropuertos": ["ZZZ"]}), 422, "VALIDATION_ERROR")
    assert _cotizar(piloto, otra).status_code == 201


def test_una_clave_en_curso_pide_reintentar(piloto):
    yo = _cuenta("piloto@demo.local")
    clave = "cotizacion-en-curso-1"
    huella = cotizacion.huella_pedido(NuevaCotizacion.model_validate(_pedido()).model_dump(mode="json"))
    envio, sid = cotizacion.reclamar_envio(yo["id"], clave, huella)
    assert sid is None
    _contrato(_cotizar(piloto, {"Idempotency-Key": clave}), 409, "REQUEST_IN_PROGRESS")
    # si quien la tenía se cayó, al vencer la concesión otro intento la retoma
    db.actualizar("envios_cotizacion", envio["id"], expira="2000-01-01 00:00:00")
    assert _cotizar(piloto, {"Idempotency-Key": clave}).status_code == 201


def test_decidir_por_la_api_crea_el_viaje(piloto, cliente):
    c = _cotizar(piloto, destino={"texto": "las vegas"}).json()      # Miami → Las Vegas, también guardado
    ruta = f"{V1}/cotizaciones/{c['id']}/decision"
    otro = next(v["id"] for v in c["vuelos"] if not v["recomendada"])
    cuerpo = _contrato(piloto.post(ruta, json={"vuelo_id": otro, "motivo": "no"}, headers=_csrf(piloto)), 422, "VALIDATION_ERROR")
    assert "por qué" in cuerpo["error"]["fields"]["motivo"]
    cuerpo = _contrato(piloto.post(ruta, json={"vuelo_id": 999999}, headers=_csrf(piloto)), 422, "VALIDATION_ERROR")
    assert "vuelo_id" in cuerpo["error"]["fields"]
    _contrato(piloto.post(ruta, json={"vuelo_id": otro, "motivo": "Llega antes"}), 403, "CSRF_INVALID")
    decision = {"vuelo_id": otro, "hotel_id": c["hoteles"][0]["id"], "motivo": "Llega antes de la reunión", "razones": ["horario"]}
    r = piloto.post(ruta, json=decision, headers=_csrf(piloto))
    assert r.status_code == 200, r.text
    hecha = r.json()
    assert hecha["estado"] == "decidido" and hecha["viaje"]["estado"] == "pendiente_aprobacion"
    assert re.fullmatch(r"V-\d{4}-\d{4}", hecha["viaje"]["codigo"])
    d = hecha["decision"]
    assert (d["vuelo_id"], d["hotel_id"], d["motivo"], d["razones"], d["siguio_recomendacion"]) == (
        otro, c["hoteles"][0]["id"], "Llega antes de la reunión", ["horario"], False)
    assert DINERO.match(d["total_usd"])
    v = viajes.de_solicitud(c["id"])
    assert v["usuario_id"] == _cuenta("piloto@demo.local")["id"] and hecha["viaje"]["id"] == v["id"]
    # el presupuesto que aprueba administración (sin riesgo de cambio ni millas, con viáticos), no el costo esperado
    assert hecha["viaje"]["presupuesto_usd"] == consultas.dinero(v["presupuesto_usd"])
    # el mismo envío otra vez no duplica nada
    assert piloto.post(ruta, json=decision, headers=_csrf(piloto)).json()["decision"]["id"] == d["id"]
    assert db.uno("select count(*) n from decisiones where solicitud_id=:s", s=c["id"])["n"] == 1
    # aprobado el presupuesto, la decisión no cambia sin reabrir
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "aprobar"})
    aprobada = piloto.get(f"{V1}/cotizaciones/{c['id']}").json()
    assert aprobada["puede_decidir"] is False and aprobada["bloqueo"] and aprobada["viaje"]["estado"] == "aprobado"
    _contrato(piloto.post(ruta, json={"vuelo_id": c["recomendada_id"]}, headers=_csrf(piloto)), 409, "DECISION_LOCKED")


def test_hay_tope_de_cotizaciones_por_persona_y_dia(piloto2, monkeypatch):
    """Cada cotización nueva puede gastar dos búsquedas pagas: la API corta al llegar al tope del día."""
    from app.rutas import v1_cotizaciones
    yo = _cuenta("piloto2@demo.local")
    hoy = db.uno("select count(*) n from solicitudes where usuario_id=:u and creado>=:h", u=yo["id"], h=db.ahora()[:10])["n"]
    monkeypatch.setattr(v1_cotizaciones, "TOPE_DIA", hoy + 1)
    assert _cotizar(piloto2, {"Idempotency-Key": "tope-1"}).status_code == 201
    antes = _solicitudes()
    cuerpo = _contrato(_cotizar(piloto2), 429, "TOO_MANY_REQUESTS")
    assert "tope" in cuerpo["error"]["message"] and _solicitudes() == antes
    assert _cotizar(piloto2, {"Idempotency-Key": "tope-1"}).status_code == 200   # repetir lo ya cotizado no cuenta
