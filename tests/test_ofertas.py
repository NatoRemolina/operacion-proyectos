"""Tarifas vistas (`ofertas_tarifa`): una fila por tarifa, solo se añaden filas y la misma tarifa no se repite."""
import json
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import config, db
from app.servicios import ofertas
from datos import migracion


def _fila(**otros) -> dict:
    return {"momento": db.ahora(), "fuente": "buscador", "origen_fila": "busqueda:prueba-unica", "origen": "MIA", "destino": "LAS",
            "ida": "2026-12-08", "regreso": "2026-12-11", "vuelos": "AA1851", "vendedor": "American", "es_aerolinea": 1,
            "tarifa": "Basic Economy", "tarifa_normalizada": "basica", "precio": 458.0, "moneda": "USD", **otros}


def test_la_tabla_existe_con_sus_indices():
    columnas = {c["name"] for c in inspect(db.motor).get_columns("ofertas_tarifa")}
    assert {"momento", "fuente", "solicitud_id", "opcion_id", "analisis_id", "busqueda_clave", "origen", "destino", "ida",
            "regreso", "vuelos", "aerolinea", "vendedor", "es_aerolinea", "tarifa", "tarifa_normalizada", "precio", "moneda",
            "equipaje_mano", "maleta_usd", "cambios", "reembolso", "asiento", "anticipacion_dias", "dia_semana",
            "noches", "crudo"} <= columnas
    indices = {i["name"] for i in inspect(db.motor).get_indexes("ofertas_tarifa")}
    assert {"ix_ofertas_tarifa_ruta_ida", "ux_ofertas_tarifa_unica"} <= indices


def test_la_misma_tarifa_de_la_misma_fuente_no_se_repite():
    db.insertar("ofertas_tarifa", **_fila())
    with pytest.raises(IntegrityError):
        db.insertar("ofertas_tarifa", **_fila(precio=460.0))
    db.insertar("ofertas_tarifa", **_fila(fuente="pagina"))          # la misma tarifa leída en la página es otra fila
    db.insertar("ofertas_tarifa", **_fila(tarifa="Main Cabin", tarifa_normalizada="estandar", precio=588.0))
    assert db.uno("select count(*) n from ofertas_tarifa where origen_fila='busqueda:prueba-unica'")["n"] == 3


def test_la_migracion_de_la_tabla_se_puede_repetir():
    hechos = migracion._tablas_modelo()
    assert hechos == migracion._tablas_modelo()
    assert "ofertas_tarifa" in hechos["tablas_modelo"]


@pytest.mark.skipif(config.ES_SQLITE, reason="RLS solo existe en PostgreSQL")
def test_la_tabla_tiene_rls():
    assert db.uno("select relrowsecurity r from pg_class where relname='ofertas_tarifa'")["r"]


def test_solo_valores_conocidos():
    assert set(ofertas.TARIFAS) == {"basica", "estandar", "flexible", "premium"}
    assert set(ofertas.CAMBIOS) == {"gratis", "cargo", "no"} and set(ofertas.REEMBOLSOS) == {"total", "parcial", "no"}
    assert set(ofertas.ASIENTOS) == {"incluido", "cargo"} and set(ofertas.FUENTES) == {"buscador", "pagina"}


# ---------- normalización del texto de Google, tabla por tabla ----------
@pytest.mark.parametrize("lineas, esperado", [
    (["1 free carry-on", "1st checked bag: $110"], (1, 110.0)),
    (["1 free carry-on", "1st checked bag: 110"], (1, 110.0)),
    (["1 free carry-on", "1st checked bag free"], (1, 0.0)),
    (["Carry-on bag: $35", "1st checked bag: $40"], (0, 40.0)),
    (["No carry-on bag", "Checked bags for a fee"], (0, None)),
    (["1 carry-on bag included", "1 checked bag included"], (1, 0.0)),
    (["Free checked bag"], (None, 0.0)),
    ([], (None, None)),
])
def test_equipaje(lineas, esperado):
    assert ofertas.equipaje(lineas) == esperado


@pytest.mark.parametrize("lineas, esperado", [
    (["Free change, possible fare difference"], "gratis"),
    (["Free changes"], "gratis"),
    (["No ticket changes"], "no"),
    (["Changes not allowed"], "no"),
    (["Change fee: $75"], "cargo"),
    (["Changes for a fee"], "cargo"),
    (["Seat selection for a fee"], None),
])
def test_cambios(lineas, esperado):
    assert ofertas.cambios(lineas) == esperado


