"""API v1: la cuenta propia — mis datos, cambiar mi contraseña y el vínculo con Telegram.

Contrato en `contracts/api-v1.md`, sección «Mi cuenta». La cuenta sale siempre de la sesión: nadie toca la de otra persona
por aquí. La regla vive en `app/servicios/usuarios.py` y `telegram.py`, las mismas que usa la pantalla actual `/mi-cuenta`.
"""
from fastapi import APIRouter, Depends, Response

from .. import db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, persona, token_csrf
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_usuarios import CambioMiClave, ClaveCambiada, MiCuenta, VinculoTelegram
from ..servicios import acceso, consultas, telegram, usuarios

router = APIRouter(prefix=PREFIJO + "/cuenta", tags=["cuenta"])

CANAL_APAGADO = "El canal de Telegram no está configurado en esta instalación. Los gastos entran por la plataforma."


def _cuenta(yo: dict) -> dict:
    fila = db.uno("select telegram_chat_id, telegram_usuario from usuarios where id=:i", i=yo["id"])
    return {"persona": consultas.persona(yo), "rol_texto": acceso.NOMBRE_ROL.get(yo["rol"], yo["rol"]),
            "telegram": {"vinculado": bool(fila["telegram_chat_id"]), "usuario": fila["telegram_usuario"] or None,
                         "canal_activo": telegram.activo()}}


@router.get("", response_model=MiCuenta, responses=errores(401))
def mi_cuenta(yo: dict = Depends(persona)):
    """Mis datos y el estado de Telegram. `canal_activo` dice si el bot está configurado (en producción hoy no lo está)."""
    return _cuenta(yo)


@router.post("/clave", response_model=ClaveCambiada, responses=errores(401, 403, 422))
def cambiar_clave(datos: CambioMiClave, response: Response, yo: dict = Depends(escritura)):
    """Exige la actual. Cierra todas las sesiones de la persona y abre una nueva en esta: la cookie y el token CSRF cambian."""
    try:
        usuarios.cambiar_mi_clave(yo, datos.actual, datos.nueva)
    except usuarios.DatosInvalidos as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {e.campo: str(e)}) from None
    acceso.abrir_sesion(response, yo["id"])
    return {"csrf_token": token_csrf(response.token_sesion), "mensaje": "Contraseña cambiada. Se cerraron tus otras sesiones."}


@router.post("/telegram/vinculo", response_model=VinculoTelegram, responses=errores(401, 403, 409))
def vincular_telegram(yo: dict = Depends(escritura)):
    """Un código de un solo uso para vincular el chat (vale unos minutos; en la base queda solo su huella).
    Con el canal apagado: 409 `INVALID_STATE`."""
    if not telegram.activo():
        raise ErrorApi(409, "INVALID_STATE", CANAL_APAGADO)
    return telegram.nuevo_vinculo(yo["id"])


@router.post("/telegram/desvincular", response_model=MiCuenta, responses=errores(401, 403))
def desvincular_telegram(yo: dict = Depends(escritura)):
    usuarios.desvincular_telegram(yo)
    return _cuenta(yo)
