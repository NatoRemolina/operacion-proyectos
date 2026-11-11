"""Convierte un soporte (foto, PDF o correo) en datos estructurados.

Con clave configurada se consulta un modelo multimodal por API. Sin clave se usan las
extracciones guardadas de los documentos de ejemplo, para que la demostración funcione
igual. El resultado siempre indica su origen: "en vivo" o "guardado".
"""
import base64
import email
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


def _guardado(nombre: str) -> dict | None:
    archivo = config.DIR_EJEMPLOS / "esperados.json"
    if not archivo.is_file():
        return None
    return json.loads(archivo.read_text()).get(nombre)


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
    if datos is None:
        datos = _guardado(nombre)
    if datos is None:
        return {**{c: None for c in CAMPOS}, "confianza": 0.0, "dudas": CAMPOS, "origen_dato": "sin datos",
                "error": error or "Sin clave del modelo y sin extracción guardada para este archivo: completar a mano."}
    salida = {c: datos.get(c) for c in CAMPOS}
    for c in ("subtotal", "impuesto", "propina", "total"):
        salida[c] = _num(salida[c])
    if salida["categoria"] not in config.CATEGORIAS:
        salida["categoria"] = "otros"
    salida["moneda"] = (salida["moneda"] or "").upper() or None
    salida["confianza"] = max(0.0, min(1.0, float(datos.get("confianza") or 0)))
    salida["dudas"] = list(datos.get("dudas") or [])
    salida["origen_dato"] = origen
    salida["error"] = error
    return salida
