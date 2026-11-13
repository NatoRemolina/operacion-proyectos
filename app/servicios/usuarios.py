"""Cuentas de la plataforma: alta, permiso, cargo, proyectos que gestiona, estado y contraseña.

Lo usan la pantalla actual (`/admin/usuarios`, `/mi-cuenta`) y la API v1 (`v1_usuarios.py`, `v1_cuenta.py`): una sola regla.
Protecciones: nadie se quita su propio rol de administración ni desactiva su cuenta, y la plataforma nunca queda sin
administración activa. Cambiar el permiso, desactivar o cambiar la contraseña cierra las sesiones abiertas de la cuenta.
"""
from .. import db
from . import acceso, eventos

NO_QUITAR_ROL = "No puedes quitarte tu propio rol ni dejar la plataforma sin administradores."
NO_DESACTIVAR = "No puedes desactivar tu propia cuenta ni al último administrador."
CLAVE_CORTA = "La contraseña debe tener al menos 10 caracteres."
CLAVE_ACTUAL = "La contraseña actual no coincide."
CLAVE_NUEVA = "La nueva contraseña debe tener al menos 10 caracteres y ser distinta."

_USUARIOS = """select u.id, u.correo, u.nombre, u.rol, u.activo, u.creado, u.viajero_id, v.nombre viajero, u.telegram_usuario,
                      u.telegram_chat_id, u.cargo_id, c.nombre cargo, (select max(ultima) from sesiones s where s.usuario_id=u.id) ultima
               from usuarios u left join viajeros v on v.id=u.viajero_id left join cargos c on c.id=u.cargo_id"""


class Protegido(ValueError):
    """El cambio dejaría a la persona sin su propio acceso o a la plataforma sin administración."""


class DatosInvalidos(ValueError):
    """Un dato no es válido. `campo` dice cuál, para señalarlo en el formulario."""

    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo


# ---------- lecturas ----------
def proyectos_por_gestor() -> dict[int, list[int]]:
    salida: dict[int, list[int]] = {}
    for m in db.todos("select usuario_id, proyecto_id from proyecto_miembros order by proyecto_id"):
        salida.setdefault(m["usuario_id"], []).append(m["proyecto_id"])
    return salida


def lista(limite: int | None = None, cursor: int | None = None, descendente: bool = False) -> list[dict]:
    donde, p = ("u.id<:_cursor", {"_cursor": cursor}) if cursor else ("1=1", {})
    orden = "desc" if descendente else ""
    tope = f" limit {int(limite)}" if limite else ""
    return db.todos(f"{_USUARIOS} where {donde} order by u.id {orden}{tope}", **p)


def uno(uid: int) -> dict | None:
    return db.uno(f"{_USUARIOS} where u.id=:i", i=uid)


def admins_activos(excepto: int = 0) -> int:
    return db.uno("select count(*) n from usuarios where rol='admin' and activo=1 and id<>:i", i=excepto)["n"]


# ---------- alta ----------
def problema_de_cuenta(correo: str, rol: str, clave: str, cargo_id: int | None) -> DatosInvalidos | None:
    """Qué impide crear la cuenta, campo por campo. Son las condiciones de `acceso.crear_usuario`."""
    correo = (correo or "").strip().lower()
    if "@" not in correo:
        return DatosInvalidos("correo", "Escribe un correo válido.")
    if rol not in acceso.ROLES:
        return DatosInvalidos("rol", "El permiso debe ser colaborador, gestor o admin.")
    if len(clave or "") < 10:
        return DatosInvalidos("clave", CLAVE_CORTA)
    if db.uno("select id from usuarios where correo=:c", c=correo):
        return DatosInvalidos("correo", "Ya existe una cuenta con ese correo.")
    if cargo_id and not db.uno("select id from cargos where id=:i and activo=1", i=cargo_id):
        return DatosInvalidos("cargo_id", "Ese cargo no existe o está desactivado.")
    return None


def crear(correo: str, nombre: str, rol: str, clave: str, viajero_id: int | None, cargo_id: int | None, quien: dict) -> int:
    """La contraseña inicial la escribe administración; se guarda solo su huella. Deja el evento `cuenta creada`."""
    uid = acceso.crear_usuario(correo, nombre, rol, clave, viajero_id, cargo_id)
    cargo = db.uno("select c.nombre from usuarios u join cargos c on c.id=u.cargo_id where u.id=:i", i=uid)
    eventos.registrar("usuario", uid, "cuenta creada", f"{correo.strip().lower()} · {rol} · {cargo['nombre'] if cargo else 'sin cargo'}",
                      quien["nombre"])
    return uid


