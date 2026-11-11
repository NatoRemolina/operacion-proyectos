"""Convierte un soporte (foto, PDF o correo) en datos estructurados.

Con clave configurada se consulta un modelo multimodal por API. Sin clave se usan las
extracciones guardadas de los documentos de ejemplo, para que la demostración funcione
igual. El resultado siempre indica su origen: "en vivo" o "guardado".
"""
import base64
import email
import hashlib
import json
import re
from email import policy

import httpx

from .. import config

CAMPOS = ["comercio", "fecha", "categoria", "subtotal", "impuesto", "propina", "total",
          "moneda", "metodo_pago", "canal_reserva", "ciudad"]

INSTRUCCION = f"""Eres un asistente de contabilidad. Lee el soporte de gasto adjunto y devuelve SOLO un objeto JSON con:
- comercio: nombre del comercio o proveedor
- fecha: fecha del gasto en formato AAAA-MM-DD (ten en cuenta que en Europa el día va antes del mes)
- categoria: una de {list(config.CATEGORIAS)}
- subtotal, impuesto, propina, total: números con punto decimal, o null si no aparecen
- moneda: código ISO de tres letras (USD, EUR, COP...)
- metodo_pago: texto corto o null
- canal_reserva: "directo" si se compró al proveedor, o el nombre de la agencia o intermediario si lo hay, o null
- ciudad: ciudad del gasto o null
- confianza: número entre 0 y 1 con tu seguridad sobre el conjunto
- dudas: lista de campos que no se leen con claridad (vacía si todo es legible)
No inventes valores: si algo no se lee, usa null y nómbralo en dudas."""


def _correo(contenido: bytes):
    """Devuelve (texto del correo, adjunto o None, mime del adjunto)."""
    msg = email.message_from_bytes(contenido, policy=policy.default)
    for parte in msg.iter_attachments():
        tipo = parte.get_content_type()
        if tipo == "application/pdf" or tipo.startswith("image/"):
            return None, parte.get_payload(decode=True), tipo
    cuerpo = msg.get_body(preferencelist=("plain", "html"))
    texto = cuerpo.get_content() if cuerpo else ""
    texto = re.sub(r"<[^>]+>", " ", texto)
    return f"De: {msg['from']}\nAsunto: {msg['subject']}\nFecha: {msg['date']}\n\n{texto}", None, None


def _bloque(contenido: bytes, mime: str) -> dict:
    datos = base64.standard_b64encode(contenido).decode()
    tipo = "document" if mime == "application/pdf" else "image"
    return {"type": tipo, "source": {"type": "base64", "media_type": mime, "data": datos}}


def _en_vivo(contenido: bytes, mime: str) -> dict:
    partes = []
    if mime == "message/rfc822":
        texto, adjunto, mime_adjunto = _correo(contenido)
        partes.append(_bloque(adjunto, mime_adjunto) if adjunto else {"type": "text", "text": texto})
    else:
        partes.append(_bloque(contenido, mime))
    partes.append({"type": "text", "text": INSTRUCCION})
    r = httpx.post(
        config.MODELO_API_URL, timeout=90,
        headers={"x-api-key": config.MODELO_API_KEY, "content-type": "application/json", **config.MODELO_CABECERAS},
        json={"model": config.MODELO_NOMBRE, "max_tokens": 1024, "messages": [{"role": "user", "content": partes}]},
    )
    r.raise_for_status()
    texto = "".join(b.get("text", "") for b in r.json().get("content", []))
    return json.loads(re.search(r"\{.*\}", texto, re.S).group(0))


def _guardado(contenido: bytes) -> dict | None:
    """Lectura guardada de un soporte de ejemplo. Se reconoce por el contenido, no por el nombre del archivo."""
    archivo = config.DIR_EJEMPLOS / "esperados.json"
    if not archivo.is_file():
        return None
    huella = hashlib.sha256(contenido).hexdigest()
    for nombre, lectura in json.loads(archivo.read_text()).items():
        ejemplo = config.DIR_EJEMPLOS / nombre
        if ejemplo.is_file() and hashlib.sha256(ejemplo.read_bytes()).hexdigest() == huella:
            return lectura
    return None


def _num(valor):
    try:
        return None if valor in (None, "") else round(float(valor), 2)
    except (TypeError, ValueError):
        return None


def extraer(contenido: bytes, mime: str, nombre: str) -> dict:
    """Devuelve {campos..., confianza, dudas, origen_dato, error}."""
    activo = config.modo()["extraccion"] == "en vivo"
    datos, origen, error = None, "guardado", None
    if activo:
        try:
            datos, origen = _en_vivo(contenido, mime), "en vivo"
        except Exception as e:  # la demostración no debe caerse por un fallo externo
            error = f"Fallo de la extracción en vivo: {type(e).__name__}"
    if datos is None and not activo:
        datos = _guardado(contenido)  # solo cuando no hay modelo configurado; un fallo en vivo nunca cae aquí
    if not isinstance(datos, dict):
        return {**{c: None for c in CAMPOS}, "confianza": 0.0, "dudas": list(CAMPOS), "origen_dato": "sin datos",
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
    try:
        salida["confianza"] = max(0.0, min(1.0, float(datos.get("confianza") or 0)))
    except (TypeError, ValueError):
        salida["confianza"] = 0.0
    dudas = datos.get("dudas")
    salida["dudas"] = [str(d)[:40] for d in dudas][:12] if isinstance(dudas, list) else []
    salida["origen_dato"] = origen
    salida["error"] = error
    return salida
