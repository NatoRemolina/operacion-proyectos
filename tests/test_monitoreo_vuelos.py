"""La opción elegida se carga completa y el vuelo se sigue el día del viaje. El buscador y el bot están simulados:
ninguna prueba sale a internet."""
import json
from urllib.parse import parse_qs, urlparse

from conftest import FORM_VIAJE

from app import config, db
from app.servicios import precios

MOAB = {"nombre": "Moab", "region": "Utah", "pais": "Estados Unidos", "lat": 38.57332, "lon": -109.54984}


# ---------- buscador simulado ----------
def _tramo(numero, desde, hasta, sale, llega, aerolinea="Delta"):
    return {"airline": aerolinea, "flight_number": numero, "departure_airport": {"id": desde, "time": sale},
            "arrival_airport": {"id": hasta, "time": llega}}


def _itinerario(tramos, precio, **extra):
    return {"flights": tramos, "total_duration": 400, "price": precio, **extra}


class _Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def json(self):
        return self.datos


class Buscador:
    """Responde según los parámetros, como el proveedor: búsqueda, regreso, opciones de reserva, reconfirmación y estado."""

    def __init__(self, ida, regreso=None, reserva=None, reconfirmacion=None, estado=None):
        self.ida, self.regreso, self.reserva, self.reconfirmacion, self.estado = ida, regreso, reserva, reconfirmacion, estado
        self.llamadas = []

    def get(self, url, params=None, **k):
        self.llamadas.append(dict(params))
        p = params
        if p["engine"] == "google_hotels":
            return _Respuesta({"properties": []})
        if p["engine"] == "google":
            return _Respuesta(self.estado if self.estado is not None else {})
        if "departure_token" in p:
            return _Respuesta(self.regreso or {"error": "sin regreso"})
        if "booking_token" in p:
            return _Respuesta(self.reserva or {"error": "sin reserva"})
        if "selected_flights_json" in p:
            return _Respuesta(self.reconfirmacion or {"error": "sin datos"})
        return _Respuesta(self.ida)

    def de(self, clave):
        return [c for c in self.llamadas if clave in c]


def _simular(monkeypatch, tmp_path, buscador, clave="clave-de-prueba"):
    monkeypatch.setattr(config, "SERPAPI_KEY", clave)
    monkeypatch.setattr(config, "DIR_RESPALDO_ESCRITURA", tmp_path)   # nada simulado queda en el repositorio
    monkeypatch.setattr(precios.httpx, "get", buscador.get)
    return buscador


def _reserva(precio=410, titulo="Main Cabin"):
    return {"search_metadata": {"created_at": "2026-11-12 10:00:00 UTC"},
            "selected_flights": [], "baggage_prices": {"together": ["1 free carry-on", "1st checked bag: 35"]},
            "booking_options": [{"together": {"book_with": "Delta", "airline": True, "marketed_as": ["DL 100", "DL 200", "DL 300"],
                                              "price": precio, "option_title": titulo,
                                              "extensions": ["Ticket changes for a fee"],
                                              "baggage_prices": ["1 free carry-on", "1st checked bag: 35"],
                                              "booking_request": {"url": "https://www.google.com/travel/clk/f",
                                                                  "post_data": "u=SECRETO-DE-RESERVA"}}}]}


