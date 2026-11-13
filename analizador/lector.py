"""Lee lo visible de una página de Google Flights y lo devuelve ordenado.

Solo biblioteca estándar: se prueba sin navegador y sin red con las páginas de `analizador/ejemplo/`. El navegador
(`navegador.py`) entrega el texto visible (`innerText`) y las etiquetas accesibles (`aria-label`) de la página real;
aquí se interpretan. Las formas de texto se tomaron de la página real el 13 de noviembre de 2026 (opciones de reserva
de Miami → Las Vegas). Si Google cambia su texto, lo que no se reconozca queda fuera y `avisos` lo dice.
"""
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

DOMINIOS = frozenset({"www.google.com", "google.com"})
# Lo que aparece cuando Google pide comprobar que no es un robot, o aceptar condiciones antes de seguir
SENALES_VERIFICACION = ("unusual traffic", "not a robot", "recaptcha", "/sorry/", "captcha")
SENALES_CONSENTIMIENTO = ("before you continue to google", "consent.google.com")
VERIFICACION = "la página pidió verificación"
CONSENTIMIENTO = "la página pidió aceptar condiciones de uso"

PRECIO = re.compile(r"^\$([\d,]+(?:\.\d\d)?)$")
FECHA = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), [A-Z][a-z]{2} \d{1,2}$")
HORA = re.compile(r"^\d{1,2}:\d\d [AP]M(\+\d)?$")
DURACION = re.compile(r"^(\d+ hr)?( ?\d+ min)?$")
RUTA = re.compile(r"^([A-Z]{3})–([A-Z]{3})$")
ESCALAS = re.compile(r"^(Nonstop|\d+ stops?)\b")
ESCALA = re.compile(r"^(\d+ hr(?: \d+ min)?|\d+ min) ([A-Z]{3})\b")
FIN_RESERVA = ("Fare and baggage fees", "Prices include required taxes", "Price insights", "Price history")
DUPLICADO_ACCESIBLE = re.compile(r"^(First|Second|Third) checked bag costs ")
SIN_INTERES = {"Hide options", "Show options", "More options", "Fewer options", "Airline", "Continue", "Book on Google",
               "Travel agency", "Learn more", "Other booking options"}


def _ruta_segura(url) -> str | None:
    """La ruta ya decodificada de una dirección de Google segura, o None. Mismo criterio que los enlaces de la plataforma
    (`precios.es_fuente_google`): https, solo google.com, sin credenciales ni puerto, sin espacios ni caracteres de
    control, y sin `..` como tramo de la ruta (tampoco codificado)."""
    if not isinstance(url, str) or re.search(r"[\s\x00-\x1f\x7f]", url):
        return None
    try:
        p = urlsplit(url)
        puerto = p.port
    except ValueError:
        return None
    if p.scheme != "https" or p.hostname not in DOMINIOS or puerto is not None or p.username or p.password:
        return None
    ruta = unquote(p.path)
    return None if ".." in ruta.split("/") else ruta


def url_permitida(url) -> bool:
    """La dirección que se le pide abrir al analizador: exactamente `https://www.google.com/travel/flights?...`."""
    return _ruta_segura(url) == "/travel/flights"


def url_navegable(url) -> bool:
    """Adónde puede ir la pestaña mientras lee: `https://www.google.com/travel/...` (búsqueda, lista y reserva). La
    verificación (`/sorry/`) y el aviso de condiciones (`consent.google.com`) quedan fuera: se detectan, nunca se abren."""
    ruta = _ruta_segura(url)
    return ruta is not None and ruta.startswith("/travel/") and not ruta.startswith("/travel/clk")


def url_envio(url) -> bool:
    """El envío que Google arma al pulsar «Continue»: `https://www.google.com/travel/clk…`. Solo ese se intercepta."""
    ruta = _ruta_segura(url)
    return ruta is not None and ruta.startswith("/travel/clk")


def bloqueo(url_final: str, texto: str) -> str | None:
    """Por qué no se puede leer la página: una verificación o un aviso de condiciones. Nunca se resuelven."""
    bajo = f"{url_final}\n{texto[:4000]}".lower()
    if any(s in bajo for s in SENALES_VERIFICACION):
        return VERIFICACION
    if any(s in bajo for s in SENALES_CONSENTIMIENTO) or urlsplit(url_final or "").hostname not in DOMINIOS:
        return CONSENTIMIENTO
    return None


def _precio(linea: str) -> float | None:
    m = PRECIO.match(linea)
    return float(m.group(1).replace(",", "")) if m else None


