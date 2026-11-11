"""Aeropuertos frecuentes para el autocompletado. También se acepta cualquier código de tres letras."""
import re
import unicodedata

AEROPUERTOS = [
    ("Miami", "MIA"), ("Fort Lauderdale", "FLL"), ("Orlando", "MCO"), ("Tampa", "TPA"), ("Atlanta", "ATL"),
    ("Nueva York JFK", "JFK"), ("Nueva York LaGuardia", "LGA"), ("Newark", "EWR"), ("Boston", "BOS"),
    ("Washington Dulles", "IAD"), ("Washington Reagan", "DCA"), ("Filadelfia", "PHL"), ("Charlotte", "CLT"),
    ("Chicago O'Hare", "ORD"), ("Detroit", "DTW"), ("Minneapolis", "MSP"), ("Nashville", "BNA"),
    ("Dallas", "DFW"), ("Houston", "IAH"), ("Austin", "AUS"), ("San Antonio", "SAT"), ("Denver", "DEN"),
    ("Salt Lake City", "SLC"), ("Phoenix", "PHX"), ("Las Vegas", "LAS"), ("Los Ángeles", "LAX"),
    ("San Diego", "SAN"), ("San Francisco", "SFO"), ("San José California", "SJC"), ("Seattle", "SEA"),
    ("Portland", "PDX"), ("Honolulu", "HNL"), ("Toronto", "YYZ"), ("Vancouver", "YVR"), ("Montreal", "YUL"),
    ("Ciudad de México", "MEX"), ("Cancún", "CUN"), ("Ciudad de Panamá", "PTY"), ("San José Costa Rica", "SJO"),
    ("Bogotá", "BOG"), ("Medellín", "MDE"), ("Cali", "CLO"), ("Cartagena", "CTG"), ("Barranquilla", "BAQ"),
    ("Lima", "LIM"), ("Quito", "UIO"), ("Santiago de Chile", "SCL"), ("Buenos Aires", "EZE"), ("São Paulo", "GRU"),
    ("Río de Janeiro", "GIG"), ("Madrid", "MAD"), ("Barcelona", "BCN"), ("Málaga", "AGP"), ("Valencia", "VLC"),
    ("Sevilla", "SVQ"), ("Palma de Mallorca", "PMI"), ("Lisboa", "LIS"), ("Oporto", "OPO"), ("París", "CDG"),
    ("Niza", "NCE"), ("Londres Heathrow", "LHR"), ("Londres Gatwick", "LGW"), ("Mánchester", "MAN"),
    ("Dublín", "DUB"), ("Ámsterdam", "AMS"), ("Bruselas", "BRU"), ("Fráncfort", "FRA"), ("Múnich", "MUC"),
    ("Berlín", "BER"), ("Zúrich", "ZRH"), ("Ginebra", "GVA"), ("Viena", "VIE"), ("Roma", "FCO"), ("Milán", "MXP"),
    ("Venecia", "VCE"), ("Atenas", "ATH"), ("Estambul", "IST"), ("Copenhague", "CPH"), ("Estocolmo", "ARN"),
    ("Oslo", "OSL"), ("Helsinki", "HEL"), ("Varsovia", "WAW"), ("Praga", "PRG"), ("Budapest", "BUD"),
    ("Dubái", "DXB"), ("Tokio", "HND"), ("Singapur", "SIN"), ("Sídney", "SYD"),
]


def _simple(texto: str) -> str:
    sin = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin if unicodedata.category(c) != "Mn").strip()


def resolver(entrada: str) -> tuple[str, str] | None:
    """Convierte "Lisboa (LIS)", "lisboa" o "LIS" en (código, ciudad). None si no se reconoce."""
    entrada = (entrada or "").strip()
    codigo = re.search(r"\(([A-Za-z]{3})\)\s*$", entrada)
    if codigo:
        cod = codigo.group(1).upper()
        return cod, next((n for n, c in AEROPUERTOS if c == cod), entrada.split("(")[0].strip())
    if re.fullmatch(r"[A-Za-z]{3}", entrada):
        cod = entrada.upper()
        conocido = next((n for n, c in AEROPUERTOS if c == cod), None)
        if conocido or entrada.isupper():
            return cod, conocido or cod
    buscado = _simple(entrada)
    if buscado:
        for nombre, cod in AEROPUERTOS:
            if _simple(nombre) == buscado:
                return cod, nombre
        for nombre, cod in AEROPUERTOS:
            if _simple(nombre).startswith(buscado) or buscado in _simple(nombre):
                return cod, nombre
        if re.fullmatch(r"[a-z]{3}", buscado):
            return buscado.upper(), buscado.upper()
    return None
