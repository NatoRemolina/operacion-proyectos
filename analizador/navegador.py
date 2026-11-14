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
# La página de error de Google («No results returned. Oops, something went wrong. Reload»: prueba 13) también termina
# la espera: no hay precios que esperar
ERROR_GOOGLE = re.compile(r"Oops, something went wrong|No results returned")
SIN_RESULTADOS = "Google no devolvió resultados; vuelve a intentarlo en unos minutos"
LISTO = re.compile(r"Booking options[\s\S]*\$\d|(Returning|Departing) flights[\s\S]*\$\d|unusual traffic|not a robot|"
                   r"Before you continue|Oops, something went wrong|No results returned")
PARAMETROS_FIJOS = {"hl": "en", "gl": "us", "curr": "USD"}   # lo que sabe leer el lector: inglés, EE. UU. y dólares
RESERVA = re.compile(r"Booking options[\s\S]*\$\d")

ALTO_CAPTURA = 4000          # px: la reserva entera cabe; lo de más abajo (historia de precios) no hace falta
TOPE_CAPTURA = 3_000_000     # bytes en base64: con los datos, la respuesta queda bajo 4 MB
TOPE_RESPUESTA = 4_000_000
OTRO_SITIO = "la página llevó a otro sitio"
# Frases fijas para la persona: el detalle técnico del error queda solo en el registro del analizador
NO_ABRIO = "no se pudo abrir la página"
ERROR_NAVEGADOR = "error del navegador"
SIN_TARIFA = "no se encontró la tarifa"
SIN_REGRESO = "no se pudo elegir el regreso"
# «Ir a…» necesita tiempo después de la lista (elegir el regreso, desplegar, «Continue» y el envío): la espera de la
# lista no puede comerse todo el plazo. Una lectura necesita menos (elegir, leer y capturar).
RESERVA_IR_MS = 20_000
RESERVA_LEER_MS = 10_000
SIN_ENVIO = "Google no respondió al elegir la tarifa"
# Con billetes separados («Separate tickets») cada tiquete se compra aparte: «Continue» de la opción abre un diálogo
# con un tiquete por tramo, cada uno con su «Continue» (prueba 12). «Ir a {aerolínea} · ida|regreso» pulsa ese.
TRAMOS_TIQUETE = ("ida", "regreso")
CONTINUAR = re.compile(r"^Continue to book with (?P<vendedor>.+?)(?:, (?P<tarifa>.+?))? for [\d,.]+ US dollars")
VENDEDOR_O_TARIFA = re.compile(r"^[\w .,&'()+/-]{1,60}$")
OTRA_PESTANA = "la página quiso abrir otra pestaña"

# Sin service workers: una página no puede atender sus propias peticiones y esquivar la lista blanca ni la intercepción
OPCIONES_CONTEXTO = {"user_agent": AGENTE, "locale": "en-US", "viewport": {"width": 1280, "height": 1600},
                     "service_workers": "block"}

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


