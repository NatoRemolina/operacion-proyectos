"""Conecta el bot de Telegram con la plataforma publicada.

Uso (desde la raíz del repositorio, con las variables de Telegram en .env):
    python -m datos.telegram_webhook https://<dirección-pública>     registra la entrada del bot
    python -m datos.telegram_webhook --estado                        muestra cómo está registrado
    python -m datos.telegram_webhook --preparar                      genera el secreto y anota el nombre del bot en .env

Nunca imprime la clave del bot ni el secreto.
"""
import secrets
import sys

from app import config
from app.servicios import telegram

ORDENES = [{"command": "viaje", "description": "Ver o fijar el viaje al que van mis gastos"},
           {"command": "ayuda", "description": "Cómo enviar recibos"}]


def _anotar(nombre: str, valor: str):
    archivo = config.RAIZ / ".env"
    lineas = [l for l in (archivo.read_text().splitlines() if archivo.is_file() else []) if not l.startswith(f"{nombre}=")]
    archivo.write_text("\n".join(lineas + [f"{nombre}={valor}"]) + "\n")


def preparar():
    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("Falta TELEGRAM_BOT_TOKEN en .env (la clave que entrega BotFather).")
    yo = telegram._llamar("getMe")
    _anotar("TELEGRAM_BOT_NOMBRE", yo["username"])
    if not config.TELEGRAM_WEBHOOK_SECRETO:
        _anotar("TELEGRAM_WEBHOOK_SECRETO", secrets.token_urlsafe(32))
    print(f"Bot: @{yo['username']}. Nombre y secreto anotados en .env.")


def estado():
    info = telegram._llamar("getWebhookInfo")
    registrada = info.get("url") or "(ninguna)"
    print(f"Entrada registrada: {registrada}")
    print(f"Entregas pendientes: {info.get('pending_update_count', 0)}")
    if info.get("last_error_message"):
        print(f"Último error: {info['last_error_message']}")


def registrar(base: str):
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_WEBHOOK_SECRETO):
        sys.exit("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_WEBHOOK_SECRETO en .env. Ejecuta primero --preparar.")
    if not base.startswith("https://"):
        sys.exit("La dirección debe empezar por https://")
    # Dos entregas a la vez como máximo: un álbum de fotos son varias entregas simultáneas
    telegram._llamar("setWebhook", url=base.rstrip("/") + "/telegram/webhook", secret_token=config.TELEGRAM_WEBHOOK_SECRETO,
                     allowed_updates=["message", "callback_query"], max_connections=2, drop_pending_updates=True)
    telegram._llamar("setMyCommands", commands=ORDENES)
    estado()


if __name__ == "__main__":
    argumento = sys.argv[1] if len(sys.argv) > 1 else "--estado"
    {"--estado": estado, "--preparar": preparar}.get(argumento, lambda: registrar(argumento))()
