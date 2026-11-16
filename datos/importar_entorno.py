"""Lleva cotizaciones, viajes y respuestas del buscador de una base de la plataforma a otra.

Uso típico: pasar lo que se hizo en un entorno de Docker a la base de Supabase de pruebas.

    ORIGEN_URL=postgresql://... DESTINO_URL=postgresql://... python -m datos.importar_entorno ensayo
    ORIGEN_URL=postgresql://... DESTINO_URL=postgresql://... python -m datos.importar_entorno aplicar

`ensayo` hace toda la carga dentro de una transacción y la revierte: dice qué entraría sin escribir nada.
Las cadenas de conexión no se imprimen. Ambas bases deben tener el esquema de esta versión (la semilla lo crea).

Reglas:
- Personas, proyectos y viajeros no se copian: se emparejan por correo y por nombre. Si alguno no existe en el
  destino, no se carga nada.
- Cotizaciones, opciones, decisiones, elecciones, viajes y tramos conservan su id, así el viaje V-2026-0001 sigue
  siéndolo. Cada fila se reconoce por lo que no cambia después de creada (`IDENTIDAD`); si un id ya existe y es otra
  fila, no se carga nada.
- De una cotización ya cargada entra lo que el destino todavía no tiene. Si trae una decisión nueva, la cotización y
  su viaje quedan como en el origen (estado, aeropuertos del vuelo elegido, presupuesto) y los tramos del viaje se
  reemplazan por los del origen, como hace la plataforma al decidir.
- Respuestas del buscador, consultas registradas, aeropuertos que solo conoce Google y los eventos de lo cargado
  entran con id nuevo y sin repetirse. Los eventos de ingreso o de la semilla son de cada entorno y no se llevan.
- De las respuestas con la misma clave se usa la de id mayor: entran, en orden, las del origen más nuevas (por
  `creado`) que la última del destino, y así la más nueva de las dos bases es la que se usa.
- Consultas y eventos se comparan por la fila entera, salvo el id: dos distintas del mismo segundo entran las dos, y
  una repetida entra tantas veces como falte en el destino.
- Una segunda corrida no duplica nada. Cada carga queda en `cargas_datos` y en un evento «datos importados».
- Nunca escribe en la base publicada: la reconoce por su proyecto (el de `.env.supabase-publicada`), se
  conecte como se conecte, y se detiene. Si el destino es remoto y no hay con qué comprobarlo, tampoco escribe.
"""
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

RAIZ = Path(__file__).resolve().parent.parent


def _raiz_principal() -> Path:
    """La carpeta principal del repositorio. En una carpeta de trabajo aparte (`git worktree`) los archivos locales
    de configuración no están: viven en la principal, a la que apunta el archivo `.git`."""
    marca = RAIZ / ".git"
    if marca.is_file():
        destino = marca.read_text().partition("gitdir:")[2].strip()
        if "/.git/" in destino:
            return Path(destino.split("/.git/")[0])
    return RAIZ


# El archivo local que dice cuál es la base publicada (el del respaldo), en esta carpeta o en la principal.
# El `.env` no sirve de referencia: puede apuntar a la base de pruebas.
ARCHIVOS_PUBLICADA = [carpeta / ".env.supabase-publicada" for carpeta in dict.fromkeys((RAIZ, _raiz_principal()))]
LOCALES = ("localhost", "127.0.0.1", "::1", "db", "host.docker.internal")
FUENTE = "otro entorno de la plataforma"

