"""Convierte un soporte (foto, PDF o correo) en datos estructurados.

Con clave configurada se consulta un modelo multimodal por API. Sin clave se usan las
extracciones guardadas de los documentos de ejemplo, para que la demostración funcione
igual. El resultado siempre indica su origen: "en vivo" o "guardado".
"""
import base64
import email
import hashlib
import json
import math
import re
from email import policy
from html.parser import HTMLParser

import httpx

from .. import config
from . import llm

CAMPOS = ["comercio", "fecha", "categoria", "subtotal", "impuesto", "propina", "total",
          "moneda", "metodo_pago", "canal_reserva", "ciudad"]
# Datos propios de una factura. No son columnas de `gastos`: viajan en la lectura original (`gastos.extraido`) y en el
# aviso a n8n, que los guarda en Drive y en la hoja de lecturas.
CAMPOS_FACTURA = ("numero_factura", "id_fiscal", "lineas")
MAX_LINEAS = 30

INSTRUCCION = f"""Eres un asistente de contabilidad. Lee el soporte de gasto adjunto y devuelve SOLO un objeto JSON con:
- comercio: nombre del comercio o proveedor
- fecha: fecha del gasto en formato AAAA-MM-DD (ten en cuenta que en Europa el día va antes del mes)
- categoria: una de {list(config.CATEGORIAS)}. Usa transporte_terrestre para taxi, bus, tren o aplicación de
  transporte; compras_proyecto para lo que se compra para el trabajo del proyecto (por ejemplo, hélices, baterías o
  repuestos del dron); otros solo si no encaja en ninguna
- subtotal, impuesto, propina, total: números con punto decimal, o null si no aparecen
- moneda: código ISO de tres letras (USD, EUR, COP...)
- metodo_pago: texto corto o null
- canal_reserva: "directo" si se compró al proveedor, o el nombre de la agencia o intermediario si lo hay, o null
- ciudad: ciudad del gasto o null
- confianza: número entre 0 y 1 con tu seguridad sobre el conjunto
- dudas: lista de campos que no se leen con claridad (vacía si todo es legible)
- numero_factura: número o código de la factura o del recibo tal como aparece, o null
- id_fiscal: identificación tributaria del proveedor tal como aparece (NIT, RUT, NIF, VAT o EIN), o null
- lineas: las líneas de detalle, como lista de objetos {{descripcion, cantidad, total}} (como mucho {MAX_LINEAS}); lista vacía
  si el soporte no las trae
Si el soporte tiene varias páginas, lee todas las páginas: el total y los impuestos suelen ir en la última.
No inventes valores: si algo no se lee, usa null y nómbralo en dudas."""


def tipo_binario(contenido: bytes) -> str | None:
    """Tipo de una foto o un PDF según sus primeros bytes, no según lo que declara quien lo envía."""
    if contenido[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    if contenido[:5] == b"%PDF-":
        return "application/pdf"
    return None


def parece_html(contenido: bytes) -> bool:
    """Una página HTML de verdad: texto (sin bytes nulos) con alguna de las etiquetas que abren un documento."""
    cabeza = contenido[:4000].decode("utf-8", "ignore").lower()
    return "\x00" not in cabeza and any(m in cabeza for m in ("<!doctype html", "<html", "<head", "<body"))


class _TextoDeHtml(HTMLParser):
    """Se queda solo con el texto visible: descarta scripts, estilos y lo incrustado, y de los enlaces deja la palabra."""
    # Solo etiquetas que se cierran: una sin cierre (como <embed>) dejaría fuera todo el texto que la sigue
    OMITIR = {"script", "style", "noscript", "template", "svg", "math", "iframe", "object", "canvas"}
    BLOQUES = {"p", "div", "br", "tr", "li", "ul", "ol", "table", "thead", "tbody", "tfoot", "caption", "title", "hr",
               "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer", "main", "address",
               "blockquote", "pre", "dt", "dd", "dl", "form", "fieldset", "nav", "aside"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self.omitir = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.OMITIR:
            self.omitir += 1
        elif tag in self.BLOQUES:
            self.partes.append("\n")
        elif tag in ("td", "th"):
            self.partes.append(" ")

    def handle_endtag(self, tag):
        if tag in self.OMITIR:
            self.omitir = max(0, self.omitir - 1)
        elif tag in self.BLOQUES:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self.omitir:
            self.partes.append(data)


def html_a_texto(html: bytes | str) -> str:
    """Reduce una página HTML a texto plano, sin código, estilos ni enlaces activos. Solo la librería estándar."""
    if isinstance(html, bytes):
        try:
            html = html.decode("utf-8-sig")
        except UnicodeDecodeError:
            html = html.decode("cp1252", "replace")
    lector = _TextoDeHtml()
    lector.feed(html)
    lector.close()
    lineas = (re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", l)).strip()
              for l in "".join(lector.partes).splitlines())
    return "\n".join(l for l in lineas if l)


def _linea(valor) -> str | None:
    """Una cabecera del correo en una sola línea, sin caracteres de control y con un largo razonable."""
    texto = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(valor or ""))).strip()[:200]
    return texto or None


