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


def _todos(url: str, sql: str, **p) -> list[dict]:
    with create_engine(url).connect() as c:
        return [dict(f._mapping) for f in c.execute(text(sql), p)]


def _decidir(url: str):
    """La decisión de la cotización 5, con su elección, su viaje y su tramo."""
    with create_engine(url).begin() as c:
        c.execute(text("update solicitudes set estado='decidido' where id=5"))
    _insertar(url, "decisiones", id=3, solicitud_id=5, proyecto_id=1, vuelo_id=10, usuario_id=1, total=785.0,
              creado="2026-11-12 19:50:00")
    _insertar(url, "elecciones", id=7, decision_id=3, solicitud_id=5, opcion_id=10, tipo="vuelo", posicion=1, elegida=1)
    _insertar(url, "viajes", id=2, solicitud_id=5, decision_id=3, proyecto_id=1, usuario_id=1, viajero_id=1,
              estado="pendiente_aprobacion", presupuesto_usd=1240.58, creado="2026-11-12 19:50:01")
    _insertar(url, "tramos_vuelo", id=4, viaje_id=2, sentido="ida", orden=1, numero="UA 1047")


def _preparar(tmp_path, decidida: bool = True) -> tuple[str, str]:
    """Origen con una cotización (decidida o todavía comparando); destino con las mismas personas, proyectos y viajeros
    en otro orden."""
    origen, destino = _base(tmp_path / "origen.db"), _base(tmp_path / "destino.db")
    _personas(origen, ["piloto@demo.local", "admin@demo.local"])
    _personas(destino, ["admin@demo.local", "piloto@demo.local"])
    for url, viajeros in ((origen, ["Andrés Molina"]), (destino, ["Otra persona", "Andrés Molina"])):
        _insertar(url, "proyectos", id=1, nombre="Residencial Summerlin (aéreo)")
        for i, nombre in enumerate(viajeros, start=1):
            _insertar(url, "viajeros", id=i, nombre=nombre)
    _insertar(origen, "solicitudes", id=5, proyecto_id=1, viajero_id=1, usuario_id=1, origen="MIA", destino="CNY",
              ida="2026-12-08", regreso="2026-12-11", estado="comparando", creado="2026-11-12 19:44:48")
    _insertar(origen, "opciones", id=10, solicitud_id=5, tipo="vuelo", titulo="UA 1047", precio=508.0, datos="{}")
    if decidida:
        _decidir(origen)
    _insertar(origen, "busquedas", clave="vuelos_MIA_CNY_2026-12-08_2026-12-11.json", cuerpo="{}", creado="2026-11-12")
    _insertar(origen, "consultas_buscador", momento="2026-11-12 19:44:48", solicitud_id=5, usuario_id=1, tipo="vuelos",
              origen="en vivo", clave="vuelos_MIA_CNY_2026-12-08_2026-12-11.json")
    _insertar(origen, "aeropuertos_google", iata="ICN", nombre="Incheon", ciudad="Seoul", visto="2026-11-12")
    _insertar(origen, "eventos", momento="2026-11-12 19:44:48", entidad="solicitud", entidad_id=5,
              paso="solicitud recibida", usuario_id=1)
    _insertar(origen, "eventos", momento="2026-11-12 19:40:00", entidad="acceso", entidad_id=1, paso="ingreso", usuario_id=1)
    return origen, destino


@pytest.fixture
def bases(tmp_path):
    """Origen con una cotización decidida; destino con las mismas personas, proyectos y viajeros en otro orden."""
    return _preparar(tmp_path)


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
    monkeypatch.setattr(importar_entorno, "ARCHIVOS_PUBLICADA", [archivo])
    with pytest.raises(importar_entorno.ImportacionImpedida, match="publicada"):
        importar_entorno.importar(origen, publicada.replace("[YOUR-PASSWORD]", "secreto"), aplicar=True)
    with pytest.raises(importar_entorno.ImportacionImpedida, match="misma base"):
        importar_entorno.importar(origen, origen, aplicar=True)


REF = "abcdefghijklmnopqrst"
CLAVE = ":" + "secreto" + "@"   # por partes: son de prueba y así no tienen la forma de una credencial real


def _publicada(tmp_path, monkeypatch, contenido: str):
    archivo = tmp_path / "publicada.env"
    archivo.write_text(contenido)
    monkeypatch.setattr(importar_entorno, "ARCHIVOS_PUBLICADA", [archivo])


@pytest.mark.parametrize("destino", [
    "postgresql://postgres" + CLAVE + "db." + REF + ".supabase.co:5432/postgres",           # conexión directa
    "postgresql://postgres." + REF + CLAVE + "aws-1-us-east-1.pooler.supabase.com:6543/postgres",   # otro agrupador
])
def test_reconoce_la_publicada_por_el_proyecto_aunque_cambie_la_forma_de_conectar(bases, tmp_path, monkeypatch, destino):
    origen, _ = bases
    _publicada(tmp_path, monkeypatch,
               "DATABASE_URL=postgresql://postgres." + REF + ":[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres\n")
    with pytest.raises(importar_entorno.ImportacionImpedida, match="publicada"):
        importar_entorno.importar(origen, destino, aplicar=True)