def _escenario(ida="2027-07-06", regreso="2027-07-09"):
    """Ida MIA → ATL → SLC (dos tramos) y otra opción a CNY; regresos desde CNY (más barato) y desde SLC."""
    vuelta = f"{regreso} "
    busqueda = {"search_metadata": {"created_at": "2026-11-12 10:00:00 UTC"},
                "best_flights": [
                    _itinerario([_tramo("DL 100", "MIA", "ATL", f"{ida} 07:00", f"{ida} 09:00"),
                                 _tramo("DL 200", "ATL", "SLC", f"{ida} 10:00", f"{ida} 12:00")], 300,
                                departure_token="tok-ida-slc"),
                    _itinerario([_tramo("UA 7", "MIA", "CNY", f"{ida} 08:00", f"{ida} 13:00", "United")], 700,
                                departure_token="tok-ida-cny")],
                "other_flights": [], "price_insights": {"lowest_price": 300, "price_level": "typical", "typical_price_range": [250, 600]},
                "airports": [{"departure": [{"airport": {"id": "MIA"}}], "arrival": [{"airport": {"id": "CNY"}}, {"airport": {"id": "SLC"}}]}]}
    regresos = {"search_metadata": {"created_at": "2026-11-12 10:00:00 UTC"},
                "best_flights": [_itinerario([_tramo("UA 8", "CNY", "MIA", vuelta + "09:00", vuelta + "18:00", "United")], 100,
                                             booking_token="book-cny")],
                "other_flights": [_itinerario([_tramo("DL 300", "SLC", "MIA", vuelta + "08:00", vuelta + "16:00")], 150,
                                              booking_token="book-slc"),
                                  _itinerario([_tramo("DL 302", "SLC", "MIA", vuelta + "14:00", vuelta + "22:00")], 210,
                                              booking_token="book-slc-tarde")]}
    return busqueda, regresos


def _cotizar(cliente, ida="2027-07-06", regreso="2027-07-09", **cambios) -> int:
    datos = {**FORM_VIAJE, "destino": "Moab, Utah, Estados Unidos", "destino_aeropuertos": "CNY,SLC",
             "destino_lugar": json.dumps(MOAB), "ida": ida, "regreso": regreso, "llegar_antes": "", "carro_dia": 0,
             "prob_cambio": 0, "baterias_n": 0, "maleta": "", **cambios}
    r = cliente.post("/viajes", data=datos, follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1])


def _decidir_slc(cliente, sid):
    from app.main import _comparacion
    c = _comparacion(sid)
    slc = next(v for v in c["vuelos"] + c["descartados"] if v["v"]["hasta"] == "SLC")
    siguio = c["vuelos"] and c["vuelos"][0]["id"] == slc["id"]
    return cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": slc["id"], "razones": ["costo_total"],
                                                        "motivo": "" if siguio else "Sale más temprano y llega con luz"},
                        follow_redirects=False)


def _tramos(sid):
    from app.servicios import viajes
    v = viajes.de_solicitud(sid)
    return v, db.todos("select * from tramos_vuelo where viaje_id=:v order by sentido, orden", v=v["id"])


