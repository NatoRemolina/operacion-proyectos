"""Pieza 6: «Ir a…» lleva al enlace del vuelo, por tiquete, con el buscador primero.

La respuesta del buscador con billetes separados sigue la forma de su documentación («Example with separate tickets»):
cada opción trae `separate_tickets`, el total en `together` (sin pedido) y un tiquete por tramo en `departing` y
`returning`, cada uno con su `booking_request`. El buscador es un doble: nunca se sale a internet; los `post_data` son
inventados.
"""
import json
import logging

import pytest

from app import config, db
from app.servicios import precios

CLK = "https://www.google.com/travel/clk/f"


def tiquete(vendedor: str, precio: float, numeros: list[str], secreto: str, aerolinea: bool = True) -> dict:
    return {"book_with": vendedor, "airline": aerolinea, "marketed_as": numeros, "price": precio,
            "baggage_prices": ["1 free carry-on", "1st checked bag: 30"],
            "booking_request": {"url": CLK, "post_data": f"u={secreto}"}}


def separados(regreso_vendedor: str = "Avianca", regreso_precio: float = 323, regreso_aerolinea: bool = True) -> dict:
    return {"booking_options": [
        {"separate_tickets": True,
         "together": {"book_with": f"COPA, {regreso_vendedor}", "airline": True, "marketed_as": ["CM 687", "CM 240", "AV 9"],
                      "price": 334 + regreso_precio},
         "departing": tiquete("COPA", 334, ["CM 687", "CM 240"], "IDA-COPA-SECRETA"),
         "returning": tiquete(regreso_vendedor, regreso_precio, ["AV 9"], "REGRESO-SECRETA", regreso_aerolinea)},
    ]}


IDA = {"numeros": ["CM 687", "CM 240"], "hasta": "MIA"}


@pytest.fixture
def buscador(monkeypatch, tmp_path):
    respuesta = {"datos": separados()}
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    monkeypatch.setattr(config, "DIR_RESPALDO_ESCRITURA", tmp_path)
    monkeypatch.setattr(precios, "_consultar", lambda *a, **k: json.loads(json.dumps(respuesta["datos"])))
    ultima = db.uno("select coalesce(max(id), 0) n from busquedas")["n"]
    yield respuesta, tmp_path
    db.ejecutar("delete from busquedas where id>:n", n=ultima)


def _en_vivo():
    return precios.reserva_en_vivo(IDA, {"booking": "TOKEN"}, "MDE", "MIA", "2026-11-20", "2026-11-29")


# ---------- punto 1: el buscador devuelve también los billetes separados ----------
def test_los_billetes_separados_salen_por_tramo_con_su_pedido(buscador):
    opciones = _en_vivo()
    assert [(o["tramo"], o["vendedor"], o["precio"], o["aerolinea"]) for o in opciones] == [
        ("ida", "COPA", 334, True), ("regreso", "Avianca", 323, True)]
    ida, regreso = opciones
    assert (ida["url"], ida["post_data"]) == (CLK, "u=IDA-COPA-SECRETA")
    assert regreso["post_data"] == "u=REGRESO-SECRETA"
    assert ida["numeros"] == ["CM 687", "CM 240"] and regreso["numeros"] == ["AV 9"]
    assert ida["equipaje"] == ["1 free carry-on", "1st checked bag: 30"] and ida["tarifa"] == "Tarifa"


def test_lo_guardado_no_lleva_el_pedido(buscador):
    _, carpeta = buscador
    _en_vivo()
    guardado = json.dumps(db.todos("select * from busquedas"), default=str) + \
        "".join(p.read_text() for p in carpeta.rglob("*") if p.is_file())
    for secreto in ("IDA-COPA-SECRETA", "REGRESO-SECRETA", "booking_request"):
        assert secreto not in guardado, secreto


def test_una_opcion_junta_es_de_ambos_tramos(buscador):
    respuesta, _ = buscador
    respuesta["datos"] = {"booking_options": [{"together": {**tiquete("American", 458, ["AA 1851"], "JUNTA"),
                                                           "option_title": "Main Cabin"}}]}
    assert [(o["tramo"], o["vendedor"], o["tarifa"]) for o in _en_vivo()] == [("ambos", "American", "Main Cabin")]


