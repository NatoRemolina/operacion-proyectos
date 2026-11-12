"""Cliente único del modelo de lenguaje.

Toda llamada pasa por aquí: reintentos ante saturación, respuesta vacía o truncada tratada
como error, y un registro por llamada (tokens, tiempo, motivo de parada) para el monitoreo.
El proveedor se elige por configuración; este módulo habla el formato `generateContent`.
"""
import base64
import json
import time
from contextvars import ContextVar

import httpx

from .. import config, db

ESPERA_S = 45
REINTENTABLES = {429, 500, 502, 503, 504}


class ErrorDelModelo(RuntimeError):
    """Fallo que quien llama debe tratar como 'no hay lectura': nunca como dato."""


def activo() -> bool:
    return bool(config.MODELO_API_URL and config.MODELO_API_KEY and config.MODELO_NOMBRE) and config.MODELO_FORMATO == "gemini"


def parte_archivo(contenido: bytes, mime: str) -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.standard_b64encode(contenido).decode()}}


def parte_texto(texto: str) -> dict:
    return {"text": texto}


def _registrar(uso: str, entidad_id, cuerpo: dict | None, ms: int, estado_http: int, error: str = ""):
    medida = (cuerpo or {}).get("usageMetadata", {})
    candidato = ((cuerpo or {}).get("candidates") or [{}])[0]
    try:
        db.insertar("llamadas_modelo", momento=db.ahora(), uso=uso, entidad_id=entidad_id, modelo=config.MODELO_NOMBRE,
                    tokens_entrada=medida.get("promptTokenCount"),
                    tokens_salida=(medida.get("candidatesTokenCount") or 0) + (medida.get("thoughtsTokenCount") or 0),
                    latencia_ms=ms, estado_http=estado_http, motivo_parada=candidato.get("finishReason"), error=error[:300])
    except Exception:
        pass  # el registro nunca debe tumbar la operación


# Canales que deben responder en segundos (un chat) piden un solo intento con espera corta
RAPIDO: ContextVar[bool] = ContextVar("lectura_rapida", default=False)


def generar(contenidos: list[dict], *, uso: str, entidad_id: int | None = None, sistema: str = "",
            esquema: dict | None = None, herramientas: list[dict] | None = None, tope_salida: int = 8192) -> dict:
    """Devuelve el primer candidato ({'content': {'parts': [...]}, 'finishReason': ...}) o lanza ErrorDelModelo."""
    cuerpo: dict = {"contents": contenidos, "generationConfig": {"maxOutputTokens": tope_salida}}
    if sistema:
        cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}
    if esquema:
        cuerpo["generationConfig"].update(responseMimeType="application/json", responseSchema=esquema)
    if herramientas:
        cuerpo["tools"] = [{"functionDeclarations": herramientas}]
    url = f"{config.MODELO_API_URL}/models/{config.MODELO_NOMBRE}:generateContent"
    ultimo = ""
    rapido = RAPIDO.get()
    for intento in range(1 if rapido else 3):
        inicio = time.perf_counter()
        try:
            r = httpx.post(url, json=cuerpo, timeout=min(ESPERA_S, 40) if rapido else ESPERA_S,
                           headers={"x-goog-api-key": config.MODELO_API_KEY, **config.MODELO_CABECERAS})
        except httpx.HTTPError as e:
            ultimo = type(e).__name__
            _registrar(uso, entidad_id, None, int((time.perf_counter() - inicio) * 1000), 0, ultimo)
            time.sleep(1 + intento)
            continue
        ms = int((time.perf_counter() - inicio) * 1000)
        if r.status_code in REINTENTABLES:
            ultimo = f"HTTP {r.status_code}"
            _registrar(uso, entidad_id, None, ms, r.status_code, ultimo)
            time.sleep(2 * (intento + 1))
            continue
        try:
            datos = r.json()
        except ValueError:
            datos = {}
        if r.status_code != 200:
            mensaje = (datos.get("error") or {}).get("message", "")[:200]
            _registrar(uso, entidad_id, None, ms, r.status_code, mensaje)
            raise ErrorDelModelo(f"El modelo rechazó la petición (HTTP {r.status_code}).")
        candidato = (datos.get("candidates") or [{}])[0]
        partes = (candidato.get("content") or {}).get("parts") or []
        motivo = candidato.get("finishReason")
        if not partes:
            bloqueo = (datos.get("promptFeedback") or {}).get("blockReason")
            _registrar(uso, entidad_id, datos, ms, 200, f"sin contenido ({bloqueo or motivo})")
            raise ErrorDelModelo("El modelo no devolvió contenido." if not bloqueo else "El modelo declinó leer este contenido.")
        if motivo == "MAX_TOKENS":
            _registrar(uso, entidad_id, datos, ms, 200, "respuesta truncada")
            raise ErrorDelModelo("La respuesta del modelo quedó truncada.")
        _registrar(uso, entidad_id, datos, ms, 200)
        return candidato
    raise ErrorDelModelo(f"El modelo no respondió ({ultimo}).")


def texto_de(candidato: dict) -> str:
    return "".join(p.get("text", "") for p in candidato["content"]["parts"] if "text" in p and not p.get("thought")).strip()


def json_de(candidato: dict) -> dict:
    try:
        datos = json.loads(texto_de(candidato))
    except ValueError as e:
        raise ErrorDelModelo("El modelo no devolvió un JSON válido.") from e
    if not isinstance(datos, dict):
        raise ErrorDelModelo("El modelo devolvió un JSON con forma inesperada.")
    return datos
