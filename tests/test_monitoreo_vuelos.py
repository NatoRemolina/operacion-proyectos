"""La opción elegida se carga completa y el vuelo se sigue el día del viaje. El buscador y el bot están simulados:
ninguna prueba sale a internet."""
import json
from urllib.parse import parse_qs, urlparse

import pytest
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
        assert "account" not in url, "el cupo se simula aparte (precios.cupo)"
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
    monkeypatch.setattr(precios, "cupo", lambda: {"restantes": 200})
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
    # el evento lleva el precio anterior y el nuevo, siempre
    assert "antes 410.00 USD, ahora 410.00 USD (sin cambio)" in _eventos(v["id"], "precio confirmado")[0]["detalle"]
    assert not list(tmp_path.glob("reconfirmacion_*"))      # la reconfirmación solo va a la tabla, no a la carpeta versionada
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
    presupuesto = viajes.de_solicitud(sid)["presupuesto_usd"]
    _aprobar(cliente, v["id"], confirmar_precio="1")
    assert len(b.llamadas) == antes and viajes.de_solicitud(sid)["estado"] == "aprobado"
    assert _eventos(v["id"], "precio nuevo confirmado")
    # el presupuesto pasa al precio nuevo, con su evento
    assert viajes.de_solicitud(sid)["presupuesto_usd"] == round(presupuesto + 41, 2)
    ajuste = _eventos(v["id"], "presupuesto ajustado al precio confirmado")
    assert ajuste and "410.00 → 451.00" in ajuste[0]["detalle"]


def test_aprobar_dentro_de_la_tolerancia_no_pide_confirmar(cliente, monkeypatch, tmp_path):
    from app.servicios import viajes
    _, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-09-21", "2027-09-24", reconfirmacion=_reserva(410.5))
    _aprobar(cliente, v["id"])
    assert viajes.de_solicitud(sid)["estado"] == "aprobado"
    # aunque cambie poco, el texto lo dice
    assert "antes 410.00 USD, ahora 410.50 USD" in _eventos(v["id"], "precio cambió")[0]["detalle"]


def test_aprobar_sin_datos_aprueba_con_aviso(cliente, monkeypatch, tmp_path):
    from app.servicios import viajes
    b, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-09-28", "2027-10-01")
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    antes = len(b.llamadas)
    destino = _aprobar(cliente, v["id"])
    assert len(b.llamadas) == antes and viajes.de_solicitud(sid)["estado"] == "aprobado"
    assert _eventos(v["id"], "precio no reconfirmado")
    assert "no reconfirmado" in parse_qs(urlparse(destino).query)["aviso"][0]



# ---------- tarea 11: estado del vuelo el día del viaje ----------
from datetime import UTC, datetime  # noqa: E402

from app.servicios import monitoreo_vuelos, telegram  # noqa: E402

MAD_LIS = dict(numero="IB 5634", desde="MAD", hasta="LIS", fecha="2026-12-13",
               sale_programada="2026-12-13 09:05", llega_programada="2026-12-13 09:30")   # horas locales de cada aeropuerto


def _estado(flight_status="On time", sale_real="9:05 AM", llega_real="9:30 AM", puerta="J58", terminal="4",
            fecha_texto="Sun, Dec 13", numero="IB 5634"):
    """Bloque «flight_status» del Google Direct Answer Box API, con los campos que documenta el proveedor."""
    return {"search_metadata": {"created_at": "2026-12-13 05:30:00 UTC"},
            "answer_box": {"type": "flight_status", "title": f"Iberia {numero}", "destination": "Madrid to Lisbon",
                           "flight_number": numero, "flight_status": flight_status, "latest_update": "Updated 2m ago",
                           "percentage_of_flight_progress": 0,
                           "sources": [{"name": "Cirium", "link": "https://www.flightstats.com/"}],
                           "departure": {"airport_name": "MAD", "planned_time": "9:05 AM", "actual_time": sale_real,
                                         "terminal": terminal, "gate": puerta, "location": "Madrid", "date": fecha_texto},
                           "arrival": {"airport_name": "LIS", "planned_time": "9:30 AM", "actual_time": llega_real,
                                       "terminal": "1", "gate": "-", "location": "Lisbon", "date": fecha_texto}}}


