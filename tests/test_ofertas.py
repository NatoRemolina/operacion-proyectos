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
            "noches", "crudo", "ordinal", "tramo", "sin_reconocer", "normalizacion"} <= columnas
    indices = {i["name"] for i in inspect(db.motor).get_indexes("ofertas_tarifa")}
    assert {"ix_ofertas_tarifa_ruta_ida", "ux_ofertas_tarifa_origen"} <= indices and "ux_ofertas_tarifa_unica" not in indices


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
    # ronda 1, punto 4: «not included» no es gratis y la segunda maleta no llena la primera
    (["Checked bag not included"], (None, None)),
    (["1 free carry-on", "Checked bags not included"], (1, None)),
    (["0 checked bags included"], (None, None)),
    (["No free checked bags"], (None, None)),
    (["Carry-on bag not included"], (0, None)),
    (["2nd checked bag: $45"], (None, None)),
    (["2nd checked bag: $45", "1st checked bag: $35"], (None, 35.0)),
    (["1st checked bag: $35", "2nd checked bag: $45"], (None, 35.0)),
    (["Checked bag: $30"], (None, 30.0)),
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
    (["Free ticket changes"], "gratis"),
])
def test_cambios(lineas, esperado):
    assert ofertas.cambios(lineas) == esperado


@pytest.mark.parametrize("lineas, esperado", [
    (["No refunds"], "no"), (["Non-refundable"], "no"), (["Nonrefundable"], "no"), (["Full refunds"], "total"), (["Fully refundable"], "total"),
    (["Partial refunds"], "parcial"), (["Refund for a fee"], "parcial"), (["Free change, possible fare difference"], None),
])
def test_reembolso(lineas, esperado):
    assert ofertas.reembolso(lineas) == esperado


@pytest.mark.parametrize("lineas, esperado", [
    (["Free seat selection"], "incluido"), (["Seat selection included"], "incluido"),
    (["Seat selection for a fee"], "cargo"), (["Paid seat selection"], "cargo"), (["Standard seat"], None),
    (["Seat selection: $25"], "cargo"),
])
def test_asiento(lineas, esperado):
    assert ofertas.asiento(lineas) == esperado


