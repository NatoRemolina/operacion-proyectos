"""Guarda y lee los soportes: en Supabase Storage si está configurado, si no en una carpeta local."""
import re

import httpx

from .. import config


def _remoto() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)


def _cabeceras() -> dict:
    return {"Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}", "apikey": config.SUPABASE_SERVICE_KEY}


CLAVE_VALIDA = re.compile(r"^[a-f0-9]{2}/[a-f0-9]{64}\.(jpg|png|webp|pdf|eml)$")


def clave(huella: str, extension: str) -> str:
    """Clave de almacenamiento derivada del contenido. El nombre original nunca forma parte de la ruta."""
    return f"{huella[:2]}/{huella}.{extension}"


def guardar(ruta: str, contenido: bytes, mime: str) -> str:
    if not CLAVE_VALIDA.match(ruta):
        raise ValueError("Clave de almacenamiento no válida")
    if _remoto():
        url = f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{ruta}"
        r = httpx.post(url, content=contenido, timeout=30,
                       headers={**_cabeceras(), "Content-Type": mime, "x-upsert": "true"})
        r.raise_for_status()
        return f"supabase:{ruta}"
    destino = config.DIR_ARCHIVOS / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return f"local:{ruta}"


def leer(ruta: str) -> bytes | None:
    tipo, _, camino = ruta.partition(":")
    if tipo == "supabase" and _remoto():
        r = httpx.get(f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{camino}",
                      headers=_cabeceras(), timeout=30)
        return r.content if r.status_code == 200 else None
    archivo = config.DIR_ARCHIVOS / camino
    return archivo.read_bytes() if archivo.is_file() else None
