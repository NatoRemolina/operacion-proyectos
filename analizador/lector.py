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


def url_permitida_hotel(url) -> bool:
    """La ficha de un hotel en Google Hotels (pieza 5): `https://www.google.com/travel/search?...` o
    `https://www.google.com/travel/hotels/...`."""
    ruta = _ruta_segura(url)
    return ruta is not None and (ruta == "/travel/search" or ruta.startswith("/travel/hotels/"))


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
                      "escalas": None, "detalle_escalas": [], "emisiones": None,
                      # el detalle desplegado de cada tramo (pieza 5)
                      "avion": None, "aviones": [], "numeros": [], "cabina": None, "piernas": None, "wifi": None,
                      "enchufes": None, "retrasos": None, "aeropuertos": [], "nocturna": False, "terminales": []}
            tramos.append(actual)
            continue
        if actual is None or linea in ("–", "-"):
            continue
        if _detalle(actual, linea):
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
    for t in tramos:
        escalas = " · ".join(t["detalle_escalas"])
        t["nocturna"] = "overnight" in escalas.lower()
        t["terminales"] = list(dict.fromkeys(re.findall(r"\bTerminal [A-Z0-9]{1,3}\b", escalas)))
    return tramos


AVION = re.compile(r"\b(Boeing|Airbus|Embraer|Bombardier|Canadair|CRJ|ATR|McDonnell Douglas|De Havilland|Saab|Fokker)\b")
CABINAS = {"Economy", "Basic Economy", "Premium economy", "Premium Economy", "Business", "First"}
NUMERO_VUELO = re.compile(r"^([A-Z0-9]{2}) ?(\d{1,4})$")
AEROPUERTO = re.compile(r"^\d{1,2}:\d\d [AP]M(\+\d)? · ")


def _detalle(actual: dict, linea: str) -> bool:
    """Una línea del detalle desplegado de un tramo: avión, cabina y número de vuelo; espacio para las piernas, wifi,
    enchufes, «often delayed», aeropuertos y emisiones. True si la reconoció."""
    bajo = linea.lower()
    if " · " in linea and AVION.search(linea):
        for parte in (x.strip() for x in linea.split(" · ")):
            if AVION.search(parte):
                actual["aviones"].append(parte)
                actual["avion"] = actual["avion"] or parte
            elif (m := NUMERO_VUELO.match(parte)):
                actual["numeros"].append(f"{m.group(1)} {m.group(2)}")
            elif parte in CABINAS:
                actual["cabina"] = actual["cabina"] or parte
        return True
    if AEROPUERTO.match(linea):
        actual["aeropuertos"].append(linea)
    elif "legroom" in bajo:
        actual["piernas"] = actual["piernas"] or linea
    elif "wi-fi" in bajo:
        actual["wifi"] = actual["wifi"] or linea
    elif re.search(r"\bpower\b|\busb\b", bajo):
        actual["enchufes"] = actual["enchufes"] or linea
    elif bajo.startswith("often delayed"):
        actual["retrasos"] = linea
    elif bajo.startswith("emissions estimate:"):
        actual["emisiones"] = actual["emisiones"] or linea.split(":", 1)[1].strip()
    elif bajo.startswith(("travel time:", "flight details")):
        pass
    else:
        return False
    return True


PRECIO_ACTUAL = re.compile(r"^\$([\d,]+) is (low|typical|high) for")
RANGO = re.compile(r"usually cost between \$([\d,]+)\s*[–-]\s*\$?([\d,]+)")


def _precios(lineas: list[str], etiquetas: list[str]) -> dict:
    """El cuadro de precios de Google: si el precio es bajo, típico o alto, el rango habitual y, si la página lo da en
    la etiqueta del gráfico, el historial."""
    salida = {"actual": None, "nivel": None, "rango": None, "historial": []}
    for linea in lineas:
        if (m := PRECIO_ACTUAL.match(linea)):
            salida["actual"], salida["nivel"] = float(m.group(1).replace(",", "")), m.group(2)
        elif (m := RANGO.search(linea)):
            salida["rango"] = [float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))]
    for e in etiquetas:
        e = normal(e)
        if e.startswith("Price history"):
            for parte in e.split(":", 1)[-1].split(","):
                if (m := re.fullmatch(r"\s*(.+?) \$([\d,]+(?:\.\d\d)?)\s*", parte)):
                    salida["historial"].append({"cuando": m.group(1), "precio": float(m.group(2).replace(",", ""))})
            break
    return salida