def _con_turno(url: str, leer, permitida=lector.url_permitida, que: str = "Google Flights") -> dict:
    inicio = time.monotonic()
    if os.environ.get("ANALIZADOR", "").strip().lower() == "apagado":
        return _resultado("fallido", inicio, "el analizador está apagado")
    if not permitida(url):
        return _resultado("fallido", inicio, f"el enlace no es de {que}")
    url = _con_parametros_fijos(url)
    if not _turno.acquire(blocking=False):
        return _resultado("fallido", inicio, "el analizador está leyendo otra página; intenta en un minuto")
    try:
        return leer(url, inicio)
    except Exception as e:  # noqa: BLE001 (un fallo del navegador es una lectura fallida, nunca una caída del servicio)
        print(f"analizador: error del navegador: {type(e).__name__}: {_primera_linea(e)}", flush=True)
        return _resultado("fallido", inicio, ERROR_NAVEGADOR)
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
          regreso_cotizacion: dict | None = None, pedido_ir: dict | None = None, completa: bool = False) -> dict:
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
            contexto = navegador.new_context(**OPCIONES_CONTEXTO)
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
            _cortar_redirecciones_al_envio(contexto, pagina, fuera)

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
                print(f"analizador: no se pudo abrir la página: {_primera_linea(e)}", flush=True)
                motivo = (fuera or abiertas) and salida() or NO_ABRIO
                return _resultado("fallido", inicio, motivo)
            if salida():
                return _resultado("fallido", inicio, salida())
            reserva = min(RESERVA_IR_MS if pedido_ir else RESERVA_LEER_MS, presupuesto_ms // 2)
            texto = _esperar(pagina, LISTO, max(min(espera_ms, restante() - reserva), 1))
            if salida():
                return _resultado("fallido", inicio, salida())
            if texto is None:
                return _resultado("fallido", inicio, "la página tardó demasiado en mostrar los precios", url_final=pagina.url,
                                  **_evidencia(pagina))
            if ERROR_GOOGLE.search(texto) and restante() > reserva + 5000:
                texto = _recargar(pagina, restante, reserva) or texto   # un solo reintento, con el «Reload» de Google
            if salida():
                return _resultado("fallido", inicio, salida())
            if ERROR_GOOGLE.search(texto):
                return _resultado("fallido", inicio, SIN_RESULTADOS, url_final=pagina.url, **_evidencia(pagina))
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
            if RESERVA.search(texto) and lector.DIALOGO_SEPARADOS not in texto and lector.leer(texto)["billetes_separados"] \
                    and _abrir_separados(pagina, restante):
                texto = pagina.inner_text("body")   # el diálogo con un tiquete por tramo (no envía nada)
            if salida():
                return _resultado("fallido", inicio, salida())
            if pedido_ir:
                if not RESERVA.search(texto):   # sin opciones de reserva no hay «Continue» que pulsar
                    return _resultado("fallido", inicio, SIN_REGRESO, url_final=pagina.url, regreso_elegido=regreso,
                                      **_evidencia(pagina))
                if completa:
                    return _completa(pagina, pedido_ir, envio, regreso, restante, salida, inicio)
                return _ir(pagina, pedido_ir, envio, regreso, restante, salida, inicio)
            restante()
            etiquetas = _etiquetas(pagina)
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


PATRONES_ENVIO = [{"urlPattern": f"https://{h}/travel/clk*", "requestStage": "Request"} for h in ("www.google.com", "google.com")]


def _cortar_redirecciones_al_envio(contexto, pagina, fuera: dict) -> None:
    """Las rutas de Playwright no ven las redirecciones (un 302 hacia `/travel/clk` saldría a la red). Chromium sí las
    pausa con su propia intercepción: todo pedido a `/travel/clk` que no sea el POST del «Continue» (que atiende
    `interceptar`, la ruta del contexto) se corta aquí, antes de salir, y la lectura termina como otro sitio."""
    sesion = contexto.new_cdp_session(pagina)

    def pausado(evento):
        pedido = evento["request"]
        if pedido.get("method") == "POST" and not evento.get("redirectedRequestId"):
            sesion.send("Fetch.continueRequest", {"requestId": evento["requestId"]})   # sigue a `interceptar`, que lo corta
            return
        fuera.setdefault("url", pedido.get("url") or "https://www.google.com/travel/clk")
        sesion.send("Fetch.failRequest", {"requestId": evento["requestId"], "errorReason": "BlockedByClient"})

    sesion.on("Fetch.requestPaused", pausado)
    sesion.send("Fetch.enable", {"patterns": PATRONES_ENVIO})


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

    def sin_tarifa():
        return _resultado("fallido", inicio, SIN_TARIFA, url_final=pagina.url, regreso_elegido=regreso, **_evidencia(pagina))

    if pedido["tarifa"].strip().lower() in TRAMOS_TIQUETE:   # billetes separados: el «Continue» del tiquete de ese tramo
        def es_el(e):
            return _es_tiquete(e, pedido["vendedor"])
        candidatas = [e for e in _etiquetas(pagina) if es_el(e)]
        etiqueta = (candidatas[-1] if pedido["tarifa"].strip().lower() == "regreso" else candidatas[0]) if candidatas else None
    else:
        def es_el(e):
            return _es_continuar(e, pedido["vendedor"], pedido["tarifa"])
        etiqueta = next((e for e in _etiquetas(pagina) if es_el(e)), None)
    if etiqueta is None:
        return sin_tarifa()
    previa = _captura(pagina, restante)
    # el botón se busca por su etiqueta exacta (no por su posición, que cambia si la página añade algo) y se relee justo
    # antes de pulsar: el clic solo va al «Continue» de esa tarifa
    boton = pagina.locator(_selector_etiqueta(etiqueta)).first
    try:
        if not es_el(boton.get_attribute("aria-label", timeout=min(3000, restante()))):
            return sin_tarifa()
    except Error:
        return sin_tarifa()
    try:
        boton.click(timeout=min(5000, restante()))
    except Error:
        return _resultado("fallido", inicio, SIN_ENVIO, url_final=pagina.url, regreso_elegido=regreso, **_evidencia(pagina))
    fin = time.monotonic() + min(10_000, restante()) / 1000
    while not envio and time.monotonic() < fin:
        pagina.wait_for_timeout(100)
    if not envio:
        motivo = salida()
        evidencia = {} if motivo else _evidencia(pagina)   # otro sitio u otra pestaña no se fotografían
        return _resultado("fallido", inicio, motivo or SIN_ENVIO, url_final=pagina.url, regreso_elegido=regreso, **evidencia)
    return _resultado("listo", inicio, url=envio["url"], cuerpo=envio["cuerpo"], vendedor=pedido["vendedor"],
                      tarifa=pedido["tarifa"], regreso_elegido=regreso, url_final=pagina.url,
                      captura_previa_png_b64=base64.b64encode(previa).decode())


# ---------- pieza 5: captura completa (vuelo con su envío, aerolínea y hotel) ----------
ALTO_COMPLETA = 12_000       # px: la página entera de Google o de la aerolínea, dentro del mismo tope de bytes
TOPE_TEXTO = 300_000         # bytes del texto visible que viajan en la respuesta
DETALLES = ('[aria-label^="Flight details"][aria-expanded="false"]', '[aria-label^="Toggle details"][aria-expanded="false"]')


def _texto(pagina) -> str:
    return lector.normal(pagina.inner_text("body")).encode()[:TOPE_TEXTO].decode(errors="ignore")


def _b64(png: bytes) -> str:
    return base64.b64encode(png).decode()


def captura_vuelo(url: str, vendedor: str, tarifa: str, *, servir=None, regreso: dict | None = None,
                  presupuesto_ms: int = PRESUPUESTO_MS) -> dict:
    """Todo lo visible del vuelo en Google Flights (con el detalle de cada tramo desplegado), su texto completo y una
    captura de página completa; después pulsa el «Continue» de la tarifa y devuelve el envío interceptado (`envio`),
    que el trabajador pasa a `captura_aerolinea` en memoria. Sin envío, la captura de Google vale igual (`motivo_envio`)."""
    if not (isinstance(vendedor, str) and VENDEDOR_O_TARIFA.match(vendedor) and isinstance(tarifa, str)
            and VENDEDOR_O_TARIFA.match(tarifa)):
        return _resultado("fallido", time.monotonic(), SIN_TARIFA)
    pedido = {"vendedor": vendedor, "tarifa": tarifa}
    return _con_turno(url, lambda u, inicio: _leer(u, inicio, True, servir, ESPERA_MS, presupuesto_ms, regreso, pedido,
                                                   completa=True))


def _completa(pagina, pedido: dict, envio: dict, regreso, restante, salida, inicio) -> dict:
    from playwright.sync_api import Error

    for selector in DETALLES:   # desplegar el detalle de cada tramo: solo muestra lo que ya está en la página
        botones = pagina.locator(selector)
        for _ in range(min(botones.count(), 6)):   # cada clic saca al botón de la lista («aria-expanded» pasa a true)
            try:
                botones.nth(0).click(timeout=min(2000, restante()))
            except Error:
                break
    if salida():
        return _resultado("fallido", inicio, salida())
    texto = _texto(pagina)
    datos = lector.leer(texto, _etiquetas(pagina))
    datos["regreso_elegido"] = regreso
    imagen = _captura(pagina, restante, ALTO_COMPLETA)
    if salida():
        return _resultado("fallido", inicio, salida())
    r = _ir(pagina, pedido, envio, regreso, restante, salida, inicio)
    con_envio = r["estado"] == "listo"
    return _resultado("listo", inicio, datos=datos, texto=texto, url_final=pagina.url, capturas_png_b64=[_b64(imagen)],
                      envio={"url": r["url"], "cuerpo": r["cuerpo"]} if con_envio else None,
                      motivo_envio=None if con_envio else r["motivo"], regreso_elegido=regreso)


ORIGEN_ENVIO = "https://analizador.invalid/envio"   # página propia (nunca sale a la red) que hace el POST a Google
PRECIO_E_IMPUESTOS = re.compile(r"price and tax|taxes and (carrier-imposed )?fees|price details|fare details", re.I)
SIN_AEROLINEA = "no se llegó a la página de la aerolínea"


def captura_aerolinea(url: str, cuerpo: str, *, servir=None, presupuesto_ms: int = PRESUPUESTO_MS) -> dict:
    """Hace el envío de Google (el de `captura_vuelo`) y lee la página de la aerolínea a la que lleva: total, impuestos
    (un clic en «Price and tax information», fuera de todo formulario), cabinas, números de vuelo, texto completo y una
    captura de página completa. Nunca escribe en campos, ni inicia sesión, ni compra. Una vez en la aerolínea, la
    pestaña no navega a otro sitio."""
    inicio = time.monotonic()
    if os.environ.get("ANALIZADOR", "").strip().lower() == "apagado":
        return _resultado("fallido", inicio, "el analizador está apagado")
    if not lector.url_envio(url) or not isinstance(cuerpo, str) or len(cuerpo) > 12_000:
        return _resultado("fallido", inicio, "el envío no es de Google")
    if not _turno.acquire(blocking=False):
        return _resultado("fallido", inicio, "el analizador está leyendo otra página; intenta en un minuto")
    try:
        return _aerolinea(url, cuerpo, servir, presupuesto_ms, inicio)
    except Exception as e:  # noqa: BLE001
        print(f"analizador: error del navegador: {type(e).__name__}: {_primera_linea(e)}", flush=True)
        return _resultado("fallido", inicio, ERROR_NAVEGADOR)
    finally:
        _turno.release()


def _aerolinea(url: str, cuerpo: str, servir, presupuesto_ms: int, inicio: float) -> dict:
    import html as html_
    from urllib.parse import parse_qsl as campos_de

    from playwright.sync_api import Error, sync_playwright

    campos = "".join(f'<input type="hidden" name="{html_.escape(k)}" value="{html_.escape(v)}">'
                     for k, v in campos_de(cuerpo, keep_blank_values=True))
    pagina_envio = (f'<!doctype html><meta charset="utf-8"><form id="e" method="post" action="{html_.escape(url)}">{campos}'
                    "</form><script>document.getElementById('e').submit()</script>")
    destino = {}

    def una_sola_aerolinea(ruta):
        pedido = ruta.request
        if not pedido.is_navigation_request():
            return ruta.fallback()
        try:
            principal = pedido.frame.parent_frame is None
        except Error:
            return ruta.abort()
        if not principal:
            return ruta.fallback()
        host = urlsplit(pedido.url).hostname or ""
        if pedido.url.startswith(ORIGEN_ENVIO) or (lector.url_envio(pedido.url) and pedido.method == "POST"):
            return ruta.fallback()
        if not pedido.url.startswith("https://") or (destino.get("host") and host != destino["host"]):
            return ruta.abort()   # ya en la aerolínea: no se va a ningún otro sitio
        return ruta.fallback()

    with sync_playwright() as p:
        navegador = p.chromium.launch(args=ARGUMENTOS)
        try:
            contexto = navegador.new_context(**OPCIONES_CONTEXTO)
            contexto.route("**/*", una_sola_aerolinea)
            pagina = contexto.new_page()
            contexto.on("page", lambda nueva: nueva.close())   # ninguna pestaña más (después de abrir la propia)
            pagina.route(ORIGEN_ENVIO, lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=pagina_envio))

            def restante() -> int:
                quedan = max(int(presupuesto_ms - (time.monotonic() - inicio) * 1000), 1)
                pagina.set_default_timeout(quedan)
                return quedan
            if servir:
                servir(pagina)
            try:
                pagina.goto(ORIGEN_ENVIO, wait_until="commit", timeout=restante())
            except Error:
                return _resultado("fallido", inicio, SIN_AEROLINEA)
            fin = time.monotonic() + min(25_000, restante() - 10_000) / 1000
            while time.monotonic() < fin:
                host = urlsplit(pagina.url).hostname or ""
                if host and host not in lector.DOMINIOS and not pagina.url.startswith(ORIGEN_ENVIO):
                    destino["host"] = host
                    break
                pagina.wait_for_timeout(250)
            if not destino:
                return _resultado("fallido", inicio, SIN_AEROLINEA, **_evidencia(pagina))
            _esperar(pagina, re.compile(r"\$\d"), max(min(15_000, restante() - 8_000), 1))
            # un clic que solo despliega el precio y los impuestos: un enlace o botón con ese nombre, fuera de formularios
            try:
                for el in pagina.get_by_role("button", name=PRECIO_E_IMPUESTOS).all() + \
                        pagina.get_by_role("link", name=PRECIO_E_IMPUESTOS).all():
                    if el.evaluate("e => !e.closest('form') && e.type !== 'submit'"):
                        el.click(timeout=min(3000, restante()))
                        pagina.wait_for_timeout(min(1000, restante()))
                        break
            except Error:
                pass   # sin el desglose se guarda lo que haya
            if (urlsplit(pagina.url).hostname or "") != destino["host"]:
                return _resultado("fallido", inicio, OTRO_SITIO)
            texto = _texto(pagina)
            imagen = _captura(pagina, restante, ALTO_COMPLETA)
            p_ = urlsplit(pagina.url)
            datos = {**lector.aerolinea(texto), "pagina": f"{p_.scheme}://{p_.hostname}{p_.path}", "titulo": pagina.title()[:200]}
            return _resultado("listo", inicio, datos=datos, texto=texto, capturas_png_b64=[_b64(imagen)],
                              url_final=f"{p_.scheme}://{p_.hostname}{p_.path}")
        finally:
            navegador.close()


