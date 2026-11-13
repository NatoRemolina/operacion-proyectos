"""API v1: cuentas y cargos, solo para administración. Contrato en `contracts/api-v1.md`, sección «Usuarios y cargos».

La regla vive en `app/servicios/usuarios.py`, la misma que usa la pantalla actual: mismas protecciones y mismos eventos.
"""
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError

from .. import db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, solo_admin
from ..api_v1.esquemas import errores
from ..api_v1.esquemas_usuarios import (
    CambioCargo,
    CambioCargoCatalogo,
    CambioEstadoCuenta,
    CambioProyectos,
    CambioRol,
    Cargo,
    ListaCargos,
    ListaUsuarios,
    NuevaClave,
    NuevaCuenta,
    NuevoCargo,
    ResultadoUsuario,
)
from ..servicios import acceso, consultas, usuarios, viajes

router = APIRouter(prefix=PREFIJO, tags=["usuarios"])


def pagina_estricta(limite: int = Query(20, ge=1, le=100, description="Cuántos elementos devolver (1 a 100)."),
                    cursor: str | None = Query(None, description="El valor de `siguiente` de la página anterior.")) -> tuple[int, int | None]:
    """La misma paginación que `api_v1.pagina`, con el cursor solo de dígitos ASCII: «²» o «٣» pasan `isdigit` y harían
    fallar `int` con un 500. Va aquí para no cambiar el borde común de la API."""
    if not cursor:
        return limite, None
    if not re.fullmatch(r"[1-9][0-9]{0,17}", cursor):
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"cursor": "El cursor no es válido. Usa el valor de `siguiente`."})
    return limite, int(cursor)


def _admin_que_escribe(yo: dict = Depends(escritura)) -> dict:
    if not acceso.es_admin(yo):
        raise ErrorApi(403, "FORBIDDEN", "Esta operación es solo para administración.")
    return yo


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _invalido(e: usuarios.DatosInvalidos) -> ErrorApi:
    return ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {e.campo: str(e)})


def _forma(u: dict, proyectos: dict[int, list[int]], nombres: dict[int, str]) -> dict:
    return {"id": u["id"], "codigo": viajes.codigo_persona(u["id"]), "correo": u["correo"], "nombre": u["nombre"], "rol": u["rol"],
            "rol_texto": acceso.NOMBRE_ROL.get(u["rol"], u["rol"]),
            "cargo": {"id": u["cargo_id"], "nombre": u["cargo"]} if u["cargo_id"] else None,
            "proyectos": [{"id": p, "nombre": nombres.get(p, f"Proyecto {p}")} for p in proyectos.get(u["id"], [])],
            "activo": bool(u["activo"]),
            "telegram": {"vinculado": bool(u["telegram_chat_id"]), "usuario": u["telegram_usuario"] or None},
            "ultima_sesion": consultas.instante(u["ultima"]), "creado": consultas.instante(u["creado"])}


def _nombres_de_proyectos() -> dict[int, str]:
    return {p["id"]: p["nombre"] for p in db.todos("select id, nombre from proyectos")}


def _usuario(uid: int) -> dict:
    return _forma(usuarios.uno(uid), usuarios.proyectos_por_gestor(), _nombres_de_proyectos())


def _cuenta(uid: int) -> dict:
    """La fila completa de la cuenta, como la usa el servicio. 404 si no existe."""
    u = db.uno("select * from usuarios where id=:i", i=uid)
    if not u:
        raise _no_encontrado()
    return u


# ---------- cuentas ----------
@router.get("/usuarios", response_model=ListaUsuarios, responses=errores(401, 403, 422))
def lista(paginacion: tuple = Depends(pagina_estricta), yo: dict = Depends(solo_admin)):
    """Todas las cuentas, activas o no, la más reciente primero."""
    limite, cursor = paginacion
    filas = usuarios.lista(limite + 1, cursor, descendente=True)
    proyectos, nombres = usuarios.proyectos_por_gestor(), _nombres_de_proyectos()
    items = [_forma(u, proyectos, nombres) for u in filas[:limite]]
    return {"items": items, "siguiente": str(items[-1]["id"]) if len(filas) > limite else None}


@router.post("/usuarios", status_code=201, response_model=ResultadoUsuario, responses=errores(401, 403, 422))
def crear(datos: NuevaCuenta, yo: dict = Depends(_admin_que_escribe)):
    """La contraseña inicial nunca se devuelve. Deja el evento `cuenta creada`."""
    problema = usuarios.problema_de_cuenta(datos.correo, datos.rol, datos.clave, datos.cargo_id or None)
    if problema:
        raise _invalido(problema)
    try:
        uid = usuarios.crear(datos.correo, datos.nombre, datos.rol, datos.clave, None, datos.cargo_id or None, yo)
    except (ValueError, IntegrityError):   # otra petición creó el mismo correo entre la comprobación y la escritura
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"correo": "Ya existe una cuenta con ese correo."}) from None
    return {"usuario": _usuario(uid), "mensaje": "Cuenta creada. Comparte la contraseña inicial por un canal seguro."}


