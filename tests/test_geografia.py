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


# ---------- tarea 6: búsqueda de lugares y aeropuertos cercanos ----------
def _buscar(q, **k):
    from app.servicios import geografia
    return geografia.buscar(q, **k)


def test_moab_sugiere_sus_aeropuertos_cercanos(cliente):
    primero = _buscar("moab")[0]
    assert (primero["tipo"], primero["nombre"], primero["region"], primero["pais"]) == ("lugar", "Moab", "Utah", "Estados Unidos")
    assert [a["iata"] for a in primero["aeropuertos"]] == ["CNY", "GJT", "SLC"]
    km = [a["km"] for a in primero["aeropuertos"]]
    assert km == sorted(km) and 15 < km[0] < 30 and 300 < km[2] < 330
    assert primero["aviso"] is None and primero["origen"] == "local"
    # cada aeropuerto trae su tiempo estimado por carretera (km x 1,3 ÷ 70 km/h)
    assert abs(primero["aeropuertos"][2]["horas"] - km[2] * 1.3 / 70) < 0.1


def test_homonimos_se_distinguen_por_pais(cliente):
    r = _buscar("moab")
    jordania = [i for i, x in enumerate(r) if x["pais"] == "Jordania"]
    assert jordania and jordania[0] > 0          # el de Jordania aparece, después del de Utah
    assert r[jordania[0]]["region"] == "Ma’an" and r[jordania[0]]["nombre"] == "Qīr Moāv"
    assert r[jordania[0]]["tambien"] == "kir moab"   # por qué coincide: su nombre alterno
    # San José: el de California y el de Costa Rica, cada uno con su región, su país y sus aeropuertos
    sanjose = [x for x in _buscar("san jose") if x["tipo"] == "lugar"]
    assert [(x["region"], x["pais"]) for x in sanjose] == [("California", "Estados Unidos"), ("San José", "Costa Rica")]
    assert sanjose[0]["aeropuertos"][0]["iata"] == "SJC" and sanjose[1]["aeropuertos"][0]["iata"] == "SJO"


def test_codigo_iata_y_pais(cliente):
    lis = _buscar("LIS")[0]
    assert (lis["tipo"], lis["id"], lis["pais"]) == ("aeropuerto", "LIS", "Portugal")
    assert [a["iata"] for a in lis["aeropuertos"]] == ["LIS"]
    portugal = _buscar("portugal")
    assert portugal[0]["tipo"] == "pais" and portugal[0]["nombre"] == "Portugal"
    assert {"LIS", "OPO"} <= {a["iata"] for a in portugal[0]["aeropuertos"]}
    assert all(a["grande"] for a in portugal[0]["aeropuertos"])
    assert _buscar("lisboa") == _buscar("Lisboa") == _buscar("  LISBOA ")
    lisboa = _buscar("lisboa")[0]
    assert (lisboa["nombre"], lisboa["tambien"], lisboa["aeropuertos"][0]["iata"]) == ("Lisbon", "lisboa", "LIS")


def test_villa_de_leyva_propone_bogota(cliente):
    villa = _buscar("Villa de Leyva")[0]
    assert villa["nombre"] == "Villa de Leyva" and villa["region"] == "Boyacá"
    assert "BOG" in [a["iata"] for a in villa["aeropuertos"]]


def test_lugar_aislado_lo_dice(cliente):
    """Punto de atención 1: un pueblo sin aeropuertos con vuelos regulares en el radio."""
    am_timan = _buscar("am timan")[0]
    assert am_timan["pais"] == "Chad" and am_timan["aeropuertos"] == []
    assert am_timan["aviso"] == "Sin aeropuertos con vuelos regulares a menos de 400 km. Busca un aeropuerto por nombre o código."
    # se puede marcar un aeropuerto buscándolo por nombre
    assert _buscar("djamena")[0]["id"] == "NDJ"


def test_cercanos_respeta_radio_y_maximo(cliente):
    from app.servicios import geografia
    lisboa = (38.72509, -9.1498)
    assert [a["iata"] for a in geografia.cercanos(*lisboa)] == ["LIS", "FAO", "OPO"]
    assert [a["iata"] for a in geografia.cercanos(*lisboa, radio_km=250)] == ["LIS", "FAO"]
    assert [a["iata"] for a in geografia.cercanos(*lisboa, maximo=1)] == ["LIS"]
    assert round(geografia.distancia_km(*lisboa, 41.1485, -8.6104)) == 273   # Lisboa-Oporto


