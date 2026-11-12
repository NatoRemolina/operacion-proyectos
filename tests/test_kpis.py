"""Indicadores con meta y semáforo, rastro de las consultas al buscador y ficha por persona, contra un conjunto conocido."""
import json
from datetime import datetime, timedelta

import pytest

from app import config, db, web
from app.servicios import acceso, inteligencia, kpis, metricas, precios, viajes

PROYECTO = 911   # proyecto exclusivo de estas pruebas: aísla las cifras de lo que carguen las demás


def _id_admin() -> int:
    return db.uno("select id from usuarios where correo='admin@demo.local'")["id"]


def _gasto(viaje, usuario, estado, total, categoria, fecha, creado, moneda="USD", total_usd=None, canal="web", leido=None):
    doc = db.insertar("documentos", nombre=f"recibo-{total}.jpg", mime="image/jpeg", canal=canal, huella=f"kpi-{total}-{estado}",
                      creado=creado, usuario_id=usuario, viaje_id=viaje, tipo="soporte")
    return db.insertar("gastos", documento_id=doc, proyecto_id=PROYECTO, viaje_id=viaje, usuario_id=usuario, comercio="Comercio",
                       fecha=fecha, categoria=categoria, total=total, moneda=moneda, total_usd=total if total_usd is None else total_usd,
                       estado=estado, confianza=0.95, creado=creado,
                       extraido=json.dumps({"comercio": "Comercio", "fecha": fecha, "categoria": categoria, "total": leido,
                                            "moneda": moneda}) if leido else None)


