"""Llevar cotizaciones, viajes y respuestas del buscador de una base de la plataforma a otra (`datos/importar_entorno.py`).

Se prueba con dos bases SQLite temporales con el esquema completo; en PostgreSQL el script además ajusta las secuencias.
"""
import pytest
from sqlalchemy import create_engine, text

from app import db
from datos import importar_entorno


def _base(ruta) -> str:
    url = f"sqlite:///{ruta}"
    db.meta.create_all(create_engine(url))
    return url


def _insertar(url: str, tabla: str, **valores):
    with create_engine(url).begin() as c:
        c.execute(db.meta.tables[tabla].insert().values(**valores))


def _uno(url: str, sql: str, **p) -> dict | None:
    with create_engine(url).connect() as c:
        fila = c.execute(text(sql), p).first()
        return dict(fila._mapping) if fila else None


def _cuenta(url: str, tabla: str) -> int:
    return _uno(url, f"select count(*) n from {tabla}")["n"]   # noqa: S608


def _personas(url: str, orden: list[str]):
    for i, correo in enumerate(orden, start=1):
        _insertar(url, "usuarios", id=i, correo=correo, nombre=correo.split("@")[0], rol="colaborador", activo=1,
                  clave_hash="x", fallos=0, creado="2026-11-01 00:00:00")


@pytest.fixture
def bases(tmp_path):
    """Origen con una cotización decidida; destino con las mismas personas, proyectos y viajeros en otro orden."""
    origen, destino = _base(tmp_path / "origen.db"), _base(tmp_path / "destino.db")
    _personas(origen, ["piloto@demo.local", "admin@demo.local"])
    _personas(destino, ["admin@demo.local", "piloto@demo.local"])
    for url, viajeros in ((origen, ["Andrés Molina"]), (destino, ["Otra persona", "Andrés Molina"])):
        _insertar(url, "proyectos", id=1, nombre="Residencial Summerlin (aéreo)")
        for i, nombre in enumerate(viajeros, start=1):
            _insertar(url, "viajeros", id=i, nombre=nombre)
    _insertar(origen, "solicitudes", id=5, proyecto_id=1, viajero_id=1, usuario_id=1, origen="MIA", destino="CNY",
              ida="2026-12-08", regreso="2026-12-11", estado="decidido", creado="2026-11-12 19:44:48")
    _insertar(origen, "opciones", id=10, solicitud_id=5, tipo="vuelo", titulo="UA 1047", precio=508.0, datos="{}")
    _insertar(origen, "decisiones", id=3, solicitud_id=5, proyecto_id=1, vuelo_id=10, usuario_id=1, total=785.0,
              creado="2026-11-12 19:50:00")
    _insertar(origen, "elecciones", id=7, decision_id=3, solicitud_id=5, opcion_id=10, tipo="vuelo", posicion=1, elegida=1)
    _insertar(origen, "viajes", id=2, solicitud_id=5, decision_id=3, proyecto_id=1, usuario_id=1, viajero_id=1,
              estado="pendiente_aprobacion", presupuesto_usd=1240.58, creado="2026-11-12 19:50:01")
    _insertar(origen, "tramos_vuelo", id=4, viaje_id=2, sentido="ida", orden=1, numero="UA 1047")
    _insertar(origen, "busquedas", clave="vuelos_MIA_CNY_2026-12-08_2026-12-11.json", cuerpo="{}", creado="2026-11-12")
    _insertar(origen, "consultas_buscador", momento="2026-11-12 19:44:48", solicitud_id=5, usuario_id=1, tipo="vuelos",
              origen="en vivo", clave="vuelos_MIA_CNY_2026-12-08_2026-12-11.json")
    _insertar(origen, "aeropuertos_google", iata="ICN", nombre="Incheon", ciudad="Seoul", visto="2026-11-12")
    _insertar(origen, "eventos", momento="2026-11-12 19:44:48", entidad="solicitud", entidad_id=5,
              paso="solicitud recibida", usuario_id=1)
    _insertar(origen, "eventos", momento="2026-11-12 19:40:00", entidad="acceso", entidad_id=1, paso="ingreso", usuario_id=1)
    return origen, destino


