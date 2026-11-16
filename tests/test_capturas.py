"""Pieza 5: captura completa al decidir, seguimiento diario y captura final al comprar.

La cola `capturas` se llena al decidir (vuelo y hotel), una vez al día por cada vuelo decidido y no comprado (hasta la
compra o la ida) y al registrar la compra. El trabajador (`app/tareas.py`) toma de a una, con el turno del analizador,
y guarda datos, texto y capturas. El analizador es un doble: nunca se sale a internet.
"""
import base64

import pytest
from starlette.testclient import TestClient

from app import api_v1, db, tareas
from app.servicios import acceso, analizador, capturas

V1 = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"pagina completa"
SECRETO = "u=UNSOLOUSO-CAPTURA-555&adurl="


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _cotizar(c: TestClient) -> dict:
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    r = c.post(f"{V1}/cotizaciones", json=pedido, headers=_csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def _decidir(c: TestClient, cot: dict, vuelo_id: int | None = None, motivo: str = "", hotel: bool = True) -> dict:
    cuerpo = {"vuelo_id": vuelo_id or cot["recomendada_id"], "motivo": motivo}
    if hotel and cot.get("hotel_recomendado_id"):
        cuerpo["hotel_id"] = cot["hotel_recomendado_id"]
    r = c.post(f"{V1}/cotizaciones/{cot['id']}/decision", json=cuerpo, headers=_csrf(c))
    assert r.status_code == 200, r.text
    return r.json()


def _de(sid: int) -> list[dict]:
    return db.todos("select * from capturas where solicitud_id=:s order by id", s=sid)


@pytest.fixture
def cola(monkeypatch):
    """El analizador como servicio (doble que cuenta sus pedidos); la cola y los topes, limpios."""
    pedidos = []
    respuestas = {
        "captura_vuelo": {"estado": "listo", "duracion_ms": 30000, "datos": {"tramos": [{"avion": "Boeing 737"}]},
                          "texto": "Booking options\nBook with American", "capturas_png_b64": [base64.b64encode(PNG).decode()],
                          "envio": {"url": "https://www.google.com/travel/clk/f?pf=1", "cuerpo": SECRETO}},
        "captura_aerolinea": {"estado": "listo", "duracion_ms": 12000, "datos": {"total": 748.80, "impuestos": 79.30},
                              "texto": "Passengers\nYour trip total $748.80",
                              "capturas_png_b64": [base64.b64encode(PNG + b"aerolinea").decode()]},
        "ir_a": {"estado": "listo", "url": "https://www.google.com/travel/clk/f?pf=1", "cuerpo": "u=UNSOLOUSO-CLIC-999&adurl=",
                 "vendedor": "American", "tarifa": "Main Cabin", "duracion_ms": 5000},
        "captura_hotel": {"estado": "listo", "duracion_ms": 20000, "datos": {"calificacion": 4.3},
                          "texto": "Prices\nBooking.com $612", "capturas_png_b64": [base64.b64encode(PNG + b"hotel").decode()]},
    }
    monkeypatch.setenv("ANALIZADOR_URL", "http://analizador:8090")
    monkeypatch.delenv("ANALIZADOR", raising=False)
    monkeypatch.setattr(analizador, "_invocar", lambda p: pedidos.append(p) or dict(respuestas[p["accion"]]))
    db.ejecutar("delete from capturas")
    db.ejecutar("delete from analisis_vuelo")
    capturas.asegurar_reglas()
    # la base de pruebas trae viajes de otras pruebas: el seguimiento se enciende solo donde se prueba
    db.ejecutar("update reglas set valor='0' where ambito='supuesto' and clave='seguimiento_diario'")
    yield pedidos, respuestas
    db.ejecutar("delete from capturas")
    db.ejecutar("update reglas set valor=:v where ambito='supuesto' and clave='capturas_dia'", v=str(capturas.TOPE_DIA))
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='seguimiento_diario'")


# ---------- cuándo se encola ----------
def test_al_decidir_se_encolan_el_vuelo_y_el_hotel_sin_esperar(piloto, cola):
    pedidos, _ = cola
    cot = _cotizar(piloto)
    assert cot["hotel_recomendado_id"], "la cotización de ejemplo trae hoteles"
    d = _decidir(piloto, cot)
    filas = _de(cot["id"])
    assert [(f["tipo"], f["motivo"], f["estado"], f["intentos"]) for f in filas] == [
        ("vuelo", "decision", "pendiente", 0), ("hotel", "decision", "pendiente", 0)]
    assert all(f["decision_id"] == d["decision"]["id"] for f in filas)
    assert filas[0]["url"].startswith("https://www.google.com/travel/flights?") and filas[0]["opcion_id"] == cot["recomendada_id"]
    assert filas[1]["url"].startswith("https://www.google.com/travel/search?") and filas[1]["opcion_id"] == cot["hotel_recomendado_id"]
    assert pedidos == []            # la decisión no espera al analizador


def test_repetir_la_decision_no_duplica_y_otra_la_reemplaza(piloto, cola):
    cot = _cotizar(piloto)
    _decidir(piloto, cot)
    _decidir(piloto, cot)
    assert len(_de(cot["id"])) == 2
    otro = next(v for v in cot["vuelos"] if v["id"] != cot["recomendada_id"])
    _decidir(piloto, cot, otro["id"], motivo="Mejor horario")
    filas = _de(cot["id"])
    viejas, nuevas = filas[:2], filas[2:]
    assert all((f["estado"], f["fallo"]) == ("fallida", capturas.REEMPLAZADA) for f in viejas)
    assert [(f["tipo"], f["estado"], f["opcion_id"]) for f in nuevas] == [("vuelo", "pendiente", otro["id"]),
                                                                          ("hotel", "pendiente", cot["hotel_recomendado_id"])]


def test_al_registrar_la_compra_se_encola_la_captura_final(piloto, cliente, cola):
    cot = _cotizar(piloto)
    d = _decidir(piloto, cot, hotel=False)
    viaje = d["viaje"]["id"]
    assert cliente.post(f"{V1}/viajes/{viaje}/estado", json={"accion": "aprobar", "confirmar_precio": True},
                        headers=_csrf(cliente)).status_code == 200
    c = db.uno("select * from compras where viaje_id=:v and activa=1", v=viaje)
    assert cliente.post(f"{V1}/compras/{c['id']}/estado", json={"accion": "se_comprara", "version": 1, "motivo": "Hoy"},
                        headers=_csrf(cliente)).status_code == 200
    r = cliente.post(f"{V1}/compras/{c['id']}/registro", json={"version": 2, "localizador": "QX7Z2P", "precio_pagado": "748.80",
                                                               "vendedor": "American"}, headers=_csrf(cliente))
    assert r.status_code == 200, r.text
    final = [f for f in _de(cot["id"]) if f["motivo"] == "compra"]
    assert [(f["tipo"], f["estado"], f["compra_id"]) for f in final] == [("vuelo", "pendiente", c["id"])]


def test_el_seguimiento_es_diario_hasta_la_compra_o_la_ida(piloto, cliente, cola):
    cot = _cotizar(piloto)
    d = _decidir(piloto, cot, hotel=False)
    seg = lambda: [f for f in _de(cot["id"]) if f["motivo"] == "seguimiento"]  # noqa: E731
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='seguimiento_diario'")
    capturas.encolar_seguimiento("2026-11-20")
    capturas.encolar_seguimiento("2026-11-20")                       # el mismo día no se repite
    assert [(f["tipo"], f["estado"]) for f in seg()] == [("vuelo", "pendiente")]
    capturas.encolar_seguimiento("2026-11-21")
    assert len(seg()) == 2
    capturas.encolar_seguimiento("2026-12-09")                       # pasó la ida
    assert len(seg()) == 2
    db.ejecutar("update reglas set valor='0' where ambito='supuesto' and clave='seguimiento_diario'")
    capturas.encolar_seguimiento("2026-11-22")                       # apagado
    assert len(seg()) == 2
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='seguimiento_diario'")
    db.ejecutar("update compras set estado='comprada' where viaje_id=:v", v=d["viaje"]["id"])
    capturas.encolar_seguimiento("2026-11-23")                       # comprado: se detiene
    assert len(seg()) == 2


# ---------- el trabajador ----------
def test_el_trabajador_guarda_datos_texto_y_capturas_sin_el_envio(piloto, cola, capfd):
    pedidos, _ = cola
    cot = _cotizar(piloto)
    _decidir(piloto, cot)
    hecho = tareas.procesar(hoy="2026-11-20")
    assert hecho["procesadas"] == 2
    assert [p["accion"] for p in pedidos] == ["captura_vuelo", "captura_aerolinea", "captura_hotel"]
    elegido = next(v for v in cot["vuelos"] if v["id"] == cot["recomendada_id"])
    assert pedidos[0]["vendedor"] == elegido["aerolinea"] and pedidos[0]["tarifa"]   # la aerolínea y la tarifa decididas
    assert pedidos[0]["url"].startswith("https://www.google.com/")
    assert pedidos[1]["cuerpo"] == SECRETO                          # el envío pasa de una invocación a la otra en memoria
    vuelo, hotel = _de(cot["id"])[:2]
    assert (vuelo["estado"], vuelo["intentos"], hotel["estado"]) == ("lista", 1, "lista")
    datos = db.de_json(vuelo["datos"], {})
    assert datos["google"]["tramos"][0]["avion"] == "Boeing 737" and datos["aerolinea"]["impuestos"] == 79.30
    assert "Book with American" in vuelo["texto"] and "Your trip total" in vuelo["texto"]
    assert len(db.de_json(vuelo["imagenes"], [])) == 2 and len(db.de_json(hotel["imagenes"], [])) == 1
    guardado = "\n".join(str(f) for t in ("capturas", "eventos") for f in db.todos(f"select * from {t}"))
    salida = capfd.readouterr()
    assert "UNSOLOUSO-CAPTURA-555" not in guardado + salida.out + salida.err   # el envío de un solo uso nunca se guarda


def test_el_texto_completo_tiene_tope(piloto, cola):
    _, respuestas = cola
    respuestas["captura_vuelo"]["texto"] = "x" * 400_000
    cot = _cotizar(piloto)
    _decidir(piloto, cot, hotel=False)
    tareas.procesar(hoy="2026-11-20")
    assert len(_de(cot["id"])[0]["texto"].encode()) <= capturas.TOPE_TEXTO


def test_tres_intentos_y_despues_fallida(piloto, cola):
    pedidos, respuestas = cola
    respuestas["captura_vuelo"] = {"estado": "fallido", "motivo": "la página tardó demasiado en mostrar los precios"}
    cot = _cotizar(piloto)
    _decidir(piloto, cot, hotel=False)
    tareas.procesar(hoy="2026-11-20")
    f = _de(cot["id"])[0]
    assert (f["estado"], f["intentos"], f["fallo"]) == ("pendiente", 1, "la página tardó demasiado en mostrar los precios")
    assert tareas.procesar(hoy="2026-11-20")["procesadas"] == 0        # el reintento espera su momento
    for _ in range(2):
        db.ejecutar("update capturas set proximo=null")
        tareas.procesar(hoy="2026-11-20")
    f = _de(cot["id"])[0]
    assert (f["estado"], f["intentos"]) == ("fallida", 3)
    assert len(pedidos) == 3


def test_respeta_el_tope_del_dia_y_el_de_cada_corrida(piloto, cola):
    pedidos, _ = cola
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='capturas_dia'")
    cot = _cotizar(piloto)
    _decidir(piloto, cot)
    assert tareas.procesar(hoy="2026-11-20")["procesadas"] == 1
    assert tareas.procesar(hoy="2026-11-20")["procesadas"] == 0
    assert [f["estado"] for f in _de(cot["id"])] == ["lista", "pendiente"]
    db.ejecutar(f"update reglas set valor='{capturas.TOPE_DIA}' where ambito='supuesto' and clave='capturas_dia'")
    for _ in range(12):
        db.insertar("capturas", tipo="hotel", motivo="decision", clave=f"prueba:{_}", url="https://www.google.com/travel/search?q=x",
                    estado="pendiente", intentos=0, creado=db.ahora())
    assert tareas.procesar(hoy="2026-11-20")["procesadas"] == tareas.POR_CORRIDA == 10


def test_no_arranca_con_el_analizador_ocupado_y_lo_ocupa_mientras_captura(piloto, cola, monkeypatch):
    pedidos, respuestas = cola
    cot = _cotizar(piloto)
    _decidir(piloto, cot, hotel=False)
    otra = db.insertar("analisis_vuelo", opcion_id=cot["vuelos"][1]["id"], solicitud_id=cot["id"], clave="x",
                       url="https://www.google.com/travel/flights", estado="pendiente", creado=db.ahora())
    assert tareas.procesar(hoy="2026-11-20")["procesadas"] == 0 and pedidos == []
    db.ejecutar("delete from analisis_vuelo where id=:i", i=otra)
    vistos = []

    def mirar(p):
        vistos.append(analizador._ocupado())      # mientras captura, una lectura de la web encontraría el turno tomado
        return dict(respuestas[p["accion"]])
    monkeypatch.setattr(analizador, "_invocar", mirar)
    assert tareas.procesar(hoy="2026-11-20")["procesadas"] == 1
    assert vistos and all(vistos) and not analizador._ocupado()


def test_el_manejador_de_lambda_encola_el_seguimiento_y_procesa(piloto, cola):
    pedidos, _ = cola
    cot = _cotizar(piloto)
    _decidir(piloto, cot, hotel=False)
    db.ejecutar("update capturas set estado='lista'")
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='seguimiento_diario'")
    r = tareas.manejador({}, None)
    assert r["procesadas"] >= 1 and r["seguimiento"] >= 1     # la base de pruebas puede traer otros viajes decididos
    assert [f["motivo"] for f in _de(cot["id"])] == ["decision", "seguimiento"]


def test_las_tablas_y_reglas_tienen_su_migracion():
    assert "capturas" in db.TABLAS
    db.ejecutar("delete from reglas where clave in ('seguimiento_diario', 'capturas_dia', 'capturas_clic_persona_dia')")
    assert capturas.asegurar_reglas() == 3 and capturas.asegurar_reglas() == 0


def test_el_adaptador_de_lambda_llega_por_post_events(cola, monkeypatch):
    """La imagen de la API corre con el adaptador web de Lambda: el evento programado llega como POST /events."""
    llamadas = []
    monkeypatch.setattr(tareas, "procesar", lambda: llamadas.append(1) or {"seguimiento": 0, "procesadas": 0, "listas": 0})
    c = TestClient(tareas.aplicacion)
    assert c.get("/salud").status_code == 200
    r = c.post("/events", json={"source": "aws.events"})
    assert r.status_code == 200 and r.json()["procesadas"] == 0 and llamadas == [1]
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


# ---------- pantallas: la evidencia, solo con permiso ----------
def test_la_evidencia_se_ve_en_la_cotizacion_y_en_la_compra_solo_con_permiso(piloto, piloto2, cliente, anonimo, cola):
    cot = _cotizar(piloto)
    _decidir(piloto, cot)
    e = piloto.get(f"{V1}/cotizaciones/{cot['id']}/evidencia").json()
    assert e["estado"] == "guardando" and e["guardada"] is None
    assert [(c["tipo"], c["estado"]) for c in e["capturas"]] == [("vuelo", "pendiente"), ("hotel", "pendiente")]
    tareas.procesar(hoy="2026-11-20")
    e = piloto.get(f"{V1}/cotizaciones/{cot['id']}/evidencia").json()
    assert e["estado"] == "guardada" and e["guardada"]
    vuelo = e["capturas"][0]
    assert vuelo["datos"]["aerolinea"]["impuestos"] == 79.30 and len(vuelo["imagenes"]) == 2
    assert e["seguimiento"] == [{"momento": vuelo["terminado"], "motivo": "decision", "precio_google_usd": None,
                                 "total_aerolinea_usd": "748.80"}]
    img = piloto.get(vuelo["imagenes"][0])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content.startswith(b"\x89PNG")
    assert img.headers["Cache-Control"] == "private, no-store"
    texto = piloto.get(vuelo["texto_url"])
    assert texto.status_code == 200 and texto.headers["content-type"].startswith("text/plain") and "Your trip total" in texto.text
    # de otra persona: no existe; sin sesión: 401
    for ruta in (f"{V1}/cotizaciones/{cot['id']}/evidencia", vuelo["imagenes"][0], vuelo["texto_url"]):
        assert piloto2.get(ruta).status_code == 404, ruta
        assert anonimo.get(ruta).status_code == 401, ruta
    assert piloto.get(vuelo["imagenes"][0].rsplit("/", 1)[0] + "/9").status_code == 404
    # administración la ve en la ficha de la compra
    compra = db.uno("select c.id from compras c join viajes v on v.id=c.viaje_id where v.solicitud_id=:s and c.activa=1", s=cot["id"])
    detalle = cliente.get(f"{V1}/compras/{compra['id']}").json()
    assert detalle["evidencia"]["estado"] == "guardada" and len(detalle["evidencia"]["capturas"]) == 2
    assert cliente.get(vuelo["imagenes"][0]).status_code == 200


# ---------- arreglos antes de unir: la evidencia nunca tumba la compra ni la decisión ----------
def test_si_no_se_puede_encolar_la_evidencia_la_compra_queda_registrada(piloto, cliente, cola, monkeypatch):
    cot = _cotizar(piloto)
    d = _decidir(piloto, cot, hotel=False)
    viaje = d["viaje"]["id"]
    assert cliente.post(f"{V1}/viajes/{viaje}/estado", json={"accion": "aprobar", "confirmar_precio": True},
                        headers=_csrf(cliente)).status_code == 200
    c = db.uno("select * from compras where viaje_id=:v and activa=1", v=viaje)
    assert cliente.post(f"{V1}/compras/{c['id']}/estado", json={"accion": "se_comprara", "version": 1, "motivo": "Hoy"},
                        headers=_csrf(cliente)).status_code == 200

    def falla(_cid):
        raise RuntimeError("almacén caído")
    monkeypatch.setattr(capturas, "al_comprar", falla)
    r = cliente.post(f"{V1}/compras/{c['id']}/registro", json={"version": 2, "localizador": "QX7Z2P", "precio_pagado": "748.80",
                                                               "vendedor": "American"}, headers=_csrf(cliente))
    assert r.status_code == 200 and r.json()["estado"] == "comprada", r.text
    assert db.uno("""select id from eventos where entidad='viaje' and entidad_id=:v and paso='aviso al viajero'
                     and detalle like '%comprada a American%'""", v=viaje)
    ev = db.uno("select detalle from eventos where entidad='compra' and entidad_id=:c and paso='evidencia de compra no encolada'",
                c=c["id"])
    assert ev and "RuntimeError" in ev["detalle"]


def test_si_no_se_puede_encolar_la_evidencia_la_decision_queda_guardada(piloto, cola, monkeypatch):
    def falla(_did):
        raise RuntimeError("cola caída")
    monkeypatch.setattr(capturas, "al_decidir", falla)
    cot = _cotizar(piloto)
    d = _decidir(piloto, cot)
    did = d["decision"]["id"]
    assert db.uno("select id from decisiones where id=:d", d=did)
    assert db.uno("select id from compras where viaje_id=:v and activa=1", v=d["viaje"]["id"])
    ev = db.uno("select detalle from eventos where entidad='solicitud' and entidad_id=:s and paso='evidencia no encolada'",
                s=cot["id"])
    assert ev and "RuntimeError" in ev["detalle"] and _de(cot["id"]) == []


def test_la_evidencia_se_encola_despues_de_confirmar_la_decision(piloto, cola, monkeypatch):
    from app import db as base
    vistos = []
    real = capturas.al_decidir
    monkeypatch.setattr(capturas, "al_decidir", lambda did: vistos.append(base._en_transaccion.get()) or real(did))
    cot = _cotizar(piloto)
    _decidir(piloto, cot)
    assert vistos == [None]                      # fuera de la transacción y del cerrojo de la decisión
    assert len(_de(cot["id"])) == 2


# ---------- el clic a la aerolínea guarda todo (pedido de la responsable) ----------
def test_el_clic_a_la_aerolinea_encola_una_captura_completa_sin_esperar(piloto, cola):
    pedidos, _ = cola
    cot = _cotizar(piloto)
    vuelo = cot["vuelos"][0]["id"]
    ir = lambda: piloto.post(f"{V1}/cotizaciones/{cot['id']}/vuelos/{vuelo}/ir",  # noqa: E731
                             json={"vendedor": "American", "tarifa": "Main Cabin"}, headers=_csrf(piloto))
    r = ir()
    assert r.status_code == 200 and r.json()["camino"] == "pagina", r.text
    assert [p["accion"] for p in pedidos] == ["ir_a"]                 # la persona no espera la captura
    (f,) = [x for x in _de(cot["id"]) if x["motivo"] == "clic"]
    assert (f["tipo"], f["estado"], f["opcion_id"], f["decision_id"]) == ("vuelo", "pendiente", vuelo, None)
    assert db.de_json(f["datos"], {})["pedido"] == {"vendedor": "American", "tarifa": "Main Cabin"}
    ir()                                                              # el mismo clic en la misma hora no se repite
    assert len([x for x in _de(cot["id"]) if x["motivo"] == "clic"]) == 1
    tareas.procesar(hoy="2026-11-20")
    capt = [p for p in pedidos if p["accion"] == "captura_vuelo"]
    assert (capt[0]["vendedor"], capt[0]["tarifa"]) == ("American", "Main Cabin")   # la tarifa del clic, no la decidida
    f = db.uno("select * from capturas where id=:i", i=f["id"])
    assert f["estado"] == "lista" and db.de_json(f["datos"], {})["pedido"]["tarifa"] == "Main Cabin"
    assert "UNSOLOUSO-CLIC-999" not in str(db.todos("select * from capturas"))


def test_si_no_se_puede_encolar_el_clic_la_persona_va_igual(piloto, cola, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("cola caída")
    monkeypatch.setattr(capturas, "al_clic", falla)
    cot = _cotizar(piloto)
    r = piloto.post(f"{V1}/cotizaciones/{cot['id']}/vuelos/{cot['vuelos'][0]['id']}/ir",
                    json={"vendedor": "American", "tarifa": "Main Cabin"}, headers=_csrf(piloto))
    assert r.status_code == 200 and r.json()["camino"] == "pagina"
    assert db.uno("select id from eventos where entidad='solicitud' and entidad_id=:s and paso='evidencia del clic no encolada'",
                  s=cot["id"])


# ---------- pieza 6, ronda 1, punto 10: un «Ir a…» no agota las capturas de la empresa ----------
def _ir_a(c: TestClient, cot: dict, tarifa: str, vendedor: str = "American"):
    r = c.post(f"{V1}/cotizaciones/{cot['id']}/vuelos/{cot['vuelos'][0]['id']}/ir",
               json={"vendedor": vendedor, "tarifa": tarifa}, headers=_csrf(c))
    assert r.status_code == 200, r.text
    return r.json()


def _clics(sid: int) -> list[dict]:
    return [f for f in _de(sid) if f["motivo"] == "clic"]


def test_con_el_tope_de_ir_a_alcanzado_no_se_encola_la_captura(piloto, cola, monkeypatch):
    monkeypatch.setattr(analizador, "_reservar_ir", lambda *a, **k: {"motivo": analizador.TOPE_IR_A_TEXTO, "tope": True})
    cot = _cotizar(piloto)
    assert _ir_a(piloto, cot, "Main Cabin")["camino"] == "google"
    assert _clics(cot["id"]) == []


def _sin_la_tarifa_en_la_pagina(cola):
    """La página no encuentra la tarifa (lo que pasa con una inventada): «Ir a…» va a Google Flights."""
    _, respuestas = cola
    respuestas["ir_a"] = {"estado": "fallido", "motivo": "no se encontró la tarifa", "duracion_ms": 5000}


def _guardadas(monkeypatch, *nombres: str):
    from app.servicios import precios
    tarifas = [{"vendedor": "American", "nombre": n, "precio": 400.0, "tramo": "ambos"} for n in nombres]
    monkeypatch.setattr(precios, "opciones_guardadas", lambda *a, **k: (tarifas, None))


def test_una_tarifa_inventada_no_encola_ni_falla(piloto, cola, monkeypatch):
    _sin_la_tarifa_en_la_pagina(cola)
    _guardadas(monkeypatch, "Main Cabin")
    cot = _cotizar(piloto)
    assert _ir_a(piloto, cot, "Tarifa Inventada 1")["camino"] == "google"
    assert _ir_a(piloto, cot, "Main Cabin", vendedor="Vendedor Inventado")["camino"] == "google"
    assert _clics(cot["id"]) == []
    _ir_a(piloto, cot, "main cabin")                        # la que sí está guardada (sin distinguir mayúsculas)
    assert len(_clics(cot["id"])) == 1


def test_el_clic_numero_11_del_dia_de_la_misma_persona_no_encola(piloto, cliente, cola, monkeypatch):
    _sin_la_tarifa_en_la_pagina(cola)
    _guardadas(monkeypatch, *(f"Tarifa {n}" for n in range(1, 13)))
    cot = _cotizar(piloto)
    for n in range(1, 12):
        _ir_a(piloto, cot, f"Tarifa {n}")
    clics = _clics(cot["id"])
    assert len(clics) == capturas.TOPE_CLIC_PERSONA == 10
    assert "Tarifa 11" not in str([f["datos"] for f in clics])
    _ir_a(cliente, cot, "Tarifa 12")                        # el tope es por persona: otra persona sí encola
    assert len(_clics(cot["id"])) == 11


def test_el_tope_de_clics_por_persona_es_una_regla_editable(piloto, cola, monkeypatch):
    _sin_la_tarifa_en_la_pagina(cola)
    _guardadas(monkeypatch, "Tarifa 1", "Tarifa 2")
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='capturas_clic_persona_dia'")
    try:
        cot = _cotizar(piloto)
        _ir_a(piloto, cot, "Tarifa 1")
        _ir_a(piloto, cot, "Tarifa 2")
        assert len(_clics(cot["id"])) == 1
    finally:
        db.ejecutar("update reglas set valor=:v where ambito='supuesto' and clave='capturas_clic_persona_dia'",
                    v=str(capturas.TOPE_CLIC_PERSONA))


def test_la_tarifa_de_la_lectura_vigente_tambien_vale(piloto, cola, monkeypatch):
    _sin_la_tarifa_en_la_pagina(cola)
    _guardadas(monkeypatch)
    cot = _cotizar(piloto)
    vuelo = cot["vuelos"][0]["id"]
    db.insertar("analisis_vuelo", opcion_id=vuelo, solicitud_id=cot["id"], usuario_id=1, clave=analizador.clave_de(cot["id"], vuelo),
                url="https://www.google.com/travel/flights", estado="listo", creado=db.ahora(), accion="leer",
                datos={"tarifas": [{"vendedor": "Expedia", "nombre": "Economy", "precio": 500.0}]})
    _ir_a(piloto, cot, "Economy", vendedor="Expedia")
    assert len(_clics(cot["id"])) == 1