def remitente_y_asunto(contenido: bytes) -> dict:
    """De quién llegó el correo y con qué asunto: el contexto del gasto que se muestra en su ficha."""
    try:
        msg = email.message_from_bytes(contenido, policy=policy.default)
        return {"remitente": _linea(msg["from"]), "asunto": _linea(msg["subject"])}
    except Exception:   # una cabecera mal formada no impide guardar el gasto: solo se queda sin contexto
        return {"remitente": None, "asunto": None}


def _adjunto_util(msg) -> tuple[bytes, str] | None:
    """El adjunto que mejor sirve para leer el gasto: un PDF antes que una foto. El tipo se mira en el contenido."""
    candidatos = []
    for parte in msg.iter_attachments():
        try:
            datos = parte.get_payload(decode=True) or b""
        except Exception:  # noqa: S112  un adjunto dañado no impide leer los demás
            continue
        tipo = tipo_binario(datos)
        if tipo:
            candidatos.append((tipo != "application/pdf", datos, tipo))
    if not candidatos:
        return None
    _, datos, tipo = min(candidatos, key=lambda c: c[0])   # el primero de los PDF, o la primera foto si no hay PDF
    return datos, tipo


def _correo(contenido: bytes):
    """Devuelve (texto del correo, adjunto o None, mime del adjunto)."""
    msg = email.message_from_bytes(contenido, policy=policy.default)
    adjunto = _adjunto_util(msg)
    if adjunto:
        return None, *adjunto
    cuerpo = msg.get_body(preferencelist=("plain", "html"))
    texto = cuerpo.get_content() if cuerpo else ""
    if cuerpo and cuerpo.get_content_subtype() == "html":
        texto = html_a_texto(texto)
    return f"De: {msg['from']}\nAsunto: {msg['subject']}\nFecha: {msg['date']}\n\n{texto}", None, None


def _bloque(contenido: bytes, mime: str) -> dict:
    datos = base64.standard_b64encode(contenido).decode()
    tipo = "document" if mime == "application/pdf" else "image"
    return {"type": tipo, "source": {"type": "base64", "media_type": mime, "data": datos}}


def _en_vivo(contenido: bytes, mime: str) -> dict:
    partes = []
    if mime == "message/rfc822":
        texto, adjunto, mime_adjunto = _correo(contenido)
        partes.append(_bloque(adjunto, mime_adjunto) if adjunto else {"type": "text", "text": texto[:20000]})
    elif mime == "text/plain":
        partes.append({"type": "text", "text": contenido.decode("utf-8", "replace")[:20000]})
    else:
        partes.append(_bloque(contenido, mime))
    partes.append({"type": "text", "text": INSTRUCCION})
    r = httpx.post(
        config.MODELO_API_URL, timeout=90,
        headers={"x-api-key": config.MODELO_API_KEY, "content-type": "application/json", **config.MODELO_CABECERAS},
        json={"model": config.MODELO_NOMBRE, "max_tokens": 4096, "messages": [{"role": "user", "content": partes}]},
    )
    r.raise_for_status()
    texto = "".join(b.get("text", "") for b in r.json().get("content", []))
    return json.loads(re.search(r"\{.*\}", texto, re.S).group(0))


