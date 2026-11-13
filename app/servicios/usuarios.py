"""Cuentas de la plataforma: alta, permiso, cargo, proyectos que gestiona, estado y contraseña.

Lo usan la pantalla actual (`/admin/usuarios`, `/mi-cuenta`) y la API v1 (`v1_usuarios.py`, `v1_cuenta.py`): una sola regla.
Protecciones: nadie se quita su propio rol de administración ni desactiva su cuenta, y la plataforma nunca queda sin
administración activa. Cambiar el permiso, desactivar o cambiar la contraseña cierra las sesiones abiertas de la cuenta.
"""
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import text

from .. import config, db
from . import acceso, eventos, telegram

NO_QUITAR_ROL = "No puedes quitarte tu propio rol ni dejar la plataforma sin administradores."
NO_DESACTIVAR = "No puedes desactivar tu propia cuenta ni al último administrador."
CLAVE_CORTA = "La contraseña debe tener al menos 10 caracteres."
CLAVE_ACTUAL = "La contraseña actual no coincide."
CLAVE_NUEVA = "La nueva contraseña debe tener al menos 10 caracteres y ser distinta."
CLAVE_PROPIA = "Para cambiar tu propia contraseña usa «Mi cuenta»: allí se pide la actual."
DEMASIADOS_INTENTOS = "Demasiados intentos con la contraseña actual: por seguridad cerramos tus sesiones. Ingresa de nuevo en unos minutos."
BLOQUEO_ADMINISTRACION = 7_341_003   # bloqueo de PostgreSQL que pone en fila los cambios que pueden quitar administración

_USUARIOS = """select u.id, u.correo, u.nombre, u.rol, u.activo, u.creado, u.viajero_id, v.nombre viajero, u.telegram_usuario,
                      u.telegram_chat_id, u.cargo_id, c.nombre cargo, (select max(ultima) from sesiones s where s.usuario_id=u.id) ultima
               from usuarios u left join viajeros v on v.id=u.viajero_id left join cargos c on c.id=u.cargo_id"""


class Protegido(ValueError):
    """El cambio dejaría a la persona sin su propio acceso o a la plataforma sin administración."""


class DemasiadosIntentos(ValueError):
    """La persona falló la contraseña actual demasiadas veces seguidas: sus sesiones se cerraron."""


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
@contextmanager
def _en_fila_de_administracion(uid: int):
    """Comprueba y escribe en una sola transacción, en fila con los demás cambios que pueden quitar administración.
    Sin esto, dos administraciones que se quitan el permiso una a la otra a la vez verían «queda otra» y pasarían las dos.
    Entrega la cuenta releída dentro de la fila."""
    with db.transaccion() as c:
        if not config.ES_SQLITE:   # en SQLite la transacción ya toma el cerrojo de escritura
            c.execute(text("select pg_advisory_xact_lock(:k)"), {"k": BLOQUEO_ADMINISTRACION})
        yield db.uno("select * from usuarios where id=:i", i=uid)


def cambiar_rol(u: dict, rol: str, quien: dict) -> bool:
    """Devuelve si cambió. El mismo permiso no hace nada: no cierra sesiones ni deja evento."""
    if rol not in acceso.ROLES:
        raise DatosInvalidos("rol", "El permiso debe ser colaborador, gestor o admin.")
    with _en_fila_de_administracion(u["id"]) as u:
        if rol == u["rol"]:
            return False
        if u["rol"] == "admin" and rol != "admin" and (u["id"] == quien["id"] or not admins_activos(u["id"])):
            raise Protegido(NO_QUITAR_ROL)
        db.actualizar("usuarios", u["id"], rol=rol)
        if u["rol"] == "gestor" and rol != "gestor":   # deja de gestionar: pierde también sus proyectos
            db.ejecutar("delete from proyecto_miembros where usuario_id=:u", u=u["id"])
        acceso.cerrar_todas(u["id"])
        eventos.registrar("usuario", u["id"], "rol cambiado", f"{u['correo']}: {u['rol']} → {rol}", quien["nombre"])
    return True