@pytest.fixture(scope="module")
def caso(cliente):
    """Dos personas con una cotización, una decisión, un viaje aprobado y gastos cada una. Cifras calculables a mano."""
    if not db.uno("select id from proyectos where id=:i", i=PROYECTO):
        db.insertar("proyectos", id=PROYECTO, nombre="Proyecto de indicadores", moneda="USD")
    admin = _id_admin()
    a = acceso.crear_usuario("kpi-a@demo.local", "Persona A de indicadores", "colaborador", "clave-de-prueba-a")
    b = acceso.crear_usuario("kpi-b@demo.local", "Persona B de indicadores", "colaborador", "clave-de-prueba-b")
    vj = {u: db.uno("select viajero_id from usuarios where id=:i", i=u)["viajero_id"] for u in (a, b)}

    def cotizacion(u, creado, ida, decidido, siguio, ahorro, presupuesto, detalle, aprobado_en):
        s = db.insertar("solicitudes", proyecto_id=PROYECTO, viajero_id=vj[u], origen="MIA", destino="LAS", ida=ida, regreso=ida,
                        estado="comparando", creado=creado, usuario_id=admin, ahorro_potencial=50)
        d = db.insertar("decisiones", solicitud_id=s, proyecto_id=PROYECTO, creado=decidido, siguio_recomendacion=siguio,
                        desglose={"ahorro": ahorro}, usuario_id=admin)
        db.insertar("elecciones", decision_id=d, solicitud_id=s, tipo="vuelo", posicion=1, elegida=1, recomendada=siguio, creado=decidido)
        v = db.insertar("viajes", solicitud_id=s, decision_id=d, proyecto_id=PROYECTO, usuario_id=u, viajero_id=vj[u], ida=ida, regreso=ida,
                        presupuesto_usd=presupuesto, presupuesto_detalle=detalle, estado="aprobado", aprobado_por=admin,
                        aprobado_en=aprobado_en, creado=decidido)
        return s, v

    # A: decide 6 h después de cotizar, 21 días antes de ir, sigue la recomendación; aprobación 12 h después
    s1, v1 = cotizacion(a, "2026-11-02 10:00:00", "2026-11-23", "2026-11-02 16:00:00", 1, 40, 1000,
                        [{"concepto": "Vuelo", "valor": 600, "grupo": "vuelo"}, {"concepto": "Viáticos", "valor": 400, "grupo": "viaticos"}],
                        "2026-11-03 04:00:00")
    # B: decide 12 h después, 7 días antes de ir, no sigue la recomendación; aprobación 24 h después
    s2, v2 = cotizacion(b, "2026-11-03 08:00:00", "2026-11-10", "2026-11-03 20:00:00", 0, 0, 100,
                        [{"concepto": "Hotel", "valor": 100, "grupo": "hotel"}], "2026-11-04 20:00:00")

    hace3 = datetime.fromisoformat(db.ahora()) - timedelta(days=3)
    g1 = _gasto(v1, a, "aprobado_auto", 500, "vuelo", "2026-11-01", "2026-11-03 10:00:00", leido=500.0)          # 2 días
    g2 = _gasto(v1, a, "aprobado", 200, "comida", "2026-11-01", "2026-11-05 00:00:00", canal="telegram", leido=250.0)  # 4 días, total corregido
    g3 = _gasto(v2, b, "aprobado_auto", 150, "hotel", "2026-11-04", "2026-11-04 09:00:00", moneda="EUR", total_usd=162)  # 0 días
    g4 = _gasto(None, b, "revision", 30, "comida", (hace3 - timedelta(days=1)).strftime("%Y-%m-%d"),               # 1 día, sin viaje
                hace3.strftime("%Y-%m-%d %H:%M:%S"))
    nota_b = db.insertar("documentos", nombre="", mime="text/plain", canal="telegram", huella="kpi-nota-b", creado=db.ahora(),
                         usuario_id=b, viaje_id=None, tipo="nota", texto="nota privada de la persona B")
    for gid, inicio, fin, paso in ((g1, "2026-11-03 10:00:00", "2026-11-03 10:00:30", "aprobado sin intervención"),
                                   (g2, "2026-11-05 00:00:00", "2026-11-05 12:00:00", "corregido y aprobado")):
        db.insertar("eventos", momento=inicio, entidad="gasto", entidad_id=gid, paso="documento recibido", detalle="", fuente="", duracion_ms=0)
        db.insertar("eventos", momento=fin, entidad="gasto", entidad_id=gid, paso=paso, detalle="", fuente="", duracion_ms=0)
    db.insertar("eventos", momento="2026-11-04 20:00:00", entidad="viaje", entidad_id=v2, paso="presupuesto aprobado",
                detalle="viaje de la persona B", fuente="", duracion_ms=0)

    # Consultas al buscador de la cotización de A: dos en vivo, dos reutilizadas, una fallida
    for origen, ms, importes, error in (("en vivo", 1200, [100, 200, 300], None), ("en vivo", 3000, [150], None),
                                        ("guardado", 5, [120, 180], None), ("guardado (otras fechas)", 4, [90], None),
                                        ("fallida", 800, [], "cupo agotado")):
        kpis.registrar_consulta("vuelos", origen, "vuelos_MIA_LAS_prueba.json", s1, ms, importes, error)
    return {"a": a, "b": b, "s1": s1, "s2": s2, "v1": v1, "v2": v2, "g": (g1, g2, g3, g4), "nota_b": nota_b}


def _por_nombre(f: dict) -> dict:
    return {k["nombre"]: k for k in kpis.evaluar(f)}


def test_una_cotizacion_deja_rastro_de_cada_consulta(nuevo_viaje):
    sid = nuevo_viaje(aprobar=False)["solicitud_id"]   # caso Miami–Las Vegas con las respuestas guardadas
    filas = db.todos("select * from consultas_buscador where solicitud_id=:s order by id", s=sid)
    assert {(c["tipo"], c["origen"]) for c in filas} == {("vuelos", "guardado"), ("tarifas", "guardado"), ("hoteles", "guardado")}
    vuelos = next(c for c in filas if c["tipo"] == "vuelos")
    assert vuelos["clave"] == "vuelos_MIA_LAS_2026-12-08_2026-12-11.json" and (config.DIR_RESPALDO / vuelos["clave"]).is_file()
    assert vuelos["resultados"] > 0 and vuelos["precio_min"] <= vuelos["precio_mediana"] and vuelos["error"] is None
    assert all(c["usuario_id"] == _id_admin() and c["duracion_ms"] is not None for c in filas)