@pytest.mark.parametrize("nombre, cambios_, reembolso_, esperado", [
    ("Basic Economy", "no", "no", "basica"), ("Economy Light", None, None, "basica"), ("Saver", None, None, "basica"),
    ("Main Cabin", "gratis", "no", "estandar"), ("Economy", None, None, "estandar"),
    ("Main Select", "gratis", "total", "flexible"), ("Economy Flex", None, None, "flexible"),
    ("Business", "gratis", "total", "premium"), ("Premium Economy", None, None, "premium"), ("First", None, None, "premium"),
    ("Tarifa", "no", None, "basica"),
    ("Delta One", None, None, "premium"), ("Mint", None, None, "premium"), ("Main Plus", "gratis", "no", "estandar"),
    ("Elite", None, None, None), ("Tarifa", None, None, None),     # sin reconocer: vacía, no «estandar»
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


def test_r1_2_una_opcion_sin_precio_se_guarda_y_la_limpieza_la_excluye():
    sin_precio = {"together": {"book_with": "Agencia Sin Precio", "airline": False, "option_title": "Economy",
                               "extensions": ["No refunds"], "baggage_prices": []}}
    clave = "reserva_MIA_LAS_2026-12-08_2026-12-11_AA7002.json"
    _guardar_respuesta(clave, _respuesta(opciones=[sin_precio]), "2026-11-02 10:00:00")
    ofertas.actualizar()
    fila = db.uno("select * from ofertas_tarifa where busqueda_clave=:c", c=clave)
    assert fila["precio"] is None and json.loads(fila["crudo"])["book_with"] == "Agencia Sin Precio"
    limpias, informe = ofertas.depurar([fila])
    assert limpias == [] and informe["descartes"] == {"sin precio": 1}


def test_r1_3_dos_opciones_iguales_del_mismo_vendedor_y_el_regreso_por_separado_no_se_pierden():
    kiwi = lambda precio: {"together": {"book_with": "Kiwi.com", "airline": False, "price": precio,  # noqa: E731
                                        "extensions": [], "baggage_prices": []}}
    separadas = {"departing": {"book_with": "Spirit", "airline": True, "price": 120, "option_title": "Basic"},
                 "returning": {"book_with": "Frontier", "airline": True, "price": 95, "option_title": "Basic"}}
    clave = "reserva_MIA_LAS_2026-12-08_2026-12-11_AA7003.json"
    _guardar_respuesta(clave, _respuesta(opciones=[kiwi(400), kiwi(430), separadas]), "2026-11-03 10:00:00")
    ofertas.actualizar()
    filas = db.todos("select ordinal, tramo, vendedor, precio from ofertas_tarifa where busqueda_clave=:c order by ordinal, tramo", c=clave)
    assert [(f["ordinal"], f["tramo"], f["vendedor"], f["precio"]) for f in filas] == [
        (0, "ida_vuelta", "Kiwi.com", 400), (1, "ida_vuelta", "Kiwi.com", 430), (2, "ida", "Spirit", 120), (2, "regreso", "Frontier", 95)]


def test_r1_5_lo_no_reconocido_queda_marcado():
    raro = {"together": {"book_with": "Aerolínea Rara", "airline": True, "price": 300, "option_title": "Elite",
                         "extensions": ["Refunds: ask the airline", "Extra legroom", "Change fee: $75"],
                         "baggage_prices": ["Bags: see airline", "1st checked bag: $40"]}}
    clave = "reserva_MIA_LAS_2026-12-08_2026-12-11_AA7005.json"
    _guardar_respuesta(clave, _respuesta(opciones=[raro]), "2026-11-04 10:00:00")
    ofertas.actualizar()
    fila = db.uno("select * from ofertas_tarifa where busqueda_clave=:c", c=clave)
    assert fila["normalizacion"] == "parcial" and fila["tarifa_normalizada"] is None
    assert json.loads(fila["sin_reconocer"]) == ["tarifa «Elite»", "Bags: see airline", "Refunds: ask the airline"]
    assert fila["cambios"] == "cargo" and fila["maleta_usd"] == 40


def test_r1_5_una_tarifa_entendida_queda_completa():
    _lectura_lista(clave="AA1851_2026-12-08_2026-12-08_2026-12-11", creado="2026-11-12 17:00:00")
    ofertas.actualizar()
    basica = db.uno("select * from ofertas_tarifa where fuente='pagina' and tarifa='Basic Economy' order by id desc limit 1")
    assert basica["normalizacion"] == "completa" and basica["sin_reconocer"] is None


def test_r1_6_el_crudo_nunca_lleva_el_pedido_de_reserva():
    """Las respuestas guardadas antes del 12 nov podían traer `booking_request` (URL y post_data de la reserva)."""
    vieja = {"together": {"book_with": "American", "airline": True, "price": 470, "option_title": "Basic Economy",
                          "booking_request": {"url": "https://www.google.com/travel/clk/f", "post_data": "u=secreto"},
                          "extensions": ["No refunds"], "baggage_prices": []}}
    clave = "reserva_MIA_LAS_2026-12-08_2026-12-11_AA7006.json"
    _guardar_respuesta(clave, _respuesta(opciones=[vieja]), "2026-11-05 10:00:00")
    ofertas.actualizar()
    fila = db.uno("select crudo from ofertas_tarifa where busqueda_clave=:c", c=clave)
    assert "booking_request" not in fila["crudo"] and "post_data" not in fila["crudo"]
    assert json.loads(fila["crudo"])["price"] == 470


def test_r1_7_una_reconfirmacion_lleva_sus_fechas_y_su_ruta():
    """La reconfirmación es el precio al decidir: su clave no trae fechas ni ruta, salen de `selected_flights`."""
    datos = _respuesta(612, search_parameters={"engine": "google_flights", "type": 1, "selected_flights_json": "{}"},
                       search_metadata={"created_at": "2026-11-12 15:30:00 UTC"})
    clave = "reconfirmacion_AA1851AA1851_202611121530.json"
    _guardar_respuesta(clave, datos, "2026-11-12 15:30:00")
    ofertas.actualizar()
    fila = db.uno("select * from ofertas_tarifa where busqueda_clave=:c", c=clave)
    assert (fila["ida"], fila["regreso"], fila["origen"], fila["destino"]) == ("2026-12-08", "2026-12-11", "MIA", "LAS")
    assert fila["anticipacion_dias"] == 26 and fila["noches"] == 3 and fila["vuelos"] == "AA1851" and fila["precio"] == 612


def test_r1_8_el_conteo_es_el_de_las_filas_que_entraron():
    clave = "reserva_MIA_LAS_2026-12-08_2026-12-11_AA7008.json"
    _guardar_respuesta(clave, _respuesta(455), "2026-11-06 10:00:00")
    antes = db.uno("select count(*) n from ofertas_tarifa")["n"]
    hechos = ofertas.actualizar()
    assert hechos["ocupado"] is False and hechos["filas"] == db.uno("select count(*) n from ofertas_tarifa")["n"] - antes >= 1


@pytest.mark.skipif(config.ES_SQLITE, reason="en SQLite la transacción de escritura ya serializa las corridas")
def test_r1_8_dos_corridas_a_la_vez_no_se_pisan():
    from sqlalchemy import text
    with db.motor.connect() as otra:   # otra corrida en curso tiene el cerrojo
        otra.execute(text("select pg_advisory_lock(:k)"), {"k": ofertas.CERROJO})
        try:
            assert ofertas.actualizar() == {"filas": 0, "respuestas": 0, "lecturas": 0, "ocupado": True}
        finally:
            otra.execute(text("select pg_advisory_unlock(:k)"), {"k": ofertas.CERROJO})