@pytest.fixture()
def tramo(nuevo_viaje):
    """Un tramo Madrid → Lisboa del 13 de diciembre en un viaje aprobado del piloto de demostración."""
    v = nuevo_viaje()
    tid = db.insertar("tramos_vuelo", viaje_id=v["id"], sentido="ida", orden=9, aerolinea="Iberia", estado="programado",
                      consultas=0, **MAD_LIS)
    return db.uno("select * from tramos_vuelo where id=:i", i=tid)


def _utc(texto):
    return datetime.fromisoformat(texto).replace(tzinfo=UTC)


def test_estado_vuelo_lee_el_bloque_del_proveedor(cliente, monkeypatch, tmp_path):
    b = _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado("Delayed", "9:25 AM", "9:52 AM")))
    r = precios.estado_vuelo("IB 5634", "2026-12-13")
    assert b.llamadas[-1]["engine"] == "google" and b.llamadas[-1]["q"] == "Flight IB5634"
    assert r["estado"] == "retrasado" and (r["retraso_salida"], r["retraso_llegada"]) == (20, 22)
    assert (r["terminal_salida"], r["puerta_salida"], r["terminal_llegada"], r["puerta_llegada"]) == ("4", "J58", "1", None)
    assert (r["sale_estimada"], r["llega_estimada"]) == ("2026-12-13 09:25", "2026-12-13 09:52")
    fila = db.uno("select * from consultas_buscador where tipo='estado_vuelo' order by id desc limit 1")
    assert fila["origen"] == "en vivo" and fila["clave"].startswith("estado_vuelo_IB5634_2026-12-13")
    # otra fecha o un número que no está en la respuesta: no hay bloque para ese vuelo
    assert precios.estado_vuelo("IB 5634", "2026-12-14") is None
    assert precios.estado_vuelo("IB 9999", "2026-12-13") is None
    # varios vuelos en la misma respuesta: se toma el del número pedido
    varios = {"answer_box": {"type": "flight_status", "flights": [
        {**_estado(numero="IB 5630")["answer_box"]}, {**_estado("Cancelled", numero="IB 5634")["answer_box"]}]}}
    b.estado = varios
    assert precios.estado_vuelo("IB5634", "2026-12-13")["estado"] == "cancelado"


def test_ventana_cache_y_tope(cliente, tramo, monkeypatch, tmp_path):
    b = _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado()))
    desde_id = db.uno("select coalesce(max(id), 0) n from consultas_buscador")["n"]
    # Madrid está en UTC+1 en diciembre: la salida de las 09:05 es 08:05 UTC y la ventana abre a las 05:05 UTC
    fuera = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 04:50"))
    assert fuera["consultado"] is False and fuera["motivo"] == "fuera de la ventana"
    assert monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-12 09:00"))["motivo"] == "fuera de la ventana"
    primera = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))
    assert primera["consultado"] is True and primera["estado"] == "a tiempo" and primera["consultas"] == 1
    segunda = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:40"))
    assert segunda["consultado"] is False and segunda["motivo"].startswith("consultado hace menos de")
    assert len(b.de("q")) == 1                                       # dos llamadas en 10 minutos: una consulta
    for minuto in range(45, 50):                                     # «Actualizar ahora» salta la caché, nunca el tope
        assert monitoreo_vuelos.consultar(tramo["id"], ahora=_utc(f"2026-12-13 05:{minuto}"), forzar=True)["consultado"]
    septima = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 06:00"), forzar=True)
    assert septima["consultado"] is False and septima["motivo"] == "tope de 6 consultas"
    assert len(b.de("q")) == 6
    # ya aterrizó (09:30 en Lisboa, UTC+0): fuera de la ventana aunque se fuerce
    assert monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 09:45"), forzar=True)["motivo"] == "fuera de la ventana"
    # trazabilidad: cada consulta hecha queda en consultas_buscador; cada motivo para no consultar, en la bitácora del viaje
    assert db.uno("select count(*) n from consultas_buscador where tipo='estado_vuelo' and id>:i", i=desde_id)["n"] == 6
    motivos = [e["detalle"] for e in db.todos("select detalle from eventos where entidad='viaje' and entidad_id=:v "
                                              "and paso='consulta de estado omitida'", v=tramo["viaje_id"])]
    assert any("tope de 6 consultas" in m for m in motivos) and any("fuera de la ventana" in m for m in motivos)


