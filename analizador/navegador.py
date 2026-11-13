"""Abre una página de Google Flights con Playwright, espera a que muestre los precios y devuelve lo visible.

Límites, a propósito:
- agente de usuario honesto: dice que es un navegador sin pantalla y para qué lee;
- solo navega dentro de `https://www.google.com/travel/flights` (y la misma página de Google si pide verificación);
- no resuelve verificaciones ni acepta condiciones: si aparecen, queda `fallido` con el motivo;
- nunca inicia sesión, ni escribe en campos, ni acepta condiciones. Sus únicos clics: elegir el regreso (el de la
  cotización si está en la página; si no, el más barato) para llegar a las opciones de reserva, desplegar «Other
  booking options» y las tarifas de cada vendedor, y, solo en «ir a», el «Continue» de la tarifa pedida;
- «ir a» intercepta el envío que Google arma al pulsar «Continue» (POST a `/travel/clk`), lo corta sin que salga del
  servidor y lo devuelve una sola vez para que el navegador de la persona lo haga;
- una lectura a la vez; con `ANALIZADOR=apagado` no abre nada.
"""
import base64
import os
import re
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import lector

AGENTE = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/130.0 Safari/537.36 "
          "AnalizadorDePrecios/1.0 (lectura bajo demanda de una página pública para verificar un precio cotizado)")
PRESUPUESTO_MS = 45_000     # toda la lectura (abrir, esperar, elegir el regreso, leer y capturar) en el minuto de la función
ESPERA_MS = 45_000          # tope de cada espera de precios; cada paso descuenta del presupuesto total
EN_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
# En Lambda no hay /dev/shm grande ni varios procesos: Chromium corre en uno solo
ARGUMENTOS = ["--disable-gpu", "--disable-dev-shm-usage", "--single-process", "--no-zygote"] if EN_LAMBDA else []
# Una lista cuenta como cargada solo con precios a la vista: el título «Returning flights» sale antes que los resultados
LISTO = re.compile(r"Booking options[\s\S]*\$\d|(Returning|Departing) flights[\s\S]*\$\d|unusual traffic|not a robot|"
                   r"Before you continue")
PARAMETROS_FIJOS = {"hl": "en", "gl": "us", "curr": "USD"}   # lo que sabe leer el lector: inglés, EE. UU. y dólares
RESERVA = re.compile(r"Booking options[\s\S]*\$\d")

ALTO_CAPTURA = 4000          # px: la reserva entera cabe; lo de más abajo (historia de precios) no hace falta
TOPE_CAPTURA = 3_000_000     # bytes en base64: con los datos, la respuesta queda bajo 4 MB
TOPE_RESPUESTA = 4_000_000
OTRO_SITIO = "la página llevó a otro sitio"
SIN_TARIFA = "no se encontró la tarifa"
SIN_ENVIO = "Google no respondió al elegir la tarifa"
CONTINUAR = re.compile(r"^Continue to book with (?P<vendedor>.+?)(?:, (?P<tarifa>.+?))? for [\d,.]+ US dollars")
VENDEDOR_O_TARIFA = re.compile(r"^[\w .,&'()+/-]{1,60}$")
OTRA_PESTANA = "la página quiso abrir otra pestaña"

_turno = threading.Lock()


def _resultado(estado: str, inicio: float, motivo: str | None = None, **extra) -> dict:
    return {"estado": estado, "motivo": motivo, "datos": None, "captura_png_b64": None, "url_final": None,
            "agente": AGENTE, "duracion_ms": int((time.monotonic() - inicio) * 1000), **extra}


def analizar(url: str, *, elegir_regreso: bool = True, servir=None, espera_ms: int = ESPERA_MS,
             presupuesto_ms: int = PRESUPUESTO_MS, regreso: dict | None = None) -> dict:
    """{"estado": "listo" | "fallido", "motivo", "datos" (lo leído), "captura_png_b64", "url_final", "duracion_ms"}.

    `regreso` ({"sale": "1:43 PM", "aerolinea": "American"}) es el de la cotización: si la página lo muestra, se elige
    ese. `servir(pagina)` registra respuestas propias para las pruebas: la página de ejemplo en lugar de internet."""
    return _con_turno(url, lambda u, inicio: _leer(u, inicio, elegir_regreso, servir, espera_ms, presupuesto_ms, regreso))