def captura_hotel(url: str, hotel: str = "", *, servir=None, presupuesto_ms: int = PRESUPUESTO_MS) -> dict:
    """La ficha del hotel elegido en Google Hotels con las fechas de la cotización: precio por vendedor y por tipo de
    habitación, qué incluye cada tarifa, servicios, calificación, reseñas y ubicación; texto completo y una captura.
    Si Google muestra una lista, un clic en el hotel por su nombre. Mismos límites que la lectura de vuelos."""
    nombre = hotel if isinstance(hotel, str) and VENDEDOR_O_TARIFA.match(hotel or "-") else ""
    return _con_turno(url, lambda u, inicio: _hotel(u, inicio, nombre, servir, presupuesto_ms),
                      permitida=lector.url_permitida_hotel, que="Google Hotels")


def _hotel(url: str, inicio: float, nombre: str, servir, presupuesto_ms: int) -> dict:
    from playwright.sync_api import Error, sync_playwright

    fuera = {}

    def solo_google_travel(ruta):
        pedido = ruta.request
        if not pedido.is_navigation_request():
            return ruta.fallback()
        try:
            principal = pedido.frame.parent_frame is None
        except Error:
            return ruta.abort()
        if principal and not lector.url_navegable(pedido.url):
            fuera.setdefault("url", pedido.url)
            return ruta.abort()
        return ruta.fallback()

    with sync_playwright() as p:
        navegador = p.chromium.launch(args=ARGUMENTOS)
        try:
            contexto = navegador.new_context(**OPCIONES_CONTEXTO)
            contexto.route("**/*", solo_google_travel)
            abiertas = []
            pagina = contexto.new_page()
            contexto.on("page", lambda nueva: abiertas.append(1) or nueva.close())

            def restante() -> int:
                quedan = max(int(presupuesto_ms - (time.monotonic() - inicio) * 1000), 1)
                pagina.set_default_timeout(quedan)
                return quedan
            if servir:
                servir(pagina)
            try:
                pagina.goto(url, wait_until="domcontentloaded", timeout=restante())
            except Error:
                return _resultado("fallido", inicio, OTRO_SITIO if fuera else NO_ABRIO)
            texto = _esperar(pagina, re.compile(r"\$\d|unusual traffic|not a robot|Before you continue"),
                             max(restante() - 10_000, 1))
            if texto is None:
                return _resultado("fallido", inicio, "la página tardó demasiado en mostrar los precios", **_evidencia(pagina))
            motivo = lector.bloqueo(pagina.url, texto)
            if motivo:
                return _resultado("fallido", inicio, motivo)
            datos = lector.hotel(texto)
            if not datos["vendedores"] and nombre:
                try:   # una lista de hoteles: abrir el elegido por su nombre (un clic)
                    pagina.get_by_text(nombre, exact=False).first.click(timeout=min(3000, restante()))
                    pagina.wait_for_timeout(min(2500, restante()))
                except Error:
                    pass
            if fuera or abiertas:
                return _resultado("fallido", inicio, OTRO_SITIO)
            texto = _texto(pagina)
            datos = lector.hotel(texto)
            imagen = _captura(pagina, restante, ALTO_COMPLETA)
            return _resultado("listo", inicio, datos=datos, texto=texto, capturas_png_b64=[_b64(imagen)],
                              url_final=pagina.url)
        finally:
            navegador.close()