def _clasificar(caracteristicas: list[str]) -> dict:
    equipaje = [c for c in caracteristicas if re.search(r"carry-on|checked bag|\bbag\b|personal item", c, re.I)]
    cambios = [c for c in caracteristicas if re.search(r"change", c, re.I)]
    reembolso = [c for c in caracteristicas if re.search(r"refund", c, re.I)]
    otras = [c for c in caracteristicas if c not in equipaje + cambios + reembolso]
    return {"equipaje": equipaje, "cambios": cambios, "reembolso": reembolso, "otras": otras}


def _tramos(lineas: list[str]) -> list[dict]:
    """Los vuelos elegidos: cada uno empieza con su fecha («Tue, Dec 8»)."""
    tramos, actual = [], None
    for linea in lineas:
        if FECHA.match(linea):
            actual = {"fecha": linea, "sale": None, "llega": None, "aerolinea": None, "duracion": None, "ruta": None,
                      "escalas": None, "detalle_escalas": [], "emisiones": None}
            tramos.append(actual)
            continue
        if actual is None or linea in ("–", "-"):
            continue
        if HORA.match(linea):
            actual["llega" if actual["sale"] else "sale"] = linea
        elif (m := RUTA.match(linea)):
            actual["ruta"] = f"{m.group(1)}–{m.group(2)}"
        elif ESCALAS.match(linea):
            actual["escalas"] = linea
        elif (m := ESCALA.match(linea)) or "layover" in linea.lower():
            actual["detalle_escalas"].append(linea)
        elif "CO2e" in linea:
            actual["emisiones"] = linea
        elif DURACION.match(linea) and re.search(r"\d", linea):
            actual["duracion"] = linea
        elif actual["llega"] and not actual["aerolinea"]:
            actual["aerolinea"] = linea
    return tramos


def _reserva(lineas: list[str]) -> list[dict]:
    """Opciones de reserva por vendedor: «Book with American» y, debajo, cada tarifa con su precio y lo que incluye."""
    vendedores, vendedor, tarifa = [], None, None
    for i, linea in enumerate(lineas):
        if linea.startswith("Book with "):
            nombre = linea.removeprefix("Book with ").strip()
            # `innerText` junta el nombre y la marca «Airline» cuando van en la misma fila: «AmericanAirline»
            pegado = nombre.endswith("Airline") and nombre != "Airline" and not nombre.endswith(" Airline")
            vendedor = {"vendedor": nombre.removesuffix("Airline") if pegado else nombre, "tarifas": [],
                        "aerolinea": pegado or (i + 1 < len(lineas) and lineas[i + 1] == "Airline")}
            vendedores.append(vendedor)
            tarifa = None
            continue
        if vendedor is None or linea in SIN_INTERES or DUPLICADO_ACCESIBLE.match(linea):
            if linea == "Continue":
                tarifa = None
            continue
        precio = _precio(linea)
        if precio is not None:
            anterior = lineas[i - 1] if i else ""
            nombre = anterior if anterior not in SIN_INTERES and not anterior.startswith("Book with ") else "Tarifa"
            tarifa = {"nombre": nombre, "precio": precio, "caracteristicas": []}
            vendedor["tarifas"].append(tarifa)
        elif tarifa is not None:
            tarifa["caracteristicas"].append(linea)
        # una línea suelta antes del precio es el nombre de la tarifa: se toma al ver el precio
    for v in vendedores:
        for t in v["tarifas"]:
            t.update(_clasificar(t.pop("caracteristicas")))
    return vendedores


ETIQUETA_ITINERARIO = re.compile(
    r"From (?P<precio>[\d,]+) US dollars (?P<tipo>round trip|one way)? ?total\. (?P<escalas>Nonstop|\d+ stops?) flight with "
    r"(?P<aerolinea>[^.]+)\. Leaves (?P<desde>.+?) at (?P<sale>\d{1,2}:\d\d [AP]M) on (?P<fecha_sale>[^,]+, [^ ]+ \d{1,2}) "
    r"and arrives at (?P<hasta>.+?) at (?P<llega>\d{1,2}:\d\d [AP]M) on (?P<fecha_llega>[^,]+, [^ ]+ \d{1,2})\. "
    r"Total duration (?P<duracion>[^.]+)\.")


ESPACIOS_RAROS = re.compile(r"[\u00a0\u2007\u2009\u202f]")


def normal(texto: str) -> str:
    """Chromium escribe la hora con un espacio fino sin salto («6:00\u202fAM») y Google usa espacios duros: todo pasa a
    espacio normal para que el lector reconozca lo mismo que se ve."""
    return ESPACIOS_RAROS.sub(" ", texto or "")


