"""El analizador con Chromium de verdad y sin red: las direcciones de Google las responde la página de ejemplo.

Corre dentro de la etapa `pruebas` de la imagen del analizador (tiene Playwright y pytest):
    docker build --target pruebas -t analizador-pruebas analizador
    docker run --rm --network none --shm-size 1g analizador-pruebas python -m pytest -q analizador/pruebas
"""
import base64
from pathlib import Path

import pytest

from analizador import lector, navegador

EJEMPLO = Path(__file__).resolve().parent.parent / "ejemplo"
URL = "https://www.google.com/travel/flights?hl=en&gl=us&curr=USD&tfs=prueba"


def _servir(paginas: dict[str, str], pedidos: list[str]):
    """Responde cada dirección de google.com con un archivo de ejemplo; cualquier otra petición se corta (sin red)."""
    def registrar(pagina):
        def atender(ruta):
            url = ruta.request.url
            for inicio, archivo in paginas.items():
                if url.startswith(inicio):
                    pedidos.append(url)
                if url.startswith(inicio) and archivo.startswith("302 "):
                    return ruta.fulfill(status=302, headers={"Location": archivo.removeprefix("302 ")})
                if url.startswith(inicio):
                    return ruta.fulfill(status=200, content_type="text/html; charset=utf-8",
                                        body=(EJEMPLO / archivo).read_text(encoding="utf-8"))
            # una navegación desconocida pasa a la lista blanca del analizador; lo demás se corta (sin red)
            return ruta.fallback() if ruta.request.is_navigation_request() else ruta.abort()
        pagina.route("**/*", atender)
    return registrar


def test_lee_la_reserva_y_guarda_la_captura():
    pedidos = []
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/travel/flights": "reserva.html"}, pedidos))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["precio_total"] == 619 and r["datos"]["vendedores"][0]["vendedor"] == "American"
    assert [t["nombre"] for t in r["datos"]["tarifas"]][:2] == ["Basic Economy", "Main Cabin"]
    assert base64.b64decode(r["captura_png_b64"]).startswith(b"\x89PNG")
    assert r["agente"] == navegador.AGENTE and "AnalizadorDePrecios" in r["agente"] and r["duracion_ms"] > 0
    assert all(p.startswith("https://www.google.com/") for p in pedidos)


