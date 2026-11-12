"""API v1: ingreso, sesión actual y salida. Contrato en `contracts/api-v1.md`."""
from fastapi import APIRouter, Depends, Request, Response

from ..api_v1 import PREFIJO, ErrorApi, escritura, persona, token_csrf
from ..api_v1.esquemas import Ingreso, Sesion, errores
from ..servicios import acceso, consultas, eventos

router = APIRouter(prefix=PREFIJO + "/auth", tags=["auth"])

# Lo que responde `acceso.autenticar` cuando el correo o la contraseña no coinciden; cualquier otro mensaje es un bloqueo
_CREDENCIALES = "Correo o contraseña incorrectos."


@router.post("/login", response_model=Sesion, responses=errores(401, 403, 422, 429))
def login(datos: Ingreso, response: Response):
    """Pública: no lleva token CSRF. El rol y la persona salen de la cuenta, nunca del cuerpo."""
    usuario, mensaje = acceso.autenticar(datos.correo, datos.clave)
    if not usuario:
        eventos.registrar("acceso", None, "ingreso fallido", datos.correo.strip().lower()[:80], "api v1")
        if mensaje != _CREDENCIALES:
            raise ErrorApi(429, "TOO_MANY_ATTEMPTS", mensaje)
        raise ErrorApi(401, "INVALID_CREDENTIALS", _CREDENCIALES)
    acceso.fijar(usuario)
    eventos.registrar("acceso", usuario["id"], "ingreso", usuario["correo"], "api v1")
    acceso.abrir_sesion(response, usuario["id"])
    return {"persona": consultas.persona(usuario), "csrf_token": token_csrf(response.token_sesion)}


@router.get("/me", response_model=Sesion, responses=errores(401))
def me(request: Request, yo: dict = Depends(persona)):
    return {"persona": consultas.persona(yo), "csrf_token": token_csrf(request.cookies.get(acceso.COOKIE))}


@router.post("/logout", status_code=204, response_class=Response, responses=errores(401, 403))
def logout(request: Request, yo: dict = Depends(escritura)):
    eventos.registrar("acceso", yo["id"], "salida", yo["correo"], "api v1")
    return acceso.cerrar_sesion(Response(status_code=204), request.cookies.get(acceso.COOKIE))