def test_consultas_fallidas_y_de_otras_fechas_quedan_registradas(monkeypatch):
    def ultima():
        return db.uno("select * from consultas_buscador order by id desc limit 1")

    assert precios.buscar_vuelos("XXA", "XXB", "2027-01-01", "2027-01-05") == ([], "sin datos", {})   # lo que devuelve no cambia
    assert ultima()["origen"] == "fallida" and ultima()["error"] == precios.SIN_DATOS and ultima()["resultados"] == 0

    monkeypatch.setattr(config, "SERPAPI_KEY", "clave-falsa")

    def falla(*_):
        raise RuntimeError("cupo agotado")
    monkeypatch.setattr(precios, "_consultar", falla)
    antes = db.uno("select max(id) n from consultas_buscador")["n"]
    vuelos, origen, _ = precios.buscar_vuelos("MIA", "LAS", "2027-03-01", "2027-03-04")
    assert origen == "guardado (otras fechas)" and vuelos
    nuevas = db.todos("select * from consultas_buscador where id>:n order by id", n=antes)
    assert [(c["origen"], c["error"]) for c in nuevas] == [("fallida", "cupo agotado"), ("guardado (otras fechas)", None)]
    assert nuevas[1]["clave"] == "vuelos_MIA_LAS_2026-11-18_2026-11-21.json"   # el archivo que de verdad se usó

    # Sin tarifas guardadas y sin permiso de consultar no se buscó nada: no hay rastro que dejar
    antes = db.uno("select count(*) n from consultas_buscador")["n"]
    assert precios.tarifas_de_vuelo("MIA", "LAS", "2027-03-01", "2027-03-04", {"numeros": ["ZZ 1"]}) == ([], "sin datos")
    assert db.uno("select count(*) n from consultas_buscador")["n"] == antes


def test_kpis_de_cotizacion(caso):
    k = _por_nombre({"proyecto_id": PROYECTO})
    esperado = {"tasa_reutilizacion": (50, "ambar"), "tasa_consultas_fallidas": (20, "rojo"), "latencia_buscador": (2100, "verde"),
                "acuerdo_recomendacion": (50, "ambar"), "ahorro_identificado": (100, "verde"), "ahorro_capturado": (40, "ambar"),
                "captura_ahorro": (40, "rojo"), "horas_cotizacion_decision": (9.0, "verde"),
                "horas_decision_aprobacion": (18.0, "verde"), "anticipacion_compra": (14.0, "ambar")}
    assert {n: (k[n]["valor"], k[n]["estado"]) for n in esperado} == esperado
    c = metricas.buscador({"proyecto_id": PROYECTO})
    assert dict(c["por_origen"]) == {"en vivo": 2, "guardado": 1, "guardado (otras fechas)": 1, "fallida": 1}
    assert c["errores"][0][2] == "cupo agotado"
    b = metricas.busquedas({"proyecto_id": PROYECTO})
    assert b["consultas_en_vivo"] == 2 and b["consultas_reutilizadas"] == 2 and b["consultas_fallidas"] == 1   # Monitoreo lee lo mismo


def test_cupo_del_buscador(monkeypatch):
    assert _por_nombre({})["cupo_usado"]["estado"] == "sin datos"      # sin clave no hay cupo que consultar
    monkeypatch.setattr(precios, "cupo", lambda: {"plan": "x", "mensual": 250, "usadas": 200, "restantes": 50})
    assert (_por_nombre({})["cupo_usado"]["valor"], _por_nombre({})["cupo_usado"]["estado"]) == (80, "ambar")


def test_kpis_de_gastos(caso):
    k = _por_nombre({"proyecto_id": PROYECTO})
    esperado = {"ejecucion_presupuesto": (78, "verde"),          # (500 + 200 + 162) / (1000 + 100)
                "viajes_sobre_presupuesto": (1, "ambar"), "tasa_sin_intervencion": (50, "ambar"),
                "dias_recibo_a_carga": (1.5, "verde"), "horas_carga_a_aprobacion": (6.0, "verde"),
                "tasa_correccion": (round(100 / (2 * len(inteligencia.CAMPOS_COMPARADOS))), "ambar"),
                "gastos_sin_viaje": (1, "ambar"), "pendientes_revision": (1, "verde")}
    assert {n: (k[n]["valor"], k[n]["estado"]) for n in esperado} == esperado
    assert 2.9 <= k["revision_mas_antigua"]["valor"] <= 3.1 and k["revision_mas_antigua"]["estado"] == "ambar"
    g = metricas.gastos({"proyecto_id": PROYECTO})
    assert [(m["moneda"], m["gastos"], m["total"], m["total_usd"]) for m in g["por_moneda"]] == [("USD", 2, 700, 700), ("EUR", 1, 150, 162)]
    assert [x["id"] for x in g["revision_antiguas"]] == [caso["g"][3]]
    v = metricas.viajes({"proyecto_id": PROYECTO})
    assert v["por_proyecto"] == [{"proyecto": "Proyecto de indicadores", "presupuesto": 1100, "gastado": 862, "pct": 78}]
    assert {c["grupo"]: (c["presupuesto"], c["gastado"]) for c in v["por_categoria"]} == {
        "Vuelo y equipaje": (600, 500), "Hotel": (100, 162), "Viáticos (comida, combustible, peajes, otros)": (400, 200)}