def test_en_la_lista_de_regresos_elige_el_mas_barato_y_llega_a_la_reserva():
    paginas = {"https://www.google.com/travel/flights/reserva": "reserva.html",
               "https://www.google.com/travel/flights?": "regresos.html"}
    r = navegador.analizar(URL, servir=_servir(paginas, []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["regreso_elegido"]["precio"] == 564 and r["datos"]["tarifas"]
    assert r["url_final"] == "https://www.google.com/travel/flights/reserva"


def test_tolera_que_la_pagina_cambie_de_direccion_mientras_carga():
    paginas = {"https://www.google.com/travel/flights/reserva": "reserva.html",
               "https://www.google.com/travel/flights?": "recarga.html"}
    r = navegador.analizar(URL, servir=_servir(paginas, []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["precio_total"] == 619


def test_si_no_aparecen_los_precios_falla_con_evidencia():
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/": "sin_precios.html"}, []), espera_ms=1500)
    assert (r["estado"], r["motivo"]) == ("fallido", "la página tardó demasiado en mostrar los precios")
    assert base64.b64decode(r["captura_png_b64"]).startswith(b"\x89PNG")
    assert r["extracto"].startswith("Something went wrong")


def test_la_lista_sin_precios_todavia_no_cuenta_como_cargada():
    """Lo que vio la prueba 3 contra Google: el título de la lista llega antes que los resultados."""
    paginas = {"https://www.google.com/travel/flights/reserva": "reserva.html",
               "https://www.google.com/travel/flights?": "regresos_tardios.html"}
    r = navegador.analizar(URL, servir=_servir(paginas, []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["regreso_elegido"]["precio"] == 564 and r["datos"]["tarifas"]


def test_elige_el_regreso_aunque_la_fila_tape_la_etiqueta():
    """Lo que vio la prueba 5 contra Google: la fila clicable intercepta el clic sobre el elemento con la etiqueta."""
    paginas = {"https://www.google.com/travel/flights/reserva": "reserva.html",
               "https://www.google.com/travel/flights?": "regresos_tapados.html"}
    r = navegador.analizar(URL, servir=_servir(paginas, []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["datos"]["regreso_elegido"]["precio"] == 564 and r["datos"]["tarifas"]


def test_la_pagina_siempre_se_pide_en_ingles_ee_uu_y_dolares():
    pedidos = []
    navegador.analizar("https://www.google.com/travel/flights?tfs=prueba&hl=es&curr=EUR",
                       servir=_servir({"https://www.google.com/travel/flights": "reserva.html"}, pedidos))
    assert pedidos[0] == "https://www.google.com/travel/flights?hl=en&gl=us&curr=USD&tfs=prueba"


def test_toda_la_lectura_respeta_el_plazo_total():
    import time
    inicio = time.monotonic()
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/": "sin_precios.html"}, []), espera_ms=60_000,
                           presupuesto_ms=3_000)
    assert (r["estado"], r["motivo"]) == ("fallido", "la página tardó demasiado en mostrar los precios")
    assert time.monotonic() - inicio < 8   # el arranque del navegador incluido


# ---------- ronda 1 · punto 2: lista blanca completa ----------
@pytest.mark.parametrize("paginas, motivo", [
    ({"https://www.google.com/travel/flights?": "302 https://otro.example/oferta"}, navegador.OTRO_SITIO),
    ({"https://www.google.com/travel/flights?": "a_otro_sitio.html"}, navegador.OTRO_SITIO),
    ({"https://www.google.com/travel/flights?": "302 https://www.google.com/search?q=vuelos"}, navegador.OTRO_SITIO),
    ({"https://www.google.com/travel/flights?": "consentimiento.html"}, lector.CONSENTIMIENTO),
    ({"https://www.google.com/travel/flights/reserva": "reserva.html",
      "https://www.google.com/travel/flights?": "regresos_otra_pestana.html"}, navegador.OTRA_PESTANA),
])
def test_salir_de_la_lista_blanca_termina_en_fallido_sin_captura(paginas, motivo):
    pedidos = []
    r = navegador.analizar(URL, servir=_servir(paginas, pedidos), espera_ms=4000)
    assert (r["estado"], r["motivo"]) == ("fallido", motivo), r
    assert r["captura_png_b64"] is None and r["datos"] is None
    assert all(p.startswith("https://www.google.com/travel/") for p in pedidos)   # solo se sirvió lo de la lista blanca


# ---------- ronda 1 · punto 14: la respuesta de Lambda no pasa de 6 MB ----------
def test_la_captura_de_una_pagina_muy_alta_queda_acotada():
    import json
    import struct
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/travel/flights": "reserva_larga.html"}, []))
    assert r["estado"] == "listo", r["motivo"]
    png = base64.b64decode(r["captura_png_b64"])
    ancho, alto = struct.unpack(">II", png[16:24])
    assert ancho == 1280 and alto <= navegador.ALTO_CAPTURA
    assert len(json.dumps(r).encode()) < navegador.TOPE_RESPUESTA


def test_una_verificacion_no_se_resuelve():
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/": "verificacion.html"}, []))
    assert (r["estado"], r["motivo"]) == ("fallido", lector.VERIFICACION) and r["captura_png_b64"] is None


@pytest.mark.parametrize("url", ["https://example.com/travel/flights", "https://www.google.com/search?q=vuelos"])
def test_no_abre_nada_fuera_de_google_flights(url):
    r = navegador.analizar(url)
    assert (r["estado"], r["motivo"]) == ("fallido", "el enlace no es de Google Flights")


def test_apagado_no_abre_nada(monkeypatch):
    monkeypatch.setenv("ANALIZADOR", "apagado")
    assert navegador.analizar(URL)["motivo"] == "el analizador está apagado"


def test_una_lectura_a_la_vez():
    navegador._turno.acquire()
    try:
        assert navegador.analizar(URL)["motivo"].startswith("el analizador está leyendo otra página")
    finally:
        navegador._turno.release()


# ---------- pieza 3b: todas las opciones e «Ir a…» ----------
COMPLETA = {"https://www.google.com/travel/flights/reserva": "reserva_completa.html",
            "https://www.google.com/travel/flights?": "regresos.html"}


def test_elige_el_mismo_regreso_de_la_cotizacion():
    r = navegador.analizar(URL, servir=_servir(dict(COMPLETA), []), regreso={"sale": "1:43 PM", "aerolinea": "American"})
    assert r["estado"] == "listo", r["motivo"]
    elegido = r["datos"]["regreso_elegido"]
    assert (elegido["precio"], elegido["sale"], elegido["elegido_por"]) == (619, "1:43 PM", "cotizacion")
    # sin ese regreso en la página, el más barato, y lo dice
    r = navegador.analizar(URL, servir=_servir(dict(COMPLETA), []), regreso={"sale": "7:00 AM", "aerolinea": "Delta"})
    assert (r["datos"]["regreso_elegido"]["precio"], r["datos"]["regreso_elegido"]["elegido_por"]) == (564, "precio")


def test_despliega_y_lee_todos_los_vendedores_y_tarifas():
    r = navegador.analizar(URL, servir=_servir(dict(COMPLETA), []))
    assert r["estado"] == "listo", r["motivo"]
    d = r["datos"]
    assert [v["vendedor"] for v in d["vendedores"]] == ["American", "Expedia", "Priceline"]
    assert [(t["vendedor"], t["nombre"], t["precio"]) for t in d["tarifas"]] == [
        ("American", "Basic Economy", 619), ("American", "Main Cabin", 1014), ("Expedia", "Economy", 612),
        ("Priceline", "Economy", 615)]


@pytest.mark.parametrize("vendedor, tarifa, cuerpo", [("American", "Main Cabin", "u=AA-MAIN-UNSOLOUSO"),
                                                       ("Expedia", "Economy", "u=EXP-ECO-UNSOLOUSO")])
def test_ir_a_devuelve_el_envio_de_esa_tarifa_sin_mandarlo(vendedor, tarifa, cuerpo):
    pedidos = []
    r = navegador.ir_a(URL, vendedor, tarifa, servir=_servir(dict(COMPLETA), pedidos))
    assert r["estado"] == "listo", r["motivo"]
    assert r["url"].startswith("https://www.google.com/travel/clk/f") and r["cuerpo"].startswith(cuerpo)
    assert base64.b64decode(r["captura_previa_png_b64"]).startswith(b"\x89PNG")
    assert (r["vendedor"], r["tarifa"]) == (vendedor, tarifa)
    assert not any("/travel/clk" in p for p in pedidos)          # la petición nunca salió del navegador del servidor


def test_ir_a_una_tarifa_que_no_esta_falla_con_evidencia():
    r = navegador.ir_a(URL, "American", "First", servir=_servir(dict(COMPLETA), []))
    assert (r["estado"], r["motivo"], r.get("cuerpo")) == ("fallido", navegador.SIN_TARIFA, None)
    # lo que se vio: captura, comienzo del texto y el regreso que se eligió, para saber por qué
    assert base64.b64decode(r["captura_png_b64"]).startswith(b"\x89PNG") and "Booking options" in r["extracto"]
    assert r["regreso_elegido"]["precio"] == 564


# ---------- prueba en vivo de «Ir a…» (13 nov): lo que la hizo fallar ----------
def test_ir_a_con_una_hora_de_regreso_que_no_esta_elige_el_mas_barato():
    r = navegador.ir_a(URL, "American", "Main Cabin", servir=_servir(dict(COMPLETA), []),
                       regreso={"sale": "1:43 PM", "aerolinea": "Delta"})
    assert r["estado"] == "listo", r["motivo"]
    assert (r["regreso_elegido"]["precio"], r["regreso_elegido"]["elegido_por"]) == (564, "precio")


def test_ir_a_sin_regreso_que_elegir_lo_dice_con_evidencia():
    r = navegador.ir_a(URL, "American", "Main Cabin",
                       servir=_servir({"https://www.google.com/travel/flights?": "regresos_sin_etiquetas.html"}, []))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.SIN_REGRESO)
    assert base64.b64decode(r["captura_png_b64"]).startswith(b"\x89PNG") and "Returning flights" in r["extracto"]


def test_ir_a_reserva_tiempo_para_sus_pasos_y_una_lista_lenta_dice_que_tardo():
    """Con 10 s de plazo, «ir a» espera la lista a lo sumo la mitad: si tarda más, lo dice (no «no se encontró la tarifa»)."""
    r = navegador.ir_a(URL, "American", "Main Cabin", presupuesto_ms=10_000,
                       servir=_servir({"https://www.google.com/travel/flights?": "regresos_lentos.html"}, []))
    assert (r["estado"], r["motivo"]) == ("fallido", "la página tardó demasiado en mostrar los precios")
    assert r["duracion_ms"] < 9_000 and r["captura_png_b64"]



def test_ir_a_con_redireccion_a_otro_dominio_falla():
    r = navegador.ir_a(URL, "American", "Main Cabin",
                       servir=_servir({"https://www.google.com/travel/flights?": "302 https://otro.example/x"}, []))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.OTRO_SITIO)


def test_ir_a_solo_acepta_vendedor_y_tarifa_razonables():
    assert navegador.ir_a(URL, "", "Main Cabin")["estado"] == "fallido"
    assert navegador.ir_a(URL, "American" * 20, "Main Cabin")["estado"] == "fallido"


def test_el_servidor_y_lambda_atienden_las_dos_acciones(monkeypatch):
    from analizador import lambda_handler, servidor
    vistos = []
    monkeypatch.setattr(navegador, "analizar", lambda url, **k: vistos.append(("leer", url, k["regreso"])) or {"estado": "listo"})
    monkeypatch.setattr(navegador, "ir_a", lambda url, v, t, **k: vistos.append(("ir_a", url, v, t)) or {"estado": "listo"})
    servidor.atender({"url": URL, "regreso": {"sale": "1:43 PM"}})
    lambda_handler.handler({"accion": "ir_a", "url": URL, "vendedor": "American", "tarifa": "Main Cabin"}, None)
    assert vistos == [("leer", URL, {"sale": "1:43 PM"}), ("ir_a", URL, "American", "Main Cabin")]


# ---------- ronda 1 · punto 7: el servidor interno no se rompe con un Content-Length raro ----------
@pytest.mark.parametrize("largo, estado", [("abc", 400), ("-5", 400), ("99999", 413), ("2", 200)])
def test_un_content_length_invalido_es_400(largo, estado):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    from analizador import servidor
    s = ThreadingHTTPServer(("127.0.0.1", 0), servidor.Manejador)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", s.server_address[1], timeout=5)
        c.putrequest("POST", "/analizar")
        c.putheader("Content-Length", largo)
        c.endheaders()
        c.send(b"{}")
        assert c.getresponse().status == estado
    finally:
        s.shutdown()


# ---------- ronda 1 · punto 5: el motivo es una frase fija; el detalle del error, solo al registro ----------
def test_el_motivo_no_lleva_el_detalle_interno_del_navegador(capsys):
    r = navegador.analizar(URL, servir=_servir({}, []))          # sin red: la página no abre
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.NO_ABRIO)
    assert "net::" in capsys.readouterr().out                     # el detalle queda en el registro del analizador


def test_un_fallo_inesperado_tiene_motivo_fijo(monkeypatch, capsys):
    def roto(*a, **k):
        raise RuntimeError("detalle interno con /ruta/del/servidor")

    monkeypatch.setattr(navegador, "_leer", roto)
    r = navegador.analizar(URL)
    assert r["motivo"] == navegador.ERROR_NAVEGADOR and "/ruta/del/servidor" not in r["motivo"]
    assert "/ruta/del/servidor" in capsys.readouterr().out


# ---------- ronda 2 · punto 3: sin service workers, ninguna navegación esquiva la lista blanca ni la intercepción ----------
def test_el_contexto_bloquea_los_service_workers():
    assert navegador.OPCIONES_CONTEXTO["service_workers"] == "block"
    assert navegador.OPCIONES_CONTEXTO["user_agent"] == navegador.AGENTE


# ---------- ronda 2 · punto 4: una redirección al envío no sale del navegador ----------
@pytest.mark.parametrize("accion", ["leer", "ir_a"])
def test_una_redireccion_a_travel_clk_se_corta_en_el_navegador(accion):
    """Las rutas de Playwright no ven las redirecciones: sin el corte propio, el GET a /travel/clk saldría a la red."""
    fallos = []
    base = _servir({"https://www.google.com/travel/flights?": "302 https://www.google.com/travel/clk/f?u=REDIR"}, [])

    def servir(pagina):
        pagina.on("requestfailed", lambda q: fallos.append((q.url, q.failure or "")))
        base(pagina)
    r = (navegador.analizar(URL, servir=servir) if accion == "leer"
         else navegador.ir_a(URL, "American", "Main Cabin", servir=servir))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.OTRO_SITIO)
    assert not r.get("cuerpo") and not r.get("captura_png_b64")
    assert any("BLOCKED_BY_CLIENT" in f for _, f in fallos), fallos            # se cortó en el navegador
    assert not any("/travel/clk" in u and "INTERNET_DISCONNECTED" in f for u, f in fallos)   # nunca intentó salir


# ---------- ronda 2 · punto 5: el clic va a la tarifa pedida aunque la página cambie entre leer y pulsar ----------
def test_ir_a_pulsa_la_tarifa_por_su_etiqueta_aunque_la_pagina_cambie(monkeypatch):
    real = navegador._etiquetas

    def y_cambia(pagina):
        leidas = real(pagina)
        # justo después de leer, la página añade un elemento con etiqueta al comienzo: los índices se corren uno
        pagina.evaluate("""() => { const b = document.createElement('button'); b.setAttribute('aria-label', 'Nuevo aviso');
                                   document.body.prepend(b); }""")
        return leidas
    monkeypatch.setattr(navegador, "_etiquetas", y_cambia)
    r = navegador.ir_a(URL, "American", "Main Cabin", servir=_servir(dict(COMPLETA), []))
    assert r["estado"] == "listo", r["motivo"]
    assert r["cuerpo"].startswith("u=AA-MAIN-UNSOLOUSO")      # el de Main Cabin, no el botón de al lado


def test_la_etiqueta_con_comillas_se_busca_tal_cual():
    assert navegador._selector_etiqueta('Continue to book with "A", B') == '[aria-label="Continue to book with \\"A\\", B"]'
    assert navegador._selector_etiqueta("a\\b") == '[aria-label="a\\\\b"]'


# ---------- producción, cotización 12 y prueba 12: billetes separados, un «Ir a…» por tiquete ----------
SEPARADOS = {"https://www.google.com/travel/flights?": "billetes_separados.html"}


def test_la_lectura_con_billetes_separados_abre_el_dialogo_y_lee_cada_tiquete():
    r = navegador.analizar(URL, servir=_servir(dict(SEPARADOS), []))
    assert r["estado"] == "listo", r["motivo"]
    d = r["datos"]
    assert d["billetes_separados"] is True
    assert [(t["vendedor"], t["nombre"], t["precio"]) for t in d["tarifas"]] == [("COPA", "ida", 334.0), ("Avianca", "regreso", 323.0)]
    assert d["por_telefono"][0]["telefono"] == "1 (786) 840-2672"


@pytest.mark.parametrize("vendedor, tramo, cuerpo", [("COPA", "ida", "u=COPA-IDA-UNSOLOUSO"),
                                                     ("Avianca", "regreso", "u=AVIANCA-REGRESO-UNSOLOUSO")])
def test_ir_a_cada_aerolinea_por_su_tiquete_sin_mandarlo(vendedor, tramo, cuerpo):
    pedidos = []
    r = navegador.ir_a(URL, vendedor, tramo, servir=_servir(dict(SEPARADOS), pedidos))
    assert r["estado"] == "listo", r["motivo"]
    assert r["url"].startswith("https://www.google.com/travel/clk/f") and r["cuerpo"].startswith(cuerpo)
    assert (r["vendedor"], r["tarifa"]) == (vendedor, tramo)
    assert not any("/travel/clk" in p for p in pedidos)          # el envío no salió del navegador del servidor


def test_si_otro_vendedor_lleva_el_tramo_ir_a_lo_dice_y_no_pulsa():
    """Google cambia el vendedor de un tramo entre cargas (14 nov: el regreso de Avianca pasó a eDreams)."""
    pedidos = []
    r = navegador.ir_a(URL, "eDreams", "regreso", servir=_servir(dict(SEPARADOS), pedidos))
    assert (r["estado"], r["motivo"]) == ("fallido", "eDreams ya no vende este tramo; ahora lo vende Avianca a 323 USD")
    assert r["vendedor_actual"] == {"vendedor": "Avianca", "precio": 323.0}
    assert not any("/travel/clk" in p for p in pedidos)


def test_ir_a_con_billetes_separados_sin_tramo_no_pulsa():
    pedidos = []
    r = navegador.ir_a(URL, "COPA", "Main Cabin", servir=_servir(dict(SEPARADOS), pedidos))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.SIN_TARIFA)
    assert not any("/travel/clk" in p for p in pedidos)


def test_la_captura_completa_del_tiquete_trae_el_envio():
    r = navegador.captura_vuelo(URL, "Avianca", "regreso", servir=_servir(dict(SEPARADOS), []))
    assert r["estado"] == "listo" and r["envio"]["cuerpo"].startswith("u=AVIANCA-REGRESO"), r.get("motivo_envio")
    assert "Purchase separate tickets" in r["texto"]


def test_continuar_reconoce_la_marca_airline_y_no_confunde_la_opcion_de_dos_tiquetes():
    assert navegador._es_continuar("Continue to book with COPA airline for 334 US dollars (Equivalent to 1102610 Colombian pesos)",
                                   "COPA", "Tarifa")
    assert not navegador._es_continuar("Continue to book with COPA, Avianca airline for 657 US dollars. The 2 tickets…",
                                       "COPA", "Avianca airline")
    assert navegador._es_continuar("Continue to book with American, Main Cabin for 1014 US dollars", "American", "Main Cabin")


# ---------- prueba 13: la página de error de Google («Oops, something went wrong») ----------
def test_la_pagina_de_error_de_google_falla_enseguida_con_su_motivo():
    pedidos = []
    r = navegador.analizar(URL, servir=_servir({"https://www.google.com/travel/flights?": "sin_resultados.html"}, pedidos))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.SIN_RESULTADOS)
    assert r["duracion_ms"] < 15_000                                 # no espera a que se agote el plazo
    assert "Oops, something went wrong" in r["extracto"]
    r = navegador.ir_a(URL, "COPA", "ida", servir=_servir({"https://www.google.com/travel/flights?": "sin_resultados.html"}, []))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.SIN_RESULTADOS)