def test_el_ensayo_no_escribe_nada(bases):
    origen, destino = bases
    r = importar_entorno.importar(origen, destino, aplicar=False)
    assert r["filas"]["solicitudes"] == 1 and r["viajes"] == ["V-2026-0002"]
    assert _cuenta(destino, "solicitudes") == 0 and _cuenta(destino, "busquedas") == 0


def test_carga_con_los_mismos_ids_y_las_personas_emparejadas(bases):
    origen, destino = bases
    r = importar_entorno.importar(origen, destino, aplicar=True)
    assert r["filas"] == {"solicitudes": 1, "opciones": 1, "decisiones": 1, "elecciones": 1, "viajes": 1, "tramos_vuelo": 1,
                          "busquedas": 1, "consultas_buscador": 1, "aeropuertos_google": 1, "eventos": 2, "cargas_datos": 1}
    piloto = _uno(destino, "select id from usuarios where correo='piloto@demo.local'")["id"]
    andres = _uno(destino, "select id from viajeros where nombre='Andrés Molina'")["id"]
    s = _uno(destino, "select * from solicitudes where id=5")
    assert (s["usuario_id"], s["viajero_id"]) == (piloto, andres) == (2, 2)           # por correo y por nombre, no por id
    v = _uno(destino, "select * from viajes where id=2")                             # V-2026-0002 sigue siendo V-2026-0002
    assert (v["usuario_id"], v["decision_id"], v["solicitud_id"]) == (piloto, 3, 5)
    assert _uno(destino, "select usuario_id from consultas_buscador")["usuario_id"] == piloto
    assert not _uno(destino, "select id from eventos where entidad='acceso'")        # los ingresos son de cada entorno
    carga = _uno(destino, "select * from cargas_datos")
    assert carga["filas"] == 10 and carga["resultado"] == "cargada" and len(carga["huella"]) == 64
    assert _uno(destino, "select id from eventos where entidad='carga' and paso='datos importados'")
    # repetirla no duplica nada
    otra = importar_entorno.importar(origen, destino, aplicar=True)
    assert otra["filas"] == {} and otra["ya_cargadas"] == [5]
    assert _cuenta(destino, "busquedas") == 1 and _cuenta(destino, "cargas_datos") == 1


def test_no_carga_nada_si_un_id_choca_o_falta_una_persona(bases):
    origen, destino = bases
    _insertar(destino, "solicitudes", id=5, proyecto_id=1, viajero_id=1, usuario_id=1, origen="BOG", destino="MAD",
              ida="2027-01-01", regreso="2027-01-05", creado="2026-11-10 00:00:00")
    with pytest.raises(importar_entorno.ImportacionImpedida, match="cotización 5 ya existe"):
        importar_entorno.importar(origen, destino, aplicar=True)
    assert _cuenta(destino, "busquedas") == 0 and _cuenta(destino, "opciones") == 0
    with create_engine(destino).begin() as c:
        c.execute(text("delete from solicitudes"))
        c.execute(text("update usuarios set correo='otra@demo.local' where correo='piloto@demo.local'"))
    with pytest.raises(importar_entorno.ImportacionImpedida, match="persona 1"):
        importar_entorno.importar(origen, destino, aplicar=True)
    assert _cuenta(destino, "solicitudes") == 0


def test_nunca_escribe_en_la_base_publicada(bases, tmp_path, monkeypatch):
    origen, _ = bases
    publicada = "postgresql://postgres.proyecto-publicado:[YOUR-PASSWORD]@servidor.pooler.example:5432/postgres"
    archivo = tmp_path / ".env.supabase-publicada"
    archivo.write_text(f"DATABASE_URL={publicada}\n")
    monkeypatch.setattr(importar_entorno, "ENV_PUBLICADA", archivo)
    with pytest.raises(importar_entorno.ImportacionImpedida, match="publicada"):
        importar_entorno.importar(origen, publicada.replace("[YOUR-PASSWORD]", "secreto"), aplicar=True)
    with pytest.raises(importar_entorno.ImportacionImpedida, match="misma base"):
        importar_entorno.importar(origen, origen, aplicar=True)