def test_tambien_la_reconoce_por_la_direccion_del_proyecto(bases, tmp_path, monkeypatch):
    origen, _ = bases
    _publicada(tmp_path, monkeypatch, "SUPABASE_URL=https://" + REF + ".supabase.co\n")
    with pytest.raises(importar_entorno.ImportacionImpedida, match="publicada"):
        importar_entorno.importar(origen, "postgresql://postgres" + CLAVE + "db." + REF + ".supabase.co:5432/postgres", aplicar=True)


def test_sin_saber_cual_es_la_publicada_no_escribe_en_una_base_remota(bases, monkeypatch):
    origen, _ = bases
    monkeypatch.setattr(importar_entorno, "ARCHIVOS_PUBLICADA", [])
    with pytest.raises(importar_entorno.ImportacionImpedida, match="no se puede comprobar"):
        importar_entorno.importar(origen, "postgresql://postgres.otroproyecto" + CLAVE + "servidor.example:5432/postgres", aplicar=True)


def test_un_destino_local_no_necesita_el_archivo_de_la_publicada(bases, monkeypatch):
    origen, destino = bases
    monkeypatch.setattr(importar_entorno, "ARCHIVOS_PUBLICADA", [])
    assert importar_entorno.importar(origen, destino, aplicar=True)["filas"]["solicitudes"] == 1


def test_no_carga_nada_si_un_nombre_esta_repetido_en_el_destino(bases):
    origen, destino = bases
    _insertar(destino, "viajeros", id=9, nombre="Andrés Molina")       # dos viajeros con el mismo nombre: no se adivina
    with pytest.raises(importar_entorno.ImportacionImpedida, match="repetido"):
        importar_entorno.importar(origen, destino, aplicar=True)
    assert _cuenta(destino, "solicitudes") == 0


CON_DECISION = ("decisiones", "elecciones", "viajes", "tramos_vuelo")


def test_una_decision_posterior_entra_en_la_cotizacion_ya_cargada(tmp_path):
    """La cotización se cargó cuando todavía comparaba; después se decidió en el origen."""
    origen, destino = _preparar(tmp_path, decidida=False)
    primera = importar_entorno.importar(origen, destino, aplicar=True)
    assert primera["filas"]["solicitudes"] == 1 and not set(CON_DECISION) & set(primera["filas"])
    _decidir(origen)
    _insertar(origen, "eventos", momento="2026-11-12 19:50:00", entidad="solicitud", entidad_id=5,
              paso="decisión guardada", usuario_id=1)
    r = importar_entorno.importar(origen, destino, aplicar=True)
    assert {t: r["filas"].get(t) for t in CON_DECISION} == dict.fromkeys(CON_DECISION, 1)
    assert r["ya_cargadas"] == [5] and r["puestas_al_dia"] == [5] and r["viajes"] == ["V-2026-0002"]
    assert r["filas"]["eventos"] == 2                                                # la decisión y el rastro de la carga
    assert _uno(destino, "select estado from solicitudes where id=5")["estado"] == "decidido"
    v = _uno(destino, "select usuario_id, decision_id from viajes where id=2")
    assert v == {"usuario_id": 2, "decision_id": 3}                                  # la persona, emparejada por correo
    otra = importar_entorno.importar(origen, destino, aplicar=True)
    assert otra["filas"] == {} and otra["puestas_al_dia"] == []


def test_una_nueva_decision_pone_al_dia_la_cotizacion_y_reemplaza_los_tramos(bases):
    """Se decide otra vez en el origen después de cargar: el vuelo nuevo sale de otro aeropuerto, el viaje pasa a la
    decisión nueva con otro presupuesto y sus tramos se reemplazan, como hace la plataforma al decidir."""
    origen, destino = bases
    importar_entorno.importar(origen, destino, aplicar=True)
    _insertar(origen, "decisiones", id=8, solicitud_id=5, proyecto_id=1, vuelo_id=10, usuario_id=1, total=812.0,
              creado="2026-11-13 09:00:00")
    _insertar(origen, "elecciones", id=9, decision_id=8, solicitud_id=5, opcion_id=10, tipo="vuelo", posicion=1, elegida=1)
    with create_engine(origen).begin() as c:
        c.execute(text("update solicitudes set origen='FLL' where id=5"))
        c.execute(text("update viajes set decision_id=8, presupuesto_usd=1300.5 where id=2"))
        c.execute(text("delete from tramos_vuelo where viaje_id=2"))
    _insertar(origen, "tramos_vuelo", id=11, viaje_id=2, sentido="ida", orden=1, numero="B6 15")
    _insertar(origen, "tramos_vuelo", id=12, viaje_id=2, sentido="regreso", orden=1, numero="B6 16")
    r = importar_entorno.importar(origen, destino, aplicar=True)
    assert r["puestas_al_dia"] == [5] and r["viajes"] == []
    assert {t: r["filas"].get(t) for t in CON_DECISION} == {"decisiones": 1, "elecciones": 1, "viajes": None, "tramos_vuelo": 2}
    assert _uno(destino, "select origen from solicitudes where id=5")["origen"] == "FLL"
    v = _uno(destino, "select decision_id, presupuesto_usd, usuario_id from viajes where id=2")
    assert v == {"decision_id": 8, "presupuesto_usd": 1300.5, "usuario_id": 2}
    assert [t["id"] for t in _todos(destino, "select id from tramos_vuelo where viaje_id=2 order by id")] == [11, 12]
    assert importar_entorno.importar(origen, destino, aplicar=True)["filas"] == {}