@router.post("/usuarios/{id}/rol", response_model=ResultadoUsuario, responses=errores(401, 403, 404, 409, 422))
def cambiar_rol(id: int, datos: CambioRol, yo: dict = Depends(_admin_que_escribe)):
    """Cierra las sesiones de la cuenta. Quien deja de ser gestor pierde sus proyectos.
    Nadie se quita su propio rol de administración ni deja la plataforma sin ella: 409 `INVALID_STATE`."""
    u = _cuenta(id)
    try:
        cambio = usuarios.cambiar_rol(u, datos.rol, yo)
    except usuarios.DatosInvalidos as e:
        raise _invalido(e) from None
    except usuarios.Protegido as e:
        raise ErrorApi(409, "INVALID_STATE", str(e)) from None
    mensaje = (f"Permiso de {u['nombre']} cambiado; sus sesiones abiertas se cerraron." if cambio
               else f"Sin cambios: {u['nombre']} ya tenía ese permiso.")
    return {"usuario": _usuario(id), "mensaje": mensaje}


@router.post("/usuarios/{id}/estado", response_model=ResultadoUsuario, responses=errores(401, 403, 404, 409, 422))
def cambiar_estado(id: int, datos: CambioEstadoCuenta, yo: dict = Depends(_admin_que_escribe)):
    """Desactivar cierra sus sesiones. Nadie desactiva su propia cuenta ni a la última administración: 409 `INVALID_STATE`."""
    u = _cuenta(id)
    try:
        mensaje = usuarios.cambiar_estado(u, datos.activo, yo)
    except usuarios.Protegido as e:
        raise ErrorApi(409, "INVALID_STATE", str(e)) from None
    return {"usuario": _usuario(id), "mensaje": mensaje}


@router.post("/usuarios/{id}/cargo", response_model=ResultadoUsuario, responses=errores(401, 403, 404, 422))
def cambiar_cargo(id: int, datos: CambioCargo, yo: dict = Depends(_admin_que_escribe)):
    u = _cuenta(id)
    try:
        mensaje = usuarios.cambiar_cargo(u, datos.cargo_id or None)
    except usuarios.DatosInvalidos as e:
        raise _invalido(e) from None
    return {"usuario": _usuario(id), "mensaje": mensaje}


@router.post("/usuarios/{id}/proyectos", response_model=ResultadoUsuario, responses=errores(401, 403, 404, 422))
def asignar_proyectos(id: int, datos: CambioProyectos, yo: dict = Depends(_admin_que_escribe)):
    """Reemplaza los proyectos que gestiona; los que no existen se ignoran. Solo para cuentas con permiso de gestor
    (la pantalla actual solo lo ofrece a ellas): si no, al volverla gestora heredaría acceso sin que nadie lo decida."""
    u = _cuenta(id)
    if u["rol"] != "gestor":
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422],
                       {"proyectos_ids": "Solo una cuenta con permiso de gestor de proyecto gestiona proyectos."})
    elegidos = usuarios.asignar_proyectos(u, datos.proyectos_ids, yo)
    return {"usuario": _usuario(id), "mensaje": f"Proyectos de {u['nombre']} guardados ({len(elegidos)})."}


@router.post("/usuarios/{id}/clave", response_model=ResultadoUsuario, responses=errores(401, 403, 404, 422))
def restablecer_clave(id: int, datos: NuevaClave, yo: dict = Depends(_admin_que_escribe)):
    """La contraseña nueva nunca se devuelve. Cierra sus sesiones, desvincula su Telegram (le avisa antes por ese chat) y
    limpia el bloqueo por intentos. La propia no se restablece aquí (409 `INVALID_STATE`): se cambia en «Mi cuenta»."""
    u = _cuenta(id)
    try:
        usuarios.restablecer_clave(u, datos.clave, yo)
    except usuarios.DatosInvalidos as e:
        raise _invalido(e) from None
    except usuarios.Protegido as e:
        raise ErrorApi(409, "INVALID_STATE", str(e)) from None
    return {"usuario": _usuario(id), "mensaje": f"Contraseña de {u['nombre']} restablecida; sus sesiones abiertas se cerraron."}


# ---------- cargos ----------
def _cargo(cid: int) -> dict:
    c = next((c for c in acceso.cargos(solo_activos=False) if c["id"] == cid), None)
    if not c:
        raise _no_encontrado()
    return {"id": c["id"], "nombre": c["nombre"], "activo": bool(c["activo"]), "personas": c["personas"]}


@router.get("/cargos", response_model=ListaCargos, responses=errores(401, 403))
def cargos(yo: dict = Depends(solo_admin)):
    return {"items": [{"id": c["id"], "nombre": c["nombre"], "activo": bool(c["activo"]), "personas": c["personas"]}
                      for c in acceso.cargos(solo_activos=False)]}


@router.post("/cargos", status_code=201, response_model=Cargo, responses=errores(401, 403, 422))
def crear_cargo(datos: NuevoCargo, yo: dict = Depends(_admin_que_escribe)):
    """Deja el evento `cargo creado`. Un nombre repetido (sin importar mayúsculas) o con menos de 3 letras: 422."""
    try:
        cid = acceso.crear_cargo(datos.nombre)
    except ValueError as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"nombre": str(e)}) from None
    return _cargo(cid)


@router.post("/cargos/{id}", response_model=Cargo, responses=errores(401, 403, 404, 422))
def cambiar_cargo_catalogo(id: int, datos: CambioCargoCatalogo, yo: dict = Depends(_admin_que_escribe)):
    """Renombra o activa/desactiva. Quien tiene un cargo desactivado lo conserva."""
    _cargo(id)
    try:
        acceso.cambiar_cargo(id, nombre=datos.nombre, activo=datos.activo)
    except ValueError as e:
        raise ErrorApi(422, "VALIDATION_ERROR", MENSAJE_HTTP[422], {"nombre": str(e)}) from None
    return _cargo(id)
