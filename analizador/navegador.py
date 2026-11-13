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
import threading
import time

from . import lector

AGENTE = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/130.0 Safari/537.36 "
          "AnalizadorDePrecios/1.0 (lectura bajo demanda de una página pública para verificar un precio cotizado)")
ESPERA_MS = 20_000          # para que aparezcan los precios; la lectura completa cabe en el minuto de la función
EN_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
# En Lambda no hay /dev/shm grande ni varios procesos: Chromium corre en uno solo
ARGUMENTOS = ["--disable-gpu", "--disable-dev-shm-usage", "--single-process", "--no-zygote"] if EN_LAMBDA else []
LISTO = r"/Booking options[\s\S]*\$\d|Returning flights|Departing flights|unusual traffic|not a robot|Before you continue/"

_turno = threading.Lock()


def _resultado(estado: str, inicio: float, motivo: str | None = None, **extra) -> dict:
    return {"estado": estado, "motivo": motivo, "datos": None, "captura_png_b64": None, "url_final": None,
            "agente": AGENTE, "duracion_ms": int((time.monotonic() - inicio) * 1000), **extra}


def analizar(url: str, *, elegir_regreso: bool = True, servir=None) -> dict:
    """{"estado": "listo" | "fallido", "motivo", "datos" (lo leído), "captura_png_b64", "url_final", "duracion_ms"}.

    `servir(pagina)` registra respuestas propias para las pruebas: la página de ejemplo en lugar de internet."""
    inicio = time.monotonic()
    if os.environ.get("ANALIZADOR", "").strip().lower() == "apagado":
        return _resultado("fallido", inicio, "el analizador está apagado")
    if not lector.url_permitida(url):
        return _resultado("fallido", inicio, "el enlace no es de Google Flights")
    if not _turno.acquire(blocking=False):
        return _resultado("fallido", inicio, "el analizador está leyendo otra página; intenta en un minuto")
    try:
        return _leer(url, inicio, elegir_regreso, servir)
    finally:
        _turno.release()


def _leer(url: str, inicio: float, elegir_regreso: bool, servir) -> dict:
    from playwright.sync_api import Error, TimeoutError, sync_playwright

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
            pagina.set_default_timeout(ESPERA_MS)
            pagina.route("**/*", solo_lista_blanca)
            if servir:
                servir(pagina)   # registrado después: atiende primero
            try:
                pagina.goto(url, wait_until="domcontentloaded")
                pagina.wait_for_function(f"() => {LISTO}.test(document.body.innerText)")
            except TimeoutError:
                return _resultado("fallido", inicio, "la página tardó demasiado en mostrar los precios",
                                  url_final=pagina.url)
            except Error:
                motivo = lector.CONSENTIMIENTO if "consent." in fuera.get("url", "") else "no se pudo abrir la página"
                return _resultado("fallido", inicio, motivo, url_final=fuera.get("url") or pagina.url)
            texto = pagina.inner_text("body")
            motivo = lector.bloqueo(pagina.url, texto)
            if motivo:
                return _resultado("fallido", inicio, motivo, url_final=pagina.url)
            regreso = None
            if "Booking options" not in texto and elegir_regreso:
                regreso = _elegir_regreso(pagina)
                if regreso:
                    try:
                        pagina.wait_for_function(r"() => /Booking options[\s\S]*\$\d/.test(document.body.innerText)")
                    except TimeoutError:
                        pass   # se lee lo que haya; `avisos` dirá que no hubo opciones de reserva
                    texto = pagina.inner_text("body")
            etiquetas = pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
            datos = lector.leer(texto, etiquetas)
            datos["regreso_elegido"] = regreso
            captura = pagina.screenshot(full_page=True, type="png")
            return _resultado("listo", inicio, datos=datos, url_final=pagina.url,
                              captura_png_b64=base64.b64encode(captura).decode())
        finally:
            navegador.close()


def _elegir_regreso(pagina) -> dict | None:
    """En la lista de regresos de una ida ya elegida, abre el más barato (como la plataforma al decidir). Un clic."""
    etiquetas = pagina.eval_on_selector_all("[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
    opciones = lector.itinerarios(etiquetas)
    if not opciones:
        return None
    barato = min(opciones, key=lambda o: o["precio"])
    indice = etiquetas.index(barato["etiqueta"]) if barato["etiqueta"] in etiquetas else \
        next(i for i, e in enumerate(etiquetas) if (e or "")[:600] == barato["etiqueta"])
    pagina.locator("[aria-label]").nth(indice).click()
    return {k: v for k, v in barato.items() if k != "etiqueta"}