TEXTO, NUMERO = {"type": "STRING", "nullable": True}, {"type": "NUMBER", "nullable": True}
ESQUEMA = {"type": "OBJECT", "properties": {
    "comercio": TEXTO, "fecha": TEXTO, "categoria": {"type": "STRING", "enum": list(config.CATEGORIAS)},
    "subtotal": NUMERO, "impuesto": NUMERO, "propina": NUMERO, "total": NUMERO, "moneda": TEXTO,
    "metodo_pago": TEXTO, "canal_reserva": TEXTO, "ciudad": TEXTO,
    "numero_factura": TEXTO, "id_fiscal": TEXTO,
    "lineas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "descripcion": TEXTO, "cantidad": NUMERO, "total": NUMERO}}},
    "confianza": {"type": "NUMBER"}, "dudas": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["comercio", "fecha", "categoria", "total", "moneda", "confianza", "dudas"]}


def _con_cliente(contenido: bytes, mime: str, entidad_id: int | None, uso: str = "recibo") -> dict:
    """Lectura con el cliente único: salida con esquema fijo, de modo que siempre llega un JSON con los mismos campos."""
    if mime == "message/rfc822":
        texto, adjunto, mime_adjunto = _correo(contenido)
        parte = llm.parte_archivo(adjunto, mime_adjunto) if adjunto else llm.parte_texto(texto[:20000])
    elif mime == "text/plain":   # una confirmación HTML ya reducida a texto
        parte = llm.parte_texto(contenido.decode("utf-8", "replace")[:20000])
    else:
        parte = llm.parte_archivo(contenido, mime)
    candidato = llm.generar([{"role": "user", "parts": [parte, llm.parte_texto(INSTRUCCION)]}],
                            uso=uso, entidad_id=entidad_id, esquema=ESQUEMA)
    return llm.json_de(candidato)


def _guardado(contenido: bytes) -> dict | None:
    """Lectura guardada de un soporte de ejemplo. Se reconoce por el contenido, no por el nombre del archivo."""
    archivo = config.DIR_EJEMPLOS / "esperados.json"
    if not archivo.is_file():
        return None
    huella = hashlib.sha256(contenido).hexdigest()
    for nombre, lectura in json.loads(archivo.read_text()).items():
        ejemplo = config.DIR_EJEMPLOS / nombre
        if not ejemplo.is_file():
            continue
        datos = ejemplo.read_bytes()
        if ejemplo.suffix.lower() in (".html", ".htm"):   # se guarda y se lee reducida a texto
            datos = html_a_texto(datos).encode()
        if hashlib.sha256(datos).hexdigest() == huella:
            return lectura
    return None


def _num(valor):
    try:
        return None if valor in (None, "") else round(float(valor), 2)
    except (TypeError, ValueError, OverflowError):   # OverflowError: un entero gigante que no cabe en un float
        return None


def _finito(valor):
    """Un importe o una cantidad de la factura: número finito con dos decimales, o None."""
    n = _num(valor) if not isinstance(valor, bool) else None
    return n if n is not None and math.isfinite(n) else None


def _texto_corto(valor, largo: int) -> str | None:
    texto = " ".join(str(valor).split()) if valor not in (None, "") else ""
    return texto[:largo] or None


def datos_de_factura(datos: dict) -> dict:
    """Número, identificación tributaria y líneas de detalle, saneados. Lo que no tenga forma de línea se descarta."""
    lineas = []
    for linea in datos.get("lineas") if isinstance(datos.get("lineas"), list) else []:
        if not isinstance(linea, dict):
            continue
        fila = {"descripcion": _texto_corto(linea.get("descripcion"), 120), "cantidad": _finito(linea.get("cantidad")),
                "total": _finito(linea.get("total"))}
        if fila["descripcion"] or fila["total"] is not None:
            lineas.append(fila)
    return {"numero_factura": _texto_corto(datos.get("numero_factura"), 60), "id_fiscal": _texto_corto(datos.get("id_fiscal"), 40),
            "lineas": lineas[:MAX_LINEAS]}


def extraer(contenido: bytes, mime: str, nombre: str, entidad_id: int | None = None, uso: str = "recibo") -> dict:
    """Devuelve {campos..., confianza, dudas, origen_dato, error}. `uso` etiqueta la llamada en `llamadas_modelo`."""
    activo = config.modo()["extraccion"] == "en vivo"
    datos, origen, error = None, "guardado", None
    if activo:
        try:
            datos = _con_cliente(contenido, mime, entidad_id, uso) if llm.activo() else _en_vivo(contenido, mime)
            origen = "en vivo"
        except llm.ErrorDelModelo as e:
            error = f"No se pudo leer el soporte: {e}"
        except Exception as e:  # la demostración no debe caerse por un fallo externo
            error = f"Fallo de la extracción en vivo: {type(e).__name__}"
    if datos is None and not activo:
        datos = _guardado(contenido)  # solo cuando no hay modelo configurado; un fallo en vivo nunca cae aquí
    if not isinstance(datos, dict):
        return {**{c: None for c in CAMPOS}, **datos_de_factura({}), "confianza": 0.0, "dudas": list(CAMPOS), "origen_dato": "sin datos",
                "error": error or "Sin modelo de lenguaje configurado y sin lectura guardada para este archivo: completar a mano."}
    salida = {c: datos.get(c) for c in CAMPOS}
    for c in ("subtotal", "impuesto", "propina", "total"):
        salida[c] = _num(salida[c])
    for c in ("comercio", "fecha", "metodo_pago", "canal_reserva", "ciudad"):
        salida[c] = str(salida[c])[:200] if salida[c] not in (None, "") else None
    if salida["fecha"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", salida["fecha"]):
        salida["fecha"] = None
    if salida["categoria"] not in config.CATEGORIAS:
        salida["categoria"] = "otros"
    salida["moneda"] = (str(salida["moneda"] or "")).upper()[:3] or None
    salida |= datos_de_factura(datos)
    try:
        salida["confianza"] = max(0.0, min(1.0, float(datos.get("confianza") or 0)))
    except (TypeError, ValueError):
        salida["confianza"] = 0.0
    dudas = datos.get("dudas")
    salida["dudas"] = [str(d)[:40] for d in dudas][:12] if isinstance(dudas, list) else []
    salida["origen_dato"] = origen
    salida["error"] = error
    return salida