# En el orden de carga: cada tabla después de aquellas a las que apunta
CON_ID = ("solicitudes", "opciones", "decisiones", "elecciones", "viajes", "tramos_vuelo")
SIN_ID = ("busquedas", "consultas_buscador", "aeropuertos_google", "eventos")
ENTIDADES_DE_EVENTO = ("solicitud", "viaje", "aeropuerto", "lugares")
# Lo que no cambia después de creada cada fila: así se reconoce la misma fila en las dos bases. Lo demás sí cambia
# (estados, tarifas, el último estado de un tramo), y al decidir la cotización pasa a los aeropuertos del vuelo elegido.
IDENTIDAD = {"solicitudes": ("creado", "ida", "regreso"), "opciones": ("solicitud_id", "tipo", "titulo"),
             "decisiones": ("solicitud_id", "creado"), "elecciones": ("decision_id", "opcion_id", "tipo", "posicion"),
             "viajes": ("solicitud_id", "creado"), "tramos_vuelo": ("viaje_id", "sentido", "orden", "numero")}
NOMBRES = {"solicitudes": "la cotización", "opciones": "la opción", "decisiones": "la decisión", "elecciones": "la elección",
           "viajes": "el viaje", "tramos_vuelo": "el tramo"}


class ImportacionImpedida(RuntimeError):
    """La carga no se hace; el mensaje dice por qué. No se escribió nada."""


def _motor(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, poolclass=NullPool)
    # El agrupador de conexiones de Supabase no admite sentencias preparadas
    return create_engine("postgresql+psycopg://" + url.split("://", 1)[1], poolclass=NullPool,
                         connect_args={"prepare_threshold": None})


def _identidad(url: str) -> tuple:
    """Servidor, usuario (en Supabase lleva el proyecto) y base, sin la contraseña."""
    u = make_url(url.replace("[YOUR-PASSWORD]", "x"))
    return u.host, u.username, u.database


def _proyectos(url: str) -> set[str]:
    """Los proyectos de Supabase que nombra una dirección: en el usuario (`postgres.<proyecto>`, por el agrupador),
    en el servidor (`db.<proyecto>.supabase.co`) o en la dirección del proyecto (`https://<proyecto>.supabase.co`)."""
    if not url:
        return set()
    servidor, usuario = url.split("://", 1)[-1].split("/", 1)[0].rsplit("@", 1)[-1].split(":", 1)[0], ""
    if url.startswith(("postgres", "sqlite")):
        try:
            u = make_url(url.replace("[YOUR-PASSWORD]", "x"))
            servidor, usuario = u.host or "", u.username or ""
        except Exception:   # noqa: BLE001  una dirección mal escrita no nombra ningún proyecto
            return set()
    encontrados = set()
    if usuario.startswith("postgres.") and len(usuario) > 9:
        encontrados.add(usuario[9:].lower())
    partes = servidor.lower().split(".")
    if servidor.lower().endswith(".supabase.co") and len(partes) >= 3:
        encontrados.add(partes[1] if partes[0] == "db" else partes[0])
    return encontrados


def _publicada() -> tuple[set, set]:
    """(proyectos, identidades) de la base publicada según los archivos locales que existan."""
    proyectos, identidades = set(), set()
    for archivo in ARCHIVOS_PUBLICADA:
        if not Path(archivo).is_file():
            continue
        valores = dotenv_values(archivo)
        for clave in ("DATABASE_URL", "SUPABASE_URL"):
            proyectos |= _proyectos(valores.get(clave) or "")
        base = valores.get("DATABASE_URL") or ""
        if base.startswith("postgres"):
            identidades.add(_identidad(base)[:2])
    return proyectos, identidades


def _comprobar_destino(origen: str, destino: str):
    if _identidad(origen) == _identidad(destino):
        raise ImportacionImpedida("El origen y el destino son la misma base.")
    if destino.startswith("sqlite") or _identidad(destino)[0] in LOCALES:
        return
    proyectos, identidades = _publicada()
    if _proyectos(destino) & proyectos or _identidad(destino)[:2] in identidades:
        raise ImportacionImpedida("El destino es la base publicada: esta carga nunca escribe allí.")
    if not proyectos and not identidades:
        raise ImportacionImpedida("No se carga nada: no se puede comprobar cuál es la base publicada (falta el archivo "
                                  "local `.env.supabase-publicada`), así que no se escribe en una base remota.")