def _servir_con_error(veces_error: int, cargas: list):
    """Google responde la página de error las primeras `veces_error` cargas y después la reserva completa."""
    def registrar(pagina):
        def atender(ruta):
            url = ruta.request.url
            if url.startswith("https://www.google.com/travel/flights?") and ruta.request.is_navigation_request():
                cargas.append(url)
                archivo = "sin_resultados.html" if len(cargas) <= veces_error else "reserva_completa.html"
                return ruta.fulfill(status=200, content_type="text/html; charset=utf-8",
                                    body=(EJEMPLO / archivo).read_text(encoding="utf-8"))
            return ruta.fallback() if ruta.request.is_navigation_request() else ruta.abort()
        pagina.route("**/*", atender)
    return registrar


def test_con_la_pagina_de_error_reintenta_una_vez_con_reload_y_lee():
    cargas = []
    r = navegador.analizar(URL, servir=_servir_con_error(1, cargas))
    assert r["estado"] == "listo", r["motivo"]
    assert len(cargas) == 2 and r["datos"]["tarifas"]


def test_nunca_mas_de_un_reintento():
    cargas = []
    r = navegador.analizar(URL, servir=_servir_con_error(5, cargas))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.SIN_RESULTADOS)
    assert len(cargas) == 2                                          # la carga y un solo «Reload»


def test_el_error_de_google_despues_de_elegir_el_regreso_tambien_se_reconoce():
    """Prueba 13, Avianca: la lista de regresos cargó, y al elegir el regreso Google mostró su página de error."""
    paginas = {"https://www.google.com/travel/flights/reserva": "sin_resultados.html",
               "https://www.google.com/travel/flights?": "regresos.html"}
    r = navegador.ir_a(URL, "Avianca", "regreso", servir=_servir(dict(paginas), []))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.SIN_RESULTADOS)
    assert r["duracion_ms"] < 20_000                                 # no espera los 45 s
    r = navegador.analizar(URL, servir=_servir(dict(paginas), []))
    assert (r["estado"], r["motivo"]) == ("fallido", navegador.SIN_RESULTADOS)