@pytest.mark.parametrize("rara", [
    {"separate_tickets": True, "departing": "no es un objeto", "returning": None},
    {"separate_tickets": True, "departing": {"book_with": 7, "price": "caro"}},
    "una opción que no es un objeto",
])
def test_una_respuesta_rara_deja_la_opcion_fuera_sin_romper(buscador, rara):
    respuesta, _ = buscador
    respuesta["datos"] = {"booking_options": [rara, *separados()["booking_options"]]}
    assert [o["tramo"] for o in _en_vivo()] == ["ida", "regreso"]


def test_la_tarifa_de_billetes_separados_sin_total_suma_los_dos_tramos():
    opcion = separados()["booking_options"][0]
    del opcion["together"]
    t = precios._tarifa(opcion)
    assert (t["precio"], t["vende"]) == (657, "COPA, Avianca")


def test_las_opciones_guardadas_muestran_cada_tiquete(buscador):
    _en_vivo()
    tarifas, _ = precios.opciones_guardadas(IDA, "MDE", "MIA", "2026-11-20", "2026-11-29")
    assert [(t["vendedor"], t["nombre"], t["precio"], t["tramo"]) for t in tarifas] == [
        ("COPA", "ida", 334, "ida"), ("Avianca", "regreso", 323, "regreso")]


# ---------- punto 2: se elige por vendedor y tramo; si el vendedor cambió, el actual con un aviso ----------
def _yo():
    return db.uno("select * from usuarios where correo='piloto@demo.local'")


