"""Lleva una base existente al modelo actual. Se puede ejecutar las veces que haga falta: cada paso comprueba antes.

`db.crear_tablas()` crea tablas y añade columnas; aquí va lo demás: datos que cambian de forma,
claves foráneas, restricciones, índices y permisos.
"""
import re

from sqlalchemy import CheckConstraint

from app import config, db

CARGOS = ("Pilotaje de dron", "Edición de video", "Desarrollo de software", "Ingeniería de datos", "Producción")
CARGO_DE_PILOTO = "Pilotaje de dron"
ROLES_VIEJOS = {"piloto": "colaborador", "usuario": "colaborador"}   # valor guardado antes → permiso actual

INDICES = [  # nombre, tabla, columnas, único
    ("ux_usuarios_telegram", "usuarios", "telegram_chat_id", True),
    ("ux_usuarios_viajero", "usuarios", "viajero_id", True),
    ("ix_viajes_usuario", "viajes", "usuario_id", False),
    ("ix_viajes_proyecto", "viajes", "proyecto_id", False),
    ("ix_gastos_viaje", "gastos", "viaje_id", False),
    ("ix_gastos_proyecto", "gastos", "proyecto_id", False),
    ("ix_gastos_usuario", "gastos", "usuario_id", False),
    ("ix_documentos_viaje", "documentos", "viaje_id", False),
    ("ix_documentos_huella", "documentos", "huella", False),
    ("ix_solicitudes_usuario", "solicitudes", "usuario_id", False),
    ("ix_opciones_solicitud", "opciones", "solicitud_id", False),
    ("ix_eventos_entidad", "eventos", "entidad, entidad_id", False),
    ("ix_miembros_usuario", "proyecto_miembros", "usuario_id", False),
]


def sembrar_cargos() -> int:
    """Los cinco cargos iniciales, solo en una tabla vacía: después la lista es de administración (renombra, desactiva)."""
    from app.servicios import acceso
    if db.uno("select id from cargos limit 1"):
        return 0
    for nombre in CARGOS:
        acceso.crear_cargo(nombre)
    return len(CARGOS)


def _sql_usuarios_sqlite() -> str:
    return db.uno("select sql from sqlite_master where type='table' and name='usuarios'")["sql"]


def _rehacer_usuarios_sqlite(roles: tuple[str, ...], renombrar: dict[str, str]) -> bool:
    """SQLite no cambia una restricción en su lugar: se rehace la tabla con la nueva y se copian las filas.

    Es el procedimiento que documenta SQLite (tabla nueva, copia, borrar, renombrar) con las claves foráneas apagadas;
    las referencias de las otras tablas siguen apuntando a `usuarios` y los índices los vuelve a crear `_indices()`.
    """
    sql = _sql_usuarios_sqlite()
    permitidos = ",".join(f"'{r}'" for r in roles)
    nuevo, cambios = re.subn(r"CHECK \(rol in \([^)]*\)\)", f"CHECK (rol in ({permitidos}))", sql)
    if not cambios:
        return False
    nuevo = re.sub(r'^CREATE TABLE "?usuarios"?', "CREATE TABLE usuarios__nueva", nuevo)
    columnas = [c["name"] for c in db.todos("pragma table_info(usuarios)")]
    caso = "case " + " ".join(f"when rol='{a}' then '{b}'" for a, b in renombrar.items()) + " else rol end" if renombrar else "rol"
    origen = ", ".join(caso if c == "rol" else c for c in columnas)
    crudo = db.motor.raw_connection()
    try:
        crudo.driver_connection.executescript(f"""
            PRAGMA foreign_keys=OFF; PRAGMA legacy_alter_table=ON;
            BEGIN;
            {nuevo};
            INSERT INTO usuarios__nueva ({", ".join(columnas)}) SELECT {origen} FROM usuarios;
            DROP TABLE usuarios;
            ALTER TABLE usuarios__nueva RENAME TO usuarios;
            COMMIT;
            PRAGMA legacy_alter_table=OFF; PRAGMA foreign_keys=ON;""")
    finally:
        crudo.close()
    db.ejecutar("select 1")   # vacía la caché de lecturas
    return True


