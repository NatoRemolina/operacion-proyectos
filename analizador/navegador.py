"""Abre una página de Google Flights con Playwright, espera a que muestre los precios y devuelve lo visible.

Límites, a propósito:
- agente de usuario honesto: dice que es un navegador sin pantalla y para qué lee;
- solo navega dentro de `https://www.google.com/travel/flights` (y la misma página de Google si pide verificación);
- no resuelve verificaciones ni acepta condiciones: si aparecen, queda `fallido` con el motivo;
- nunca inicia sesión ni llena formularios. Lo único que toca es «elegir» un regreso cuando la página es la lista de
  regresos de una ida ya elegida, para llegar a las opciones de reserva: un clic, el regreso más barato;
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

_turno = threading.Lock()


def _resultado(estado: str, inicio: float, motivo: str | None = None, **extra) -> dict:
    return {"estado": estado, "motivo": motivo, "datos": None, "captura_png_b64": None, "url_final": None,
            "agente": AGENTE, "duracion_ms": int((time.monotonic() - inicio) * 1000), **extra}


def analizar(url: str, *, elegir_regreso: bool = True, servir=None, espera_ms: int = ESPERA_MS,
             presupuesto_ms: int = PRESUPUESTO_MS) -> dict:
    """{"estado": "listo" | "fallido", "motivo", "datos" (lo leído), "captura_png_b64", "url_final", "duracion_ms"}.

    `servir(pagina)` registra respuestas propias para las pruebas: la página de ejemplo en lugar de internet."""
    inicio = time.monotonic()
    if os.environ.get("ANALIZADOR", "").strip().lower() == "apagado":
        return _resultado("fallido", inicio, "el analizador está apagado")
    if not lector.url_permitida(url):
        return _resultado("fallido", inicio, "el enlace no es de Google Flights")
    url = _con_parametros_fijos(url)
    if not _turno.acquire(blocking=False):
        return _resultado("fallido", inicio, "el analizador está leyendo otra página; intenta en un minuto")
    try:
        return _leer(url, inicio, elegir_regreso, servir, espera_ms, presupuesto_ms)
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


def _leer(url: str, inicio: float, elegir_regreso: bool, servir, espera_ms: int, presupuesto_ms: int) -> dict:
    from playwright.sync_api import Error, sync_playwright

    fuera = {}

    def solo_lista_blanca(ruta):
        pedido = ruta.request
        if pedido.is_navigation_request() and pedido.frame.parent_frame is None:
            destino = pedido.url
            if not destino.startswith(("https://www.google.com/", "https://google.com/")):
                fuera["url"] = destino
                return ruta.abort()
        return ruta.fallback()

    with sync_playwright() as p:
        navegador = p.chromium.launch(args=ARGUMENTOS)
        try:
            contexto = navegador.new_context(user_agent=AGENTE, locale="en-US", viewport={"width": 1280, "height": 1600})
            pagina = contexto.new_page()

            def restante() -> int:
                """Lo que queda del plazo total; cada paso del navegador lo usa como su tiempo máximo."""
                quedan = max(int(presupuesto_ms - (time.monotonic() - inicio) * 1000), 1)
                pagina.set_default_timeout(quedan)
                return quedan

            restante()
            pagina.route("**/*", solo_lista_blanca)
            if servir:
                servir(pagina)   # registrado después: atiende primero
            try:
                pagina.goto(url, wait_until="domcontentloaded", timeout=restante())
            except Error as e:
                motivo = lector.CONSENTIMIENTO if "consent." in fuera.get("url", "") else \
                    f"no se pudo abrir la página ({_primera_linea(e)})"
                return _resultado("fallido", inicio, motivo, url_final=fuera.get("url") or pagina.url)
            texto = _esperar(pagina, LISTO, min(espera_ms, restante()))
            if texto is None:
                motivo = lector.CONSENTIMIENTO if "consent." in fuera.get("url", "") else \
                    "la página tardó demasiado en mostrar los precios"
                return _resultado("fallido", inicio, motivo, url_final=pagina.url, **_evidencia(pagina))
            motivo = lector.bloqueo(pagina.url, texto)
            if motivo:   # una verificación no se fotografía: no se guarda nada de ella
                return _resultado("fallido", inicio, motivo, url_final=pagina.url)
            regreso = None
            if not RESERVA.search(texto) and elegir_regreso:
                regreso = _elegir_regreso(pagina, min(5000, restante()))
                if regreso:
                    # sin opciones de reserva a tiempo se lee lo que haya: `avisos` dirá que no las hubo
                    texto = _esperar(pagina, RESERVA, min(espera_ms, restante())) or pagina.inner_text("body")
            restante()
            etiquetas = pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
            datos = lector.leer(texto, etiquetas)
            datos["regreso_elegido"] = regreso
            if not datos["tarifas"] and not datos["itinerarios"]:
                # para saber qué no se reconoció: unas pocas etiquetas con precio, sin datos de la persona
                datos["muestra_etiquetas"] = [e[:300] for e in etiquetas if e and "dollar" in e][:3]
            captura = pagina.screenshot(full_page=True, type="png", timeout=restante())
            return _resultado("listo", inicio, datos=datos, url_final=pagina.url,
                              captura_png_b64=base64.b64encode(captura).decode())
        finally:
            navegador.close()


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


def _elegir_regreso(pagina, plazo_ms: int = 5000) -> dict | None:
    """En la lista de regresos de una ida ya elegida, abre el más barato (como la plataforma al decidir). Un clic."""
    etiquetas = pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
    opciones = lector.itinerarios(etiquetas)
    if not opciones:
        return None
    barato = min(opciones, key=lambda o: o["precio"])
    indice = etiquetas.index(barato["etiqueta"]) if barato["etiqueta"] in etiquetas else \
        next(i for i, e in enumerate(etiquetas) if (e or "")[:600] == barato["etiqueta"])
    from playwright.sync_api import Error

    # En Google la fila clicable queda por encima del elemento con la etiqueta: se hace clic en su centro sin esperar a
    # que «nada lo tape» (lo que recibe el clic es la propia fila del vuelo). Un clic, con tiempo corto.
    try:
        pagina.locator("[aria-label]").nth(indice).click(force=True, timeout=plazo_ms)
    except Error:
        return None
    return {k: v for k, v in barato.items() if k != "etiqueta"}