def _cotizacion(c) -> dict:
    from app import api_v1
    from app.servicios import acceso
    pedido = {"proyecto_id": 1, "origen": {"texto": "Miami (MIA)"}, "destino": {"texto": "Las Vegas (LAS)"},
              "ida": "2026-12-08", "regreso": "2026-12-11"}
    r = c.post("/api/v1/cotizaciones", json=pedido, headers={"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def con_regreso(monkeypatch, buscador):
    monkeypatch.setattr(precios, "vuelo_regreso", lambda *a, **k: {"booking": "TOKEN"})
    db.ejecutar("delete from cupos_buscador")
    db.ejecutar("delete from consultas_buscador where tipo in ('vendedor', 'vendedor_regreso')")
    yield buscador
    db.ejecutar("delete from cupos_buscador")


def test_elegir_tiquete_por_vendedor_y_tramo(buscador):
    opciones = _en_vivo()
    o, aviso = precios.elegir_tiquete(opciones, "COPA", "ida")
    assert (o["vendedor"], o["tramo"], aviso) == ("COPA", "ida", None)
    o, aviso = precios.elegir_tiquete(opciones, "avianca", "Regreso")
    assert (o["vendedor"], aviso) == ("Avianca", None)
    assert precios.elegir_tiquete(opciones, "COPA", "Main Cabin") == (None, None)   # ningún tiquete es el viaje entero


def test_si_otro_vende_el_regreso_se_elige_el_actual_con_aviso(buscador):
    respuesta, _ = buscador
    respuesta["datos"] = separados("eDreams", 316, regreso_aerolinea=False)
    o, aviso = precios.elegir_tiquete(_en_vivo(), "Avianca", "regreso")
    assert (o["vendedor"], o["post_data"]) == ("eDreams", "u=REGRESO-SECRETA")
    assert aviso == "Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD"


def test_el_enlace_al_vendedor_lleva_la_ida_de_copa(piloto, con_regreso):
    from app.servicios import cotizacion
    c = _cotizacion(piloto)
    destino = cotizacion.enlace_vendedor(_yo(), c["id"], c["vuelos"][0]["id"], vendedor="COPA", tarifa="ida")
    assert (destino["tipo"], destino["vendedor"], destino["url"], destino["campos"]) == (
        "envio", "COPA", CLK, [("u", "IDA-COPA-SECRETA")])
    assert destino["aviso"] is None and destino["tiquete"]["numeros"] == ["CM 687", "CM 240"]


def test_el_enlace_al_vendedor_con_otro_vendedor_lo_avisa(piloto, con_regreso):
    from app.servicios import cotizacion
    respuesta, _ = con_regreso
    respuesta["datos"] = separados("eDreams", 316, regreso_aerolinea=False)
    c = _cotizacion(piloto)
    destino = cotizacion.enlace_vendedor(_yo(), c["id"], c["vuelos"][0]["id"], vendedor="Avianca", tarifa="regreso")
    assert (destino["tipo"], destino["vendedor"]) == ("envio", "eDreams")
    assert destino["aviso"] == "Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD"


def test_sin_tramo_el_enlace_al_vendedor_no_compra_solo_la_ida(piloto, con_regreso):
    from app.servicios import cotizacion
    c = _cotizacion(piloto)
    assert cotizacion.enlace_vendedor(_yo(), c["id"], c["vuelos"][0]["id"])["tipo"] == "google"


@pytest.fixture
def analizador_doble(monkeypatch):
    """El analizador como servicio (doble): cada prueba dice qué responde."""
    from app.servicios import analizador
    pedidos, respuesta = [], {"estado": "fallido", "motivo": "no se encontró la tarifa"}
    monkeypatch.setenv("ANALIZADOR_URL", "http://analizador:8090")
    monkeypatch.delenv("ANALIZADOR", raising=False)
    monkeypatch.setattr(analizador, "_invocar", lambda p: pedidos.append(p) or dict(respuesta))
    db.ejecutar("delete from analisis_vuelo")
    yield pedidos, respuesta
    db.ejecutar("delete from analisis_vuelo")


def _ir(c, sid: int, vuelo: int, vendedor: str, tarifa: str):
    from app import api_v1
    from app.servicios import acceso
    return c.post(f"/api/v1/cotizaciones/{sid}/vuelos/{vuelo}/ir", json={"vendedor": vendedor, "tarifa": tarifa},
                  headers={"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))})


def test_ir_a_un_tiquete_que_ahora_vende_otro_lleva_al_actual_y_lo_dice(piloto, con_regreso, analizador_doble):
    respuesta, _ = con_regreso
    respuesta["datos"] = separados("eDreams", 316, regreso_aerolinea=False)
    c = _cotizacion(piloto)
    vuelo = c["vuelos"][0]
    r = _ir(piloto, c["id"], vuelo["id"], "Avianca", "regreso")
    assert r.status_code == 200, r.text
    e = r.json()
    assert (e["camino"], e["vendedor"], e["tarifa"], e["campos"]) == ("buscador", "eDreams", "regreso", [["u", "REGRESO-SECRETA"]])
    assert e["motivo"] == "Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD"
    fila = db.uno("select * from analisis_vuelo where accion='ir_a' order by id desc limit 1")
    assert (fila["camino"], fila["vendedor"]) == ("buscador", "Avianca")   # lo que pidió la persona
    ev = db.uno("select detalle from eventos where paso='ir a vendedor' order by id desc limit 1")["detalle"]
    assert "camino buscador" in ev and "ahora lo vende eDreams" in ev and "REGRESO-SECRETA" not in ev


# ---------- punto 3: el orden de caminos es buscador → página → Google Flights ----------
def test_el_buscador_va_primero_y_no_ocupa_al_analizador(piloto, con_regreso, analizador_doble):
    pedidos, _ = analizador_doble
    c = _cotizacion(piloto)
    e = _ir(piloto, c["id"], c["vuelos"][0]["id"], "COPA", "ida").json()
    assert (e["camino"], e["vendedor"], e["campos"], e["motivo"]) == ("buscador", "COPA", [["u", "IDA-COPA-SECRETA"]], None)
    assert pedidos == []                                           # el analizador no se usó
    fila = db.uno("select * from analisis_vuelo where accion='ir_a' order by id desc limit 1")
    assert (fila["estado"], fila["camino"]) == ("listo", "buscador")
    clic = db.uno("select * from clics_fuente order by id desc limit 1")
    assert clic["destino"] == "vendedor"


def test_sin_el_tiquete_en_el_buscador_va_la_pagina(piloto, con_regreso, analizador_doble):
    respuesta_buscador, _ = con_regreso
    respuesta_buscador["datos"] = {"booking_options": []}
    pedidos, respuesta = analizador_doble
    respuesta.update(estado="listo", url=CLK, cuerpo="u=DE-LA-PAGINA")
    c = _cotizacion(piloto)
    e = _ir(piloto, c["id"], c["vuelos"][0]["id"], "COPA", "ida").json()
    assert (e["camino"], e["campos"]) == ("pagina", [["u", "DE-LA-PAGINA"]]) and len(pedidos) == 1


def test_sin_buscador_ni_pagina_va_a_google_flights_con_el_motivo_de_la_pagina(piloto, con_regreso, analizador_doble):
    respuesta_buscador, _ = con_regreso
    respuesta_buscador["datos"] = {"booking_options": []}
    _, respuesta = analizador_doble
    respuesta.update(estado="fallido", motivo="la página pidió verificación")
    c = _cotizacion(piloto)
    vuelo = c["vuelos"][0]
    e = _ir(piloto, c["id"], vuelo["id"], "COPA", "ida").json()
    assert (e["camino"], e["url"], e["motivo"]) == ("google", vuelo["fuente_url"], "la página pidió verificación")


# ---------- punto 4: la página propia de envío dice qué vuelo elegir en el vendedor ----------
def test_la_guia_del_tiquete():
    guia = precios.guia_tiquete({"vendedor": "COPA", "tramo": "ida", "numeros": ["CM 687", "CM 240"],
                                         "sale": "2026-11-20 12:40", "tarifa": "Economy", "precio": 334})
    assert guia == "En COPA, elige CM 687 · CM 240, sale 12:40 pm, Economy desde 334 USD."
    guia = precios.guia_tiquete({"vendedor": "eDreams", "tramo": "regreso", "numeros": ["AV 9"],
                                         "sale": "2026-11-29 01:35", "tarifa": "Tarifa", "precio": 316})
    assert guia == "En eDreams, elige el regreso AV 9, sale 1:35 am, desde 316 USD."
    assert precios.guia_tiquete(None) is None


def test_la_pagina_de_envio_muestra_la_guia_el_aviso_y_un_solo_boton():
    from app.api_v1 import comun
    r = comun.pagina_envio({"url": CLK, "campos": [("u", "IDA-COPA-SECRETA")], "vendedor": "eDreams",
                                       "aviso": "Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD",
                                       "tiquete": {"vendedor": "eDreams", "tramo": "regreso", "numeros": ["AV 9"],
                                                   "sale": "2026-11-29 01:35", "tarifa": "Tarifa", "precio": 316}})
    pagina = r.body.decode()
    assert "En eDreams, elige el regreso AV 9, sale 1:35 am, desde 316 USD." in pagina
    assert "Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD" in pagina
    assert "puede pedir una verificación" in pagina and pagina.count("<button") == 1
    assert '<button type="submit">Ir a eDreams</button>' in pagina and "<script" not in pagina
    assert r.headers["Cache-Control"] == "no-store" and "form-action https:" in r.headers["Content-Security-Policy"]


# ---------- ronda 1 de la pieza 6 ----------
def test_post_ir_devuelve_la_guia(piloto, con_regreso, analizador_doble):
    """La página que abre «Ir a…» (`GET …/ir`) recibe la guía por `POST …/ir`: qué vuelo elegir en el vendedor."""
    c = _cotizacion(piloto)
    e = _ir(piloto, c["id"], c["vuelos"][0]["id"], "COPA", "ida").json()
    assert e["camino"] == "buscador"
    assert e["guia"].startswith("En COPA, elige CM 687 · CM 240")


def test_por_google_flights_no_hay_guia(piloto, con_regreso, analizador_doble):
    respuesta_buscador, _ = con_regreso
    respuesta_buscador["datos"] = {"booking_options": []}
    c = _cotizacion(piloto)
    e = _ir(piloto, c["id"], c["vuelos"][0]["id"], "COPA", "ida").json()
    assert (e["camino"], e["guia"]) == ("google", None)


MAL = '<img src=x onerror=alert(1)>'


def test_la_pagina_de_envio_escapa_todo_lo_que_viene_de_afuera():
    from app.api_v1 import comun
    r = comun.pagina_envio({"url": CLK + '"><script>x()</script>', "campos": [('a"><b', MAL)], "vendedor": MAL,
                                       "aviso": MAL, "tiquete": {"vendedor": MAL, "tramo": "ida",
                                                                 "numeros": [MAL, "</p><script>1</script>"],
                                                                 "sale": "2026-11-20 12:40<script>", "tarifa": MAL, "precio": 1}})
    p = r.body.decode()
    assert "<img" not in p and "<script" not in p and "<b" not in p.replace("<body", "").replace("<button", ""), p


def test_lo_del_buscador_llega_escapado_a_la_pagina_de_envio(piloto, con_regreso):
    from app.api_v1 import comun
    from app.servicios import cotizacion
    respuesta, _ = con_regreso
    respuesta["datos"] = {"booking_options": [{"together": {**tiquete(MAL, 458, [MAL], "JUNTA"), "option_title": MAL}}]}
    c = _cotizacion(piloto)
    d = cotizacion.enlace_vendedor(_yo(), c["id"], c["vuelos"][0]["id"])
    assert d["tipo"] == "envio"
    assert "<img" not in comun.pagina_envio(d).body.decode()


def test_el_pedido_no_deja_rastro(piloto, con_regreso, analizador_doble, capfd, caplog):
    caplog.set_level(logging.DEBUG)
    respuesta, carpeta = con_regreso
    respuesta["datos"] = separados("eDreams", 316, regreso_aerolinea=False)
    c = _cotizacion(piloto)
    for v, t in (("COPA", "ida"), ("Avianca", "regreso"), ("eDreams", "regreso")):
        assert _ir(piloto, c["id"], c["vuelos"][0]["id"], v, t).status_code == 200
    todo = ""
    for tabla in ("busquedas", "eventos", "consultas_buscador", "analisis_vuelo", "clics_fuente", "cupos_buscador"):
        todo += json.dumps(db.todos(f"select * from {tabla}"), default=str)
    todo += "".join(p.read_text(errors="ignore") for p in carpeta.rglob("*") if p.is_file())
    salida = capfd.readouterr()
    todo += salida.out + salida.err + caplog.text
    for x in ("IDA-COPA-SECRETA", "REGRESO-SECRETA", "booking_request", "post_data"):
        assert x not in todo, x


def test_el_cambio_de_vendedor_que_ve_la_pagina_llega_al_motivo(piloto, con_regreso, analizador_doble):
    respuesta_buscador, _ = con_regreso
    respuesta_buscador["datos"] = {"booking_options": []}
    _, respuesta = analizador_doble
    respuesta.update(estado="fallido", motivo="Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD",
                     vendedor_actual={"vendedor": "eDreams", "precio": 316.0})
    c = _cotizacion(piloto)
    e = _ir(piloto, c["id"], c["vuelos"][0]["id"], "Avianca", "regreso").json()
    assert e["camino"] == "google" and e["motivo"].startswith("Avianca ya no vende"), e


def test_la_guia_empieza_con_el_aviso_si_cambio_el_vendedor(piloto, con_regreso, analizador_doble):
    """Mientras la página de «Ir a…» no pinte el `motivo`, el cambio de vendedor tiene que verse en la guía."""
    respuesta, _ = con_regreso
    respuesta["datos"] = separados("eDreams", 316, regreso_aerolinea=False)
    c = _cotizacion(piloto)
    e = _ir(piloto, c["id"], c["vuelos"][0]["id"], "Avianca", "regreso").json()
    assert e["guia"] == ("Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD. "
                         "En eDreams, elige el regreso AV 9, desde 316 USD.")


def _avianca_con_enlace_fuera_de_la_lista_blanca() -> dict:
    d = separados()
    d["booking_options"][0]["returning"]["booking_request"]["url"] = "https://evil.example/clk"
    d["booking_options"].append({"separate_tickets": True, "departing": tiquete("COPA", 334, ["CM 687"], "X"),
                                 "returning": tiquete("eDreams", 316, ["AV 9"], "Y", False)})
    return d


def test_un_enlace_fuera_de_la_lista_blanca_no_es_cambio_de_vendedor(buscador):
    """Avianca sí vende el regreso, pero su enlace no pasa la lista blanca: no se dice que «ya no vende» ni se lleva a
    otro vendedor; se sigue por el camino siguiente (la página), que pide Avianca."""
    respuesta, _ = buscador
    respuesta["datos"] = _avianca_con_enlace_fuera_de_la_lista_blanca()
    assert precios.elegir_tiquete(_en_vivo(), "Avianca", "regreso") == (None, None)


def test_con_el_enlace_no_valido_ir_a_sigue_por_la_pagina_con_el_vendedor_pedido(piloto, con_regreso, analizador_doble):
    respuesta_buscador, _ = con_regreso
    respuesta_buscador["datos"] = _avianca_con_enlace_fuera_de_la_lista_blanca()
    pedidos, respuesta = analizador_doble
    respuesta.update(estado="listo", url=CLK, cuerpo="u=DE-LA-PAGINA")
    c = _cotizacion(piloto)
    e = _ir(piloto, c["id"], c["vuelos"][0]["id"], "Avianca", "regreso").json()
    assert (e["camino"], e["vendedor"], e["motivo"]) == ("pagina", "Avianca", None)
    assert [p["vendedor"] for p in pedidos] == ["Avianca"]


# ---------- integración (16 nov), hallazgo de la prueba 15: la guía separa la ida y el regreso ----------
IDA_AA = {"numeros": ["AA 1851"], "sale": "2026-12-08 09:48", "hasta": "LAS"}
REGRESO_AA = {"numeros": ["AA 3321"], "sale": "2026-12-11 23:06"}


def test_la_guia_del_itinerario_completo_separa_ida_y_regreso():
    t = precios.tiquete({"tramo": "ambos", "vendedor": "American", "tarifa": "Main Cabin", "precio": 694,
                         "numeros": ["AA 1851", "AA 3321"]}, IDA_AA, REGRESO_AA)
    assert precios.vuelos_a_elegir(t) == "la ida AA 1851, sale 9:48 am, y el regreso AA 3321, sale 11:06 pm"
    assert precios.guia_tiquete(t) == ("En American, elige la ida AA 1851, sale 9:48 am, y el regreso AA 3321, "
                                       "sale 11:06 pm; Main Cabin desde 694 USD.")


def test_sin_el_regreso_la_guia_del_itinerario_completo_queda_como_antes():
    t = precios.tiquete({"tramo": "ambos", "vendedor": "American", "tarifa": "Main Cabin", "precio": 694,
                         "numeros": ["AA 1851", "AA 3321"]}, IDA_AA, None)
    assert precios.guia_tiquete(t) == "En American, elige AA 1851 · AA 3321, sale 9:48 am, Main Cabin desde 694 USD."


def test_un_tiquete_de_billetes_separados_nombra_solo_su_tramo():
    ida = precios.tiquete({"tramo": "ida", "vendedor": "COPA", "precio": 334, "numeros": ["CM 687", "CM 240"]},
                          {"numeros": ["CM 687", "CM 240"], "sale": "2026-11-20 12:40"}, {"numeros": ["AV 9"], "sale": "2026-11-29 01:35"})
    vuelta = precios.tiquete({"tramo": "regreso", "vendedor": "eDreams", "precio": 316, "numeros": ["AV 9"]},
                             {"numeros": ["CM 687", "CM 240"], "sale": "2026-11-20 12:40"}, {"numeros": ["AV 9"], "sale": "2026-11-29 01:35"})
    assert precios.vuelos_a_elegir(ida) == "CM 687 · CM 240, sale 12:40 pm"
    assert precios.vuelos_a_elegir(vuelta) == "el regreso AV 9, sale 1:35 am"


def test_las_opciones_guardadas_dicen_que_vuelos_elegir(buscador, monkeypatch):
    monkeypatch.setattr(precios, "regreso_guardado", lambda *a, **k: {"numeros": ["AV 9"], "sale": "2026-11-29 01:35"})
    _en_vivo()
    vuelo = {**IDA, "sale": "2026-11-20 12:40"}
    tarifas, _ = precios.opciones_guardadas(vuelo, "MDE", "MIA", "2026-11-20", "2026-11-29")
    assert [(t["nombre"], t["elige"]) for t in tarifas] == [
        ("ida", "CM 687 · CM 240, sale 12:40 pm"), ("regreso", "el regreso AV 9, sale 1:35 am")]


def test_la_api_de_opciones_del_buscador_dice_que_vuelos_elegir(piloto, con_regreso, monkeypatch):
    """GET …/reserva lleva `elige` en cada tarifa: la web lo muestra bajo los botones «Ir a…»."""
    from app.servicios import cotizacion
    monkeypatch.setattr(precios, "regreso_guardado", lambda *a, **k: {"numeros": ["AV 9"], "sale": "2026-11-29 01:35"})
    c = _cotizacion(piloto)
    vuelo = c["vuelos"][0]
    cotizacion.enlace_vendedor(_yo(), c["id"], vuelo["id"], vendedor="COPA", tarifa="ida")   # guarda las opciones
    r = piloto.get(f"/api/v1/cotizaciones/{c['id']}/vuelos/{vuelo['id']}/reserva")
    assert r.status_code == 200, r.text
    assert [(t["nombre"], t["elige"]) for t in r.json()["tarifas"]][-1] == ("regreso", "el regreso AV 9, sale 1:35 am")
