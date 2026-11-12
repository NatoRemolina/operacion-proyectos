"""Datos geográficos del mundo y buscador de origen y destino (con el subconjunto de `tests/datos/geografia_mini`)."""
from pathlib import Path

from app import db

MINI = Path(__file__).parent / "datos" / "geografia_mini"


# ---------- tarea 5: datos ----------
def test_carga_idempotente_del_subconjunto(cliente):
    from app.servicios import geografia
    antes = db.uno("select max(id) n from cargas_datos")["n"]
    primera = geografia.cargar(MINI)
    segunda = geografia.cargar(MINI)
    # dos cargas, dos filas por archivo: ninguna carga pasa sin registro
    filas = db.todos("select resultado from cargas_datos where id>:i and archivo='aeropuertos.csv' order by id", i=antes)
    assert [f["resultado"] for f in filas] == ["sin cambios", "sin cambios"]   # la semilla ya lo había cargado
    assert primera == segunda == {"aeropuertos": 18, "lugares": 16, "paises": 7}
    for tabla, n in (("aeropuertos_mundo", 18), ("lugares", 16), ("paises", 7)):
        assert db.uno(f"select count(*) n from {tabla}")["n"] == n  # noqa: S608
    assert db.uno("select nombre_es from paises where codigo='US'")["nombre_es"] == "Estados Unidos"
    moab = db.uno("select * from lugares where id=5543307")
    assert (moab["nombre"], moab["region"], moab["pais"], moab["poblacion"]) == ("Moab", "Utah", "US", 5235)
    assert db.uno("select grande from aeropuertos_mundo where iata='SLC'")["grande"] == 1


def test_cada_carga_queda_registrada_aunque_no_cambie_nada(cliente):
    from app.servicios import geografia
    geografia.cargar(MINI)
    ultima = db.uno("select max(id) n from cargas_datos")["n"]
    geografia.cargar(MINI, quien="Pruebas")
    nuevas = db.todos("select * from cargas_datos where id>:i order by id", i=ultima)
    # una fila por archivo (aeropuertos, lugares con sus regiones y países), todas «sin cambios» y firmadas
    assert {f["archivo"] for f in nuevas} == {"aeropuertos.csv", "lugares.csv.gz", "regiones.csv", "paises.csv"}
    assert {f["resultado"] for f in nuevas} == {"sin cambios"}
    assert {f["quien"] for f in nuevas} == {"Pruebas"}
    lugares = next(f for f in nuevas if f["archivo"] == "lugares.csv.gz")
    assert lugares["url"].endswith("cities1000.zip") and "GeoNames" in lugares["fuente"]
    assert len(lugares["huella"]) == 64 and lugares["filas"] == 16
    # la primera carga de cada archivo quedó como «cargada», con la misma huella
    primera = db.uno("select huella from cargas_datos where archivo='lugares.csv.gz' and resultado='cargada' order by id limit 1")
    assert primera["huella"] == lugares["huella"]
    evento = db.uno("select * from eventos where paso='datos de referencia cargados' order by id desc limit 1")
    assert evento["detalle"] == "sin cambios" and "Pruebas" in evento["fuente"]


def test_un_archivo_que_cambia_se_vuelve_a_cargar(cliente, tmp_path):
    import shutil

    from app.servicios import geografia
    for f in MINI.iterdir():
        shutil.copy(f, tmp_path / f.name)
    texto = (tmp_path / "aeropuertos.csv").read_text()
    (tmp_path / "aeropuertos.csv").write_text("\n".join(l for l in texto.splitlines() if not l.startswith("NDJ,")) + "\n")
    try:
        assert geografia.cargar(tmp_path)["aeropuertos"] == 17
        ultima = db.uno("select * from cargas_datos where archivo='aeropuertos.csv' order by id desc limit 1")
        assert (ultima["resultado"], ultima["filas"]) == ("cargada", 17)
    finally:
        assert geografia.cargar(MINI)["aeropuertos"] == 18


def test_normalizar():
    from app.servicios.geografia import normalizar
    assert normalizar("  São   Paulo ") == "sao paulo"
    assert normalizar("Bogotá D.C.") == "bogota d c"
    assert normalizar("LISBOA") == normalizar("lisboa") == "lisboa"
    assert normalizar("Rabbat-Moab") == "rabbat moab"
