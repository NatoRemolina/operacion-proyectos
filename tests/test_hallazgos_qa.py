"""Hallazgos del recorrido de punta a punta del 13 de noviembre: cada prueba reproduce el caso que falló."""
import pytest
from conftest import FORM_VIAJE


# ---------- I-2: los hoteles se comparan todos antes de recortar ----------
def _hotel_de_buscador(nombre, total, calificacion=4.2):
    return {"nombre": nombre, "noche": round(total / 3, 2), "noche_sin_cargos": None, "total": float(total),
            "calificacion": calificacion, "clase": 3, "vendedores": []}


def test_el_mejor_hotel_despues_del_puesto_12_se_recomienda(cliente, monkeypatch):
    from app.servicios import cotizacion, precios
    caros = [_hotel_de_buscador(f"Independiente {i}", 400 + i) for i in range(13)]
    respuesta = caros + [_hotel_de_buscador("Independiente Barato", 150), _hotel_de_buscador("Barato mal calificado", 120, 3.0)]
    monkeypatch.setattr(precios, "buscar_hoteles", lambda *a, **k: (list(respuesta), "guardado"))
    r = cliente.post("/viajes", data={**FORM_VIAJE}, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1])
    c = cotizacion.comparacion(sid)
    assert c["hotel_recomendado"]["h"]["nombre"] == "Independiente Barato"
    assert [h["h"]["nombre"] for h in c["hoteles_descartados"]] == ["Barato mal calificado"]
    # la lista se ordena por costo total y recién después se recorta
    assert len(c["hoteles"]) <= 12
    assert [h["ev"]["total"] for h in c["hoteles"]] == sorted(h["ev"]["total"] for h in c["hoteles"])


def test_las_vegas_guardado_muestra_el_descartado_por_calificacion(cliente):
    from app import db
    from app.servicios import cotizacion
    r = cliente.post("/viajes", data={**FORM_VIAJE}, follow_redirects=False)
    sid = int(r.headers["location"].rsplit("/", 1)[1])
    # la respuesta guardada trae 15 hoteles: se guardan todos
    assert db.uno("select count(*) n from opciones where solicitud_id=:i and tipo='hotel'", i=sid)["n"] == 15
    c = cotizacion.comparacion(sid)
    assert any(h["h"]["nombre"].startswith("OYO") for h in c["hoteles_descartados"])


# ---------- I-3: Lisboa elegida de la lista encuentra los hoteles guardados ----------
LISBOA = {"nombre": "Lisbon", "region": "Lisbon", "pais": "Portugal", "lat": 38.71667, "lon": -9.13333}