# ---------- tarea 10: la opción elegida se carga completa ----------
def test_decidir_registra_tramos_de_ida_y_regreso(cliente, monkeypatch, tmp_path):
    ida, regresos = _escenario()
    b = _simular(monkeypatch, tmp_path, Buscador(ida, regresos, _reserva()))
    sid = _cotizar(cliente)
    assert db.uno("select destino from solicitudes where id=:i", i=sid)["destino"] == "CNY"   # el marcado más cercano
    antes = len(b.llamadas)
    assert _decidir_slc(cliente, sid).status_code == 303
    nuevas = b.llamadas[antes:]
    # dos búsquedas al decidir: el regreso (mismos códigos que la búsqueda original) y las opciones de reserva
    assert len(nuevas) == 2
    assert nuevas[0]["departure_token"] == "tok-ida-slc"
    assert (nuevas[0]["departure_id"], nuevas[0]["arrival_id"]) == ("MIA", "CNY,SLC")
    assert nuevas[1]["booking_token"] == "book-slc"     # el regreso más barato que sale de SLC, no el de CNY
    v, tramos = _tramos(sid)
    ida_ = [t for t in tramos if t["sentido"] == "ida"]
    vuelta = [t for t in tramos if t["sentido"] == "regreso"]
    assert [(t["orden"], t["numero"], t["desde"], t["hasta"]) for t in ida_] == [(1, "DL 100", "MIA", "ATL"), (2, "DL 200", "ATL", "SLC")]
    assert [(t["numero"], t["desde"], t["hasta"], t["fecha"]) for t in vuelta] == [("DL 300", "SLC", "MIA", "2027-07-09")]
    assert ida_[0]["sale_programada"] == "2027-07-06 07:00" and ida_[1]["llega_programada"] == "2027-07-06 12:00"
    assert all(t["estado"] == "programado" and t["consultas"] == 0 and t["aerolinea"] == "Delta" for t in tramos)
    # la solicitud queda con los aeropuertos reales del vuelo
    s = db.uno("select origen, destino from solicitudes where id=:i", i=sid)
    assert (s["origen"], s["destino"]) == ("MIA", "SLC")
    # el presupuesto usa la tarifa real de las opciones de reserva
    d = db.de_json(db.uno("select desglose from decisiones where solicitud_id=:i order by id desc", i=sid)["desglose"])
    precio = next(l for l in d["lineas"] if l["concepto"].startswith("Precio"))
    assert precio["concepto"] == "Precio (Main Cabin)" and precio["valor"] == 410 and precio["origen"] == "buscador"
    assert d["regreso"]["numeros"] == ["DL 300"]
    ficha = cliente.get(f"/viajes/{sid}/ficha").text
    assert "Tramos del vuelo" in ficha and "DL 300" in ficha and "Regreso:" in ficha
    # trazabilidad: una fila por consulta y un evento con los números de vuelo
    tipos = [f["tipo"] for f in db.todos("select tipo from consultas_buscador where solicitud_id=:i and origen='en vivo' and tipo<>'hoteles' order by id",
                                         i=sid)]
    assert tipos == ["vuelos", "regreso", "tarifas"]
    ev = db.uno("select detalle from eventos where entidad='viaje' and entidad_id=:v and paso='tramos registrados'", v=v["id"])
    assert ev and "DL 100" in ev["detalle"] and "DL 200" in ev["detalle"] and "DL 300" in ev["detalle"]
    # nada de lo guardado trae cómo ejecutar una reserva
    for f in db.todos("select cuerpo from busquedas where clave like 'reserva_%' or clave like 'regreso_%'"):
        assert "booking_request" not in f["cuerpo"] and "post_data" not in f["cuerpo"]
    assert all("post_data" not in a.read_text() for a in tmp_path.glob("*.json"))


def test_decidir_dos_veces_no_duplica_tramos_ni_consultas(cliente, monkeypatch, tmp_path):
    ida, regresos = _escenario("2027-07-13", "2027-07-16")
    b = _simular(monkeypatch, tmp_path, Buscador(ida, regresos, _reserva()))
    sid = _cotizar(cliente, ida="2027-07-13", regreso="2027-07-16")
    _decidir_slc(cliente, sid)
    antes = len(b.llamadas)
    from app.main import _comparacion
    hotel_previo = _comparacion(sid)["decision"]
    # se repite con otro motivo: la decisión cambia, el regreso y la reserva ya están guardados
    cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": hotel_previo["vuelo_id"], "motivo": "Cambio de idea, mismo vuelo",
                                                 "razones": ["horario"]})
    assert len(b.llamadas) == antes
    _, tramos = _tramos(sid)
    assert len(tramos) == 3


