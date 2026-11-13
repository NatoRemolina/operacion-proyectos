"""Buzón de correo simulado: lee los correos (.eml) y las confirmaciones en HTML de la carpeta de ejemplos como si
llegaran a un buzón de gastos. Es una demostración del canal «correo»: no se conecta a ningún buzón real.

Lo usan la pantalla de carga de administración (`/gastos/cargar`, `/gastos/ejemplos`) y la API v1 (`/api/v1/buzon`).
La lectura y la validación son las de cualquier recibo (`gastos.registrar_envio`).
"""
from pathlib import Path

from .. import config
from . import extraccion
from . import gastos as soportes

FORMATOS = (".eml", ".html")
AVISO = ("Buzón simulado: lee los correos de ejemplo de la plataforma como si llegaran a un buzón de gastos. "
         "No está conectado a ningún correo real.")


def nombres() -> list[str]:
    """Los correos y confirmaciones que hay en el buzón simulado, por nombre."""
    return sorted(p.name for p in config.DIR_EJEMPLOS.iterdir() if p.is_file() and p.suffix in FORMATOS)


def archivo(nombre: str, formatos: tuple[str, ...] | None = None) -> Path | None:
    """El archivo de ejemplo con ese nombre, sin salir de la carpeta (se ignora cualquier ruta). None si no existe
    o, con `formatos`, si no es de esos formatos."""
    ruta = config.DIR_EJEMPLOS / Path(nombre or "").name
    if not ruta.name or not ruta.is_file() or (formatos and ruta.suffix not in formatos):
        return None
    return ruta


def mensajes() -> list[dict]:
    """Lo que hay en el buzón: nombre, formato y, si es un correo, de quién llegó y con qué asunto."""
    salida = []
    for nombre in nombres():
        es_correo = nombre.endswith(".eml")
        cabecera = extraccion.remitente_y_asunto(archivo(nombre).read_bytes()) if es_correo else {}
        salida.append({"nombre": nombre, "formato": "correo" if es_correo else "html",
                       "remitente": cabecera.get("remitente"), "asunto": cabecera.get("asunto")})
    return salida


def leer(lista: list[str], usuario: dict, viaje: dict | None) -> dict:
    """Lee cada correo como un recibo que llega por el canal «correo». Devuelve {gastos: [id], errores: [{nombre, mensaje}]}.
    Leer dos veces el mismo correo crea otro gasto, que las reglas marcan como posible duplicado."""
    gastos, errores = [], []
    for nombre in lista:
        ruta = archivo(nombre, FORMATOS)
        if not ruta:
            errores.append({"nombre": Path(nombre or "").name or nombre, "mensaje": "No está en el buzón simulado."})
            continue
        try:
            gid, _ = soportes.registrar_envio(ruta.read_bytes(), ruta.name, "correo", usuario, viaje)
            gastos.append(gid)
        except soportes.SoporteRechazado as e:
            errores.append({"nombre": ruta.name, "mensaje": str(e)})
    return {"gastos": gastos, "errores": errores}