def test_topes_por_dia_y_cupo_minimo(cliente, tramo, monkeypatch, tmp_path):
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado()))
    monkeypatch.setattr(precios, "cupo", lambda: {"restantes": 10})
    r = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))
    assert r["consultado"] is False and r["motivo"].startswith("cupo del buscador bajo")
    monkeypatch.setattr(precios, "cupo", lambda: {"restantes": 200})
    db.ejecutar("update reglas set valor='0' where ambito='supuesto' and clave='monitoreo_tope_dia'")
    try:
        assert monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))["motivo"].startswith("tope de 0 consultas del día")
    finally:
        db.ejecutar("update reglas set valor='30' where ambito='supuesto' and clave='monitoreo_tope_dia'")


def test_aviso_solo_cuando_cambia_algo(cliente):
    base = {"numero": "IB 5634", "desde": "MAD", "hasta": "LIS", "fecha": "2026-12-13", "estado": "a tiempo",
            "retraso_salida": 0, "terminal": "4", "puerta": "J58", "ultimo_aviso": None}
    a = monitoreo_vuelos.aviso
    assert "20 min" in a(base, {**base, "estado": "retrasado", "retraso_salida": 20})
    assert a({**base, "retraso_salida": 20}, {**base, "retraso_salida": 25}) is None
    assert "40 min" in a({**base, "retraso_salida": 20}, {**base, "retraso_salida": 40})
    assert "J60" in a(base, {**base, "puerta": "J60"})
    assert "terminal" in a(base, {**base, "terminal": "4S"}).lower()
    assert "cancelado" in a(base, {**base, "estado": "cancelado"}).lower()
    assert a({**base, "estado": "cancelado"}, {**base, "estado": "cancelado"}) is None
    assert a(base, dict(base)) is None                                       # la misma información, nunca
    assert a(base, {**base, "puerta": None}) is None                         # una puerta que desaparece no es un cambio
    # el retraso que crece de a poco se mide contra el último aviso, no contra la consulta anterior
    avisado = {**base, "retraso_salida": 30, "ultimo_aviso": json.dumps({"retraso": 20})}
    assert "36 min" in a(avisado, {**base, "retraso_salida": 36})
    assert a({**base, "retraso_salida": 10}, {**base, "retraso_salida": 12}) is None


def test_retraso_avisa_una_vez_por_telegram(cliente, tramo, monkeypatch, tmp_path):
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado("Delayed", "9:25 AM", "9:50 AM")))
    enviados = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: enviados.append((metodo, d)) or {})
    titular = db.uno("select usuario_id from viajes where id=:v", v=tramo["viaje_id"])["usuario_id"]
    previo = db.uno("select telegram_chat_id from usuarios where id=:u", u=titular)["telegram_chat_id"]
    db.ejecutar("update usuarios set telegram_chat_id=:c where id=:u", c=previo or 77001122, u=titular)
    try:
        monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))
        monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:50"), forzar=True)
    finally:
        db.ejecutar("update usuarios set telegram_chat_id=:c where id=:u", c=previo, u=titular)
    mensajes = [d["text"] for m, d in enviados if m == "sendMessage"]
    assert len(mensajes) == 1 and "IB 5634" in mensajes[0] and "20 min" in mensajes[0]
    ev = db.todos("select detalle from eventos where entidad='viaje' and entidad_id=:v and paso='aviso de vuelo enviado'", v=tramo["viaje_id"])
    assert len(ev) == 1 and ev[0]["detalle"] == mensajes[0]
    t = db.uno("select * from tramos_vuelo where id=:i", i=tramo["id"])
    assert db.de_json(t["ultimo_aviso"])["retraso"] == 20 and t["retraso_salida"] == 20 and t["estado"] == "retrasado"


