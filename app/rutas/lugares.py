"""Buscador de origen y destino: lugares, aeropuertos y países del mundo para el formulario de cotización."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..servicios import geografia
from ..web import _yo

router = APIRouter()


@router.get("/lugares/buscar")
def lugares_buscar(q: str = "", limite: int = 8, google: int = 0):
    """Sugerencias mientras se escribe. Sin `google`, solo datos locales (al instante); con `google=1`, tras una pausa,
    suma las de Google. Las búsquedas no se registran una por una: se registra el lugar elegido al cotizar."""
    resultados, aviso = geografia.buscar_con_aviso(q[:80], min(max(limite, 1), 20), _yo() or None, bool(google))
    return JSONResponse({"resultados": resultados, "aviso_google": aviso})
