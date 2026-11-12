"""Entrada del canal de Telegram."""
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .. import config
from ..servicios import telegram
from ..web import (
    _error_registrado,
)

router = APIRouter()


# ---------- canal de Telegram ----------
@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Entrada del bot. Solo Telegram conoce la cabecera secreta; todo lo demás se rechaza sin procesar."""
    secreto = config.TELEGRAM_WEBHOOK_SECRETO
    if not telegram.activo() or not secreto or \
            not secrets.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", "").encode(), secreto.encode()):
        return Response(status_code=403)
    try:
        entrega = await request.json()
    except ValueError:
        return Response(status_code=400)
    from starlette.concurrency import run_in_threadpool
    try:
        estado = await run_in_threadpool(telegram.procesar, entrega if isinstance(entrega, dict) else {})
    except Exception as e:   # se responde 200 para que Telegram no reintente sin fin; el fallo queda registrado
        _error_registrado(request, e)
        estado = "error"
    return {"ok": True, "estado": estado}