def test_aviso_sin_telegram_queda_en_el_tablero(cliente, tramo, monkeypatch, tmp_path):
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado("Cancelled")))
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))
    t = db.uno("select * from tramos_vuelo where id=:i", i=tramo["id"])
    assert t["estado"] == "cancelado" and db.de_json(t["ultimo_aviso"])["enviado"] is False
    assert db.uno("select id from eventos where entidad='viaje' and entidad_id=:v and paso='aviso de vuelo sin Telegram'", v=tramo["viaje_id"])


def test_respuesta_sin_bloque_queda_sin_datos(cliente, tramo, monkeypatch, tmp_path):
    """Punto de atención 5: número inexistente o fecha fuera de rango."""
    _simular(monkeypatch, tmp_path, Buscador({}, estado={"organic_results": [{"title": "Iberia"}]}))
    enviados = []
    monkeypatch.setattr(telegram, "avisar", lambda *a: enviados.append(a))
    r = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))
    assert r["consultado"] is True and r["estado"] == "sin datos" and r["consultas"] == 1 and enviados == []
    fila = db.uno("select * from consultas_buscador where tipo='estado_vuelo' order by id desc limit 1")
    assert fila["resultados"] == 0 and "bloque" in (fila["error"] or "")


def test_respaldo_de_ejemplo_sin_clave(cliente, tramo, monkeypatch):
    """La respuesta de ejemplo guardada sirve para la demostración y las pruebas sin gastar búsquedas."""
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    assert (config.DIR_RESPALDO / "estado_vuelo_IB5634_2026-12-13.json").is_file()
    r = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 06:00"))
    assert r["consultado"] and r["estado"] == "retrasado" and r["retraso_salida"] == 20 and r["puerta"] == "J58"
    assert db.uno("select origen from consultas_buscador where tipo='estado_vuelo' order by id desc limit 1")["origen"] == "guardado"


def test_tablero_muestra_el_estado_y_la_hora_limite(cliente, monkeypatch, tmp_path):
    # viaje a Moab con hora límite 18:30: el vuelo llega a SLC a las 12:00 y el traslado es de unas 6 h
    _, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-10-05", "2027-10-08")
    db.ejecutar("update solicitudes set llegar_antes='2027-10-05T18:30' where id=:i", i=sid)
    db.ejecutar("update viajes set estado='aprobado' where id=:v", v=v["id"])
    ultimo = db.uno("select id from tramos_vuelo where viaje_id=:v and numero='DL 200'", v=v["id"])
    db.actualizar("tramos_vuelo", ultimo["id"], estado="retrasado", retraso_salida=40, retraso_llegada=40, terminal="S",
                  puerta="B12", llega_estimada="2027-10-05 12:40", actualizado="2027-10-05 15:00:00")
    html = cliente.get("/admin/viajes?fecha=2027-10-05").text
    assert "DL 200" in html and "Retrasado" in html and "40 min" in html and "B12" in html
    marca = 'title="Llegada estimada más el traslado: 2027-10-05 18:4'   # la marca «No llega a la grabación» de la fila
    assert marca in html and "No llega a la grabación" in html
    assert f"/admin/vuelos/{ultimo['id']}/actualizar" in html and "/admin/viajes/vuelos" in html
    # con la llegada programada sí alcanzaba: la marca sale de la llegada estimada
    db.actualizar("tramos_vuelo", ultimo["id"], llega_estimada=None, estado="a tiempo", retraso_llegada=0)
    assert 'title="Llegada estimada más el traslado' not in cliente.get("/admin/viajes?fecha=2027-10-05").text
    # el JSON del tablero (fuera de la ventana: no consulta) trae lo mismo
    datos = cliente.get("/admin/viajes/vuelos?fecha=2027-10-05").json()
    fila = next(f for f in datos if f["numero"] == "DL 200")
    assert fila["puerta"] == "B12" and fila["no_llega"] is False and fila["codigo"] == v["codigo"]