def ir_a(url: str, vendedor: str, tarifa: str, *, servir=None, regreso: dict | None = None,
         presupuesto_ms: int = PRESUPUESTO_MS) -> dict:
    """Llega a la tarifa `tarifa` de `vendedor` y pulsa su «Continue»; devuelve el envío que Google iba a hacer sin
    hacerlo: {"estado", "motivo", "url" (`https://www.google.com/travel/clk…`), "cuerpo", "vendedor", "tarifa",
    "captura_previa_png_b64", "regreso_elegido", "duracion_ms"}. El cuerpo es de un solo uso: no se registra."""
    if not (isinstance(vendedor, str) and VENDEDOR_O_TARIFA.match(vendedor) and isinstance(tarifa, str)
            and VENDEDOR_O_TARIFA.match(tarifa)):
        return _resultado("fallido", time.monotonic(), SIN_TARIFA)
    pedido = {"vendedor": vendedor, "tarifa": tarifa}
    return _con_turno(url, lambda u, inicio: _leer(u, inicio, True, servir, ESPERA_MS, presupuesto_ms, regreso, pedido))


def _con_turno(url: str, leer) -> dict:
    inicio = time.monotonic()
    if os.environ.get("ANALIZADOR", "").strip().lower() == "apagado":
        return _resultado("fallido", inicio, "el analizador está apagado")
    if not lector.url_permitida(url):
        return _resultado("fallido", inicio, "el enlace no es de Google Flights")
    url = _con_parametros_fijos(url)
    if not _turno.acquire(blocking=False):
        return _resultado("fallido", inicio, "el analizador está leyendo otra página; intenta en un minuto")
    try:
        return leer(url, inicio)
    except Exception as e:  # noqa: BLE001 (un fallo del navegador es una lectura fallida, nunca una caída del servicio)
        return _resultado("fallido", inicio, f"error del navegador ({_primera_linea(e)})")
    finally:
        _turno.release()


def _evidencia(pagina) -> dict:
    """Lo que se vio cuando la lectura no llegó a los precios: captura de la pantalla y el comienzo del texto."""
    try:
        texto = pagina.inner_text("body", timeout=2000)
    except Exception:  # noqa: BLE001 (la página puede estar cambiando: la evidencia es opcional)
        texto = ""
    try:
        captura = base64.b64encode(pagina.screenshot(type="png", timeout=2000)).decode()
    except Exception:  # noqa: BLE001
        captura = None
    return {"captura_png_b64": captura, "extracto": " ".join(texto.split())[:500] or None}


def _con_parametros_fijos(url: str) -> str:
    p = urlsplit(url)
    parametros = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k not in PARAMETROS_FIJOS]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode([*PARAMETROS_FIJOS.items(), *parametros]), ""))