def _roles() -> dict:
    """El permiso `piloto` pasa a `colaborador` con el cargo «Pilotaje de dron», y toda cuenta queda con perfil de viajero."""
    from app.servicios import acceso, eventos
    hechos = {"cargos_sembrados": sembrar_cargos(), "permisos_migrados": 0, "perfiles_creados": 0}
    viejos = db.todos("select id, correo, rol, cargo_id from usuarios where rol in ('piloto','usuario')")
    if config.ES_SQLITE:
        sql = _sql_usuarios_sqlite()
        if "ck_usuarios_rol" in sql and "'colaborador'" not in sql:
            _rehacer_usuarios_sqlite(acceso.ROLES, ROLES_VIEJOS)
    else:
        actual = db.uno("select pg_get_constraintdef(oid) d from pg_constraint where conname='ck_usuarios_rol'")
        if actual and "colaborador" not in actual["d"]:   # `_restricciones_postgres` la vuelve a crear con el valor nuevo
            db.ejecutar("alter table usuarios drop constraint ck_usuarios_rol")
    if viejos:
        db.ejecutar("update usuarios set rol='colaborador' where rol in ('piloto','usuario')")
        cargo = next((c for c in acceso.cargos(solo_activos=False) if c["nombre"].casefold() == CARGO_DE_PILOTO.casefold()), None)
        cargo_id = cargo["id"] if cargo else acceso.crear_cargo(CARGO_DE_PILOTO)
        for u in viejos:
            if not u["cargo_id"]:
                db.actualizar("usuarios", u["id"], cargo_id=cargo_id)
            eventos.registrar("usuario", u["id"], "permiso migrado",
                              f"{u['correo']}: {u['rol']} → colaborador" + ("" if u["cargo_id"] else f" · cargo {CARGO_DE_PILOTO}"), "migración")
            hechos["permisos_migrados"] += 1
    for u in db.todos("""select u.id, u.nombre, c.nombre cargo from usuarios u left join cargos c on c.id=u.cargo_id
                         where u.viajero_id is null"""):
        db.actualizar("usuarios", u["id"], viajero_id=acceso.crear_perfil_viajero(u["nombre"], u["cargo"]))
        hechos["perfiles_creados"] += 1
    return hechos


def _datos() -> dict:
    """Cambios en los datos: viajes de las decisiones que ya existían y gastos enlazados."""
    from app.servicios import viajes
    hechos = {"viajes_creados": 0, "gastos_enlazados": 0}
    db.ejecutar("update documentos set tipo='soporte' where tipo is null")
    vigentes = db.todos("""select max(d.id) id from decisiones d where d.vuelo_id is not null
                           and not exists (select 1 from viajes v where v.solicitud_id=d.solicitud_id) group by d.solicitud_id""")
    for d in vigentes:
        viajes.crear_desde_decision(d["id"])
        hechos["viajes_creados"] += 1
    # Un gasto anterior se enlaza solo si su viajero y su proyecto apuntan a un único viaje
    for g in db.todos("select id, viajero_id, proyecto_id from gastos where viaje_id is null and viajero_id is not null and proyecto_id is not null"):
        candidatos = db.todos("select id from viajes where viajero_id=:v and proyecto_id=:p", v=g["viajero_id"], p=g["proyecto_id"])
        if len(candidatos) == 1:
            db.actualizar("gastos", g["id"], viaje_id=candidatos[0]["id"])
            hechos["gastos_enlazados"] += 1
    return hechos


def _indices():
    for nombre, tabla, columnas, unico in INDICES:
        db.ejecutar(f"create {'unique ' if unico else ''}index if not exists {nombre} on {tabla} ({columnas})")


def _restricciones_postgres() -> dict:
    """Claves foráneas y restricciones declaradas en `app/db.py` que la base todavía no tiene."""
    presentes = {r["conname"] for r in db.todos("select conname from pg_constraint")}
    hechos = {"claves_foraneas": 0, "referencias_huerfanas": 0, "restricciones": 0}
    for t in db.meta.sorted_tables:
        for fk in t.foreign_keys:
            columna, destino = fk.parent.name, fk.column.table.name
            if fk.name in presentes:
                continue
            huerfanas = f"{columna} is not null and not exists (select 1 from {destino} r where r.id={t.name}.{columna})"
            n = db.uno(f"select count(*) n from {t.name} where {huerfanas}")["n"]
            if n:   # una referencia a algo que no existe no dice nada: se vacía y se cuenta
                db.ejecutar(f"update {t.name} set {columna}=null where {huerfanas}")
                hechos["referencias_huerfanas"] += n
            db.ejecutar(f"alter table {t.name} add constraint {fk.name} foreign key ({columna}) references {destino}(id)")
            hechos["claves_foraneas"] += 1
        for c in t.constraints:
            if isinstance(c, CheckConstraint) and c.name and c.name not in presentes:
                db.ejecutar(f"alter table {t.name} add constraint {c.name} check ({c.sqltext})")
                hechos["restricciones"] += 1
    return hechos


def _permisos_postgres():
    """La aplicación entra con su propio rol. Los roles públicos del proveedor no deben poder tocar nada."""
    publicos = [r["rolname"] for r in db.todos("select rolname from pg_roles where rolname in ('anon','authenticated')")]
    for t in db.meta.sorted_tables:
        db.ejecutar(f"alter table {t.name} enable row level security")
        for rol in publicos:
            db.ejecutar(f"revoke all on {t.name} from {rol}")


def permisos_de_vistas(vistas):
    if config.ES_SQLITE:
        return
    for rol in [r["rolname"] for r in db.todos("select rolname from pg_roles where rolname in ('anon','authenticated')")]:
        for v in vistas:
            db.ejecutar(f"revoke all on {v} from {rol}")


def migrar() -> dict:
    hechos = {**_roles(), **_datos()}
    _indices()
    if not config.ES_SQLITE:
        hechos.update(_restricciones_postgres())
        _permisos_postgres()
    return hechos