def test_actualizar_ahora(cliente, tramo, monkeypatch, tmp_path):
    b = _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado()))
    r = cliente.post(f"/admin/vuelos/{tramo['id']}/actualizar", follow_redirects=False)
    assert r.status_code == 303 and "/admin/viajes" in r.headers["location"]
    assert "fuera%20de%20la%20ventana" in r.headers["location"]
    # dentro de la ventana, forzar consulta
    monkeypatch.setenv("MONITOREO_AHORA", "2026-12-13T06:00")
    monkeypatch.setattr(config, "LOCAL", True)
    r = cliente.post(f"/admin/vuelos/{tramo['id']}/actualizar", data={"fecha": "2026-12-13"}, follow_redirects=False)
    assert "estado%20actualizado" in r.headers["location"] and "fecha=2026-12-13" in r.headers["location"]
    assert len(b.de("q")) == 1


def test_solo_administracion_ve_el_monitoreo(piloto, tramo):
    assert piloto.get("/admin/viajes/vuelos").status_code in (401, 403)
    assert piloto.post(f"/admin/vuelos/{tramo['id']}/actualizar").status_code in (401, 403)


# ---------- ronda de arreglos 1 ----------
def test_regreso_y_reserva_no_usan_otras_fechas(cliente):
    """Punto 1: el regreso y las tarifas guardados del 8 al 11 de diciembre no sirven para un viaje del 1 al 5 de marzo."""
    aa = {"numeros": ["AA 1851"], "desde": "MIA", "hasta": "LAS", "token": None}
    assert precios.vuelo_regreso(aa, "MIA", "LAS", "2027-03-01", "2027-03-05") is None
    assert precios.opciones_reserva(aa, None, "MIA", "LAS", "2027-03-01", "2027-03-05")[:2] == ([], "sin datos")
    assert precios.tarifas_de_vuelo("MIA", "LAS", "2027-03-01", "2027-03-05", aa) == ([], "sin datos")
    # las de las mismas fechas sí
    assert precios.vuelo_regreso(aa, "MIA", "LAS", "2026-12-08", "2026-12-11")["numeros"] == ["AA 1851"]


def test_reconfirmar_sin_regreso_no_consulta_solo_ida(cliente, monkeypatch, tmp_path):
    """Punto 2."""
    b = _simular(monkeypatch, tmp_path, Buscador({}, reconfirmacion=_reserva(410)))
    ida = {"tramos": [{"numero": "DL 100", "desde": "MIA", "hasta": "ATL", "sale": "2027-07-06 07:00"}], "precio": 410}
    r = precios.reconfirmar({"solicitud_id": None, "tarifa": "Main Cabin", "desglose": {"vuelo": ida, "regreso": None}})
    assert (r["estado"], r["motivo"]) == ("sin datos", "sin tramos del regreso") and b.llamadas == []