def test_costo_por_recibo():
    for _ in range(2):
        db.insertar("llamadas_modelo", momento="2020-01-05 10:00:00", uso="recibo", modelo="prueba", tokens_entrada=1000,
                    tokens_salida=100, latencia_ms=900, estado_http=200)
    k = _por_nombre({"desde": "2020-01-01", "hasta": "2020-01-31"})["costo_por_recibo"]
    assert (k["valor"], k["estado"]) == (0.0008, "verde")    # (1000 × 0,5 + 100 × 3) / 1 000 000 por lectura


def test_sin_datos_no_hay_color_ni_division_por_cero():
    vacio = {"proyecto_id": 99999, "desde": "2099-01-01"}
    k = kpis.evaluar(vacio)
    assert {x["estado"] for x in k} == {"sin datos"} and all(x["valor"] is None for x in k)
    assert all(p["valor"] is None for fila in kpis.tendencia(vacio)["filas"] for p in fila["puntos"])
    assert kpis.estado(None, "mayor", 1, 0) == "sin datos"


def test_cambiar_una_meta_en_reglas_cambia_el_color(caso, cliente):
    f = {"proyecto_id": PROYECTO}
    assert _por_nombre(f)["ejecucion_presupuesto"]["estado"] == "verde"
    reglas = {r["clave"]: r["id"] for r in db.todos("select id, clave from reglas where ambito='kpi' and entidad='ejecucion_presupuesto'")}
    assert set(reglas) == {"meta", "umbral_alerta"}
    assert "ejecucion_presupuesto" in cliente.get("/reglas").text          # se editan en la pantalla de Reglas que ya existe
    cliente.post(f"/reglas/{reglas['meta']}", data={"valor": "50"})
    cliente.post(f"/reglas/{reglas['umbral_alerta']}", data={"valor": "60"})
    try:
        k = _por_nombre(f)["ejecucion_presupuesto"]
        assert (k["meta"], k["alerta"], k["estado"]) == (50, 60, "rojo")
        cliente.post(f"/reglas/{reglas['umbral_alerta']}", data={"valor": "80"})
        assert _por_nombre(f)["ejecucion_presupuesto"]["estado"] == "ambar"
    finally:
        cliente.post(f"/reglas/{reglas['meta']}", data={"valor": "100"})
        cliente.post(f"/reglas/{reglas['umbral_alerta']}", data={"valor": "110"})


def test_tendencia_semanal(caso):
    t = kpis.tendencia({"proyecto_id": PROYECTO, "hasta": "2026-11-08"})
    assert t["semanas"][-1] == "2026-11-02" and len(t["semanas"]) == 8
    fila = next(x for x in t["filas"] if x["nombre"] == "horas_decision_aprobacion")
    assert fila["puntos"][-1]["valor"] == 18.0 and all(p["valor"] is None for p in fila["puntos"][:-1])


