"""Cuentas, sesiones y roles.

- Contraseñas con Argon2id.
- La sesión es un token aleatorio; en la base solo se guarda su huella, así que se puede revocar
  (cerrar sesión, desactivar una cuenta) y un volcado de la tabla no sirve para entrar.
- Tres permisos: `colaborador` (cotiza y reporta lo suyo), `gestor` (además ve lo de sus proyectos) y `admin`
  (ve todo, revisa gastos, administra).
- El cargo (pilotaje de dron, edición de video...) dice qué hace la persona en la empresa. Es un dato aparte: no da permisos.
"""
import hashlib
import secrets
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

from .. import config, db
from . import eventos

COOKIE = "sesion" if config.LOCAL else "__Host-sesion"
VIDA = timedelta(hours=12)
INACTIVIDAD = timedelta(hours=2)
MAX_FALLOS = 5
ROLES = ("colaborador", "gestor", "admin")
NOMBRE_ROL = {"colaborador": "colaborador", "gestor": "gestor de proyecto", "admin": "administrador"}
PERFIL_SIN_CARGO = "Viajero"

# Rutas que no piden sesión, y prefijos reservados al administrador
PUBLICAS = ("/static", "/entrar", "/salud", "/telegram/webhook")
API_V1, API_V1_PUBLICAS = "/api/v1", ("/api/v1/auth/login",)
SOLO_ADMIN = ("/admin", "/analitica", "/flujo", "/reglas", "/api", "/docs", "/openapi.json", "/gastos/ejemplos")

_hasher = PasswordHasher()
_HASH_FICTICIO = _hasher.hash("valor-que-nadie-usa")
_actual: ContextVar[dict | None] = ContextVar("usuario_actual", default=None)