def test_sin_regreso_igual_se_decide(cliente, monkeypatch, tmp_path):
    ida, regresos = _escenario("2027-07-20", "2027-07-23")
    _simular(monkeypatch, tmp_path, Buscador(ida, regresos, _reserva()))
    monkeypatch.setattr(precios, "vuelo_regreso", lambda *a, **k: None)
    sid = _cotizar(cliente, ida="2027-07-20", regreso="2027-07-23")
    assert _decidir_slc(cliente, sid).headers["location"] == f"/viajes/{sid}/ficha"
    v, tramos = _tramos(sid)
    assert v and [t["numero"] for t in tramos] == ["DL 100", "DL 200"] and {t["sentido"] for t in tramos} == {"ida"}
    assert db.uno("select id from eventos where entidad='solicitud' and entidad_id=:i and paso='regreso sin datos'", i=sid)
    # sin opciones de reserva el presupuesto queda con la tarifa estimada, marcada como tal
    d = db.de_json(db.uno("select desglose from decisiones where solicitud_id=:i order by id desc", i=sid)["desglose"])
    assert "(supuesta)" in next(l for l in d["lineas"] if l["concepto"].startswith("Precio"))["concepto"]


def test_regreso_toma_el_mas_barato_desde_el_aeropuerto_real(cliente, monkeypatch, tmp_path):
    _, regresos = _escenario("2027-08-03", "2027-08-06")
    b = _simular(monkeypatch, tmp_path, Buscador({}, regresos))
    ida = {"numeros": ["DL 100", "DL 200"], "desde": "MIA", "hasta": "SLC", "token": "tok"}
    r = precios.vuelo_regreso(ida, ["MIA"], ["SLC", "CNY"], "2027-08-03", "2027-08-06")
    assert r["numeros"] == ["DL 300"] and r["desde"] == "SLC" and r["booking"] == "book-slc"
    assert b.llamadas[0]["arrival_id"] == "CNY,SLC" and "no_cache" not in b.llamadas[0]
    assert precios.vuelo_regreso({**ida, "token": None}, ["MIA"], ["SLC"], "2027-08-03", "2027-08-06") is None   # sin token
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    assert precios.vuelo_regreso({**ida, "numeros": ["XX 1"]}, ["MIA"], ["SLC"], "2027-08-03", "2027-08-06") is None   # sin clave


def test_traer_tarifas_deja_una_fila_por_consulta(cliente, monkeypatch, tmp_path):
    from app.main import _comparacion
    ida, regresos = _escenario("2027-08-10", "2027-08-13")
    b = _simular(monkeypatch, tmp_path, Buscador(ida, regresos, _reserva(395, "Basic Economy")))
    sid = _cotizar(cliente, ida="2027-08-10", regreso="2027-08-13")
    slc = next(v for v in _comparacion(sid)["vuelos"] + _comparacion(sid)["descartados"] if v["v"]["hasta"] == "SLC")
    antes = len(b.llamadas)
    cliente.post(f"/viajes/{sid}/tarifas/{slc['id']}")
    assert len(b.llamadas) - antes == 2
    tipos = [f["tipo"] for f in db.todos("select tipo from consultas_buscador where solicitud_id=:i and tipo<>'vuelos' and tipo<>'hoteles' order by id", i=sid)]
    assert tipos == ["regreso", "tarifas"]
    o = db.de_json(db.uno("select tarifas from opciones where id=:i", i=slc["id"])["tarifas"])
    assert o["lista"][0]["precio"] == 395 and o["lista"][0]["nombre"] == "Basic Economy"


def test_respuestas_guardadas_sin_post_data(cliente):
    archivo = config.DIR_RESPALDO / "tarifas_MIA_LAS_2026-12-08_2026-12-11_AA1851.json"
    texto = archivo.read_text()
    assert "booking_request" not in texto and "post_data" not in texto
    assert json.loads(texto)["reserva"]["booking_options"]          # lo demás sigue ahí
    limpio = precios._sin_reserva({"a": [{"together": {"price": 1, "booking_request": {"post_data": "x"}}}],
                                  "booking_request": {"url": "u"}})
    assert limpio == {"a": [{"together": {"price": 1}}]}


# ---------- tarea 10: al aprobar se reconfirma el precio ----------
def _decidido(cliente, monkeypatch, tmp_path, ida, regreso, reconfirmacion=None):
    vuelos, regresos = _escenario(ida, regreso)
    b = _simular(monkeypatch, tmp_path, Buscador(vuelos, regresos, _reserva(), reconfirmacion))
    sid = _cotizar(cliente, ida=ida, regreso=regreso)
    _decidir_slc(cliente, sid)
    v, _ = _tramos(sid)
    return b, sid, v