def _leer(url: str, inicio: float, elegir_regreso: bool, servir, espera_ms: int, presupuesto_ms: int,
          regreso_cotizacion: dict | None = None, pedido_ir: dict | None = None) -> dict:
    from playwright.sync_api import Error, sync_playwright

    fuera, abiertas, envio = {}, [], {}

    def interceptar(ruta):
        """El envío al vendedor (POST a /travel/clk): se guarda en memoria y se corta; nunca sale del servidor."""
        pedido = ruta.request
        if pedido_ir and pedido.method == "POST" and lector.url_envio(pedido.url) and not envio:
            envio.update(url=pedido.url, cuerpo=pedido.post_data or "")
        return ruta.abort()

    def solo_lista_blanca(ruta):
        from playwright.sync_api import Error

        pedido = ruta.request
        if not pedido.is_navigation_request():
            return ruta.fallback()
        try:
            principal = pedido.frame.parent_frame is None
        except Error:
            return ruta.abort()   # la primera navegación de una pestaña nueva aún no tiene marco: no carga nada
        if principal and not lector.url_navegable(pedido.url):
            fuera.setdefault("url", pedido.url)
            return ruta.abort()
        return ruta.fallback()

    with sync_playwright() as p:
        navegador = p.chromium.launch(args=ARGUMENTOS)
        try:
            contexto = navegador.new_context(user_agent=AGENTE, locale="en-US", viewport={"width": 1280, "height": 1600})
            # la lista blanca vale para todo el contexto: también una pestaña que la página intente abrir
            contexto.route("**/*", solo_lista_blanca)
            # registrada después, atiende antes: ningún envío a /travel/clk sale del navegador del servidor
            contexto.route(re.compile(r"^https://(www\.)?google\.com/travel/clk"), interceptar)
            pagina = contexto.new_page()

            def otra_pestana(nueva):
                abiertas.append(nueva.url)
                nueva.close()

            def navegacion(pedido):
                # una redirección del servidor no pasa por la ruta: se anota aquí para no leer ni capturar otro sitio
                try:
                    principal = pedido.is_navigation_request() and pedido.frame == pagina.main_frame
                except Exception:  # noqa: BLE001 (un pedido sin marco no es una navegación de la pestaña)
                    principal = False
                if principal and not lector.url_navegable(pedido.url):
                    fuera.setdefault("url", pedido.url)

            contexto.on("page", otra_pestana)
            pagina.on("request", navegacion)

            def salida() -> str | None:
                """Por qué ya no se puede leer: la pestaña salió de la lista blanca o la página abrió otra."""
                if envio:
                    return None   # el envío a /travel/clk se cortó a propósito: es lo que pide «ir a»
                if abiertas:
                    return OTRA_PESTANA
                destino = fuera.get("url") or ("" if lector.url_navegable(pagina.url) else pagina.url)
                if not destino:
                    return None
                return lector.CONSENTIMIENTO if "consent." in destino else \
                    lector.VERIFICACION if "/sorry/" in destino else OTRO_SITIO

            def restante() -> int:
                """Lo que queda del plazo total; cada paso del navegador lo usa como su tiempo máximo."""
                quedan = max(int(presupuesto_ms - (time.monotonic() - inicio) * 1000), 1)
                pagina.set_default_timeout(quedan)
                return quedan

            restante()
            if servir:
                servir(pagina)   # las rutas de la pestaña atienden antes que las del contexto
            try:
                pagina.goto(url, wait_until="domcontentloaded", timeout=restante())
            except Error as e:
                motivo = (fuera or abiertas) and salida() or f"no se pudo abrir la página ({_primera_linea(e)})"
                return _resultado("fallido", inicio, motivo)
            if salida():
                return _resultado("fallido", inicio, salida())
            texto = _esperar(pagina, LISTO, min(espera_ms, restante()))
            if salida():
                return _resultado("fallido", inicio, salida())
            if texto is None:
                return _resultado("fallido", inicio, "la página tardó demasiado en mostrar los precios", url_final=pagina.url,
                                  **_evidencia(pagina))
            motivo = lector.bloqueo(pagina.url, texto)
            if motivo:   # una verificación no se fotografía: no se guarda nada de ella
                return _resultado("fallido", inicio, motivo, url_final=pagina.url)
            regreso = None
            if not RESERVA.search(texto) and elegir_regreso:
                regreso = _elegir_regreso(pagina, min(5000, restante()), regreso_cotizacion)
                if regreso:
                    # sin opciones de reserva a tiempo se lee lo que haya: `avisos` dirá que no las hubo
                    texto = _esperar(pagina, RESERVA, min(espera_ms, restante())) or pagina.inner_text("body")
            if salida():   # antes de leer y de capturar: nunca otro sitio ni una pestaña que se abrió
                return _resultado("fallido", inicio, salida())
            if RESERVA.search(texto) and _desplegar(pagina, restante):
                texto = pagina.inner_text("body")
            if salida():
                return _resultado("fallido", inicio, salida())
            if pedido_ir:
                return _ir(pagina, pedido_ir, envio, regreso, restante, salida, inicio)
            restante()
            etiquetas = pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
            datos = lector.leer(texto, etiquetas)
            datos["regreso_elegido"] = regreso
            if not datos["tarifas"] and not datos["itinerarios"]:
                # para saber qué no se reconoció: unas pocas etiquetas con precio, sin datos de la persona
                datos["muestra_etiquetas"] = [e[:300] for e in etiquetas if e and "dollar" in e][:3]
            captura = _captura(pagina, restante)
            if salida():
                return _resultado("fallido", inicio, salida())
            return _resultado("listo", inicio, datos=datos, url_final=pagina.url,
                              captura_png_b64=base64.b64encode(captura).decode())
        finally:
            navegador.close()


def _desplegar(pagina, restante) -> bool:
    """Clics que solo despliegan lo que ya está en la página: «Other booking options» y las tarifas de cada vendedor
    («Show fare options on …»). No eligen nada. Devuelve si se desplegó algo."""
    from playwright.sync_api import Error

    hubo = False
    for selector in ('[aria-label="Other booking options"]:not([aria-expanded="true"])', '[aria-label^="Show fare options on "]'):
        botones = pagina.locator(selector)
        for i in range(min(botones.count(), 12)):
            try:
                botones.nth(i).click(timeout=min(3000, restante()))
                hubo = True
            except Error:
                pass   # un botón que ya no está (la página cambió): se sigue con lo que hay
    if hubo:
        pagina.wait_for_timeout(min(500, restante()))
    return hubo


