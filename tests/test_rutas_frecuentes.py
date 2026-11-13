"""Rutas frecuentes contra un conjunto conocido: rutas inventadas (ZQA → ZQB) para que nada de otras pruebas cambie las cifras."""
from datetime import date, timedelta

from app import db
from app.servicios import rutas_frecuentes

HOY = date(2027, 3, 1)


def _cotizacion(origen="ZQA", destino="ZQB", dias_atras=10) -> int:
    return db.insertar("solicitudes", origen=origen, destino=destino, ida="2027-04-01", regreso="2027-04-04", estado="cotizado",
                       creado=(HOY - timedelta(days=dias_atras)).isoformat() + " 10:00:00")


def _observacion(precio, anticipacion, capturado="2027-02-20"):
    db.insertar("observaciones", busqueda=f"ZQA_ZQB_{anticipacion}", origen="ZQA", destino="ZQB", ida="2027-04-01",
                regreso="2027-04-04", aerolinea="Zeta", precio=precio, anticipacion=anticipacion, capturado=capturado,
                tipico_min=200, tipico_max=320, fuente="pruebas")


def _oferta(origen_fila, tarifa, normalizada, precio, vendedor="Zeta Air", es_aerolinea=1, cambios="no", maleta=40.0):
    db.insertar("ofertas_tarifa", momento="2027-02-20 10:00:00", fuente="buscador", origen_fila=origen_fila, origen="ZQA",
                destino="ZQB", ida="2027-04-01", regreso="2027-04-04", vuelos=origen_fila[-3:], vendedor=vendedor, es_aerolinea=es_aerolinea,
                tarifa=tarifa, tarifa_normalizada=normalizada, precio=precio, moneda="USD", cambios=cambios, maleta_usd=maleta,
                anticipacion_dias=40)


def _preparar():
    if db.uno("select id from solicitudes where origen='ZQA'"):
        return
    for _ in range(3):
        _cotizacion()
    _cotizacion(dias_atras=200)                       # fuera de los 90 días: no cuenta
    _cotizacion(origen="ZQC", destino="ZQD")          # otra ruta con una sola cotización
    for precio, anticipacion in ((400, 3), (420, 5), (300, 10), (320, 15), (310, 20), (250, 30), (260, 40), (240, 60)):
        _observacion(precio, anticipacion)
    for i, precio in enumerate((300, 300, 300, 330, 330, 330)):   # sube 10 % de la primera mitad a la segunda
        db.insertar("historial_ruta", busqueda="ZQA_ZQB_h", origen="ZQA", destino="ZQB",
                    fecha=(HOY - timedelta(days=12 - 2 * i)).isoformat(), precio=precio)
    for n, (basica, flexible) in enumerate(((200, 260), (220, 290))):
        _oferta(f"busqueda:zq{n}", "Basic", "basica", basica)
        _oferta(f"busqueda:zq{n}", "Main", "estandar", flexible, cambios="gratis")
        _oferta(f"busqueda:zq{n}", "Basic", "basica", basica + 15, vendedor="Agencia Uno", es_aerolinea=0)


def test_top_de_rutas_con_sus_cifras():
    _preparar()
    rutas = {r["ruta"]: r for r in rutas_frecuentes.top(n=50, hoy=HOY)}
    r = rutas["ZQA → ZQB"]
    assert r["cotizaciones"] == 3 and r["viajes"] == 0 and r["observaciones"] == 8
    assert rutas["ZQC → ZQD"]["cotizaciones"] == 1
    assert list(rutas).index("ZQA → ZQB") < list(rutas).index("ZQC → ZQD")
    assert r["por_anticipacion"] == {"0-7": 410, "8-21": 310, "22-45": 255, "46+": 240}
    assert r["mediana"] == 305 and r["volatilidad"] == 50.0           # desviación absoluta mediana
    assert r["tendencia"] == {"cambio_pct": 10.0, "sentido": "sube"}
    assert r["prima_flexibilidad"] == {"usd": 65.0, "pct": 30.9, "pares": 2}
    assert r["aerolinea_agencia"] == {"aerolinea": 210.0, "agencia": 225.0, "diferencia_usd": 15.0, "pares": 2}
    assert r["senal"]["valor"] == "dentro" and r["senal"]["referencia"] == "rango propio (p25–p75)"


def test_senal_por_debajo_y_por_encima():
    assert rutas_frecuentes.senal(100, [200, 210, 220, 230, 240])["valor"] == "por debajo"
    assert rutas_frecuentes.senal(400, [200, 210, 220, 230, 240])["valor"] == "por encima"
    assert rutas_frecuentes.senal(300, [200, 210], tipico=(250, 350))["referencia"] == "rango típico de Google"
    assert rutas_frecuentes.senal(None, [])["valor"] == "sin datos"


def test_tramos_de_anticipacion():
    assert [rutas_frecuentes.tramo(d) for d in (0, 7, 8, 21, 22, 45, 46, 300)] == ["0-7", "0-7", "8-21", "8-21", "22-45",
                                                                                    "22-45", "46+", "46+"]