def test_la_ruta_exige_sesion_y_responde_rapido(anonimo, piloto):
    import time
    r = anonimo.get("/lugares/buscar?q=moab", follow_redirects=False)
    assert r.status_code in (303, 401)
    inicio = time.perf_counter()
    r = piloto.get("/lugares/buscar?q=moab&limite=8")
    assert r.status_code == 200 and (time.perf_counter() - inicio) < 0.3
    assert r.json()["resultados"][0]["nombre"] == "Moab"
    assert piloto.get("/lugares/buscar?q=m").json()["resultados"] == []


# ---------- autocompletado de Google combinado (con doble: nunca sale a internet) ----------
BUSAN = {"search_metadata": {"status": "Success"}, "suggestions": [
    {"position": 1, "name": "South Korea", "type": "region", "description": "Country in East Asia", "id": "/m/06qd3"},
    {"position": 2, "name": "Busan, South Korea", "type": "city", "description": "City in South Korea", "id": "/m/0hv7l",
     "airports": [{"name": "Gimhae International Airport", "id": "PUS", "city": "Busan", "city_id": "/m/0hv7l", "distance": "7 mi"}]},
    {"position": 3, "name": "Madrid, Spain", "type": "city", "description": "Capital of Spain", "id": "/m/056_y",
     "airports": [{"name": "Adolfo Suárez Madrid–Barajas Airport", "id": "MAD", "city": "Madrid", "city_id": "/m/056_y", "distance": "8 mi"}]},
]}


class _Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def json(self):
        return self.datos


def _google(monkeypatch, datos=BUSAN, clave="clave-de-prueba"):
    """Simula el buscador: cuenta las llamadas y guarda los parámetros enviados."""
    from app import config
    from app.servicios import precios
    llamadas = []
    monkeypatch.setattr(config, "SERPAPI_KEY", clave)
    monkeypatch.setattr(precios.httpx, "get", lambda url, params=None, **k: llamadas.append(params) or _Respuesta(datos))
    return llamadas


def test_google_suma_sus_sugerencias_y_el_mismo_texto_se_paga_una_vez(piloto, monkeypatch):
    llamadas = _google(monkeypatch)
    antes = db.uno("select count(*) n from consultas_buscador where tipo='autocompletado'")["n"]
    r1 = piloto.get("/lugares/buscar?q=Busan&google=1").json()
    r2 = piloto.get("/lugares/buscar?q=busan&google=1").json()
    assert len(llamadas) == 1 and r1 == r2
    # solo el texto del campo sale al buscador: nada de la persona
    assert llamadas[0]["engine"] == "google_flights_autocomplete" and llamadas[0]["q"] == "busan"
    assert not {"correo", "nombre", "usuario"} & set(llamadas[0])
    busan = next(x for x in r1["resultados"] if x["origen"] == "google")
    assert busan["nombre"] == "Busan, South Korea" and busan["aeropuertos"][0]["iata"] == "PUS"
    assert busan["aeropuertos"][0]["km"] == 11       # 7 millas
    assert all(x["tipo"] != "region" for x in r1["resultados"])
    filas = db.todos("select * from consultas_buscador where tipo='autocompletado' order by id")[antes:]
    assert len(filas) == 1 and filas[0]["origen"] == "en vivo" and filas[0]["clave"] == "autocompletado_busan"
    assert r1["aviso_google"] is None
    # lo que la lista local ya muestra no se repite como sugerencia de Google
    madrid = piloto.get("/lugares/buscar?q=madrid&google=1").json()["resultados"]
    assert madrid[0]["origen"] == "local" and madrid[0]["nombre"] == "Madrid"
    assert [x["nombre"] for x in madrid if x["origen"] == "google"] == ["Busan, South Korea"]


def test_un_aeropuerto_que_solo_trae_google_queda_registrado(piloto, monkeypatch):
    _google(monkeypatch)
    piloto.get("/lugares/buscar?q=busan%20ciudad&google=1")
    pus = db.uno("select * from aeropuertos_google where iata='PUS'")
    assert pus and pus["nombre"] == "Gimhae International Airport" and pus["ciudad"] == "Busan"
    assert db.uno("select id from eventos where paso='aeropuerto conocido por Google' and detalle like 'PUS%'")
    assert db.uno("select id from aeropuertos_google where iata='MAD'") is None   # ya estaba en los datos locales