def _ir(pagina, pedido: dict, envio: dict, regreso, restante, salida, inicio) -> dict:
    """Pulsa el «Continue» de la tarifa pedida y espera el envío interceptado. Captura la página antes del clic."""
    from playwright.sync_api import Error

    etiquetas = pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
    indice = next((i for i, e in enumerate(etiquetas) if _es_continuar(e, pedido["vendedor"], pedido["tarifa"])), None)
    if indice is None:
        return _resultado("fallido", inicio, SIN_TARIFA, url_final=pagina.url)
    previa = _captura(pagina, restante)
    try:
        pagina.locator("[aria-label]").nth(indice).click(timeout=min(5000, restante()))
    except Error:
        return _resultado("fallido", inicio, SIN_ENVIO, url_final=pagina.url)
    fin = time.monotonic() + min(10_000, restante()) / 1000
    while not envio and time.monotonic() < fin:
        pagina.wait_for_timeout(100)
    if not envio:
        return _resultado("fallido", inicio, salida() or SIN_ENVIO, url_final=pagina.url)
    return _resultado("listo", inicio, url=envio["url"], cuerpo=envio["cuerpo"], vendedor=pedido["vendedor"],
                      tarifa=pedido["tarifa"], regreso_elegido=regreso, url_final=pagina.url,
                      captura_previa_png_b64=base64.b64encode(previa).decode())


def _es_continuar(etiqueta, vendedor: str, tarifa: str) -> bool:
    """«Continue to book with American, Main Cabin for 1014 US dollars»; sin nombre de tarifa, vale «Tarifa»."""
    m = CONTINUAR.match(lector.normal(etiqueta or ""))
    if not m:
        return False
    return (m["vendedor"].strip().lower() == vendedor.strip().lower()
            and (m["tarifa"] or "Tarifa").strip().lower() == tarifa.strip().lower())


def _captura(pagina, restante) -> bytes:
    """Captura PNG de la página, con el alto acotado: la respuesta síncrona de Lambda no puede pasar de 6 MB. Si aun
    así queda grande (una página muy cargada), se repite más corta."""
    alto_pagina = pagina.evaluate("() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)")
    alto = min(int(alto_pagina or 0) or ALTO_CAPTURA, ALTO_CAPTURA)
    while True:
        png = pagina.screenshot(full_page=True, type="png", timeout=restante(),
                                clip={"x": 0, "y": 0, "width": 1280, "height": alto})
        if len(png) * 4 // 3 < TOPE_CAPTURA or alto <= 1000:
            return png
        alto //= 2


def _primera_linea(error: Exception) -> str:
    return (str(error).strip().splitlines() or ["error del navegador"])[0][:160]


def _esperar(pagina, patron: re.Pattern, plazo_ms: int = ESPERA_MS) -> str | None:
    """El texto visible en cuanto cumple `patron`; None si no llega a tiempo. Tolera que la página se recargue o cambie
    de dirección mientras carga (Google lo hace): se vuelve a leer en vez de fallar."""
    from playwright.sync_api import Error

    fin = time.monotonic() + plazo_ms / 1000
    while time.monotonic() < fin:
        try:
            texto = pagina.inner_text("body", timeout=max(min(2000, int((fin - time.monotonic()) * 1000)), 1))
            if patron.search(texto):
                return texto
        except Error:
            pass   # contexto destruido por una navegación: se reintenta
        pagina.wait_for_timeout(400)
    return None


def _elegir_regreso(pagina, plazo_ms: int = 5000, de_la_cotizacion: dict | None = None) -> dict | None:
    """En la lista de regresos de una ida ya elegida, abre el de la cotización (misma hora de salida y aerolínea) si la
    página lo muestra; si no, el más barato, como la plataforma al decidir. Un clic. `elegido_por` dice cuál fue."""
    etiquetas = pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
    opciones = lector.itinerarios(etiquetas)
    if not opciones:
        return None
    buscado = de_la_cotizacion or {}
    iguales = [o for o in opciones if buscado.get("sale") and o.get("sale") == buscado["sale"]
               and (not buscado.get("aerolinea") or (o.get("aerolinea") or "").lower() == buscado["aerolinea"].lower())]
    barato = min(iguales or opciones, key=lambda o: o["precio"])
    elegido_por = "cotizacion" if iguales else "precio"
    indice = etiquetas.index(barato["etiqueta"]) if barato["etiqueta"] in etiquetas else \
        next(i for i, e in enumerate(etiquetas) if (e or "")[:600] == barato["etiqueta"])
    from playwright.sync_api import Error

    # En Google la fila clicable queda por encima del elemento con la etiqueta: se hace clic en su centro sin esperar a
    # que «nada lo tape» (lo que recibe el clic es la propia fila del vuelo). Un clic, con tiempo corto.
    try:
        pagina.locator("[aria-label]").nth(indice).click(force=True, timeout=plazo_ms)
    except Error:
        return None
    return {**{k: v for k, v in barato.items() if k != "etiqueta"}, "elegido_por": elegido_por}