def _cotizar_lisboa(cliente, **cambios):
    import json
    datos = {**FORM_VIAJE, "origen": "MAD", "destino": "Lisbon, Lisbon, Portugal", "destino_aeropuertos": "LIS",
             "destino_lugar": json.dumps(LISBOA), "ida": "2026-12-13", "regreso": "2026-12-16",
             "llegar_antes": "2026-12-13T18:00", **cambios}
    r = cliente.post("/viajes", data=datos, follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_lisboa_elegida_de_la_lista_trae_los_hoteles_guardados(cliente, monkeypatch):
    from app import config, db
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    sid = _cotizar_lisboa(cliente)
    s = db.uno("select ciudad from solicitudes where id=:i", i=sid)
    assert s["ciudad"] == "Lisbon"
    assert db.uno("select count(*) n from opciones where solicitud_id=:i and tipo='hotel'", i=sid)["n"] == 18


def test_con_el_buscador_en_vivo_se_consulta_con_el_nombre_elegido(cliente, monkeypatch):
    from app import config
    from app.servicios import precios
    consultas = []

    def consultar(parametros, *a, **k):
        consultas.append(parametros)
        return {"properties": []}
    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-de-prueba")
    monkeypatch.setattr(precios, "_consultar", consultar)
    monkeypatch.setattr(precios, "_guardar", lambda *a, **k: None)
    hoteles, origen = precios.buscar_hoteles("Lisbon", "2026-12-13", "2026-12-16", None, otros_nombres=["lisboa"])
    assert [c["q"] for c in consultas if c.get("engine") == "google_hotels"] == ["Lisbon hotels"]
    assert origen == "en vivo" and hoteles == []


# ---------- I-4 e I-5: el asistente y los proyectos ----------



@pytest.fixture()
def proyectos_con_revision(nuevo_viaje, monkeypatch):
    """Un gasto en revisión en cada proyecto: el 1 lo gestiona el gestor de demostración y el 2 no."""
    from app import db
    from app.servicios import asistente
    monkeypatch.setattr(asistente, "tope_diario", lambda: 10_000)
    laura = db.uno("select * from usuarios where correo='piloto2@demo.local'")
    creados = []
    for proyecto, comercio, total in ((1, "Parqueo Torre Summerlin", 61.25), (2, "Taller Alfama Reservado", 88.4)):
        v = nuevo_viaje(viajero_id=2, proyecto_id=proyecto)
        creados.append(db.insertar("gastos", usuario_id=laura["id"], viaje_id=v["id"], proyecto_id=proyecto, viajero_id=2,
                                   comercio=comercio, fecha="2026-12-09", categoria="comida", total=total, moneda="USD",
                                   total_usd=total, estado="revision", motivos='["atipico"]', confianza=0.95, creado=db.ahora()))
    yield
    for gid in creados:
        db.ejecutar("delete from eventos where entidad='gasto' and entidad_id=:i", i=gid)
        db.ejecutar("delete from gastos where id=:i", i=gid)


def _usuario(correo):
    from app import db
    return db.uno("select * from usuarios where correo=:c", c=correo)


def test_la_palabra_proyecto_no_es_una_persona(proyectos_con_revision):
    from app.servicios import asistente
    admin = _usuario("admin@demo.local")
    assert asistente.personas_en_texto("¿Cuánto llevamos gastado en el proyecto Summerlin?", asistente.Alcance(admin)) == []
    r = asistente.responder("¿Cuánto llevamos gastado en el proyecto Summerlin?", admin)
    assert "Gestión de proyecto (demo)" not in r["texto"]
    assert "Residencial Summerlin" in r["texto"] and "gastado aprobado" in r["texto"]
    assert "Parqueo Torre Summerlin" in r["texto"] and "Taller Alfama Reservado" not in r["texto"]
    assert "No encontré registros" not in r["texto"]


def test_el_gestor_tiene_sus_propias_preguntas_sugeridas():
    from app.servicios import asistente
    gestor = asistente.preguntas_sugeridas(_usuario("gestor@demo.local"))
    assert "¿Cómo va el presupuesto de mi proyecto?" in gestor and "¿Qué gastos de mi proyecto están en revisión?" in gestor
    assert gestor != asistente.preguntas_sugeridas(_usuario("piloto@demo.local"))


def test_el_gestor_ve_lo_que_esta_en_revision_en_su_proyecto(proyectos_con_revision):
    from app.servicios import asistente
    gestor = _usuario("gestor@demo.local")
    r = asistente.responder("¿Qué gastos de mi proyecto están en revisión?", gestor)
    assert "Parqueo Torre Summerlin" in r["texto"] and "Ningún gasto está en revisión" not in r["texto"]
    assert "Taller Alfama Reservado" not in r["texto"] and "Alfama" not in r["texto"]
    r = asistente.responder("¿Cómo va el presupuesto de mi proyecto?", gestor)
    assert "Residencial Summerlin" in r["texto"] and "presupuesto" in r["texto"] and "Alfama" not in r["texto"]
    assert "Sin viajes como titular" not in r["texto"]


def test_el_gestor_no_ve_un_proyecto_que_no_gestiona(proyectos_con_revision):
    from app.servicios import asistente
    gestor = _usuario("gestor@demo.local")
    r = asistente.responder("¿Qué gastos del proyecto Alfama están en revisión?", gestor)
    assert "Taller Alfama Reservado" not in r["texto"] and "88.40" not in r["texto"]
    res = asistente.ejecutar(asistente.Rastro(gestor), "gastos_de", {"proyecto": "Apartamentos Alfama (aéreo)"})
    assert "error" in res
    res = asistente.ejecutar(asistente.Rastro(gestor), "gastos_de", {"proyecto": "2"})
    assert "error" in res


# ---------- I-6: el Excel contable cubre por omisión el año en curso ----------
def test_el_anio_en_curso_va_del_primero_de_enero_al_31_de_diciembre(monkeypatch):
    from datetime import UTC, date, datetime

    from app.servicios import contable
    assert contable.anio_en_curso(date(2026, 2, 14)) == ("2026-01-01", "2026-12-31")
    # a las 22:00 de Nueva York del 31 de diciembre, en UTC ya es el año siguiente: manda la zona de la empresa
    monkeypatch.setattr(contable, "_ahora", lambda: datetime(2027, 1, 1, 3, 0, tzinfo=UTC))
    assert contable.anio_en_curso() == ("2026-01-01", "2026-12-31")


def test_sin_fechas_el_excel_es_del_anio_en_curso(cliente):
    from app.servicios import contable
    desde, hasta = contable.anio_en_curso()
    assert desde.endswith("-01-01") and hasta.endswith("-12-31")
    nombre = f'attachment; filename="libro_contable_{desde}_{hasta}.xlsx"'
    assert cliente.get("/gastos/contable.xlsx").headers["content-disposition"] == nombre
    assert cliente.get("/api/v1/gastos/contable").headers["content-disposition"] == nombre
    lista = cliente.get("/gastos").text
    assert f'name="desde" value="{desde}"' in lista and f'name="hasta" value="{hasta}"' in lista