def test_sin_clave_solo_responde_local(piloto, monkeypatch):
    llamadas = _google(monkeypatch, clave="")
    r = piloto.get("/lugares/buscar?q=moab&google=1").json()
    assert llamadas == [] and r["resultados"][0]["nombre"] == "Moab"
    assert all(x["origen"] == "local" for x in r["resultados"])
    assert "Sin clave" in r["aviso_google"]


def test_con_proveedor_local_nunca_llama_afuera(piloto, monkeypatch):
    llamadas = _google(monkeypatch)
    monkeypatch.setenv("PROVEEDOR_LUGARES", "local")
    r = piloto.get("/lugares/buscar?q=seul&google=1").json()
    assert llamadas == [] and r["aviso_google"] is None


def test_alcanzado_el_tope_solo_responde_local(piloto, monkeypatch):
    llamadas = _google(monkeypatch)
    db.ejecutar("update reglas set valor='0' where ambito='supuesto' and clave='tope_autocompletado_persona_dia'")
    try:
        r = piloto.get("/lugares/buscar?q=gimhae&google=1").json()
    finally:
        db.ejecutar("update reglas set valor='15' where ambito='supuesto' and clave='tope_autocompletado_persona_dia'")
    assert llamadas == [] and "tope" in r["aviso_google"]
    db.ejecutar("update reglas set valor='0' where ambito='supuesto' and clave='tope_autocompletado_mes'")
    try:
        r = piloto.get("/lugares/buscar?q=gimhae&google=1").json()
    finally:
        db.ejecutar("update reglas set valor='60' where ambito='supuesto' and clave='tope_autocompletado_mes'")
    assert llamadas == [] and "tope" in r["aviso_google"]


def test_sin_pausa_no_se_consulta_google(piloto, monkeypatch):
    llamadas = _google(monkeypatch)
    piloto.get("/lugares/buscar?q=gimhae")        # búsqueda inmediata: solo local
    piloto.get("/lugares/buscar?q=gi&google=1")   # menos de 3 letras
    assert llamadas == []


# ---------- ronda de arreglos 1 ----------
def test_dos_peticiones_con_el_mismo_aeropuerto_nuevo_no_fallan(piloto, monkeypatch):
    """Dos pausas casi simultáneas con el mismo aeropuerto que solo trae Google: la segunda no rompe con 500."""
    from app.servicios import geografia
    datos = {"suggestions": [{"type": "city", "name": "Jeju", "id": "/g/121z6l6y",
                              "airports": [{"name": "Jeju International Airport", "id": "CJU", "city": "Jeju"}]}]}
    real = db.insertar
    def insertar_tras_otro(tabla, **valores):   # simula que otra petición insertó la misma fila un instante antes
        if tabla == "aeropuertos_google" and valores.get("iata") == "CJU" and not db.uno("select id from aeropuertos_google where iata='CJU'"):
            real(tabla, **valores)
        return real(tabla, **valores)
    monkeypatch.setattr(db, "insertar", insertar_tras_otro)
    geografia._anotar_aeropuertos_nuevos(datos, "jeju")
    assert db.uno("select count(*) n from aeropuertos_google where iata='CJU'")["n"] == 1


def test_el_autocompletado_no_cuenta_en_los_indicadores_del_buscador(cliente):
    from app.servicios import metricas
    antes = metricas.buscador({})
    for _ in range(3):
        db.insertar("consultas_buscador", momento=db.ahora(), tipo="autocompletado", origen="en vivo",
                    clave="autocompletado_prueba-indicadores", duracion_ms=99999, resultados=0)
    despues = metricas.buscador({})
    for clave in ("consultas", "en_vivo", "reutilizadas", "fallidas", "tasa_reutilizacion", "tasa_fallidas", "latencia_mediana_ms"):
        assert despues[clave] == antes[clave], clave
    assert all(t != "autocompletado" for t, _ in despues["por_tipo"])
    # su propio dato: consultas del mes frente al tope
    auto = despues["autocompletado"]
    assert auto["mes"] == antes["autocompletado"]["mes"] + 3 and auto["tope_mes"] == 60 and auto["tope_persona_dia"] == 15
    assert "Autocompletado de Google" in cliente.get("/admin/monitoreo?pestana=cupos").text