# ---------- cambios ----------
def cambiar_rol(u: dict, rol: str, quien: dict) -> None:
    if rol not in acceso.ROLES:
        raise DatosInvalidos("rol", "El permiso debe ser colaborador, gestor o admin.")
    if u["rol"] == "admin" and rol != "admin" and (u["id"] == quien["id"] or not admins_activos(u["id"])):
        raise Protegido(NO_QUITAR_ROL)
    db.actualizar("usuarios", u["id"], rol=rol)
    if u["rol"] == "gestor" and rol != "gestor":   # deja de gestionar: pierde también sus proyectos
        db.ejecutar("delete from proyecto_miembros where usuario_id=:u", u=u["id"])
    acceso.cerrar_todas(u["id"])
    eventos.registrar("usuario", u["id"], "rol cambiado", f"{u['correo']}: {u['rol']} → {rol}", quien["nombre"])


def cambiar_estado(u: dict, activo: bool, quien: dict) -> str:
    """Devuelve lo que pasó, en palabras. Desactivar cierra sus sesiones; reactivar también limpia el bloqueo por intentos."""
    quiere = int(bool(activo))
    if quiere == u["activo"]:
        return f"Sin cambios: la cuenta de {u['nombre']} ya estaba {'activa' if quiere else 'desactivada'}."
    if not quiere and (u["id"] == quien["id"] or (u["rol"] == "admin" and not admins_activos(u["id"]))):
        raise Protegido(NO_DESACTIVAR)
    db.actualizar("usuarios", u["id"], activo=quiere, fallos=0, bloqueado_hasta=None)
    acceso.cerrar_todas(u["id"])
    eventos.registrar("usuario", u["id"], "cuenta reactivada" if quiere else "cuenta desactivada", u["correo"], quien["nombre"])
    return f"Cuenta de {u['nombre']} {'reactivada' if quiere else 'desactivada'}; sus sesiones abiertas se cerraron."


def cambiar_cargo(u: dict, cargo_id: int | None) -> str:
    """El cargo no da permisos: no hace falta cerrar las sesiones. El evento lo deja `acceso.asignar_cargo`."""
    try:
        acceso.asignar_cargo(u["id"], cargo_id or None)
    except ValueError as e:
        raise DatosInvalidos("cargo_id", str(e)) from None
    return f"Cargo de {u['nombre']} actualizado."


def asignar_proyectos(u: dict, proyectos_ids: list[int], quien: dict) -> list[int]:
    """Reemplaza los proyectos que gestiona. Lo que no existe se ignora."""
    validos = {p["id"] for p in db.todos("select id from proyectos")}
    elegidos = sorted(set(proyectos_ids) & validos)
    db.ejecutar("delete from proyecto_miembros where usuario_id=:u", u=u["id"])
    db.insertar_varios("proyecto_miembros", [{"usuario_id": u["id"], "proyecto_id": p, "papel": "gestor", "creado": db.ahora()}
                                             for p in elegidos])
    eventos.registrar("usuario", u["id"], "proyectos asignados", f"{u['correo']}: {elegidos}", quien["nombre"])
    return elegidos


def restablecer_clave(u: dict, clave: str, quien: dict) -> None:
    """Administración pone una contraseña nueva. Se cierran sus sesiones y se limpia el bloqueo por intentos."""
    if len(clave or "") < 10:
        raise DatosInvalidos("clave", CLAVE_CORTA)
    db.actualizar("usuarios", u["id"], clave_hash=acceso.hash_clave(clave), fallos=0, bloqueado_hasta=None)
    acceso.cerrar_todas(u["id"])
    eventos.registrar("usuario", u["id"], "contraseña restablecida", u["correo"], quien["nombre"])


def cambiar_mi_clave(yo: dict, actual: str, nueva: str) -> None:
    """La persona cambia su propia contraseña: exige la actual. Cierra todas sus sesiones; quien llama abre una nueva."""
    hash_actual = db.uno("select clave_hash from usuarios where id=:i", i=yo["id"])["clave_hash"]
    if not acceso._coincide(hash_actual, actual or ""):
        raise DatosInvalidos("actual", CLAVE_ACTUAL)
    if len(nueva or "") < 10 or nueva == actual:
        raise DatosInvalidos("nueva", CLAVE_NUEVA)
    db.actualizar("usuarios", yo["id"], clave_hash=acceso.hash_clave(nueva))
    acceso.cerrar_todas(yo["id"])
    eventos.registrar("usuario", yo["id"], "contraseña cambiada por la persona", "", yo["nombre"])
