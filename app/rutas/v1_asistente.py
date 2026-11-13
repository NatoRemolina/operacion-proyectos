"""API v1: asistente de administración, por escrito o dictado. Contrato en `contracts/api-v1.md`.

La pregunta sigue la misma vía que la pantalla `/admin/asistente` (asesor, modelo con herramientas o consultas directas),
con el mismo tope diario y el mismo rastro. La voz la transcribe el modelo de lectura; el asesor solo recibe texto.
"""
import re

from fastapi import APIRouter, Depends, File, UploadFile

from .. import config
from ..api_v1 import PREFIJO, ErrorApi, escritura
from ..api_v1.esquemas import PreguntaAsistente, RespuestaAsistente, Transcripcion, errores
from ..servicios import acceso, asistente, llm
from .asistente import modo_visible

router = APIRouter(prefix=PREFIJO + "/asistente", tags=["administracion"])

# Las fuentes traen el enlace de la pantalla actual; aquí se traducen a un destino que cada interfaz enlaza a su manera
_DESTINOS = ((re.compile(r"^/gastos/(\d+)$"), "gasto"), (re.compile(r"^/viaje/(\d+)$"), "viaje"),
             (re.compile(r"^/viajes/(\d+)$"), "cotizacion"))
AUDIO_WAV = ("audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave")


def _destino(enlace: str | None) -> dict | None:
    for patron, tipo in _DESTINOS:
        m = patron.match(enlace or "")
        if m:
            return {"tipo": tipo, "id": int(m.group(1))}
    return None


def _solo_admin(yo: dict) -> None:
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "El asistente es solo para administración.")


@router.post("", response_model=RespuestaAsistente, responses=errores(401, 403, 422))
def preguntar(datos: PreguntaAsistente, yo: dict = Depends(escritura)):
    """Solo administración. Puede tardar hasta un minuto con el asesor; si no responde, contesta la vía siguiente."""
    _solo_admin(yo)
    if not datos.pregunta.strip():
        raise ErrorApi(422, "VALIDATION_ERROR", "Escribe una pregunta.", {"pregunta": "Escribe una pregunta."})
    r = asistente.responder(datos.pregunta, yo)
    return {"texto": r["texto"], "modo": r["modo"], "modo_texto": modo_visible(r["modo"])[0],
            "fuentes": [{"tipo": f["tipo"], "codigo": f["codigo"], "destino": _destino(f["enlace"])} for f in r["fuentes"]],
            "herramientas": r["herramientas"], "duracion_ms": r["duracion_ms"],
            "usadas": asistente.usadas_hoy(yo["id"]), "tope": asistente.tope_diario()}


@router.post("/voz", response_model=Transcripcion, responses=errores(401, 403, 413, 415, 422, 429, 503))
def dictar(audio: UploadFile = File(..., description="La pregunta grabada, en WAV (la web graba y convierte en el navegador)."),
           yo: dict = Depends(escritura)):
    """Solo administración. Devuelve la pregunta dictada en texto; no la responde ni la guarda."""
    _solo_admin(yo)
    contenido = audio.file.read(config.MAX_BYTES_SOPORTE + 1)
    if len(contenido) > config.MAX_BYTES_SOPORTE:
        raise ErrorApi(413, "PAYLOAD_TOO_LARGE", "El audio es demasiado largo: graba una pregunta más corta.")
    if not contenido:
        raise ErrorApi(422, "VALIDATION_ERROR", "El audio llegó vacío.", {"audio": "El audio llegó vacío."})
    if (audio.content_type or "").split(";")[0].strip().lower() not in AUDIO_WAV or contenido[:4] != b"RIFF" or contenido[8:12] != b"WAVE":
        raise ErrorApi(415, "UNSUPPORTED_MEDIA_TYPE", "El audio debe llegar en WAV.")
    if not asistente.puede_dictar():
        raise ErrorApi(503, "SERVICE_UNAVAILABLE", "La transcripción de voz no está configurada. Escribe la pregunta.")
    try:
        return {"texto": asistente.transcribir_pregunta(contenido, "audio/wav", yo)}
    except asistente.TopeDeDictado as e:
        raise ErrorApi(429, "TOO_MANY_REQUESTS", str(e)) from None
    except llm.ErrorDelModelo:
        raise ErrorApi(503, "SERVICE_UNAVAILABLE", "No se pudo transcribir el audio ahora. Intenta de nuevo o escribe la pregunta.") from None