def test_ficha_de_una_persona_no_muestra_nada_de_otra(caso, cliente):
    a, b = kpis.ficha_persona(caso["a"]), kpis.ficha_persona(caso["b"])
    assert a["usuario"]["codigo"] == viajes.codigo_persona(caso["a"]) and a["usuario"]["rol"] == "colaborador"
    assert [c["id"] for c in a["cotizaciones"]] == [caso["s1"]] and a["cotizaciones"][0]["ida"] == "2026-11-23"
    assert [v["id"] for v in a["viajes"]] == [caso["v1"]] and [v["id"] for v in b["viajes"]] == [caso["v2"]]
    assert {g["id"] for g in a["gastos"]} == set(caso["g"][:2]) and {g["id"] for g in b["gastos"]} == set(caso["g"][2:])
    assert dict(a["gastos_por_canal"]) == {"web": 1, "telegram": 1} and dict(b["gastos_por_estado"]) == {"aprobado_auto": 1, "revision": 1}
    assert caso["nota_b"] in {d["id"] for d in b["evidencias"]} and caso["nota_b"] not in {d["id"] for d in a["evidencias"]}
    texto_a = json.dumps(a, default=str)
    v2 = viajes.uno(caso["v2"])["codigo"]
    assert v2 not in texto_a and "nota privada" not in texto_a
    assert "Persona B de indicadores" not in texto_a and "viaje de la persona B" not in texto_a
    assert any(e["entidad"] == "viaje" and e["entidad_id"] == caso["v2"] for e in b["eventos"])
    assert not any(e["entidad"] == "viaje" and e["entidad_id"] == caso["v2"] for e in a["eventos"])
    ka, kb = ({k["nombre"]: k for k in x["indicadores"]} for x in (a, b))
    assert (ka["ejecucion_presupuesto"]["valor"], kb["ejecucion_presupuesto"]["valor"]) == (70, 162)
    assert (ka["acuerdo_recomendacion"]["valor"], kb["acuerdo_recomendacion"]["valor"]) == (100, 0)
    assert ka["tasa_reutilizacion"]["valor"] == 50 and kb["tasa_reutilizacion"]["estado"] == "sin datos"
    assert (ka["gastos_sin_viaje"]["valor"], kb["gastos_sin_viaje"]["valor"]) == (0, 1)
    assert kpis.ficha_persona(10 ** 6) is None

    pagina = cliente.get(f"/admin/kpis/persona/{caso['a']}")
    assert pagina.status_code == 200 and a["usuario"]["codigo"] in pagina.text and viajes.uno(caso["v1"])["codigo"] in pagina.text
    assert v2 not in pagina.text and "nota privada" not in pagina.text
    assert cliente.get("/admin/kpis/persona/999999").status_code == 404
    assert cliente.get(f"/api/kpis?persona_id={caso['b']}").json()["usuario"]["codigo"] == viajes.codigo_persona(caso["b"])


def test_filtro_por_persona_falla_cerrado():
    with pytest.raises(ValueError):
        metricas._filtro({"persona_id": 1}, "momento")


def test_tablero_api_csv_y_acceso(caso, cliente, piloto, gestor):
    pagina = cliente.get(f"/admin/kpis?proyecto_id={PROYECTO}&desde=2026-01-01")
    assert pagina.status_code == 200 and "Ejecución por categoría" in pagina.text
    assert f"/admin/kpis/persona/{caso['a']}" in pagina.text
    assert cliente.get("/admin/kpis").status_code == 200
    datos = cliente.get(f"/api/kpis?proyecto_id={PROYECTO}").json()
    assert {k["nombre"] for k in datos["kpis"]} == set(kpis.KPIS)
    assert all({"meta", "alerta", "estado", "responsable", "formula", "para_que", "sentido"} <= set(k) for k in datos["kpis"])
    assert next(p for p in datos["personas"] if p["id"] == caso["a"])["cotizaciones"] == 1
    for que, columna, filas in (("kpis", "estado", len(kpis.KPIS)), ("consultas", "precio_mediana", 5), ("personas", "codigo", None)):
        r = cliente.get(f"/admin/kpis/exportar.csv?que={que}&proyecto_id={PROYECTO}")
        assert r.status_code == 200 and columna in r.text.splitlines()[0], que
        if filas:
            assert len(r.text.splitlines()) == filas + 1, que
    assert cliente.get("/admin/kpis/exportar.csv?que=usuarios").status_code == 404
    assert {"texto": "KPIs", "href": "/admin/kpis", "orden": 65, "rol": "admin"} in web.MENU
    for quien in (piloto, gestor):
        for ruta in ("/admin/kpis", "/api/kpis", f"/admin/kpis/persona/{caso['a']}", "/admin/kpis/exportar.csv"):
            assert quien.get(ruta).status_code == 403, ruta
    assert "/admin/kpis" not in piloto.get("/").text
