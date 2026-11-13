"""Claves de servicio: credenciales para integraciones (por ejemplo, n8n), no para personas.

- Cada clave tiene un nombre (el que queda en la bitácora) y una lista de permisos del catálogo `PERMISOS`
  (`recurso:acción`). Un flujo nuevo añade su permiso al catálogo y su endpoint lo pide con `autorizar`.
- Ninguna clave aprueba, rechaza ni revisa: esas decisiones son siempre de una persona con sesión. Un permiso con esas
  acciones no puede entrar al catálogo ni a una clave.
- Se muestra una sola vez al crearla; en la base solo queda su huella y un prefijo para reconocerla.
- Se revoca sin borrarla: la fila queda como registro de que existió.
- Viaja en la cabecera `X-Clave-Servicio`, sin cookie ni token CSRF: no hay navegador de por medio.
"""
import hmac
import re
import secrets

from sqlalchemy import Column, Text, UniqueConstraint

from .. import db
from . import acceso, eventos

CABECERA = "X-Clave-Servicio"
PREFIJO = "isk_"
PERMISOS = {"soportes:leer": "Descargar el soporte de un gasto con un enlace firmado y vigente"}
FORMATO_PERMISO = re.compile(r"^[a-z_]+:[a-z_]+$")
ACCIONES_VEDADAS = ("aprobar", "rechazar", "revisar", "decidir", "excepcion")


def _vedado(permiso: str) -> bool:
    return any(a in permiso for a in ACCIONES_VEDADAS)


def comprobar_catalogo(catalogo: dict | None = None) -> None:
    """Falla al cargar si alguien añade al catálogo un permiso mal escrito o que decide por una persona."""
    for p in catalogo if catalogo is not None else PERMISOS:
        if not FORMATO_PERMISO.match(p) or _vedado(p):
            raise RuntimeError(f"Permiso de servicio no admitido en el catálogo: {p}")


comprobar_catalogo()

claves_servicio = db._tabla(
    "claves_servicio",
    Column("nombre", Text, nullable=False), Column("prefijo", Text, nullable=False), Column("huella", Text, nullable=False),
    Column("permisos", Text, nullable=False), Column("creado", Text), Column("creado_por", Text),
    Column("revocado", Text), Column("ultimo_uso", Text),
    UniqueConstraint("huella", name="ux_claves_servicio_huella"),
)


class ClaveInvalida(Exception):
    """Falta la clave, no existe o está revocada (401)."""


class SinPermiso(Exception):
    """La clave es válida pero no tiene el permiso que pide la operación (403)."""


def _limpiar_nombre(nombre: str) -> str:
    nombre = " ".join((nombre or "").split())[:60]
    if sum(ch.isalnum() for ch in nombre) < 2:
        raise ValueError("El nombre de la clave necesita al menos 2 letras o números.")
    return nombre


def crear(nombre: str, permisos: list[str], creado_por: str = "administración") -> tuple[int, str]:
    """Crea la clave y devuelve (id, clave en claro). La clave en claro no se puede recuperar después."""
    nombre = _limpiar_nombre(nombre)
    permisos = sorted(set(permisos))
    desconocidos = [p for p in permisos if p not in PERMISOS or _vedado(p) or not FORMATO_PERMISO.match(p)]
    if not permisos or desconocidos:
        raise ValueError("Permisos no válidos: " + (", ".join(desconocidos) or "ninguno") + ". Opciones: " + ", ".join(PERMISOS))
    clave = PREFIJO + secrets.token_urlsafe(32)
    cid = db.insertar("claves_servicio", nombre=nombre, prefijo=clave[:10], huella=acceso.huella(clave),
                      permisos=",".join(permisos), creado=db.ahora(), creado_por=creado_por)
    eventos.registrar("clave_servicio", cid, "clave de servicio creada", f"{nombre} · {', '.join(permisos)}", creado_por)
    return cid, clave


def revocar(clave_id: int, revocado_por: str = "administración") -> bool:
    c = db.uno("select id, nombre, revocado from claves_servicio where id=:i", i=clave_id)
    if not c:
        raise ValueError("Esa clave no existe.")
    if c["revocado"]:
        return False
    db.actualizar("claves_servicio", clave_id, revocado=db.ahora())
    eventos.registrar("clave_servicio", clave_id, "clave de servicio revocada", c["nombre"], revocado_por)
    return True


def listar() -> list[dict]:
    return db.todos("select id, nombre, prefijo, permisos, creado, creado_por, revocado, ultimo_uso from claves_servicio order by id")


def autorizar(clave: str | None, permiso: str) -> dict:
    """La clave vigente que pide la operación. Lanza `ClaveInvalida` (401) o `SinPermiso` (403)."""
    clave = (clave or "").strip()
    if not clave.startswith(PREFIJO):
        raise ClaveInvalida
    c = db.uno("select id, nombre, huella, permisos, revocado, ultimo_uso from claves_servicio where huella=:h",
               h=acceso.huella(clave))
    # La búsqueda ya es por huella; la comparación en tiempo constante evita depender de cómo compara la base
    if not c or c["revocado"] or not hmac.compare_digest(c["huella"], acceso.huella(clave)):
        raise ClaveInvalida
    if _vedado(permiso) or permiso not in c["permisos"].split(","):
        raise SinPermiso
    ahora = db.ahora()
    if (c["ultimo_uso"] or "")[:16] != ahora[:16]:   # a lo sumo una escritura por minuto
        db.actualizar("claves_servicio", c["id"], ultimo_uso=ahora)
    return {"id": c["id"], "nombre": c["nombre"]}