def test_dos_consultas_a_la_vez_pagan_una(cliente, tramo, monkeypatch, tmp_path):
    """Punto 3: mientras una consulta espera al proveedor, otra petición del mismo tramo no paga otra."""
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado("Delayed", "9:25 AM", "9:50 AM")))
    real, segundas = precios.estado_vuelo, []

    def lento(*a, **k):
        segundas.append(monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"), forzar=True))
        return real(*a, **k)
    monkeypatch.setattr(precios, "estado_vuelo", lento)
    assert monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))["consultado"]
    assert segundas[0]["consultado"] is False
    assert db.uno("select consultas from tramos_vuelo where id=:i", i=tramo["id"])["consultas"] == 1
    # dos avisos sobre el mismo tramo leído antes: solo uno se registra
    antes = db.uno("select * from tramos_vuelo where id=:i", i=tramo["id"])   # los dos leen el mismo tramo
    despues = {**antes, "estado": "cancelado"}
    monitoreo_vuelos._avisar(antes, "texto 1", despues, _utc("2026-12-13 05:31"))
    monitoreo_vuelos._avisar(antes, "texto 2", despues, _utc("2026-12-13 05:31"))
    pasos = db.todos("select detalle from eventos where entidad='viaje' and entidad_id=:v and detalle like 'texto %'", v=tramo["viaje_id"])
    assert [p["detalle"] for p in pasos] == ["texto 1"]
    assert "pidiendoVuelos" in cliente.get("/admin/viajes").text      # el tablero no lanza un refresco si hay otro en curso


def test_cancelacion_no_se_repite_y_sin_datos_no_borra_lo_conocido(cliente, tramo, monkeypatch, tmp_path):
    """Punto 4."""
    b = _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado("Cancelled")))
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    pasos = ("2026-12-13 05:30", "2026-12-13 05:40", "2026-12-13 05:50")
    monitoreo_vuelos.consultar(tramo["id"], ahora=_utc(pasos[0]))
    b.estado = {"organic_results": []}                                # el proveedor deja de traer el bloque
    r = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc(pasos[1]), forzar=True)
    assert r["estado"] == "cancelado" and r["ultima_consulta"] == "sin datos"
    b.estado = _estado("Cancelled")
    monitoreo_vuelos.consultar(tramo["id"], ahora=_utc(pasos[2]), forzar=True)
    avisos = db.todos("select detalle from eventos where entidad='viaje' and entidad_id=:v and paso like 'aviso de vuelo%'", v=tramo["viaje_id"])
    assert len(avisos) == 1 and "CANCELADO" in avisos[0]["detalle"]


def test_terminal_y_puerta_conservan_el_ultimo_valor(cliente, tramo, monkeypatch, tmp_path):
    """Punto 4: el proveedor manda «-» cuando no sabe la puerta."""
    b = _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado()))
    monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))
    b.estado = _estado(puerta="-", terminal="-")
    r = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:40"), forzar=True)
    assert (r["terminal"], r["puerta"]) == ("4", "J58")


def test_zona_horaria_por_el_lugar_mas_cercano(cliente):
    """Punto 5: la zona de GeoNames del lugar más cercano respeta las fronteras horarias dentro de un país."""
    from app.servicios import geografia
    monitoreo_vuelos._zonas_cache.clear()
    casos = {"MOB": "America/Chicago", "PNS": "America/Chicago", "ELP": "America/Denver", "IGU": "America/Sao_Paulo",
             "MIA": "America/New_York", "SLC": "America/Denver", "MAD": "Europe/Madrid", "LIS": "Europe/Lisbon"}
    assert {c: str(monitoreo_vuelos.zona(c)) for c in casos} == casos
    assert db.uno("select zona from lugares where nombre='Pensacola'")["zona"] == "America/Chicago"
    assert geografia.zona_horaria(0.0, -140.0) is None                 # en medio del océano no hay lugar cercano
    # Pensacola está en hora central: las 09:00 del 13 de diciembre son las 15:00 UTC (no las 14:00 de Miami)
    assert monitoreo_vuelos._en_utc("2026-12-13 09:00", "PNS") == _utc("2026-12-13 15:00")


def test_el_tope_del_viaje_no_deja_sin_monitoreo_el_regreso(cliente, tramo, monkeypatch, tmp_path):
    """Punto 6: el tope del viaje se aplica a cada sentido."""
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado()))
    db.insertar("tramos_vuelo", viaje_id=tramo["viaje_id"], sentido="ida", orden=8, numero="IB 5600", estado="programado",
                consultas=12, **{k: v for k, v in MAD_LIS.items() if k != "numero"})
    regreso = db.insertar("tramos_vuelo", viaje_id=tramo["viaje_id"], sentido="regreso", orden=9, numero="IB 5634",
                          estado="programado", consultas=0, **{k: v for k, v in MAD_LIS.items() if k != "numero"})
    assert monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))["motivo"] == "tope de 12 consultas del viaje de ida"
    assert monitoreo_vuelos.consultar(regreso, ahora=_utc("2026-12-13 05:30"))["consultado"] is True