# Billetes separados («Separate tickets»): Google muestra un tiquete por tramo, cada uno con su vendedor. Estas frases
# son avisos, nunca tarifas ni vendedores (producción, cotización 12, 13 nov 2026)
AVISO_RESERVA = re.compile(r"^Separate tickets|tickets in your itinerary|booked (individually|separately)|^Price includes|"
                           r"service fee", re.I)
TRAMO_IDA = re.compile(r"^(Departing|Departure|Outbound)( flights?)?\b", re.I)
TRAMO_REGRESO = re.compile(r"^(Return|Returning)( flights?)?\b", re.I)


def _reserva(lineas: list[str]) -> tuple[list[dict], list[str], bool]:
    """Opciones de reserva por vendedor: «Book with American» y, debajo, cada tarifa con su precio y lo que incluye.
    Con billetes separados, cada vendedor lleva su `tramo` («ida» o «regreso»); el resumen con los vendedores juntos
    («Book with COPA, Avianca») no es un vendedor. Devuelve (vendedores, avisos, billetes separados)."""
    vendedores, vendedor, tarifa, tramo, avisos, separados = [], None, None, None, [], False
    for i, linea in enumerate(lineas):
        if AVISO_RESERVA.search(linea):
            avisos.append(linea)
            separados = separados or bool(re.search(r"separate tickets|booked individually", linea, re.I))
            continue
        if TRAMO_IDA.match(linea) or TRAMO_REGRESO.match(linea):
            tramo, vendedor, tarifa = ("ida" if TRAMO_IDA.match(linea) else "regreso"), None, None
            continue
        if linea.startswith("Book with "):
            nombre = linea.removeprefix("Book with ").strip()
            # `innerText` junta el nombre y la marca «Airline» cuando van en la misma fila: «AmericanAirline»
            pegado = nombre.endswith("Airline") and nombre != "Airline" and not nombre.endswith(" Airline")
            nombre = nombre.removesuffix("Airline") if pegado else nombre
            tarifa = None
            if ", " in nombre:   # varios vendedores juntos: el resumen de billetes separados, no se reserva ahí
                vendedor, separados = None, True
                continue
            vendedor = {"vendedor": nombre, "tarifas": [], "tramo": tramo,
                        "aerolinea": pegado or (i + 1 < len(lineas) and lineas[i + 1] == "Airline")}
            vendedores.append(vendedor)
            continue
        if vendedor is None or linea in SIN_INTERES or DUPLICADO_ACCESIBLE.match(linea):
            if linea == "Continue":
                tarifa = None
            continue
        precio = _precio(linea)
        if precio is not None:
            anterior = lineas[i - 1] if i else ""
            nombre = anterior if anterior not in SIN_INTERES and not anterior.startswith("Book with ") \
                and not AVISO_RESERVA.search(anterior) and _precio(anterior) is None else "Tarifa"
            tarifa = {"nombre": nombre, "precio": precio, "caracteristicas": []}
            vendedor["tarifas"].append(tarifa)
        elif tarifa is not None:
            tarifa["caracteristicas"].append(linea)
        # una línea suelta antes del precio es el nombre de la tarifa: se toma al ver el precio
    if separados and len(vendedores) == 2 and not any(v["tramo"] for v in vendedores):
        vendedores[0]["tramo"], vendedores[1]["tramo"] = "ida", "regreso"   # sin encabezados: un tiquete por tramo, en orden
    if not separados:
        for v in vendedores:
            v["tramo"] = None
    for v in vendedores:
        for t in v["tarifas"]:
            t.update(_clasificar(t.pop("caracteristicas")))
    return vendedores, avisos, separados


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
    vendedores, avisos_reserva, separados = _reserva(lineas[inicio_reserva + 1:fin_reserva]) if inicio_reserva is not None \
        else ([], [], False)
    avisos += avisos_reserva
    lista = itinerarios(etiquetas or [])
    if inicio_reserva is None:
        avisos.append("La página no mostró opciones de reserva.")
    elif not vendedores:
        avisos.append("Hubo opciones de reserva, pero no se reconoció ningún vendedor.")
    notas = [l for l in lineas[fin_reserva:] if l.startswith(("Fare and baggage fees", "Prices include required taxes"))]
    tarifas = [{**t, "vendedor": v["vendedor"], "tramo": v["tramo"]} for v in vendedores for t in v["tarifas"]]
    return {
        "precio_total": total,
        "tramos": tramos,
        "vendedores": [{"vendedor": v["vendedor"], "aerolinea": v["aerolinea"], "tramo": v["tramo"],
                        "precio_desde": min((t["precio"] for t in v["tarifas"]), default=None)} for v in vendedores],
        "billetes_separados": separados,
        "tarifas": tarifas,
        "equipaje": sorted({e for t in tarifas for e in t["equipaje"]}),
        "cambios": sorted({e for t in tarifas for e in t["cambios"]}),
        "reembolso": sorted({e for t in tarifas for e in t["reembolso"]}),
        "escalas": [{"ruta": t["ruta"], "escalas": t["escalas"], "detalle": t["detalle_escalas"]} for t in tramos],
        "itinerarios": lista,
        "precios": _precios(lineas, etiquetas or []),
        "notas": notas,
        "avisos": avisos,
    }


