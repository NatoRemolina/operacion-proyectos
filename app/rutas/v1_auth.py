"""API v1: ingreso, sesión actual y salida. Contrato en `contracts/api-v1.md`."""
from fastapi import APIRouter, Depends, Request, Response

from ..api_v1 import PREFIJO, ErrorApi, datos_demostracion, escritura, persona, token_csrf
from ..api_v1.esquemas import Ingreso, Sesion, errores
from ..servicios import acceso, consultas, eventos, intentos

router = APIRouter(prefix=PREFIJO + "/auth", tags=["auth"])

# Lo que responde `acceso.autenticar` cuando el correo o la contraseña no coinciden; cualquier otro mensaje es un bloqueo
_CREDENCIALES = "Correo o contraseña incorrectos."


@router.post("/login", response_model=Sesion, responses=errores(401, 403, 422, 429))
def login(datos: Ingreso, request: Request, response: Response):
    """Pública: no lleva token CSRF. El rol y la persona salen de la cuenta, nunca del cuerpo.
    Con demasiados fallos recientes desde la dirección o con el correo, 429 antes de mirar la contraseña."""
    if intentos.limitado(request.state.direccion, datos.correo):
        if intentos.avisar_limite(request.state.direccion, datos.correo):   # una vez por ventana
            eventos.registrar("acceso", None, "ingreso limitado", datos.correo.strip().lower()[:80], "api v1")
        raise ErrorApi(429, "TOO_MANY_ATTEMPTS", intentos.DEMASIADOS)
    usuario, mensaje = acceso.autenticar(datos.correo, datos.clave)
    if not usuario:
        intentos.anotar_fallo(request.state.direccion, datos.correo)
        eventos.registrar("acceso", None, "ingreso fallido", datos.correo.strip().lower()[:80], "api v1")
        if mensaje != _CREDENCIALES:
            raise ErrorApi(429, "TOO_MANY_ATTEMPTS", mensaje)
        raise ErrorApi(401, "INVALID_CREDENTIALS", _CREDENCIALES)
    intentos.anotar_exito(request.state.direccion, datos.correo)
    acceso.fijar(usuario)
    eventos.registrar("acceso", usuario["id"], "ingreso", usuario["correo"], "api v1")
    acceso.abrir_sesion(response, usuario["id"])
    return {"persona": consultas.persona(usuario), "csrf_token": token_csrf(response.token_sesion),
            "demostracion": datos_demostracion()}


@router.get("/me", response_model=Sesion, responses=errores(401))
def me(request: Request, yo: dict = Depends(persona)):
    return {"persona": consultas.persona(yo), "csrf_token": token_csrf(request.cookies.get(acceso.COOKIE)),
            "demostracion": datos_demostracion()}


@router.post("/logout", status_code=204, response_class=Response, responses=errores(401, 403))
def logout(request: Request, yo: dict = Depends(escritura)):
    eventos.registrar("acceso", yo["id"], "salida", yo["correo"], "api v1")
    return acceso.cerrar_sesion(Response(status_code=204), request.cookies.get(acceso.COOKIE))
