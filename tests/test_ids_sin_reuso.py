"""Un gasto borrado no presta su número: en SQLite, sin AUTOINCREMENT, el id más alto que se borra se vuelve a dar, y el
gasto nuevo heredaba los eventos del anterior (la bitácora de otro gasto). En PostgreSQL la secuencia nunca repite."""
import pytest

from app import config, db

SOLO_SQLITE = pytest.mark.skipif(not config.ES_SQLITE, reason="la reutilización de ids es propia de SQLite")


@SOLO_SQLITE
@pytest.mark.parametrize("tabla, columnas", [
    ("gastos", {"estado": "revision"}),
    ("analisis_vuelo", {"clave": "zz_sonda", "url": "https://ejemplo.invalid", "estado": "pendiente"}),
    ("tramos_vuelo", {"sentido": "ida", "orden": 1}),
])
def test_la_fila_borrada_no_presta_su_id(tabla, columnas):
    primero = db.insertar(tabla, **columnas)
    db.ejecutar(f"delete from {tabla} where id=:i", i=primero)  # noqa: S608  nombre fijo de la prueba
    segundo = db.insertar(tabla, **columnas)
    try:
        assert segundo > primero
    finally:
        db.ejecutar(f"delete from {tabla} where id=:i", i=segundo)  # noqa: S608


def test_un_gasto_nuevo_no_hereda_la_bitacora_de_uno_borrado():
    from app.servicios import eventos
    viejo = db.insertar("gastos", estado="revision")
    eventos.registrar("gasto", viejo, "documento recibido", "de otro gasto", "prueba")
    db.ejecutar("delete from gastos where id=:i", i=viejo)
    nuevo = db.insertar("gastos", estado="revision")
    try:
        assert not db.uno("select id from eventos where entidad='gasto' and entidad_id=:i and detalle='de otro gasto'", i=nuevo)
    finally:
        db.ejecutar("delete from gastos where id=:i", i=nuevo)
        db.ejecutar("delete from eventos where entidad='gasto' and entidad_id in (:v, :n)", v=viejo, n=nuevo)
