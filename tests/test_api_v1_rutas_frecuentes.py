"""API v1 de rutas frecuentes y precios: solo administración, con el contrato publicado."""
V1 = "/api/v1/kpis/rutas-frecuentes"


def test_trae_rutas_exactitud_y_aviso(cliente, nuevo_viaje):
    nuevo_viaje(aprobar=False)
    r = cliente.get(V1)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dias"] == 90 and "demostrativas" in d["aviso"] and isinstance(d["pocos_datos"], bool)
    assert {"mae", "mape", "mensaje", "por_ruta", "por_mes", "contra_pagado"} <= set(d["exactitud"])
    assert d["rutas"], "la cotización de la prueba cuenta como ruta frecuente"
    ruta = d["rutas"][0]
    assert {"por_anticipacion", "volatilidad", "tendencia", "prima_flexibilidad", "aerolinea_agencia", "senal"} <= set(ruta)
    assert ruta["senal"]["valor"] in ("por debajo", "dentro", "por encima", "sin datos")


def test_solo_administracion(piloto, gestor, anonimo):
    assert piloto.get(V1).status_code == 403
    assert gestor.get(V1).status_code == 403
    assert anonimo.get(V1).status_code == 401


def test_n_fuera_de_rango(cliente):
    assert cliente.get(V1 + "?n=0").status_code == 422