def _filas(c, sql: str, **p) -> list[dict]:
    return [dict(r._mapping) for r in c.execute(text(sql), p)]


def _leer(url: str) -> dict:
    with _motor(url).connect() as o:
        lee = lambda tabla, donde="": _filas(o, f"select * from {tabla} {donde} order by id")   # noqa: E731,S608
        en = ", ".join(f"'{e}'" for e in ENTIDADES_DE_EVENTO)
        return {"usuarios": _filas(o, "select id, correo from usuarios"), "proyectos": _filas(o, "select id, nombre from proyectos"),
                "viajeros": _filas(o, "select id, nombre from viajeros"),
                **{t: lee(t) for t in CON_ID + SIN_ID if t != "eventos"},
                "eventos": lee("eventos", f"where entidad in ({en})")}


def importar(origen: str, destino: str, aplicar: bool = False, fuente: str = FUENTE) -> dict:
    """Devuelve {"filas": insertadas por tabla, "ya_cargadas": ids de cotizaciones de una corrida anterior,
    "puestas_al_dia": las ya cargadas que recibieron una decisión nueva, "viajes": códigos de los viajes cargados}."""
    _comprobar_destino(origen, destino)
    datos = _leer(origen)
    huella = hashlib.sha256(json.dumps({k: v for k, v in datos.items() if k not in ("usuarios", "proyectos", "viajeros")},
                                       sort_keys=True, default=str).encode()).hexdigest()
    motor = _motor(destino)
    meta = MetaData()
    meta.reflect(motor, only=["usuarios", "proyectos", "viajeros", *CON_ID, *SIN_ID, "cargas_datos"])
    filas: dict[str, int] = {}

    with motor.connect() as d:
        d.begin()

        def mapa(sql: str, clave: str, origen_: list[dict]) -> dict:
            filas_destino = _filas(d, sql)
            en_destino = {f[clave]: f["id"] for f in filas_destino}
            usados = {f[clave] for f in origen_}
            vistos, repetidos = set(), set()
            for f in filas_destino:
                (repetidos if f[clave] in vistos else vistos).add(f[clave])
            if repetidos & usados:   # con dos filas iguales no se sabe a cuál pertenece lo que se carga
                raise ImportacionImpedida(f"No se carga nada: «{sorted(repetidos & usados)[0]}» está repetido en el destino.")
            return {f["id"]: en_destino[f[clave]] for f in origen_ if f[clave] in en_destino}

        persona = mapa("select id, correo from usuarios", "correo", datos["usuarios"])
        proyecto = mapa("select id, nombre from proyectos", "nombre", datos["proyectos"])
        viajero = mapa("select id, nombre from viajeros", "nombre", datos["viajeros"])

        def exigir(m: dict, valor, que: str):
            if valor is None:
                return None
            if valor not in m:
                raise ImportacionImpedida(f"No se carga nada: {que} {valor} del origen no existe en el destino.")
            return m[valor]

        def valores(tabla: str, fila: dict, con_id: bool) -> dict:
            columnas = {c.name for c in meta.tables[tabla].columns}
            return {k: v for k, v in fila.items() if k in columnas and (con_id or k != "id")}

        def insertar(tabla: str, fila: dict, con_id: bool):
            d.execute(meta.tables[tabla].insert().values(**valores(tabla, fila, con_id)))
            filas[tabla] = filas.get(tabla, 0) + 1

        def poner_al_dia(tabla: str, fila: dict):
            t = meta.tables[tabla]
            d.execute(t.update().where(t.c.id == fila["id"]).values(**valores(tabla, fila, con_id=False)))

        def ya_esta(tabla: str, fila: dict) -> bool:
            """Si el id ya está en el destino y es la misma fila. Si es otra, no se carga nada."""
            claves = IDENTIDAD[tabla]
            previa = _filas(d, f"select {', '.join(claves)} from {tabla} where id=:i", i=fila["id"])
            if not previa:
                return False
            if previa[0] == {k: fila[k] for k in claves}:
                return True
            raise ImportacionImpedida(f"No se carga nada: {NOMBRES[tabla]} {fila['id']} ya existe en el destino con otro contenido.")

        def de_la_persona(fila: dict) -> dict:
            return {**fila, "usuario_id": exigir(persona, fila["usuario_id"], "la persona"),
                    "proyecto_id": exigir(proyecto, fila["proyecto_id"], "el proyecto"),
                    **({"viajero_id": exigir(viajero, fila["viajero_id"], "el viajero")} if "viajero_id" in fila else {})}

        def del_viaje(v: dict) -> dict:
            return {**de_la_persona(v), "aprobado_por": exigir(persona, v.get("aprobado_por"), "quien aprobó")}

        # ---------- cotizaciones y lo que cuelga de ellas, con su id ----------
        # De una cotización ya cargada entra lo que el destino todavía no tiene, como una decisión posterior
        ya = set()
        for s in datos["solicitudes"]:
            if ya_esta("solicitudes", s):
                ya.add(s["id"])
            else:
                insertar("solicitudes", de_la_persona(s), con_id=True)
        cotizaciones = {s["id"]: s for s in datos["solicitudes"]}
        for o in datos["opciones"]:
            if o["solicitud_id"] in cotizaciones and not ya_esta("opciones", o):
                insertar("opciones", o, con_id=True)
        decisiones, decididas = [x for x in datos["decisiones"] if x["solicitud_id"] in cotizaciones], set()
        for x in decisiones:
            if not ya_esta("decisiones", x):
                insertar("decisiones", de_la_persona(x), con_id=True)
                decididas.add(x["solicitud_id"])
        de_decisiones = {x["id"] for x in decisiones}
        for e in datos["elecciones"]:
            if e["decision_id"] in de_decisiones and not ya_esta("elecciones", e):
                insertar("elecciones", e, con_id=True)
        # Al decidir cambian el estado y los aeropuertos de la cotización, el viaje pasa a la decisión nueva y sus tramos
        # se reemplazan: una cotización ya cargada que recibe una decisión queda como en el origen
        al_dia = sorted(decididas & ya)
        for sid in al_dia:
            poner_al_dia("solicitudes", de_la_persona(cotizaciones[sid]))
        viajes, cargados = [v for v in datos["viajes"] if v["solicitud_id"] in cotizaciones], []
        for v in viajes:
            if not ya_esta("viajes", v):
                insertar("viajes", del_viaje(v), con_id=True)
                cargados.append(v)
            elif v["solicitud_id"] in al_dia:
                poner_al_dia("viajes", del_viaje(v))
                d.execute(text("delete from tramos_vuelo where viaje_id=:v"), {"v": v["id"]})
        de_viajes = {v["id"] for v in viajes}
        for t in datos["tramos_vuelo"]:
            if t["viaje_id"] in de_viajes and not ya_esta("tramos_vuelo", t):
                insertar("tramos_vuelo", t, con_id=True)

        # ---------- buscador y eventos, sin repetir ----------
        igual = "(({c} = :{p}) or ({c} is null and :{p} is null))"   # «no distinto de», también en SQLite
        # Con la misma clave se usa la respuesta de id mayor (`precios._leer`). Entran, de la más vieja a la más nueva,
        # las del origen posteriores a la última del destino: la más nueva de las dos bases queda de última.
        por_clave: dict = {}
        for b in datos["busquedas"]:
            por_clave.setdefault(b["clave"], []).append(b)
        for clave, respuestas in por_clave.items():
            en_destino = [f["creado"] or "" for f in _filas(d, f"select creado from busquedas where {igual.format(c='clave', p='clave')}",
                                                             clave=clave)]
            ultima = max(en_destino) if en_destino else None
            for b in sorted(respuestas, key=lambda r: (r["creado"] or "", r["id"])):
                if ultima is None or (b["creado"] or "") > ultima:
                    insertar("busquedas", b, con_id=False)

        def sin_repetir(tabla: str, filas_origen: list[dict]):
            """Entra lo que falte comparando la fila entera salvo el id: dos filas distintas del mismo segundo entran las
            dos, y una fila repetida en el origen entra tantas veces como falte en el destino."""
            restan: dict[tuple, int] = {}
            for f in filas_origen:
                v = valores(tabla, f, con_id=False)
                llave = tuple(sorted(v.items()))
                if llave not in restan:
                    donde = " and ".join(igual.format(c=c, p=c) for c in v)
                    restan[llave] = d.execute(text(f"select count(*) from {tabla} where {donde}"), v).scalar()
                if restan[llave]:
                    restan[llave] -= 1
                else:
                    insertar(tabla, v, con_id=False)

        sin_repetir("consultas_buscador", [{**q, "usuario_id": persona.get(q["usuario_id"])} for q in datos["consultas_buscador"]])
        for a in datos["aeropuertos_google"]:
            if d.execute(text("select 1 from aeropuertos_google where iata=:i"), {"i": a["iata"]}).first() is None:
                insertar("aeropuertos_google", a, con_id=False)
        sin_repetir("eventos", [{**ev, "usuario_id": persona.get(ev["usuario_id"])} for ev in datos["eventos"]
                                if not (ev["entidad"] == "solicitud" and ev["entidad_id"] not in cotizaciones)
                                and not (ev["entidad"] == "viaje" and ev["entidad_id"] not in de_viajes)])

        # ---------- el siguiente id sigue después de lo cargado (PostgreSQL) ----------
        if aplicar and d.dialect.name == "postgresql":   # `setval` no se revierte: en el ensayo no se toca
            for tabla in CON_ID:
                d.execute(text(f"select setval(pg_get_serial_sequence('{tabla}', 'id'), "                  # noqa: S608
                               f"greatest((select coalesce(max(id), 0) from {tabla}), 1))"))

        # ---------- rastro de la carga ----------
        total = sum(filas.values())
        if total:
            ahora = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            resumen = json.dumps({**{k: v for k, v in filas.items() if k != "eventos"},
                                  **({"cotizaciones puestas al día": al_dia} if al_dia else {})}, ensure_ascii=False)
            insertar("cargas_datos", {"fuente": fuente, "archivo": "cotizaciones, viajes y respuestas del buscador", "url": None,
                                      "huella": huella, "filas": total, "resultado": "cargada", "momento": ahora,
                                      "quien": "datos.importar_entorno"}, con_id=False)
            insertar("eventos", {"momento": ahora, "entidad": "carga", "entidad_id": None, "paso": "datos importados",
                                 "detalle": resumen[:500], "fuente": fuente, "duracion_ms": 0, "usuario_id": None}, con_id=False)
        resultado = {"filas": filas, "ya_cargadas": sorted(ya), "puestas_al_dia": al_dia,
                     "viajes": [f"V-{(v['creado'] or '0000')[:4]}-{v['id']:04d}" for v in cargados]}
        if aplicar:
            d.commit()
        else:
            d.rollback()
    return resultado


def _con_clave(url: str, clave: str) -> str:
    """Las cadenas de Supabase llevan `[YOUR-PASSWORD]`; la contraseña va aparte, como en `app/config.py`."""
    from urllib.parse import quote
    return url.replace("[YOUR-PASSWORD]", quote(clave, safe="")) if clave else url


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo not in ("ensayo", "aplicar") or not os.getenv("ORIGEN_URL") or not os.getenv("DESTINO_URL"):
        print(__doc__)
        sys.exit(2)
    try:
        r = importar(os.environ["ORIGEN_URL"], _con_clave(os.environ["DESTINO_URL"], os.getenv("DESTINO_CLAVE", "")),
                     aplicar=modo == "aplicar", fuente=os.getenv("FUENTE_CARGA", FUENTE))
    except ImportacionImpedida as e:
        print(e)
        sys.exit(1)
    print(json.dumps({"modo": modo, **r}, ensure_ascii=False))