def cambiar_estado(u: dict, activo: bool, quien: dict) -> str:
    """Devuelve lo que pasó, en palabras. Desactivar cierra sus sesiones; reactivar también limpia el bloqueo por intentos."""
    quiere = int(bool(activo))
    with _en_fila_de_administracion(u["id"]) as u:
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


def _cortar_accesos(uid: int, firma: str) -> None:
    """Con una contraseña nueva no sobrevive nada de antes: sesiones, chat de Telegram vinculado ni códigos de vínculo pendientes.
    Así, quien se hubiera colado con una sesión robada no se queda con el chat."""
    acceso.cerrar_todas(uid)
    db.ejecutar("delete from vinculos_telegram where usuario_id=:u", u=uid)
    if db.uno("select telegram_chat_id from usuarios where id=:i", i=uid)["telegram_chat_id"]:
        telegram.desvincular(uid)
        eventos.registrar("usuario", uid, "Telegram desvinculado", "al cambiar la contraseña", firma)


def restablecer_clave(u: dict, clave: str, quien: dict) -> None:
    """Administración pone una contraseña nueva a otra persona, que recibe un aviso. La propia se cambia en «Mi cuenta»,
    que pide la actual. Se cierran sus sesiones, se desvincula su Telegram y se limpia el bloqueo por intentos."""
    if u["id"] == quien["id"]:
        raise Protegido(CLAVE_PROPIA)
    if len(clave or "") < 10:
        raise DatosInvalidos("clave", CLAVE_CORTA)
    telegram.avisar(u["id"], f"{quien['nombre']} restableció la contraseña de tu cuenta. Si no lo pediste, avisa a administración.")
    db.actualizar("usuarios", u["id"], clave_hash=acceso.hash_clave(clave), fallos=0, bloqueado_hasta=None)
    _cortar_accesos(u["id"], quien["nombre"])
    eventos.registrar("usuario", u["id"], "contraseña restablecida",
                      u["correo"] + (" · cuenta de administración" if u["rol"] == "admin" else ""), quien["nombre"])


def _fallo_de_clave_actual(yo: dict) -> None:
    """Cuenta el fallo con el mismo contador y bloqueo progresivo del ingreso. Al llegar al máximo cierra las sesiones:
    seguir probando exige pasar por el ingreso, que está bloqueado unos minutos."""
    fila = db.uno("select fallos from usuarios where id=:i", i=yo["id"])
    fallos = (fila["fallos"] or 0) + 1
    espera = timedelta(minutes=min(2 ** (fallos - acceso.MAX_FALLOS), 30)) if fallos >= acceso.MAX_FALLOS else None
    db.actualizar("usuarios", yo["id"], fallos=fallos, bloqueado_hasta=acceso._fmt(acceso._ahora() + espera) if espera else None)
    eventos.registrar("usuario", yo["id"], "contraseña actual equivocada", f"intento {fallos}", yo["nombre"])
    if espera:
        acceso.cerrar_todas(yo["id"])
        raise DemasiadosIntentos(DEMASIADOS_INTENTOS)


def cambiar_mi_clave(yo: dict, actual: str, nueva: str) -> None:
    """La persona cambia su propia contraseña: exige la actual. Cierra todas sus sesiones y desvincula su Telegram;
    quien llama abre una sesión nueva."""
    hash_actual = db.uno("select clave_hash from usuarios where id=:i", i=yo["id"])["clave_hash"]
    if not acceso._coincide(hash_actual, actual or ""):
        _fallo_de_clave_actual(yo)
        raise DatosInvalidos("actual", CLAVE_ACTUAL)
    if len(nueva or "") < 10 or nueva == actual:
        raise DatosInvalidos("nueva", CLAVE_NUEVA)
    db.actualizar("usuarios", yo["id"], clave_hash=acceso.hash_clave(nueva), fallos=0, bloqueado_hasta=None)
    _cortar_accesos(yo["id"], yo["nombre"])
    eventos.registrar("usuario", yo["id"], "contraseña cambiada por la persona", "", yo["nombre"])


def desvincular_telegram(yo: dict) -> None:
    """La persona desconecta su chat: deja de recibir avisos y de cargar gastos por Telegram."""
    telegram.desvincular(yo["id"])
    eventos.registrar("usuario", yo["id"], "Telegram desvinculado", "", yo["nombre"])
