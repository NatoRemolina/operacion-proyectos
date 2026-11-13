"""Limpieza al cargar para entrenar: nada se borra de la base; se descarta al leer y cada descarte queda contado por motivo."""
from app import db
from app.servicios import ofertas


def _f(precio=300.0, **otros) -> dict:
    return {"origen": "BOG", "destino": "MDE", "ida": "2027-02-10", "regreso": "2027-02-13", "vuelos": "AV9300",
            "vendedor": "Avianca", "tarifa": "Basic", "tarifa_normalizada": "basica", "moneda": "USD", "momento": "2027-01-10 10:00:00",
            "anticipacion_dias": 31, "precio": precio, **otros}


def test_descarta_por_motivo_y_lo_cuenta():
    filas = [_f(300 + i, vuelos=f"AV{i}") for i in range(8)] + [
        _f(None, vuelos="X1"), _f(0, vuelos="X2"), _f(300, moneda="EUR", vuelos="X3"), _f(300, origen=None, vuelos="X4"),
        _f(300, anticipacion_dias=-2, vuelos="X5"), _f(300, anticipacion_dias=900, vuelos="X6"),
        _f(9000, vuelos="X7"),                                        # atípico frente a la ruta y la tarifa
        _f(301, vuelos="AV1", momento="2027-01-10 18:00:00"),          # la misma tarifa vista otra vez el mismo día
    ]
    limpias, informe = ofertas.depurar(filas)
    assert len(limpias) == 8 and informe["leidas"] == 16 and informe["utiles"] == 8
    assert informe["descartes"] == {"sin precio": 2, "otra moneda": 1, "sin ruta o fecha": 1, "anticipación imposible": 2,
                                    "precio atípico": 1, "repetida el mismo día": 1}
    assert next(f for f in limpias if f["vuelos"] == "AV1")["precio"] == 301    # de las repetidas queda la más reciente


def test_con_pocos_datos_no_juzga_atipicos():
    limpias, informe = ofertas.depurar([_f(300, vuelos="A"), _f(9000, vuelos="B")])
    assert len(limpias) == 2 and "precio atípico" not in informe["descartes"]


def test_la_tabla_no_se_toca():
    antes = db.uno("select count(*) n from ofertas_tarifa")["n"]
    ofertas.limpias()
    assert db.uno("select count(*) n from ofertas_tarifa")["n"] == antes


def test_dos_ofertas_de_una_misma_respuesta_no_son_repetidas():
    """Kiwi.com a 400 y a 430 en la misma respuesta son dos ofertas; la misma tarifa en otra respuesta del mismo día sí se repite."""
    misma = [_f(400, vendedor="Kiwi.com", origen_fila="busqueda:1", ordinal=0), _f(430, vendedor="Kiwi.com", origen_fila="busqueda:1", ordinal=1)]
    limpias, informe = ofertas.depurar(misma)
    assert len(limpias) == 2 and informe["descartes"] == {}
    otra = _f(405, vendedor="Kiwi.com", origen_fila="busqueda:2", ordinal=0, momento="2027-01-10 18:00:00")
    limpias, informe = ofertas.depurar([*misma, otra])
    assert [f["precio"] for f in limpias] == [405] and informe["descartes"] == {"repetida el mismo día": 2}


def test_un_solo_tramo_no_se_mezcla_con_ida_y_vuelta():
    limpias, informe = ofertas.depurar([_f(300, vuelos="A"), _f(120, vuelos="B", tramo="ida"), _f(95, vuelos="B", tramo="regreso")])
    assert [f["vuelos"] for f in limpias] == ["A"] and informe["descartes"] == {"un solo tramo": 2}