def test_no_carga_nada_si_una_decision_de_una_cotizacion_ya_cargada_choca(tmp_path):
    origen, destino = _preparar(tmp_path, decidida=False)
    importar_entorno.importar(origen, destino, aplicar=True)
    _decidir(origen)
    _insertar(destino, "decisiones", id=3, solicitud_id=5, proyecto_id=1, total=10.0, creado="2026-11-12 23:00:00")
    with pytest.raises(importar_entorno.ImportacionImpedida, match="decisión 3 ya existe"):
        importar_entorno.importar(origen, destino, aplicar=True)
    assert _cuenta(destino, "viajes") == 0 and _cuenta(destino, "elecciones") == 0
    assert _uno(destino, "select estado from solicitudes where id=5")["estado"] == "comparando"


CLAVE_VUELOS = "vuelos_MIA_CNY_2026-12-08_2026-12-11.json"
ULTIMA = f"select cuerpo from busquedas where clave='{CLAVE_VUELOS}' order by id desc limit 1"   # la que usa `precios._leer`


def test_de_las_respuestas_con_la_misma_clave_queda_de_ultima_la_mas_nueva(bases):
    origen, destino = bases
    _insertar(destino, "busquedas", clave=CLAVE_VUELOS, cuerpo='{"de": "destino"}', creado="2026-11-10 08:00:00")
    # en el origen la más nueva no es la última por id
    _insertar(origen, "busquedas", clave=CLAVE_VUELOS, cuerpo='{"de": "origen, la más nueva"}', creado="2026-11-13 08:00:00")
    _insertar(origen, "busquedas", clave=CLAVE_VUELOS, cuerpo='{"de": "origen, anterior a la del destino"}',
              creado="2026-11-01 08:00:00")
    r = importar_entorno.importar(origen, destino, aplicar=True)
    assert r["filas"]["busquedas"] == 2                                    # las dos más nuevas que la del destino, en orden
    assert _uno(destino, ULTIMA)["cuerpo"] == '{"de": "origen, la más nueva"}'
    assert not _uno(destino, "select id from busquedas where cuerpo like '%anterior%'")
    assert "busquedas" not in importar_entorno.importar(origen, destino, aplicar=True)["filas"]


def test_no_cambia_la_respuesta_si_la_del_destino_es_mas_nueva(bases):
    origen, destino = bases
    _insertar(destino, "busquedas", clave=CLAVE_VUELOS, cuerpo='{"de": "destino"}', creado="2026-11-14 08:00:00")
    assert "busquedas" not in importar_entorno.importar(origen, destino, aplicar=True)["filas"]
    assert _uno(destino, ULTIMA)["cuerpo"] == '{"de": "destino"}'


def test_consultas_y_eventos_del_mismo_segundo_no_se_juntan(bases):
    """Dos filas distintas del mismo segundo entran las dos; una fila repetida entra tantas veces como falte."""
    origen, destino = bases
    consulta = dict(momento="2026-11-12 19:44:48", solicitud_id=5, tipo="vuelos", origen="en vivo", clave=CLAVE_VUELOS)
    _insertar(origen, "consultas_buscador", **{**consulta, "usuario_id": 1})              # la misma otra vez
    _insertar(origen, "consultas_buscador", **{**consulta, "usuario_id": 1, "origen": "guardado"})   # otra, del mismo segundo
    _insertar(destino, "consultas_buscador", **{**consulta, "usuario_id": 2})             # una de las dos ya está
    _insertar(origen, "eventos", momento="2026-11-12 19:44:48", entidad="solicitud", entidad_id=5,
              paso="solicitud recibida", detalle="otra solicitud recibida en el mismo segundo", usuario_id=1)
    r = importar_entorno.importar(origen, destino, aplicar=True)
    assert r["filas"]["consultas_buscador"] == 2 and r["filas"]["eventos"] == 3          # más el rastro de la carga
    assert _cuenta(destino, "consultas_buscador") == 3
    assert _uno(destino, "select count(*) n from consultas_buscador where origen='en vivo'")["n"] == 2
    assert _uno(destino, "select count(*) n from eventos where paso='solicitud recibida'")["n"] == 2
    otra = importar_entorno.importar(origen, destino, aplicar=True)
    assert otra["filas"] == {}
