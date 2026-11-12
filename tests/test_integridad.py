"""Integridad del flujo de gastos: importes, duplicados, transacciones, envíos repetidos y revisión versionada."""
from datetime import UTC, datetime, timedelta

import pytest

from app import db
from app.servicios import dinero, validacion


def _sin_rastro(*ids):
    for i in ids:
        db.ejecutar("delete from eventos where entidad='gasto' and entidad_id=:i", i=i)
        db.ejecutar("delete from gastos where id=:i", i=i)


# ---------- importes y reglas ----------
@pytest.mark.parametrize("total", [-10, 0, float("nan"), float("inf"), "NaN", "0.001", "Infinity", 1e15])
def test_importe_invalido_va_a_revision_con_su_motivo(total, viaje_aprobado):
    g = {"comercio": "Sonda de importes", "fecha": viaje_aprobado["ida"], "total": total, "moneda": "USD", "confianza": 1}
    r = validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)
    assert r["estado"] == "revision" and "importe_invalido" in r["motivos"]
    assert g["total"] is total   # la lectura original no se toca: es lo que se guarda en `extraido`


def test_componente_negativo_es_importe_invalido(viaje_aprobado):
    g = {"comercio": "Sonda componentes", "fecha": viaje_aprobado["ida"], "total": 10, "subtotal": 12, "propina": -2,
         "moneda": "USD", "confianza": 1}
    assert "importe_invalido" in validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)["motivos"]


def test_dinero_rechaza_lo_que_no_es_un_importe():
    for malo in (None, True, "abc", float("nan"), float("-inf"), "1e13"):
        with pytest.raises(ValueError):
            dinero.decimal(malo)
    for malo in (0, "0.004", -1):
        with pytest.raises(ValueError):
            dinero.decimal(malo, positivo=True)
    assert str(dinero.decimal("10.005")) == "10.01" and str(dinero.decimal(0)) == "0.00"


def test_fecha_imposible_va_a_revision(viaje_aprobado):
    g = {"comercio": "Fecha imposible", "fecha": "2026-02-31", "total": 10, "moneda": "USD", "confianza": 1}
    r = validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)
    assert r["estado"] == "revision" and "fecha_invalida" in r["motivos"]


def test_fecha_futura_se_avisa():
    futura = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    hoy = datetime.now(UTC).date().isoformat()
    g = {"comercio": "Sonda futura", "fecha": futura, "total": 12.5, "moneda": "USD", "confianza": 1, "categoria": "otros"}
    assert "fecha_futura" in validacion.revisar(g, {"id": 1})["motivos"] and validacion.MOTIVOS["fecha_futura"]
    assert "fecha_futura" not in validacion.revisar({**g, "fecha": hoy}, {"id": 1})["motivos"]


def test_fecha_futura_no_bloquea_por_ahora(viaje_aprobado):
    """Decisión de la usuaria: mientras los recibos y viajes de demostración sean de diciembre, la fecha futura solo avisa."""
    if viaje_aprobado["ida"] <= datetime.now(UTC).date().isoformat():
        pytest.skip("El viaje de prueba ya no está en el futuro")
    g = {"comercio": "Sonda futura en viaje", "fecha": viaje_aprobado["ida"], "total": 12.5, "moneda": "USD",
         "confianza": 1, "categoria": "otros"}
    r = validacion.revisar(g, {"id": 1}, viaje=viaje_aprobado)
    assert "fecha_futura" in r["motivos"] and r["estado"] == "aprobado_auto"


def test_duplicado_exacto_compara_la_moneda():
    gid = db.insertar("gastos", comercio="Café Moneda", fecha="2026-10-01", total=50, moneda="USD", estado="aprobado")
    try:
        base = {"comercio": "café moneda", "fecha": "2026-10-01", "total": 50, "confianza": 1}
        assert "duplicado" in validacion.revisar({**base, "moneda": "USD"}, None)["motivos"]
        otra = validacion.revisar({**base, "moneda": "EUR"}, None)["motivos"]
        assert "duplicado" not in otra and "duplicado_aproximado" not in otra
    finally:
        _sin_rastro(gid)


def test_dos_gastos_sin_moneda_del_mismo_comercio_dia_e_importe_son_duplicado():
    gid = db.insertar("gastos", comercio="Peaje sin moneda", fecha="2026-10-02", total=7, moneda=None, estado="revision")
    try:
        r = validacion.revisar({"comercio": "Peaje sin moneda", "fecha": "2026-10-02", "total": 7, "moneda": None,
                                "confianza": 1}, None)
        assert "duplicado" in r["motivos"]
    finally:
        _sin_rastro(gid)