def test_el_tablero_sin_fecha_incluye_vuelos_en_curso_de_ayer(cliente, nuevo_viaje):
    """Punto 7: un vuelo nocturno de Las Vegas del 12 sigue en el aire el 13 en UTC."""
    v = nuevo_viaje()
    nocturno = db.insertar("tramos_vuelo", viaje_id=v["id"], sentido="regreso", orden=7, numero="AA 9", desde="LAS", hasta="MIA",
                           fecha="2026-12-12", sale_programada="2026-12-12 23:30", llega_programada="2026-12-13 07:20",
                           estado="programado", consultas=0)
    de_dia = db.insertar("tramos_vuelo", viaje_id=v["id"], sentido="regreso", orden=8, numero="AA 10", desde="LAS", hasta="MIA",
                         fecha="2026-12-12", sale_programada="2026-12-12 10:00", llega_programada="2026-12-12 17:50",
                         estado="programado", consultas=0)
    ids = {f["id"] for f in monitoreo_vuelos.tablero(None, _utc("2026-12-13 06:00"))}
    assert nocturno in ids and de_dia not in ids
    assert {nocturno, de_dia} <= {f["id"] for f in monitoreo_vuelos.tablero("2026-12-12", _utc("2026-12-13 06:00"))}


def test_el_tope_del_dia_cuenta_el_dia_de_ahora(cliente, tramo, monkeypatch, tmp_path):
    """Punto 8: el tope por día se cuenta con `ahora`, no con el reloj."""
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado()))
    db.insertar("consultas_buscador", momento=db.ahora(), tipo="estado_vuelo", origen="en vivo", clave="hoy", resultados=0)
    db.ejecutar("update reglas set valor='1' where ambito='supuesto' and clave='monitoreo_tope_dia'")
    try:
        assert monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))["consultado"] is True
        db.insertar("consultas_buscador", momento="2026-12-13 05:31:00", tipo="estado_vuelo", origen="en vivo", clave="ese día", resultados=0)
        r = monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:40"), forzar=True)
        assert r["motivo"] == "tope de 1 consultas del día"
    finally:
        db.ejecutar("update reglas set valor='30' where ambito='supuesto' and clave='monitoreo_tope_dia'")


def test_el_estado_del_vuelo_no_se_escribe_en_la_carpeta_de_respaldos(cliente, monkeypatch, tmp_path):
    """Punto 9: solo la tabla `busquedas`; el ejemplo versionado se queda."""
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado()))
    assert precios.estado_vuelo("IB 5634", "2026-12-13")
    assert not list(tmp_path.glob("*.json"))
    clave = db.uno("select clave from consultas_buscador where tipo='estado_vuelo' order by id desc limit 1")["clave"]
    assert db.uno("select id from busquedas where clave=:c", c=clave)
    assert (config.DIR_RESPALDO / "estado_vuelo_IB5634_2026-12-13.json").is_file()


