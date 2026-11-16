"""Enlaces firmados de la cotización: «Ver en el vendedor» y «Ir a…» solo sirven en la sesión que los pidió.

`{vence}.{firma}`: HMAC con el token de la sesión como clave sobre lo que nombra el enlace y su vencimiento. No sirve en
otra sesión, para otro vuelo o tarifa ni pasados 5 minutos; no se guarda nada.
"""
import hashlib
import hmac
import re
import time
from urllib.parse import urlencode

from .acceso import API_V1

VIDA_ENLACE_S = 300   # 5 minutos: la web refresca la cotización antes de que venza


def _firma(sesion: str, partes: tuple, vence: int) -> str:
    mensaje = "|".join(str(p) for p in (*partes, vence)).encode()
    return hmac.new(sesion.encode(), mensaje, hashlib.sha256).hexdigest()[:32]


def _firmar(sesion: str, partes: tuple, ahora: float | None) -> str:
    """`{vence}.{firma}`: HMAC con el token de la sesión como clave sobre `partes` y el vencimiento. No sirve en otra
    sesión, para otras partes ni pasados 5 minutos; no se guarda nada."""
    vence = int((time.time() if ahora is None else ahora) + VIDA_ENLACE_S)
    return f"{vence}.{_firma(sesion, partes, vence)}"


def _firmado(token: str | None, sesion: str, partes: tuple) -> bool:
    vence, _, firma = (token or "").partition(".")
    if not (sesion and re.fullmatch(r"[0-9]{1,12}", vence) and firma and int(vence) >= time.time()):
        return False
    return hmac.compare_digest(firma, _firma(sesion, partes, int(vence)))


def token_vendedor(sesion: str, sid: int, vuelo_id: int, ahora: float | None = None) -> str:
    return _firmar(sesion, ("vendedor-v1", sid, vuelo_id), ahora)


def token_valido(token: str | None, sesion: str, sid: int, vuelo_id: int) -> bool:
    return _firmado(token, sesion, ("vendedor-v1", sid, vuelo_id))


def url_ir(sesion: str, sid: int, vuelo_id: int, vendedor: str, tarifa: str, ahora: float | None = None) -> str:
    """La página de «Ir a…» de esa tarifa de ese vendedor, firmada: abrirla sin el token de esta sesión no hace el pedido."""
    t = _firmar(sesion, ("ir-v1", sid, vuelo_id, vendedor, tarifa), ahora)
    return f"{API_V1}/cotizaciones/{sid}/vuelos/{vuelo_id}/ir?{urlencode({'vendedor': vendedor, 'tarifa': tarifa, 't': t})}"


def token_ir_valido(token: str | None, sesion: str, sid: int, vuelo_id: int, vendedor: str, tarifa: str) -> bool:
    return _firmado(token, sesion, ("ir-v1", sid, vuelo_id, vendedor, tarifa))


def url_vendedor(sesion: str, sid: int, vuelo_id: int) -> str:
    return f"{API_V1}/cotizaciones/{sid}/vuelos/{vuelo_id}/vendedor?t={token_vendedor(sesion, sid, vuelo_id)}"