@pytest.mark.parametrize("lineas, esperado", [
    (["No refunds"], "no"), (["Non-refundable"], "no"), (["Full refunds"], "total"), (["Fully refundable"], "total"),
    (["Partial refunds"], "parcial"), (["Refund for a fee"], "parcial"), (["Free change, possible fare difference"], None),
])
def test_reembolso(lineas, esperado):
    assert ofertas.reembolso(lineas) == esperado


@pytest.mark.parametrize("lineas, esperado", [
    (["Free seat selection"], "incluido"), (["Seat selection included"], "incluido"),
    (["Seat selection for a fee"], "cargo"), (["Paid seat selection"], "cargo"), (["Standard seat"], None),
])
def test_asiento(lineas, esperado):
    assert ofertas.asiento(lineas) == esperado


@pytest.mark.parametrize("nombre, cambios_, reembolso_, esperado", [
    ("Basic Economy", "no", "no", "basica"), ("Economy Light", None, None, "basica"), ("Saver", None, None, "basica"),
    ("Main Cabin", "gratis", "no", "estandar"), ("Economy", None, None, "estandar"),
    ("Main Select", "gratis", "total", "flexible"), ("Economy Flex", None, None, "flexible"),
    ("Business", "gratis", "total", "premium"), ("Premium Economy", None, None, "premium"), ("First", None, None, "premium"),
    ("Tarifa", "no", None, "basica"),
])
def test_tarifa_normalizada(nombre, cambios_, reembolso_, esperado):
    assert ofertas.tarifa_normalizada(nombre, cambios_, reembolso_) == esperado


# ---------- extractor ----------
LECTURA = json.loads((Path(__file__).parent / "datos" / "analisis_prueba6.json").read_text())


def _lectura_lista(clave="AA1851_2026-12-08_2026-12-08_2026-12-11", creado="2026-11-12 15:00:00") -> int:
    """Una lectura del analizador como la que guarda el otro frente. En esta rama la tabla aún no existe: se crea igual."""
    db.ejecutar("""create table if not exists analisis_vuelo (id integer primary key, opcion_id integer, solicitud_id integer,
                   usuario_id integer, clave text not null, url text not null, estado text not null, motivo text, datos text,
                   captura text, duracion_ms integer, creado text, terminado text)""")
    aid = (db.uno("select max(id) i from analisis_vuelo")["i"] or 0) + 1   # el id explícito vale con y sin la tabla real
    db.ejecutar("""insert into analisis_vuelo (id, clave, url, estado, datos, creado, terminado)
                   values (:i, :c, 'https://www.google.com/travel/flights/booking', 'listo', :d, :t, :t)""",
                i=aid, c=clave, d=json.dumps(LECTURA), t=creado)
    return aid


def test_extrae_la_lectura_de_la_pagina_y_las_respuestas_guardadas():
    aid = _lectura_lista()
    hechos = ofertas.actualizar()
    assert hechos["filas"] >= 4 and hechos["lecturas"] >= 1
    basica = db.uno("select * from ofertas_tarifa where analisis_id=:a and tarifa='Basic Economy'", a=aid)
    assert basica["fuente"] == "pagina" and basica["precio"] == 619.0 and basica["maleta_usd"] == 110.0
    assert basica["cambios"] == "no" and basica["reembolso"] == "no" and basica["tarifa_normalizada"] == "basica"
    assert basica["origen"] == "MIA" and basica["destino"] == "LAS" and basica["vuelos"] == "AA1851"
    assert basica["vendedor"] == "American" and basica["es_aerolinea"] == 1 and basica["asiento"] == "cargo"
    assert basica["ida"] == "2026-12-08" and basica["noches"] == 3 and basica["anticipacion_dias"] == 26
    assert basica["dia_semana"] == 1 and basica["equipaje_mano"] == 1 and json.loads(basica["crudo"])["nombre"] == "Basic Economy"
    plus = db.uno("select * from ofertas_tarifa where analisis_id=:a and tarifa='Main Plus'", a=aid)
    assert plus["maleta_usd"] == 0 and plus["cambios"] == "gratis" and plus["asiento"] == "incluido"
    select = db.uno("select * from ofertas_tarifa where analisis_id=:a and tarifa='Main Select'", a=aid)
    assert select["reembolso"] == "total" and select["tarifa_normalizada"] == "flexible"
    clave = "tarifas_MIA_LAS_2026-12-08_2026-12-11_AA1851.json"
    del_buscador = db.uno("select * from ofertas_tarifa where busqueda_clave=:c and tarifa='Basic Economy'", c=clave)
    assert del_buscador["fuente"] == "buscador" and del_buscador["precio"] == 458.0 and del_buscador["maleta_usd"] == 110.0
    assert del_buscador["cambios"] == "no" and del_buscador["reembolso"] == "no" and del_buscador["vuelos"] == "AA1851"
    assert del_buscador["momento"].startswith("2026-11-11") and del_buscador["anticipacion_dias"] == 27
    assert db.uno("select id from eventos where entidad='ofertas_tarifa' and paso='tarifas extraídas' order by id desc limit 1")