def _etiquetas(pagina) -> list[str | None]:
    """Las etiquetas (`aria-label`) de la página, en orden."""
    return pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")


def _selector_etiqueta(etiqueta: str) -> str:
    """El selector CSS del elemento con esa etiqueta exacta (barras, comillas y saltos de línea escapados)."""
    return '[aria-label="' + etiqueta.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\a ") + '"]'


def _sin_marca(nombre: str | None) -> str:
    """«COPA airline» → «COPA»: Google añade la marca a la etiqueta cuando vende la aerolínea (prueba 12)."""
    nombre = (nombre or "").strip()
    return nombre[:-len(" airline")].strip() if nombre.lower().endswith(" airline") else nombre


def _es_continuar(etiqueta, vendedor: str, tarifa: str) -> bool:
    """«Continue to book with American, Main Cabin for 1014 US dollars»; sin nombre de tarifa, vale «Tarifa». La opción
    de dos tiquetes («…COPA, Avianca airline… must be booked individually») nunca es una tarifa."""
    texto = lector.normal(etiqueta or "")
    m = CONTINUAR.match(texto)
    if not m or "booked individually" in texto:
        return False
    return (_sin_marca(m["vendedor"]).lower() == vendedor.strip().lower()
            and (_sin_marca(m["tarifa"]) or "Tarifa").lower() == tarifa.strip().lower())


