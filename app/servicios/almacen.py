"""Guarda y lee los soportes: en Supabase Storage si está configurado, si no en una carpeta local."""
import httpx

from .. import config


def _remoto() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)


def _cabeceras() -> dict:
    return {"Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}", "apikey": config.SUPABASE_SERVICE_KEY}


def guardar(ruta: str, contenido: bytes, mime: str) -> str:
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