def test_correrlo_dos_veces_no_duplica():
    _lectura_lista(clave="AA1851_2026-12-08_2026-12-08_2026-12-11", creado="2026-11-12 16:00:00")
    ofertas.actualizar()
    antes = db.uno("select count(*) n from ofertas_tarifa")["n"]
    assert ofertas.actualizar()["filas"] == 0
    assert db.uno("select count(*) n from ofertas_tarifa")["n"] == antes


def test_una_respuesta_de_la_tabla_compartida_se_extrae_con_su_cotizacion():
    cuerpo = json.loads((config.DIR_RESPALDO / "tarifas_MIA_LAS_2026-12-08_2026-12-11_AA1851.json").read_text())["reserva"]
    clave = "reserva_MIA_LAS_2026-12-08_2026-12-11_AA9999.json"
    db.insertar("busquedas", clave=clave, cuerpo=json.dumps(cuerpo), creado="2026-11-11 21:25:22")
    db.insertar("consultas_buscador", momento=db.ahora(), solicitud_id=None, tipo="tarifas", origen="en vivo", clave=clave)
    ofertas.actualizar()
    filas = db.todos("select * from ofertas_tarifa where busqueda_clave=:c", c=clave)
    assert len(filas) == 4 and {f["tarifa_normalizada"] for f in filas} == {"basica", "estandar", "flexible"}


def test_sin_la_tabla_del_analizador_no_falla(monkeypatch):
    monkeypatch.setattr(ofertas, "_existe", lambda tabla: tabla != "analisis_vuelo")
    hechos = ofertas.actualizar()
    assert hechos["lecturas"] == 0


def test_el_tablero_lo_llama_como_mucho_cada_diez_minutos(monkeypatch):
    llamadas = []
    monkeypatch.setattr(ofertas, "actualizar", lambda: llamadas.append(1) or {"filas": 0})
    monkeypatch.setattr(ofertas, "_ultima", [None])
    ofertas.actualizar_si_toca()
    ofertas.actualizar_si_toca()
    assert len(llamadas) == 1


def test_se_puede_correr_desde_la_linea_de_comandos(capsys):
    from datos import ofertas as programa
    programa.main()
    assert "ofertas_tarifa:" in capsys.readouterr().out


# ---------- ronda 1 ----------
def _respuesta(precio=458, opciones=None, **cambios) -> dict:
    """Una respuesta del buscador con opciones de reserva, a partir de la guardada de MIA-LAS."""
    base = json.loads((config.DIR_RESPALDO / "tarifas_MIA_LAS_2026-12-08_2026-12-11_AA1851.json").read_text())["reserva"]
    base = json.loads(json.dumps(base))
    base["booking_options"] = opciones if opciones is not None else [
        {"together": {**base["booking_options"][0]["together"], "price": precio}}]
    return {**base, **cambios}


def _guardar_respuesta(clave: str, datos: dict, creado: str) -> int:
    return db.insertar("busquedas", clave=clave, cuerpo=json.dumps(datos), creado=creado)


def test_r1_1_la_misma_tarifa_vista_en_tres_momentos_queda_tres_veces():
    clave = "reserva_MIA_LAS_2026-12-08_2026-12-11_AA7001.json"
    ids = [_guardar_respuesta(clave, _respuesta(458), "2026-11-01 10:00:00"),
           _guardar_respuesta(clave, _respuesta(499), "2026-11-05 10:00:00")]
    ofertas.actualizar()
    ids.append(_guardar_respuesta(clave, _respuesta(520), "2026-11-09 10:00:00"))
    ofertas.actualizar()
    filas = db.todos("select origen_fila, precio, busqueda_clave from ofertas_tarifa where busqueda_clave=:c order by precio", c=clave)
    assert [f["precio"] for f in filas] == [458, 499, 520]
    assert [f["origen_fila"] for f in filas] == [f"busqueda:{i}" for i in ids]


def test_r1_1_un_archivo_de_respaldo_solo_entra_si_la_tabla_no_tiene_esa_clave():
    archivo = "tarifas_MIA_LAS_2026-12-08_2026-12-11_AA1851.json"
    ofertas.actualizar()
    de_archivo = db.todos("select origen_fila from ofertas_tarifa where busqueda_clave=:c", c=archivo)
    assert de_archivo and all(f["origen_fila"] == f"archivo:{archivo}" for f in de_archivo)
    assert db.uno("select count(*) n from ofertas_tarifa where origen_fila like 'busqueda:%' and busqueda_clave=:c", c=archivo)["n"] == 0