def _es_tiquete(etiqueta, vendedor: str) -> bool:
    """El «Continue» de un tiquete del diálogo de billetes separados: «Continue to book with COPA airline for 334 US
    dollars…» (un vendedor, sin tarifa)."""
    texto = lector.normal(etiqueta or "")
    m = CONTINUAR.match(texto)
    return bool(m) and "booked individually" not in texto and not m["tarifa"] \
        and _sin_marca(m["vendedor"]).lower() == vendedor.strip().lower()


def _abrir_separados(pagina, restante) -> bool:
    """Pulsa el «Continue» de la opción de billetes separados, que solo abre el diálogo con un tiquete por tramo (no
    envía nada: prueba 12), y espera ese diálogo. False si no se pudo."""
    from playwright.sync_api import Error

    etiqueta = next((e for e in _etiquetas(pagina) if e and e.startswith("Continue to book with ")
                     and "booked individually" in lector.normal(e)), None)
    if not etiqueta:
        return False
    try:
        pagina.locator(_selector_etiqueta(etiqueta)).first.click(timeout=min(3000, restante()))
    except Error:
        return False
    return _esperar(pagina, re.compile(re.escape(lector.DIALOGO_SEPARADOS)), min(5000, restante())) is not None


def _captura(pagina, restante, alto_max: int = ALTO_CAPTURA) -> bytes:
    """Captura PNG de la página, con el alto acotado: la respuesta síncrona de Lambda no puede pasar de 6 MB. Si aun
    así queda grande (una página muy cargada), se repite más corta."""
    alto_pagina = pagina.evaluate("() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)")
    alto = min(int(alto_pagina or 0) or alto_max, alto_max)
    while True:
        png = pagina.screenshot(full_page=True, type="png", timeout=restante(),
                                clip={"x": 0, "y": 0, "width": 1280, "height": alto})
        if len(png) * 4 // 3 < TOPE_CAPTURA or alto <= 1000:
            return png
        alto //= 2