def test_la_tolerancia_del_diez_por_ciento_se_conserva(nuevo_viaje):
    v = nuevo_viaje(proyecto_id=2)
    db.actualizar("viajes", v["id"], presupuesto_usd=100)
    v = {**v, "presupuesto_usd": 100}
    gid = db.insertar("gastos", viaje_id=v["id"], comercio="Base tolerancia", fecha=v["ida"], total=80, moneda="USD",
                      total_usd=80, estado="aprobado")
    try:
        g = {"comercio": "Sonda tolerancia", "fecha": v["ida"], "moneda": "USD", "confianza": 1, "categoria": "otros"}
        assert "presupuesto_superado" not in validacion.revisar({**g, "total": 30}, {"id": 1}, viaje=v)["motivos"]   # 110
        assert "presupuesto_superado" in validacion.revisar({**g, "total": 30.01}, {"id": 1}, viaje=v)["motivos"]
    finally:
        _sin_rastro(gid)
        db.actualizar("viajes", v["id"], estado="rechazado")


def test_la_api_no_publica_importes_no_finitos():
    from app.servicios import consultas
    assert consultas.dinero(float("nan")) is None and consultas.dinero(float("inf")) is None
    assert consultas.dinero(54) == "54.00"


# ---------- transacción real ----------
def test_transaccion_revierte_todas_las_escrituras():
    ids = []
    with pytest.raises(RuntimeError), db.transaccion():
        ids.append(db.insertar("proyectos", nombre="No debe quedar"))
        ids.append(db.insertar("proyectos", nombre="Tampoco"))
        db.actualizar("proyectos", ids[0], ciudad="Ninguna")
        raise RuntimeError("caída controlada")
    assert ids and all(db.uno("select id from proyectos where id=:i", i=i) is None for i in ids)


def test_transaccion_confirma_y_la_anidada_participa_en_la_exterior():
    with db.transaccion() as c:
        pid = db.insertar("proyectos", nombre="Confirmado en transacción")
        with db.transaccion() as interna:
            assert interna is c
            db.actualizar("proyectos", pid, ciudad="Bogotá")
    assert db.uno("select ciudad from proyectos where id=:i", i=pid)["ciudad"] == "Bogotá"
    with pytest.raises(RuntimeError), db.transaccion():
        db.actualizar("proyectos", pid, ciudad="Revertida")
        with db.transaccion():
            db.actualizar("proyectos", pid, nombre="Revertido")
        raise RuntimeError("caída después de la anidada")
    fila = db.uno("select nombre, ciudad from proyectos where id=:i", i=pid)
    assert fila == {"nombre": "Confirmado en transacción", "ciudad": "Bogotá"}
    db.ejecutar("delete from proyectos where id=:i", i=pid)


def test_un_error_atrapado_dentro_usa_punto_de_guardado():
    from sqlalchemy.exc import IntegrityError
    with db.transaccion() as c:
        pid = db.insertar("proyectos", nombre="Sigue tras el error")
        with pytest.raises(IntegrityError), c.begin_nested():
            db.insertar("cargos", nombre="Pilotaje de dron")   # nombre único que ya existe
        db.actualizar("proyectos", pid, ciudad="Lisboa")
    assert db.uno("select ciudad from proyectos where id=:i", i=pid)["ciudad"] == "Lisboa"
    db.ejecutar("delete from proyectos where id=:i", i=pid)


def test_bloquear_viaje_devuelve_la_fila_vigente(viaje_aprobado):
    with db.transaccion() as c:
        fila = db.bloquear_viaje(c, viaje_aprobado["id"])
        assert fila["id"] == viaje_aprobado["id"] and fila["estado"] == "aprobado"
        assert db.bloquear_viaje(c, None) is None


def test_una_segunda_transaccion_espera_a_la_primera():
    """En SQLite la transacción toma el cerrojo de escritura al empezar: la segunda lee lo que confirmó la primera."""
    import threading
    import time
    dentro, vista = threading.Event(), {}

    def primera():
        with db.transaccion():
            pid = db.insertar("proyectos", nombre="Primera transacción")
            dentro.set()
            time.sleep(0.3)
            db.actualizar("proyectos", pid, ciudad="Confirmada")
        vista["pid"] = pid

    hilo = threading.Thread(target=primera)
    hilo.start()
    assert dentro.wait(5)
    with db.transaccion():
        vista["fila"] = db.uno("select ciudad from proyectos where nombre='Primera transacción'")
    hilo.join(5)
    assert vista["fila"] == {"ciudad": "Confirmada"}
    db.ejecutar("delete from proyectos where id=:i", i=vista["pid"])


# ---------- bloqueo al registrar, al asignar viaje y al aprobar ----------
def _viaje_con_tope(nuevo_viaje, margen: float) -> dict:
    """Un viaje propio de la prueba cuyo tope (presupuesto más la tolerancia del 10 %) deja `margen` USD libres.

    Va al proyecto 2: el tablero del proyecto 1 se compara en otra prueba con el detalle del presupuesto.
    """
    from app.servicios import viajes
    v = nuevo_viaje(proyecto_id=2)
    db.actualizar("viajes", v["id"], presupuesto_usd=round((viajes.gastado(v["id"]) + margen) / 1.10, 2))
    return viajes.uno(v["id"])