def itinerarios(etiquetas: list[str]) -> list[dict]:
    """Las opciones de una lista de vuelos (por ejemplo, los regresos de una ida ya elegida), de su etiqueta accesible.
    `etiqueta` guarda la original (sin normalizar), para encontrar el elemento en la página."""
    vistos, salida = set(), []
    for e in etiquetas:
        m = ETIQUETA_ITINERARIO.search(re.sub(r" {2,}", " ", normal(e)))
        if not m or e in vistos:
            continue
        vistos.add(e)
        d = m.groupdict()
        equipaje = re.findall(r"(\d+ (?:carry-on|checked) bags? included)", normal(e))
        escalas = re.findall(r"Layover \(\d+ of \d+\) is a ([^.]+)\.", normal(e))
        salida.append({**{k: v.strip() for k, v in d.items() if k != "precio" and v}, "precio": float(d["precio"].replace(",", "")),
                       "equipaje": equipaje, "detalle_escalas": escalas, "etiqueta": e[:600]})
    return salida


def leer(texto: str, etiquetas: list[str] | None = None) -> dict:
    """Lo visible de la página, ordenado: precio total, vuelos elegidos, opciones de reserva por vendedor y, si la página
    es una lista, los itinerarios. `avisos` dice lo que no se encontró."""
    lineas = [l.strip() for l in normal(texto).splitlines() if l.strip()]
    avisos = []
    total = None
    for i, linea in enumerate(lineas):
        if linea == "Lowest total price" and i and _precio(lineas[i - 1]) is not None:
            total = _precio(lineas[i - 1])
            break
    inicio_tramos = lineas.index("Selected flights") if "Selected flights" in lineas else None
    inicio_reserva = lineas.index("Booking options") if "Booking options" in lineas else None
    fin_reserva = next((i for i, l in enumerate(lineas) if inicio_reserva is not None and i > inicio_reserva
                        and l.startswith(FIN_RESERVA)), len(lineas))
    tramos = _tramos(lineas[inicio_tramos + 1:inicio_reserva or len(lineas)]) if inicio_tramos is not None else []
    vendedores = _reserva(lineas[inicio_reserva + 1:fin_reserva]) if inicio_reserva is not None else []
    lista = itinerarios(etiquetas or [])
    if inicio_reserva is None:
        avisos.append("La página no mostró opciones de reserva.")
    elif not vendedores:
        avisos.append("Hubo opciones de reserva, pero no se reconoció ningún vendedor.")
    notas = [l for l in lineas[fin_reserva:] if l.startswith(("Fare and baggage fees", "Prices include required taxes"))]
    tarifas = [{**t, "vendedor": v["vendedor"]} for v in vendedores for t in v["tarifas"]]
    return {
        "precio_total": total,
        "tramos": tramos,
        "vendedores": [{"vendedor": v["vendedor"], "aerolinea": v["aerolinea"],
                        "precio_desde": min((t["precio"] for t in v["tarifas"]), default=None)} for v in vendedores],
        "tarifas": tarifas,
        "equipaje": sorted({e for t in tarifas for e in t["equipaje"]}),
        "cambios": sorted({e for t in tarifas for e in t["cambios"]}),
        "reembolso": sorted({e for t in tarifas for e in t["reembolso"]}),
        "escalas": [{"ruta": t["ruta"], "escalas": t["escalas"], "detalle": t["detalle_escalas"]} for t in tramos],
        "itinerarios": lista,
        "notas": notas,
        "avisos": avisos,
    }


# ---------- lo mismo desde el HTML guardado (pruebas sin navegador) ----------
_BLOQUES = {"p", "div", "li", "ul", "ol", "section", "h1", "h2", "h3", "h4", "span", "button", "a", "tr", "td", "header", "main"}


class _Texto(HTMLParser):
    """Aproxima `innerText`: un salto de línea por bloque, sin scripts ni estilos, y junta las `aria-label` de las listas."""

    def __init__(self):
        super().__init__()
        self.partes, self.etiquetas, self._oculto = [], [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "template"):
            self._oculto += 1
        if a.get("aria-label") and tag in ("li", "div"):
            self.etiquetas.append(a["aria-label"])
        if tag in _BLOQUES:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template") and self._oculto:
            self._oculto -= 1
        if tag in _BLOQUES:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._oculto:
            self.partes.append(data)


def desde_html(html: str) -> tuple[str, list[str]]:
    """(texto visible, etiquetas accesibles) de un HTML guardado."""
    p = _Texto()
    p.feed(html)
    return "".join(p.partes), p.etiquetas