def _fmt(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S")


def _ahora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_clave(clave: str) -> str:
    return _hasher.hash(clave)


def _coincide(hash_guardado: str, clave: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, clave)
    except (Argon2Error, InvalidHashError):
        return False


def actual() -> dict | None:
    """Usuario de la petición en curso (lo fija el middleware)."""
    return _actual.get()


def fijar(usuario: dict | None):
    _actual.set(usuario)


def es_admin(u: dict | None) -> bool:
    return bool(u) and u["rol"] == "admin"


def nivel(ruta: str) -> str:
    """Nivel de acceso que exige una ruta: 'publica', 'api', 'admin' o 'usuario'.

    'api' es la API v1: exige sesión y responde siempre en JSON; los permisos finos los aplica cada endpoint.
    """
    if ruta.startswith(PUBLICAS) or ruta.startswith(API_V1_PUBLICAS):
        return "publica"
    if ruta == API_V1 or ruta.startswith(API_V1 + "/"):
        return "api"
    return "admin" if ruta.startswith(SOLO_ADMIN) else "usuario"


def _firma() -> str:
    """Quién hace el cambio, para la bitácora: la persona de la petición o el proceso que corre sin sesión."""
    u = actual()
    return u["nombre"] if u else "sistema"


def _limpiar_nombre_cargo(nombre: str) -> str:
    nombre = " ".join((nombre or "").split())[:60]
    if sum(ch.isalpha() for ch in nombre) < 3:
        raise ValueError("El nombre del cargo necesita al menos 3 letras.")
    return nombre


def _cargo_repetido(nombre: str, excepto: int = 0) -> bool:
    return any(c["nombre"].casefold() == nombre.casefold() and c["id"] != excepto
               for c in db.todos("select id, nombre from cargos"))


def cargos(solo_activos: bool = True) -> list[dict]:
    """Cargos de la empresa con cuántas personas tienen cada uno."""
    filtro = "where c.activo=1" if solo_activos else ""
    return db.todos(f"""select c.id, c.nombre, c.activo, (select count(*) from usuarios u where u.cargo_id=c.id) personas
                        from cargos c {filtro} order by c.nombre""")


def crear_cargo(nombre: str) -> int:
    nombre = _limpiar_nombre_cargo(nombre)
    if _cargo_repetido(nombre):
        raise ValueError(f"Ya existe el cargo «{nombre}».")
    cid = db.insertar("cargos", nombre=nombre, activo=1, creado=db.ahora())
    eventos.registrar("cargo", cid, "cargo creado", nombre, _firma())
    return cid


def cambiar_cargo(cargo_id: int, nombre: str | None = None, activo: bool | None = None) -> None:
    """Renombra o cambia el estado. Un cargo nunca se borra: con personas asignadas solo se desactiva."""
    c = db.uno("select * from cargos where id=:i", i=cargo_id)
    if not c:
        raise ValueError("Ese cargo no existe.")
    if nombre is not None:
        nombre = _limpiar_nombre_cargo(nombre)
        if _cargo_repetido(nombre, excepto=cargo_id):
            raise ValueError(f"Ya existe el cargo «{nombre}».")
        if nombre != c["nombre"]:
            db.actualizar("cargos", cargo_id, nombre=nombre)
            eventos.registrar("cargo", cargo_id, "cargo renombrado", f"{c['nombre']} → {nombre}", _firma())
    if activo is not None and int(bool(activo)) != c["activo"]:
        db.actualizar("cargos", cargo_id, activo=int(bool(activo)))
        eventos.registrar("cargo", cargo_id, "cargo reactivado" if activo else "cargo desactivado", nombre or c["nombre"], _firma())


def _cargo_activo(cargo_id: int | None) -> dict | None:
    if not cargo_id:
        return None
    c = db.uno("select id, nombre from cargos where id=:i and activo=1", i=cargo_id)
    if not c:
        raise ValueError("Ese cargo no existe o está desactivado.")
    return c


def asignar_cargo(usuario_id: int, cargo_id: int | None) -> None:
    """Pone o quita el cargo de una cuenta. El cargo pasa a ser la descripción de su perfil de viajero."""
    u = db.uno("select id, correo, cargo_id, viajero_id from usuarios where id=:i", i=usuario_id)
    if not u:
        raise ValueError("Esa cuenta no existe.")
    if (cargo_id or None) == u["cargo_id"]:
        return
    c = _cargo_activo(cargo_id)
    antes = db.uno("select nombre from cargos where id=:i", i=u["cargo_id"]) if u["cargo_id"] else None
    db.actualizar("usuarios", usuario_id, cargo_id=c["id"] if c else None)
    if u["viajero_id"]:
        db.actualizar("viajeros", u["viajero_id"], rol=c["nombre"] if c else PERFIL_SIN_CARGO)
    eventos.registrar("usuario", usuario_id, "cargo asignado",
                      f"{u['correo']}: {antes['nombre'] if antes else 'sin cargo'} → {c['nombre'] if c else 'sin cargo'}", _firma())


def crear_perfil_viajero(nombre: str, cargo: str | None) -> int:
    """Perfil operativo (base, membresías) de quien viaja. Toda cuenta tiene uno: todos los permisos viajan."""
    vid = db.insertar("viajeros", nombre=nombre, base="", rol=cargo or PERFIL_SIN_CARGO)
    eventos.registrar("viajero", vid, "perfil de viajero creado", f"{nombre} · {cargo or PERFIL_SIN_CARGO}", _firma())
    return vid


def crear_usuario(correo: str, nombre: str, rol: str, clave: str, viajero_id: int | None = None,
                  cargo_id: int | None = None) -> int:
    correo = correo.strip().lower()
    if rol not in ROLES or "@" not in correo or len(clave) < 10:
        raise ValueError("Datos de la cuenta no válidos (correo, rol o contraseña de menos de 10 caracteres).")
    if db.uno("select id from usuarios where correo=:c", c=correo):
        raise ValueError("Ya existe una cuenta con ese correo.")
    cargo = _cargo_activo(cargo_id)
    nombre = nombre.strip()[:80] or correo
    if not viajero_id:
        viajero_id = crear_perfil_viajero(nombre, cargo["nombre"] if cargo else None)
    return db.insertar("usuarios", correo=correo, nombre=nombre, rol=rol, activo=1, cargo_id=cargo["id"] if cargo else None,
                       clave_hash=hash_clave(clave), viajero_id=viajero_id, fallos=0, creado=db.ahora())


def autenticar(correo: str, clave: str) -> tuple[dict | None, str]:
    """Devuelve (usuario, mensaje). El mensaje es el mismo para correo o contraseña equivocados."""
    generico = "Correo o contraseña incorrectos."
    u = db.uno("select * from usuarios where correo=:c", c=correo.strip().lower())
    if not u:
        _coincide(_HASH_FICTICIO, clave)  # mismo trabajo aunque la cuenta no exista
        return None, generico
    ahora = _fmt(_ahora())
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
        return None, "Demasiados intentos. Espera unos minutos y vuelve a intentar."
    if not u["activo"] or not _coincide(u["clave_hash"], clave):
        fallos = (u["fallos"] or 0) + 1
        # Bloqueo progresivo por cuenta: 1, 2, 4... minutos a partir del quinto fallo
        espera = timedelta(minutes=min(2 ** (fallos - MAX_FALLOS), 30)) if fallos >= MAX_FALLOS else None
        db.actualizar("usuarios", u["id"], fallos=fallos, bloqueado_hasta=_fmt(_ahora() + espera) if espera else None)
        return None, generico
    db.actualizar("usuarios", u["id"], fallos=0, bloqueado_hasta=None)
    return u, ""


def abrir_sesion(respuesta, usuario_id: int):
    """Crea la sesión y pone la cookie. El token queda también en `respuesta.token_sesion`: la API v1 deriva de él el CSRF."""
    token = secrets.token_urlsafe(32)
    ahora = _ahora()
    db.ejecutar("delete from sesiones where usuario_id=:u and expira<:a", u=usuario_id, a=_fmt(ahora))
    db.insertar("sesiones", huella=huella(token), usuario_id=usuario_id, creada=_fmt(ahora), ultima=_fmt(ahora),
                expira=_fmt(ahora + VIDA))
    respuesta.set_cookie(COOKIE, token, httponly=True, secure=not config.LOCAL, samesite="lax", path="/",
                         max_age=int(VIDA.total_seconds()))
    respuesta.token_sesion = token
    return respuesta


def cerrar_sesion(respuesta, token: str | None):
    if token:
        db.ejecutar("delete from sesiones where huella=:h", h=huella(token))
    respuesta.delete_cookie(COOKIE, path="/")
    return respuesta


def cerrar_todas(usuario_id: int):
    db.ejecutar("delete from sesiones where usuario_id=:u", u=usuario_id)


def usuario_de(token: str | None, tocar: bool = True) -> dict | None:
    """Usuario dueño de una sesión vigente, o None. Cuenta desactivada o sesión vencida no entran."""
    if not token:
        return None
    ahora = _ahora()
    u = db.uno("""select u.id, u.correo, u.nombre, u.rol, u.viajero_id, u.telegram_chat_id, u.viaje_activo_id,
                         c.nombre cargo, s.id sesion_id, s.ultima
                  from sesiones s join usuarios u on u.id=s.usuario_id left join cargos c on c.id=u.cargo_id
                  where s.huella=:h and s.expira>:a and s.ultima>:i and u.activo=1""",
               h=huella(token), a=_fmt(ahora), i=_fmt(ahora - INACTIVIDAD))
    if tocar and u and u["ultima"] < _fmt(ahora - timedelta(minutes=2)):  # no escribir en cada petición
        db.actualizar("sesiones", u["sesion_id"], ultima=_fmt(ahora))
    return u


def mismo_origen(cabeceras) -> bool:
    """Toda petición de escritura debe venir de la propia página (defensa frente a falsificación de peticiones)."""
    sitio = cabeceras.get("sec-fetch-site")
    if sitio:
        return sitio in ("same-origin", "none")
    origen = cabeceras.get("origin")
    if origen:
        return origen.split("://", 1)[-1] == cabeceras.get("host", "")
    return True  # sin cabeceras de navegador: no es un formulario enviado desde otra página


def origen_permitido(cabeceras) -> bool:
    """Para la API v1: la misma página, o un origen declarado en `ORIGENES_WEB`. No confía en Host reescrito."""
    sitio = cabeceras.get("sec-fetch-site")
    if sitio in ("same-origin", "none"):
        return True
    origen = (cabeceras.get("origin") or "").rstrip("/")
    if origen:
        return origen in config.ORIGENES_WEB or origen.split("://", 1)[-1] == cabeceras.get("host", "")
    return sitio is None   # sin cabeceras de navegador (por ejemplo, una prueba o un cliente de consola)


def alcance(u: dict, alias: str = "") -> tuple[str, dict]:
    """Fragmento SQL que limita un listado a lo propio: lo que la persona creó o donde es el viajero."""
    if es_admin(u):
        return "1=1", {}
    p = f"{alias}." if alias else ""
    propio = f"{p}usuario_id=:_yo or ({p}viajero_id is not null and {p}viajero_id=:_mi_viajero)"
    if u["rol"] == "gestor":   # además, todo lo de los proyectos que gestiona
        propio += f" or {p}proyecto_id in (select proyecto_id from proyecto_miembros where usuario_id=:_yo)"
    return f"({propio})", {"_yo": u["id"], "_mi_viajero": u.get("viajero_id") or -1}


def es_propio(u: dict, fila: dict | None) -> bool:
    """Lo creó la persona o es quien viaja. Es la condición para modificar; ver puede ser más amplio."""
    if not fila or not u:
        return False
    return es_admin(u) or fila.get("usuario_id") == u["id"] or bool(u.get("viajero_id") and fila.get("viajero_id") == u["viajero_id"])


def proyectos_de(u: dict) -> set[int]:
    return {f["proyecto_id"] for f in db.todos("select proyecto_id from proyecto_miembros where usuario_id=:u", u=u["id"])}


def puede_ver(u: dict, fila: dict | None) -> bool:
    if es_propio(u, fila):
        return True
    return bool(fila and u and u["rol"] == "gestor" and fila.get("proyecto_id") in proyectos_de(u))
