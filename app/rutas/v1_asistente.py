"""API v1: el asistente, por escrito o dictado, para los tres permisos. Contrato en `contracts/api-v1.md`.

La pregunta sigue la misma vía que la plataforma (asesor, modelo con herramientas o consultas directas), con el mismo
tope diario por persona y el mismo rastro. El alcance lo pone la sesión: el colaborador ve lo suyo, el gestor además lo
de sus proyectos y administración todo. La voz la transcribe el modelo de lectura; el asesor solo recibe texto.
"""
import re

from fastapi import APIRouter, Depends, File, UploadFile

from .. import config
from ..api_v1 import PREFIJO, ErrorApi, escritura
from ..api_v1.esquemas import PreguntaAsistente, RespuestaAsistente, Transcripcion, errores
from ..servicios import asistente, llm
from .asistente import modo_visible

router = APIRouter(prefix=PREFIJO + "/asistente", tags=["asistente"])

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


def _con_permiso(yo: dict) -> None:
    """Cualquiera de los tres permisos; lo que ve cada uno lo decide `asistente.Alcance`."""
    if not asistente.Alcance(yo).valido:
        raise ErrorApi(403, "FORBIDDEN", "El asistente necesita una sesión válida.")


@router.post("", response_model=RespuestaAsistente, responses=errores(401, 403, 422))
def preguntar(datos: PreguntaAsistente, yo: dict = Depends(escritura)):
    """Para los tres permisos, cada uno con su alcance. Con el asesor puede tardar hasta un minuto; si no, responde la vía siguiente."""
    _con_permiso(yo)
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
    """Para los tres permisos. Devuelve la pregunta dictada en texto; no la responde ni la guarda."""
    _con_permiso(yo)
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