# ---------- pieza 5: la página de la aerolínea y la ficha del hotel ----------
DINERO = re.compile(r"\$([\d,]+(?:\.\d\d)?)")
CABINAS_AEROLINEA = ("Basic Economy", "Main Cabin", "Main Plus", "Main Select", "Main", "Premium Economy", "Economy",
                     "Business", "First", "Flagship Business", "Flagship First")


def _lineas(texto: str) -> list[str]:
    return [l.strip() for l in normal(texto).splitlines() if l.strip()]


def _dinero_tras(lineas: list[str], i: int) -> float | None:
    """El importe de la línea `i` o, si no lo trae, el de la siguiente."""
    for linea in lineas[i:i + 2]:
        if (m := DINERO.search(linea)):
            return float(m.group(1).replace(",", ""))
    return None


def aerolinea(texto: str) -> dict:
    """La página de la aerolínea a la que llega el envío (pasajeros o resumen del viaje): total, tarifa base, impuestos,
    cabinas y números de vuelo. Lo que no aparezca queda en None o vacío; el texto completo se guarda aparte."""
    lineas = _lineas(texto)
    salida = {"total": None, "tarifa_base": None, "impuestos": None, "cabinas": [], "numeros": [], "ruta": None}
    for i, linea in enumerate(lineas):
        bajo = linea.lower()
        if salida["total"] is None and ("trip total" in bajo or bajo in ("total", "total price")):
            salida["total"] = _dinero_tras(lineas, i)
        elif salida["tarifa_base"] is None and bajo in ("fare", "base fare", "fare total"):
            salida["tarifa_base"] = _dinero_tras(lineas, i)
        elif salida["impuestos"] is None and bajo.startswith("taxes"):
            salida["impuestos"] = _dinero_tras(lineas, i)
        elif linea in CABINAS_AEROLINEA and linea not in salida["cabinas"]:
            salida["cabinas"].append(linea)
        elif linea.upper() in ("ROUND TRIP", "ONE WAY") and i + 1 < len(lineas):
            salida["ruta"] = lineas[i + 1]
        for m in re.finditer(r"·\s*([A-Z0-9]{2}) ?(\d{1,4})\b", linea):
            numero = f"{m.group(1)} {m.group(2)}"
            if numero not in salida["numeros"]:
                salida["numeros"].append(numero)
    return salida


INCLUYE = re.compile(r"cancellation|refundable|breakfast|included|deposit|pay at|pay later|pay now", re.I)
SECCIONES_HOTEL = ("Prices", "All options", "Rooms", "Amenities", "Reviews", "About", "Location", "Overview", "Photos")
FECHAS = re.compile(r"^[A-Z][a-z]{2} \d{1,2} [–-] ")