def _gasto_en(v: dict, comercio: str, total: float, estado: str = "revision", **extra) -> int:
    return db.insertar("gastos", **{"viaje_id": v["id"], "proyecto_id": v["proyecto_id"], "viajero_id": v["viajero_id"],
                                    "usuario_id": v["usuario_id"], "comercio": comercio, "fecha": v["ida"], "categoria": "otros",
                                    "total": total, "moneda": "USD", "confianza": 1.0, "estado": estado, **extra})


def test_registrar_valida_con_el_viaje_releido(nuevo_viaje, ejemplos):
    """Si el viaje se cerró mientras se leía el recibo, cuenta lo que dice la base, no la copia de antes."""
    from app.servicios import gastos
    v = nuevo_viaje()
    db.actualizar("viajes", v["id"], estado="cerrado")
    contenido = (ejemplos / "recibo_gasolina.png").read_bytes()
    gid = gastos.registrar(contenido, "r.png", "web", {"id": v["usuario_id"]}, v)   # `v` todavía dice «aprobado»
    g = db.uno("select estado, motivos from gastos where id=:i", i=gid)
    assert g["estado"] == "revision" and "viaje_cerrado" in db.de_json(g["motivos"])


def test_asignar_viaje_no_toca_un_gasto_que_se_sigue_leyendo(nuevo_viaje):
    from app.servicios import gastos
    v = nuevo_viaje()
    gid = _gasto_en(v, "Sonda procesando", 10, estado="procesando", viaje_id=None)
    with pytest.raises(ValueError, match="leyendo"):
        gastos.asignar_viaje(gid, v)
    assert db.uno("select viaje_id from gastos where id=:i", i=gid)["viaje_id"] is None
    _sin_rastro(gid)


def test_un_gasto_aprobado_no_se_mueve_a_un_viaje_que_no_lo_admite(nuevo_viaje):
    from app.servicios import gastos
    origen, destino = nuevo_viaje(), _viaje_con_tope(nuevo_viaje, 20)
    gid = _gasto_en(origen, "Sonda aprobada", 50, estado="aprobado", total_usd=50)
    with pytest.raises(ValueError, match="no admite"):
        gastos.asignar_viaje(gid, destino)
    assert db.uno("select viaje_id from gastos where id=:i", i=gid)["viaje_id"] == origen["id"]
    _sin_rastro(gid)


def test_telegram_responde_cuando_no_se_puede_asignar_el_viaje(anonimo, monkeypatch, nuevo_viaje):
    from app import config
    from app.servicios import telegram
    enviados = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", "secreto-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: enviados.append((metodo, d)) or {})
    v = nuevo_viaje()
    db.actualizar("usuarios", v["usuario_id"], telegram_chat_id=880001)
    gid = _gasto_en(v, "Sonda Telegram", 10, estado="procesando", viaje_id=None)
    try:
        r = anonimo.post("/telegram/webhook", headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-de-pruebas"},
                         json={"update_id": 880001, "callback_query": {"id": "q", "data": f"v:{gid}:{v['id']}",
                                                                       "message": {"chat": {"id": 880001}}}})
        assert r.status_code == 200 and r.json()["estado"] == "rechazado"
        texto = next(d["text"] for m, d in reversed(enviados) if m == "sendMessage")
        assert f"#{gid}" in texto and v["codigo"] in texto and "leyendo" in texto
    finally:
        db.actualizar("usuarios", v["usuario_id"], telegram_chat_id=None)
        _sin_rastro(gid)


def test_dos_aprobaciones_a_la_vez_no_gastan_el_mismo_saldo(cliente, nuevo_viaje, monkeypatch):
    """Las dos leen lo gastado antes de que la otra escriba, salvo que la aprobación bloquee el viaje."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.servicios import viajes
    v = _viaje_con_tope(nuevo_viaje, 100)
    ids = [_gasto_en(v, f"Sonda saldo {n}", 70) for n in range(2)]
    barrera, leer = threading.Barrier(2), viajes.gastado

    def gastado_lento(*a, **k):
        valor = leer(*a, **k)
        try:
            barrera.wait(timeout=1)   # sin bloqueo, las dos lecturas se cruzan aquí
        except threading.BrokenBarrierError:
            pass
        return valor

    monkeypatch.setattr(viajes, "gastado", gastado_lento)

    def aprobar(gid):
        return cliente.post(f"/gastos/{gid}", data={"accion": "aprobar", "comercio": f"Sonda saldo {ids.index(gid)}",
                                                    "fecha": v["ida"], "categoria": "otros", "total": "70", "moneda": "USD"},
                            follow_redirects=False).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            assert list(ejecutor.map(aprobar, ids)) == [303, 303]
        estados = sorted(db.uno("select estado from gastos where id=:i", i=i)["estado"] for i in ids)
        assert estados == ["aprobado", "revision"]
    finally:
        _sin_rastro(*ids)