def test_aviso_fallido_y_ultimo_aviso_en_el_tablero(cliente, tramo, monkeypatch, tmp_path):
    """Punto 11: «aviso de vuelo enviado» solo si Telegram respondió bien; el último aviso se ve en el tablero."""
    _simular(monkeypatch, tmp_path, Buscador({}, estado=_estado("Delayed", "9:25 AM", "9:50 AM")))
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")

    def caido(metodo, **d):
        raise telegram.ErrorTelegram("sendMessage: Bad Gateway")
    monkeypatch.setattr(telegram, "_llamar", caido)
    titular = db.uno("select usuario_id from viajes where id=:v", v=tramo["viaje_id"])["usuario_id"]
    previo = db.uno("select telegram_chat_id from usuarios where id=:u", u=titular)["telegram_chat_id"]
    db.ejecutar("update usuarios set telegram_chat_id=:c where id=:u", c=previo or 77001133, u=titular)
    try:
        monitoreo_vuelos.consultar(tramo["id"], ahora=_utc("2026-12-13 05:30"))
    finally:
        db.ejecutar("update usuarios set telegram_chat_id=:c where id=:u", c=previo, u=titular)
    pasos = [e["paso"] for e in db.todos("select paso from eventos where entidad='viaje' and entidad_id=:v and paso like 'aviso de vuelo%'",
                                         v=tramo["viaje_id"])]
    assert pasos == ["aviso de vuelo fallido"]
    ultimo = db.de_json(db.uno("select ultimo_aviso from tramos_vuelo where id=:i", i=tramo["id"])["ultimo_aviso"])
    assert ultimo["enviado"] is False and "Bad Gateway" in ultimo["error"]
    html = cliente.get("/admin/viajes?fecha=2026-12-13").text
    assert "Último aviso al viajero" in html and "Bad Gateway" in html
    fila = next(f for f in cliente.get("/admin/viajes/vuelos?fecha=2026-12-13").json() if f["id"] == tramo["id"])
    assert fila["aviso"]["texto"].startswith("Vuelo IB 5634")


def test_la_confirmacion_de_precio_caduca_al_rechazar_o_reabrir(cliente, monkeypatch, tmp_path):
    """Punto 13."""
    from app.servicios import viajes
    b, sid, v = _decidido(cliente, monkeypatch, tmp_path, "2027-11-02", "2027-11-05", reconfirmacion=_reserva(451))
    _aprobar(cliente, v["id"])
    assert viajes.precio_por_confirmar(v["id"])
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "rechazar", "motivo": "Revisar fechas con el cliente"})
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "reabrir"})
    assert viajes.precio_por_confirmar(v["id"]) is None
    antes = len(b.llamadas)
    _aprobar(cliente, v["id"], confirmar_precio="1")                 # la confirmación vieja ya no vale: se reconfirma
    assert len(b.llamadas) == antes + 1 and viajes.de_solicitud(sid)["estado"] == "pendiente_aprobacion"


def test_el_json_del_tablero_lee_una_vez(cliente, tramo, monkeypatch):
    """Punto 14: una lectura del tablero y de las reglas por petición."""
    llamadas = {"tablero": 0, "reglas": 0}
    tablero, reglas = monitoreo_vuelos.tablero, monitoreo_vuelos.reglas

    def contar(nombre, funcion):
        def envoltura(*a, **k):
            llamadas[nombre] += 1
            return funcion(*a, **k)
        return envoltura
    monkeypatch.setattr(monitoreo_vuelos, "tablero", contar("tablero", tablero))
    monkeypatch.setattr(monitoreo_vuelos, "reglas", contar("reglas", reglas))
    assert any(f["id"] == tramo["id"] for f in cliente.get("/admin/viajes/vuelos?fecha=2026-12-13").json())
    assert llamadas == {"tablero": 1, "reglas": 1}


def test_monitoreo_ahora_solo_en_local(monkeypatch):
    """Punto 15: el momento fijado para la demostración solo vale en local."""
    monkeypatch.setenv("MONITOREO_AHORA", "2026-12-13T06:00")
    monkeypatch.setattr(config, "LOCAL", True)
    assert monitoreo_vuelos.momento_actual() == _utc("2026-12-13 06:00")
    monkeypatch.setattr(config, "LOCAL", False)
    assert abs((monitoreo_vuelos.momento_actual() - datetime.now(UTC)).total_seconds()) < 5
    monkeypatch.setattr(config, "LOCAL", True)
    monkeypatch.setenv("MONITOREO_AHORA", "no es una fecha")
    assert abs((monitoreo_vuelos.momento_actual() - datetime.now(UTC)).total_seconds()) < 5