def _seccion(lineas: list[str], nombre: str) -> list[str]:
    if nombre not in lineas:
        return []
    i = lineas.index(nombre) + 1
    fin = next((j for j in range(i, len(lineas)) if lineas[j] in SECCIONES_HOTEL), len(lineas))
    return lineas[i:fin]


def _ofertas(lineas: list[str], clave: str) -> list[dict]:
    """Bloques «nombre · precio · (total) · lo que incluye» de una sección de la ficha (vendedores o habitaciones)."""
    salida, actual, nombre = [], None, None
    for linea in lineas:
        if FECHAS.match(linea):
            continue
        if (precio := _precio(linea)) is not None:
            if nombre:
                actual = {clave: nombre, "precio": precio, "incluye": []}
                salida.append(actual)
                nombre = None
            continue
        if actual and (m := re.fullmatch(r"\$([\d,]+(?:\.\d\d)?) total", linea)):
            actual["total"] = float(m.group(1).replace(",", ""))
        elif linea == "Official site":
            if nombre:
                nombre = (nombre, True)
        elif actual and INCLUYE.search(linea):
            actual["incluye"].append(linea)
        else:
            nombre, actual = linea, None
    return salida


def hotel(texto: str) -> dict:
    """La ficha del hotel en Google Hotels: nombre, clase, calificación y reseñas, ubicación, precio por vendedor (por
    noche y total, con lo que incluye), precio por tipo de habitación y servicios."""
    lineas = _lineas(texto)
    salida = {"nombre": None, "clase": None, "calificacion": None, "resenas": None, "ubicacion": None,
              "vendedores": [], "habitaciones": [], "servicios": []}
    for i, linea in enumerate(lineas):
        if salida["clase"] is None and re.fullmatch(r"\d-star hotel", linea):
            salida["clase"] = linea
            salida["nombre"] = lineas[i - 1] if i else None
        elif salida["calificacion"] is None and re.fullmatch(r"\d\.\d", linea) and i + 1 < len(lineas) \
                and (m := re.fullmatch(r"\(?([\d,]+) reviews?\)?", lineas[i + 1])):
            salida["calificacion"], salida["resenas"] = float(linea), int(m.group(1).replace(",", ""))
        elif salida["ubicacion"] is None and re.match(r"^\d+ .+, .+, [A-Z]{2} \d{5}", linea):
            salida["ubicacion"] = linea
    salida["nombre"] = salida["nombre"] or (lineas[0] if lineas else None)
    for o in _ofertas(_seccion(lineas, "Prices") or _seccion(lineas, "All options"), "vendedor"):
        nombre, oficial = o["vendedor"] if isinstance(o["vendedor"], tuple) else (o["vendedor"], False)
        salida["vendedores"].append({"vendedor": nombre, "por_noche": o["precio"], "total": o.get("total"),
                                     "incluye": o["incluye"], "oficial": oficial})
    salida["habitaciones"] = [{"tipo": o["tipo"], "precio": o["precio"], "incluye": o["incluye"]}
                              for o in _ofertas(_seccion(lineas, "Rooms"), "tipo")]
    salida["servicios"] = _seccion(lineas, "Amenities")
    return salida


# ---------- lo mismo desde el HTML guardado (pruebas sin navegador) ----------
_BLOQUES = {"p", "div", "li", "ul", "ol", "section", "h1", "h2", "h3", "h4", "span", "button", "a", "tr", "td", "header", "main"}


class _Texto(HTMLParser):
    """Aproxima `innerText`: un salto de línea por bloque, sin scripts ni estilos, y junta las `aria-label` de las listas."""

    def __init__(self):
        super().__init__()
        self.partes, self.etiquetas, self._oculto = [], [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "template", "title"):   # como `innerText` del cuerpo: sin el título
            self._oculto += 1
        if a.get("aria-label") and tag in ("li", "div"):
            self.etiquetas.append(a["aria-label"])
        if tag in _BLOQUES:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template", "title") and self._oculto:
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