def _primera_linea(error: Exception) -> str:
    return (str(error).strip().splitlines() or ["error del navegador"])[0][:160]


def _recargar(pagina, restante, reserva: int) -> str | None:
    """Un clic en el botón «Reload» de la página de error de Google (no es un formulario) y la espera de los precios
    otra vez. Devuelve el texto nuevo, o None si no hubo botón o no llegó nada. Se llama una sola vez por lectura."""
    from playwright.sync_api import Error

    try:
        boton = pagina.get_by_role("button", name="Reload", exact=True).first
        if (boton.inner_text(timeout=min(2000, restante())) or "").strip() != "Reload":
            return None
        boton.click(timeout=min(3000, restante()))
    except Error:
        return None
    fin = time.monotonic() + 3   # que la página deje el aviso de error antes de volver a esperar los precios
    while time.monotonic() < fin:
        try:
            if not ERROR_GOOGLE.search(pagina.inner_text("body", timeout=1000)):
                break
        except Error:
            break   # está recargando
        pagina.wait_for_timeout(200)
    return _esperar(pagina, LISTO, max(restante() - reserva, 1))


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
    etiquetas = _etiquetas(pagina)
    opciones = lector.itinerarios(etiquetas)
    if not opciones:
        return None
    buscado = de_la_cotizacion or {}
    iguales = [o for o in opciones if buscado.get("sale") and o.get("sale") == buscado["sale"]
               and (not buscado.get("aerolinea") or (o.get("aerolinea") or "").lower() == buscado["aerolinea"].lower())]
    barato = min(iguales or opciones, key=lambda o: o["precio"])
    elegido_por = "cotizacion" if iguales else "precio"
    etiqueta = barato["etiqueta"] if barato["etiqueta"] in etiquetas else \
        next(e for e in etiquetas if (e or "")[:600] == barato["etiqueta"])
    from playwright.sync_api import Error

    # En Google la fila clicable queda por encima del elemento con la etiqueta: se hace clic en su centro sin esperar a
    # que «nada lo tape» (lo que recibe el clic es la propia fila del vuelo). Un clic, con tiempo corto, en el elemento
    # de esa etiqueta exacta (no en una posición, que cambia si la página añade algo).
    try:
        pagina.locator(_selector_etiqueta(etiqueta)).first.click(force=True, timeout=plazo_ms)
    except Error:
        return None
    return {**{k: v for k, v in barato.items() if k != "etiqueta"}, "elegido_por": elegido_por}