def _aprobar(cliente, vid, **extra):
    r = cliente.post(f"/admin/viajes/{vid}", data={"accion": "aprobar", **extra}, follow_redirects=False)
    return r.headers["location"]


def _eventos(vid, paso):
    return db.todos("select detalle from eventos where entidad='viaje' and entidad_id=:v and paso=:p", v=vid, p=paso)


def test_aprobar_reconfirma_el_precio_igual(cliente, monkeypatch, tmp_path):
    from app.servicios import viajes
    b, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-09-07", "2027-09-10", reconfirmacion=_reserva(410))
    antes = len(b.llamadas)
    _aprobar(cliente, v["id"])
    nuevas = b.llamadas[antes:]
    assert len(nuevas) == 1                                         # una búsqueda al aprobar
    fijado = json.loads(nuevas[0]["selected_flights_json"])
    assert [s["flight_number"] for s in fijado["outbound"]] == ["DL100", "DL200"]
    assert fijado["outbound"][1] == {"flight_number": "DL200", "departure_id": "ATL", "arrival_id": "SLC", "date": "2027-09-07"}
    assert [s["flight_number"] for s in fijado["return"]] == ["DL300"]
    assert viajes.de_solicitud(sid)["estado"] == "aprobado"
    assert _eventos(v["id"], "precio confirmado")
    assert db.uno("select origen from consultas_buscador where solicitud_id=:i and tipo='reconfirmacion'", i=sid)["origen"] == "en vivo"


def test_aprobar_con_precio_mayor_que_la_tolerancia_pide_confirmar(cliente, monkeypatch, tmp_path):
    from app.servicios import viajes
    b, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-09-14", "2027-09-17", reconfirmacion=_reserva(451))
    destino = _aprobar(cliente, v["id"])
    assert viajes.de_solicitud(sid)["estado"] == "pendiente_aprobacion"
    assert "410" in parse_qs(urlparse(destino).query)["aviso"][0] and "451" in parse_qs(urlparse(destino).query)["aviso"][0]
    cambio = _eventos(v["id"], "precio cambió")
    assert cambio and "antes 410" in cambio[0]["detalle"] and "ahora 451" in cambio[0]["detalle"]
    # la página ofrece confirmar; al confirmar no se vuelve a pagar la consulta
    assert "confirmar_precio" in cliente.get("/admin/viajes").text
    antes = len(b.llamadas)
    _aprobar(cliente, v["id"], confirmar_precio="1")
    assert len(b.llamadas) == antes and viajes.de_solicitud(sid)["estado"] == "aprobado"
    assert _eventos(v["id"], "precio nuevo confirmado")


def test_aprobar_dentro_de_la_tolerancia_no_pide_confirmar(cliente, monkeypatch, tmp_path):
    from app.servicios import viajes
    _, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-09-21", "2027-09-24", reconfirmacion=_reserva(420))
    _aprobar(cliente, v["id"])
    assert viajes.de_solicitud(sid)["estado"] == "aprobado"
    assert "antes 410" in _eventos(v["id"], "precio cambió")[0]["detalle"]


def test_aprobar_sin_datos_aprueba_con_aviso(cliente, monkeypatch, tmp_path):
    from app.servicios import viajes
    b, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-09-28", "2027-10-01")
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    antes = len(b.llamadas)
    destino = _aprobar(cliente, v["id"])
    assert len(b.llamadas) == antes and viajes.de_solicitud(sid)["estado"] == "aprobado"
    assert _eventos(v["id"], "precio no reconfirmado")
    assert "no reconfirmado" in parse_qs(urlparse(destino).query)["aviso"][0]

