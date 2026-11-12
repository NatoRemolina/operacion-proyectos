"""Integridad del flujo de gastos: importes, duplicados, transacciones, envíos repetidos y revisión versionada."""
from datetime import UTC, datetime, timedelta

import pytest

from app import config, db
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


@pytest.mark.skipif(not config.ES_SQLITE, reason="en PostgreSQL lo cubre test_concurrencia_de_presupuesto_y_envios_en_postgres")
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
                                    "total": total, "moneda": "USD", "confianza": 1.0, "estado": estado, "creado": db.ahora(), **extra})


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


# ---------- envíos idempotentes ----------
def _csrf(c) -> dict:
    from app import api_v1
    from app.servicios import acceso
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _foto(ejemplos, marca: str) -> bytes:
    """Una foto única para cada prueba: misma cabecera PNG, cola distinta."""
    return (ejemplos / "recibo_lisboa.png").read_bytes() + marca.encode()


def _api_enviar(c, contenido: bytes, clave: str | None, **datos):
    cabeceras = {**_csrf(c), **({"Idempotency-Key": clave} if clave else {})}
    return c.post("/api/v1/gastos", headers=cabeceras, data=datos, files={"archivo": ("recibo.png", contenido, "image/png")})


def test_reintento_con_la_misma_clave_devuelve_el_mismo_gasto(piloto, ejemplos):
    foto = _foto(ejemplos, "reintento")
    a, b = _api_enviar(piloto, foto, "clave-reintento"), _api_enviar(piloto, foto, "clave-reintento")
    assert (a.status_code, b.status_code) == (201, 200) and a.json()["id"] == b.json()["id"]
    otro = _api_enviar(piloto, _foto(ejemplos, "otro archivo"), "clave-reintento")
    assert otro.status_code == 409 and otro.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    sin_clave = [_api_enviar(piloto, foto, None).json()["id"] for _ in range(2)]
    assert len(set(sin_clave)) == 2   # sin cabecera, cada envío es un gasto nuevo, como antes


def test_la_misma_clave_con_otro_viaje_es_otro_envio(piloto, ejemplos, viaje_aprobado):
    foto = _foto(ejemplos, "otro viaje")
    assert _api_enviar(piloto, foto, "clave-viaje").status_code == 201
    r = _api_enviar(piloto, foto, "clave-viaje", viaje_id=str(viaje_aprobado["id"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_la_clave_es_de_cada_persona(piloto, piloto2, ejemplos):
    foto = _foto(ejemplos, "dos personas")
    a, b = _api_enviar(piloto, foto, "clave-compartida"), _api_enviar(piloto2, foto, "clave-compartida")
    assert (a.status_code, b.status_code) == (201, 201) and a.json()["id"] != b.json()["id"]


def test_un_reintento_durante_la_lectura_recibe_el_mismo_gasto(piloto, ejemplos, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.servicios import extraccion
    leyendo, seguir, extraer = threading.Event(), threading.Event(), extraccion.extraer

    def lenta(*a, **k):
        leyendo.set()
        assert seguir.wait(5)
        return extraer(*a, **k)

    monkeypatch.setattr(extraccion, "extraer", lenta)
    foto = _foto(ejemplos, "concurrente")
    with ThreadPoolExecutor(max_workers=1) as ejecutor:
        primero = ejecutor.submit(_api_enviar, piloto, foto, "clave-concurrente")
        assert leyendo.wait(5)
        try:
            segundo = _api_enviar(piloto, foto, "clave-concurrente")
        finally:
            seguir.set()
        primero = primero.result(timeout=10)
    assert (primero.status_code, segundo.status_code) == (201, 200)
    assert primero.json()["id"] == segundo.json()["id"] and segundo.json()["estado"] == "procesando"
    assert db.uno("select estado from gastos where id=:i", i=primero.json()["id"])["estado"] != "procesando"


def test_si_la_lectura_se_cae_el_gasto_queda_en_revision_y_la_concesion_se_libera(piloto, ejemplos, monkeypatch):
    from app.servicios import extraccion

    def rota(*a, **k):
        raise ConnectionError("proveedor caído")

    monkeypatch.setattr(extraccion, "extraer", rota)
    foto = _foto(ejemplos, "lectura caída")
    r = _api_enviar(piloto, foto, "clave-caida")
    assert r.status_code == 201 and r.json()["estado"] == "revision" and "lectura_fallida" in r.json()["motivos"]
    envio = db.uno("select estado from envios_soporte where clave='clave-caida'")
    assert envio["estado"] == "completado"
    otra = _api_enviar(piloto, foto, "clave-caida")
    assert otra.status_code == 200 and otra.json()["id"] == r.json()["id"]
    # Sin clave también: nunca queda un gasto «procesando» para siempre
    assert _api_enviar(piloto, _foto(ejemplos, "lectura caída 2"), None).json()["estado"] == "revision"


def test_un_envio_vencido_se_recupera_y_el_trabajador_anterior_no_escribe():
    from app.servicios import envios
    op, repetido = envios.reclamar(1, "clave-vencida", "huella-1")
    assert not repetido
    gid = db.insertar("gastos", estado="procesando", usuario_id=1)
    try:
        with db.transaccion():
            envios.enlazar(op, gid)
        db.actualizar("envios_soporte", op["id"], expira="2000-01-01 00:00:00")
        recuperado, repetido = envios.reclamar(1, "clave-vencida", "huella-1")
        assert repetido and recuperado["gasto_id"] == gid
        g = db.uno("select estado, motivos from gastos where id=:i", i=gid)
        assert g["estado"] == "revision" and "lectura_fallida" in db.de_json(g["motivos"])
        with pytest.raises(envios.EnvioEnCurso), db.transaccion():
            envios.comprobar(op)
    finally:
        db.ejecutar("delete from envios_soporte where id=:i", i=op["id"])
        _sin_rastro(gid)


def test_un_envio_en_curso_sin_gasto_responde_que_siga_esperando():
    from app.servicios import envios
    op, _ = envios.reclamar(1, "clave-en-curso", "huella")
    try:
        with pytest.raises(envios.EnvioEnCurso):
            envios.reclamar(1, "clave-en-curso", "huella")
        with pytest.raises(envios.ConflictoEnvio):
            envios.reclamar(1, "clave-en-curso", "otra huella")
        envios.terminar(op, "fallido")
        de_nuevo, repetido = envios.reclamar(1, "clave-en-curso", "huella")   # el que falló sin gasto se puede retomar
        assert not repetido and de_nuevo["propietario"] != op["propietario"]
    finally:
        db.ejecutar("delete from envios_soporte where id=:i", i=op["id"])


def test_la_pagina_de_carga_envia_la_clave_y_el_servidor_la_respeta(cliente, ejemplos, viaje_aprobado):
    assert "Idempotency-Key" in cliente.get("/gastos/cargar").text
    datos = {"viaje_id": viaje_aprobado["id"], "canal": "web"}
    foto = _foto(ejemplos, "web")

    def subir(contenido, clave):
        return cliente.post("/gastos/cargar", data=datos, files={"archivos": ("r.png", contenido, "image/png")},
                            headers={"X-Envio": "pagina", "Idempotency-Key": clave})

    a, b = subir(foto, "clave-web"), subir(foto, "clave-web")
    assert a.status_code == b.status_code == 200 and a.json()["gastos"] == b.json()["gastos"]
    c = subir(_foto(ejemplos, "web distinto"), "clave-web")
    assert c.status_code == 409 and c.json()["errores"]


# ---------- revisión versionada ----------
def _version(gid) -> int:
    return db.uno("select version from gastos where id=:i", i=gid)["version"]


def test_la_revision_web_exige_la_version_que_se_vio(cliente, nuevo_viaje):
    v = _viaje_con_tope(nuevo_viaje, 500)
    gid = _gasto_en(v, "Sonda versión web", 20)
    try:
        pagina = cliente.get(f"/gastos/{gid}").text
        assert f'name="version" value="{_version(gid)}"' in pagina
        campos = {"comercio": "Sonda versión web", "fecha": v["ida"], "categoria": "otros", "total": "20", "moneda": "USD"}
        vista = _version(gid)
        db.ejecutar("update gastos set version=version+1 where id=:i", i=gid)   # otra persona lo cambió mientras tanto
        r = cliente.post(f"/gastos/{gid}", data={**campos, "accion": "aprobar", "version": vista}, follow_redirects=False)
        assert r.status_code == 303 and db.uno("select estado from gastos where id=:i", i=gid)["estado"] == "revision"
        assert "Otra persona cambió" in cliente.get(r.headers["location"]).text
        r = cliente.post(f"/gastos/{gid}", data={**campos, "accion": "aprobar", "version": _version(gid)}, follow_redirects=False)
        assert db.uno("select estado from gastos where id=:i", i=gid)["estado"] == "aprobado" and _version(gid) == vista + 2
    finally:
        _sin_rastro(gid)


def test_rechazar_exige_motivo_lo_guarda_y_avisa_por_telegram(cliente, nuevo_viaje, monkeypatch):
    from app.servicios import telegram
    avisos = []
    v = nuevo_viaje()
    monkeypatch.setattr(telegram, "avisar", lambda uid, texto: avisos.append((uid, texto)))
    gid = _gasto_en(v, "Sonda rechazo", 20)
    try:
        r = cliente.post(f"/gastos/{gid}", data={"accion": "rechazar", "motivo_rechazo": "no", "version": 0}, follow_redirects=False)
        assert db.uno("select estado from gastos where id=:i", i=gid)["estado"] == "revision" and not avisos
        assert "motivo" in cliente.get(r.headers["location"]).text
        alertas = db.uno("select alertas from gastos where id=:i", i=gid)["alertas"]
        assert "motivo" not in (alertas or "")   # el aviso al revisor no se guarda como alerta del gasto
        cliente.post(f"/gastos/{gid}", data={"accion": "rechazar", "motivo_rechazo": "Recibo de otro viaje", "version": 0})
        g = db.uno("select estado, motivo_rechazo, revisado_por, version from gastos where id=:i", i=gid)
        assert g["estado"] == "rechazado" and g["motivo_rechazo"] == "Recibo de otro viaje" and g["version"] == 1
        assert avisos == [(v["usuario_id"], avisos[0][1])] and "Recibo de otro viaje" in avisos[0][1] and f"#{gid}" in avisos[0][1]
        evento = db.uno("select * from eventos where entidad='gasto' and entidad_id=:i and paso='rechazado en revisión'", i=gid)
        assert "Recibo de otro viaje" in evento["detalle"] and evento["fuente"]
        assert "Recibo de otro viaje" in cliente.get(f"/gastos/{gid}").text
    finally:
        _sin_rastro(gid)


def test_excepcion_sin_motivo_no_se_guarda_como_alerta(cliente, nuevo_viaje):
    v = nuevo_viaje()
    base = _gasto_en(v, "Sonda excepción", 20, estado="aprobado", total_usd=20)
    gid = _gasto_en(v, "Sonda excepción", 20)   # duplicado exacto: las reglas no lo dejan pasar
    try:
        campos = {"comercio": "Sonda excepción", "fecha": v["ida"], "categoria": "otros", "total": "20", "moneda": "USD"}
        cliente.post(f"/gastos/{gid}", data={**campos, "accion": "excepcion", "motivo_excepcion": "corto", "version": 0})
        g = db.uno("select estado, alertas, version from gastos where id=:i", i=gid)
        assert g["estado"] == "revision" and g["version"] == 0 and "motivo" not in (g["alertas"] or "")
    finally:
        _sin_rastro(gid, base)


def _revisar_api(c, gid, **cuerpo):
    return c.post(f"/api/v1/gastos/{gid}/revision", json=cuerpo, headers=_csrf(c))


def test_revision_por_la_api_con_version_csrf_y_permisos(cliente, piloto, nuevo_viaje, monkeypatch):
    from app.servicios import telegram
    avisos = []
    v = nuevo_viaje()
    monkeypatch.setattr(telegram, "avisar", lambda uid, texto: avisos.append((uid, texto)))
    gid = _gasto_en(v, "Sonda API", 20)
    try:
        datos = {"version": 0, "accion": "rechazar", "motivo": "No corresponde al viaje"}
        assert piloto.get(f"/api/v1/gastos/{gid}").json()["version"] == 0
        assert _revisar_api(piloto, gid, **datos).status_code == 403
        assert cliente.post(f"/api/v1/gastos/{gid}/revision", json=datos).status_code == 403   # sin token CSRF
        r = _revisar_api(cliente, gid, **{**datos, "motivo": "no"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
        r = _revisar_api(cliente, gid, **datos)
        assert r.status_code == 200 and r.json()["estado"] == "rechazado" and r.json()["version"] == 1
        assert r.json()["motivo_rechazo"] == "No corresponde al viaje" and avisos
        r = _revisar_api(cliente, gid, **datos)
        assert r.status_code == 409 and r.json()["error"]["code"] == "EDIT_CONFLICT"
        assert _revisar_api(cliente, 99999999, **datos).status_code == 404
    finally:
        _sin_rastro(gid)


def test_la_api_aprueba_y_corrige_con_las_mismas_reglas(cliente, nuevo_viaje):
    v = _viaje_con_tope(nuevo_viaje, 500)
    gid = _gasto_en(v, "Sonda API aprobar", 20)
    try:
        r = _revisar_api(cliente, gid, version=0, accion="aprobar", total="abc")
        assert r.status_code == 422
        r = _revisar_api(cliente, gid, version=0, accion="aprobar", total="-5")
        assert r.status_code == 200 and r.json()["estado"] == "revision" and "importe_invalido" in r.json()["motivos"]
        r = _revisar_api(cliente, gid, version=1, accion="aprobar", total="25.50")
        assert r.status_code == 200 and r.json()["estado"] == "aprobado" and r.json()["total"] == "25.50"
    finally:
        _sin_rastro(gid)


def test_un_admin_no_aprueba_su_propio_gasto_por_la_api(cliente):
    yo = db.uno("select * from usuarios where correo='admin@demo.local'")
    gid = db.insertar("gastos", usuario_id=yo["id"], viajero_id=yo["viajero_id"], comercio="Sonda propia", fecha="2026-10-05",
                      total=12, moneda="USD", confianza=1.0, estado="revision", creado=db.ahora())
    try:
        for accion, extra in (("aprobar", {}), ("rechazar", {"motivo": "Me lo rechazo yo"}), ("excepcion", {"motivo": "Excepción propia"})):
            r = _revisar_api(cliente, gid, version=0, accion=accion, **extra)
            assert r.status_code == 403 and "Nadie revisa sus propios gastos" in r.json()["error"]["message"]
        assert db.uno("select estado, version from gastos where id=:i", i=gid) == {"estado": "revision", "version": 0}
        intentos = db.todos("select id from eventos where entidad='gasto' and entidad_id=:i and paso='autoaprobación impedida'", i=gid)
        assert len(intentos) == 3
    finally:
        _sin_rastro(gid)


def test_dos_revisiones_por_la_api_no_gastan_el_mismo_saldo(cliente, nuevo_viaje):
    from concurrent.futures import ThreadPoolExecutor
    v = _viaje_con_tope(nuevo_viaje, 100)
    ids = [_gasto_en(v, f"Sonda API saldo {n}", 70) for n in range(2)]
    try:
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            respuestas = list(ejecutor.map(lambda i: _revisar_api(cliente, i, version=0, accion="aprobar"), ids))
        assert sorted(r.json()["estado"] for r in respuestas) == ["aprobado", "revision"]
    finally:
        _sin_rastro(*ids)


# ---------- migración ----------
def _columna(tabla: str, nombre: str) -> dict:
    return next(c for c in db.todos(f"pragma table_info({tabla})") if c["name"] == nombre)


def _como_base_anterior(tabla: str, columna: str):
    """Deja la columna como la añade `crear_tablas` a una base existente: solo con su tipo, sin NOT NULL ni DEFAULT."""
    from datos import migracion
    sql, patron = migracion.definicion_sqlite(tabla, columna)
    migracion.rehacer_tabla_sqlite(tabla, patron.sub(lambda m: m.group(1), sql, count=1))


SOLO_SQLITE = pytest.mark.skipif(not config.ES_SQLITE, reason="comprueba el comportamiento propio de SQLite")


@SOLO_SQLITE
def test_la_migracion_alinea_version_con_el_modelo_sin_perder_datos():
    """Una base anterior recibe `version` de `crear_tablas` sin NOT NULL; la migración la deja como dice el modelo."""
    from app.servicios import revision
    from datos import migracion
    assert not revision.db.gastos.c.version.nullable
    _como_base_anterior("gastos", "version")
    assert _columna("gastos", "version")["notnull"] == 0
    gid = db.insertar("gastos", comercio="Sonda migración", estado="revision", total=9.5)
    db.ejecutar("update gastos set version=null where id=:i", i=gid)
    antes = db.uno("select count(*) n, coalesce(sum(total),0) t from gastos")
    hechos = migracion.migrar()
    assert hechos["columnas_alineadas"] == ["gastos.version"]
    col = _columna("gastos", "version")
    assert col["notnull"] == 1 and col["dflt_value"] in ("0", "'0'")
    assert db.uno("select version from gastos where id=:i", i=gid)["version"] == 0
    assert db.uno("select count(*) n, coalesce(sum(total),0) t from gastos") == antes
    assert not db.todos("pragma foreign_key_check")
    indices = {i["name"] for i in db.todos("pragma index_list(gastos)")}
    assert {"ix_gastos_viaje", "ix_gastos_proyecto", "ix_gastos_usuario"} <= indices
    assert migracion.migrar()["columnas_alineadas"] == []   # se puede repetir
    assert migracion.columnas_desalineadas() == []
    _sin_rastro(gid)


@SOLO_SQLITE
def test_la_tabla_de_envios_existe_con_sus_restricciones():
    columnas = {c["name"]: c for c in db.todos("pragma table_info(envios_soporte)")}
    assert {n for n, c in columnas.items() if c["notnull"]} >= {"usuario_id", "clave", "huella", "estado"}
    unicos = [i for i in db.todos("pragma index_list(envios_soporte)") if i["unique"]]
    assert any({c["name"] for c in db.todos(f"pragma index_info('{i['name']}')")} == {"usuario_id", "clave"} for i in unicos)


# ---------- comprobación de la base (solo lectura) ----------
PG_LOCAL = "postgresql://operacion:operacion-local@127.0.0.1:5433/operacion"


def _pg_local_responde() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 5433), timeout=1):
            return True
    except OSError:
        return False


def _comprobar(capsys, url: str | None) -> tuple[int, str]:
    from datos import comprobar_supabase
    codigo = comprobar_supabase.main({"DATABASE_URL": url} if url else {})
    return codigo, capsys.readouterr().out


def test_comprobar_no_conecta_sin_lo_necesario(capsys):
    assert _comprobar(capsys, None)[0] == 2
    assert _comprobar(capsys, "sqlite:///x.db")[0] == 2
    codigo, salida = _comprobar(capsys, "postgresql://u:clave-secreta@db.ejemplo.invalid:5432/x?sslmode=disable")
    assert codigo == 2 and "SSL" in salida and "clave-secreta" not in salida


def test_comprobar_no_imprime_la_conexion_si_falla(capsys):
    codigo, salida = _comprobar(capsys, "postgresql://u:clave-secreta@127.0.0.1:1/x")
    assert codigo == 1 and "clave-secreta" not in salida and "127.0.0.1" not in salida
    assert '"conexion": "no verificada"' in salida


@pytest.mark.skipif(not _pg_local_responde(), reason="PostgreSQL local (127.0.0.1:5433) no responde")
def test_comprobar_contra_el_postgres_local(capsys):
    import json
    codigo, salida = _comprobar(capsys, PG_LOCAL)
    informe = json.loads(salida)
    assert informe["conexion"] == "correcta" and informe["escritura_temporal"] == "correcta" and informe["rollback_verificado"]
    assert {"tablas_sin_seguridad_por_filas", "permisos_publicos", "tablas", "columnas"} <= set(informe)
    assert "operacion-local" not in salida
    assert codigo in (0, 1)


# ---------- concurrencia contra PostgreSQL de verdad ----------
_GUION_PG = r'''
import json, threading
from concurrent.futures import ThreadPoolExecutor

from app import config, db
from app.servicios import envios, revision, viajes

assert not config.ES_SQLITE
db.crear_tablas()
ahora = db.ahora()
proyecto = db.insertar("proyectos", nombre="Prueba concurrente")
viajero = db.insertar("viajeros", nombre="Viajera de prueba")
colaboradora = db.insertar("usuarios", correo="colaboradora@prueba.local", nombre="Colaboradora", rol="colaborador",
                           activo=1, viajero_id=viajero, creado=ahora)
admin = {"id": db.insertar("usuarios", correo="admin@prueba.local", nombre="Admin", rol="admin", activo=1, creado=ahora),
         "nombre": "Admin", "rol": "admin"}
# Presupuesto 90,91 + 10 % de tolerancia = tope de 100 USD: cabe un gasto de 70, no dos
vid = db.insertar("viajes", proyecto_id=proyecto, usuario_id=colaboradora, viajero_id=viajero, ida="2026-12-08",
                  regreso="2026-12-11", presupuesto_usd=90.91, estado="aprobado", creado=ahora)
ids = [db.insertar("gastos", viaje_id=vid, proyecto_id=proyecto, viajero_id=viajero, usuario_id=colaboradora,
                   comercio=f"Sonda concurrente {n}", fecha="2026-12-09", categoria="otros", total=70, moneda="USD",
                   confianza=1.0, estado="revision", creado=ahora) for n in range(2)]

cruce, leer = threading.Barrier(2), viajes.gastado
def gastado_lento(*a, **k):
    valor = leer(*a, **k)
    try:
        cruce.wait(timeout=1)   # sin bloqueo del viaje, las dos lecturas se cruzarían aquí
    except threading.BrokenBarrierError:
        pass
    return valor
viajes.gastado = gastado_lento

salida = threading.Barrier(2)
def aprobar(gid):
    salida.wait(5)
    return revision.guardar(gid, admin, 0, "aprobar")["estado"]
with ThreadPoolExecutor(max_workers=2) as ejecutor:
    respuestas = sorted(ejecutor.map(aprobar, ids))
guardados = sorted(db.uno("select estado from gastos where id=:i", i=i)["estado"] for i in ids)

def reclamar(_):
    salida.wait(5)
    try:
        return "nuevo" if not envios.reclamar(colaboradora, "clave-pg", "huella")[1] else "repetido"
    except envios.EnvioEnCurso:
        return "en_curso"
with ThreadPoolExecutor(max_workers=2) as ejecutor:
    reclamos = sorted(ejecutor.map(reclamar, range(2)))

try:
    with db.transaccion():
        revertido = db.insertar("proyectos", nombre="No debe quedar")
        raise RuntimeError
except RuntimeError:
    pass
print(json.dumps({"respuestas": respuestas, "guardados": guardados, "reclamos": reclamos,
                  "revertido": db.uno("select id from proyectos where id=:i", i=revertido) is None}))
'''


@pytest.mark.skipif(not _pg_local_responde(), reason="PostgreSQL local (127.0.0.1:5433) no responde")
def test_concurrencia_de_presupuesto_y_envios_en_postgres():
    """Dos aprobaciones a la vez contra un saldo que alcanza para una, en PostgreSQL y en un esquema propio que se borra."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from sqlalchemy import create_engine, text
    esquema = f"prueba_integridad_{os.getpid()}"
    crudo = create_engine(PG_LOCAL.replace("postgresql://", "postgresql+psycopg://"), isolation_level="AUTOCOMMIT")
    with crudo.connect() as c:
        c.execute(text(f"drop schema if exists {esquema} cascade"))
        c.execute(text(f"create schema {esquema}"))
    try:
        entorno = {**os.environ, "ENTORNO": "local", "DATABASE_URL": f"{PG_LOCAL}?options=-csearch_path%3D{esquema}"}
        r = subprocess.run([sys.executable, "-c", _GUION_PG], cwd=Path(__file__).resolve().parent.parent, env=entorno,  # noqa: S603  guion fijo de esta prueba
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stderr[-2000:]
        resultado = json.loads(r.stdout.strip().splitlines()[-1])
        assert resultado["respuestas"] == ["aprobado", "revision"] and resultado["guardados"] == ["aprobado", "revision"]
        assert resultado["reclamos"] == ["en_curso", "nuevo"] and resultado["revertido"]
    finally:
        with crudo.connect() as c:
            c.execute(text(f"drop schema if exists {esquema} cascade"))
        crudo.dispose()


# ---------- Telegram: una entrega que falla no queda como procesada ----------
def test_telegram_una_entrega_que_falla_queda_en_error_y_se_puede_reintentar(anonimo, monkeypatch):
    from app import config
    from app.servicios import telegram
    enviados = []
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", "secreto-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: enviados.append((metodo, d)) or {})
    original, fallos = telegram._mensaje, []

    def a_veces_falla(m, registro):
        if not fallos:
            fallos.append(1)
            registro["_chat"] = (m.get("chat") or {}).get("id")
            raise RuntimeError("fallo inesperado")
        return original(m, registro)

    monkeypatch.setattr(telegram, "_mensaje", a_veces_falla)
    entrega = {"update_id": 880777, "message": {"chat": {"id": 880777, "type": "private"}, "text": "hola"}}

    def enviar():
        return anonimo.post("/telegram/webhook", json=entrega, headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-de-pruebas"})

    assert enviar().json()["estado"] == "error"
    assert db.uno("select estado from telegram_mensajes where update_id=880777")["estado"] == "error"
    assert any(m == "sendMessage" and "No pude" in d["text"] for m, d in enviados)   # la persona recibe respuesta
    segundo = enviar().json()["estado"]
    assert segundo not in ("error", "repetido")
    assert db.uno("select estado from telegram_mensajes where update_id=880777")["estado"] == segundo
    assert enviar().json()["estado"] == "repetido"
    assert db.uno("select count(*) n from telegram_mensajes where update_id=880777")["n"] == 1


# ---------- ronda 1 de la revisión ----------
def _hace(minutos: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S")


def test_un_gasto_atascado_en_procesando_se_puede_revisar_y_asignar(cliente, nuevo_viaje):
    from app.servicios import gastos
    v = nuevo_viaje()
    atascado = _gasto_en(v, "Sonda atascada", 20, estado="procesando", creado=_hace(60))
    reciente = _gasto_en(v, "Sonda reciente", 20, estado="procesando", creado=_hace(0))
    sin_viaje = _gasto_en(v, "Sonda atascada sin viaje", 20, estado="procesando", creado=_hace(60), viaje_id=None)
    try:
        cliente.post(f"/gastos/{atascado}", data={"accion": "rechazar", "motivo_rechazo": "Recibo ilegible", "version": 0})
        g = db.uno("select estado, motivo_rechazo from gastos where id=:i", i=atascado)
        assert g == {"estado": "rechazado", "motivo_rechazo": "Recibo ilegible"}
        r = cliente.post(f"/gastos/{reciente}", data={"accion": "rechazar", "motivo_rechazo": "Recibo ilegible", "version": 0},
                         follow_redirects=False)
        assert "leyendo" in cliente.get(r.headers["location"]).text   # el que se está leyendo de verdad sigue protegido
        assert gastos.asignar_viaje(sin_viaje, v)["viaje_id"] == v["id"]
        assert "lectura_fallida" in db.de_json(db.uno("select motivos from gastos where id=:i", i=sin_viaje)["motivos"])
    finally:
        _sin_rastro(atascado, reciente, sin_viaje)


def test_la_lectura_tardia_no_pisa_un_gasto_ya_recuperado(ejemplos, monkeypatch, viaje_aprobado):
    from app.servicios import envios, extraccion, gastos
    extraer = extraccion.extraer

    def tarda_y_otro_lo_recupera(contenido, mime, nombre, gid):
        envios.marcar_interrumpido(gid)
        db.actualizar("gastos", gid, estado="rechazado")
        return extraer(contenido, mime, nombre, gid)

    monkeypatch.setattr(extraccion, "extraer", tarda_y_otro_lo_recupera)
    gid = gastos.registrar(_foto(ejemplos, "tardía"), "r.png", "web", {"id": viaje_aprobado["usuario_id"]}, viaje_aprobado)
    assert db.uno("select estado from gastos where id=:i", i=gid)["estado"] == "rechazado"


def test_el_reintento_web_no_duplica_la_justificacion(cliente, ejemplos, viaje_aprobado):
    datos = {"viaje_id": viaje_aprobado["id"], "canal": "web", "justificacion": "Taxi del hotel al set de grabación"}
    foto = _foto(ejemplos, "justificación web")
    respuestas = [cliente.post("/gastos/cargar", data=datos, files={"archivos": ("r.png", foto, "image/png")},
                               headers={"X-Envio": "pagina", "Idempotency-Key": "clave-justificada"}) for _ in range(2)]
    gastos_ = {g for r in respuestas for g in r.json()["gastos"]}
    assert len(gastos_) == 1
    assert db.uno("select count(*) n from justificaciones where gasto_id=:g", g=gastos_.pop())["n"] == 1


def test_telegram_reprocesar_una_entrega_no_crea_otro_gasto(anonimo, monkeypatch, nuevo_viaje, ejemplos):
    from app import config
    from app.servicios import telegram
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", "secreto-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: {})
    monkeypatch.setattr(telegram, "descargar", lambda file_id: _foto(ejemplos, "telegram reproceso"))
    resumen, fallos = telegram._resumen_gasto, []

    def falla_una_vez(*a, **k):
        if not fallos:
            fallos.append(1)
            raise RuntimeError("caída después de registrar")
        return resumen(*a, **k)

    monkeypatch.setattr(telegram, "_resumen_gasto", falla_una_vez)
    v = nuevo_viaje()
    db.actualizar("usuarios", v["usuario_id"], telegram_chat_id=880555)
    entrega = {"update_id": 880555, "message": {"chat": {"id": 880555, "type": "private"},
                                                "photo": [{"file_id": "f", "file_size": 1000}]}}
    ultimo = db.uno("select coalesce(max(id),0) i from gastos")["i"]
    try:
        antes = db.uno("select count(*) n from gastos where usuario_id=:u", u=v["usuario_id"])["n"]
        for _ in range(2):
            anonimo.post("/telegram/webhook", json=entrega, headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-de-pruebas"})
        assert fallos and db.uno("select estado from telegram_mensajes where update_id=880555")["estado"] != "error"
        assert db.uno("select count(*) n from gastos where usuario_id=:u", u=v["usuario_id"])["n"] == antes + 1
    finally:
        db.actualizar("usuarios", v["usuario_id"], telegram_chat_id=None)
        # Fuera de la ventana en que el bot toma el siguiente mensaje como justificación: no interfiere con otras pruebas
        db.ejecutar("update gastos set creado=:c where id>:i and usuario_id=:u", c=_hace(24 * 60), i=ultimo, u=v["usuario_id"])


def test_un_importe_no_valido_no_llega_a_la_base(ejemplos, monkeypatch, viaje_aprobado):
    from app.servicios import extraccion, gastos
    leido = {"comercio": "Sonda NaN", "fecha": viaje_aprobado["ida"], "categoria": "otros", "subtotal": float("inf"),
             "impuesto": None, "propina": None, "total": float("nan"), "moneda": "USD", "metodo_pago": None,
             "canal_reserva": None, "ciudad": None, "confianza": 0.95, "dudas": [], "origen_dato": "en vivo", "error": None}
    monkeypatch.setattr(extraccion, "extraer", lambda *a, **k: dict(leido))
    gid = gastos.registrar(_foto(ejemplos, "nan"), "r.png", "web", {"id": viaje_aprobado["usuario_id"]}, viaje_aprobado)
    g = db.uno("select total, subtotal, estado, motivos, extraido from gastos where id=:i", i=gid)
    assert g["total"] is None and g["subtotal"] is None and g["estado"] == "revision"
    assert "importe_invalido" in db.de_json(g["motivos"])
    import json

    def no_finito(c):
        raise AssertionError(f"`extraido` guarda {c}, que no es JSON válido")
    original = json.loads(g["extraido"], parse_constant=no_finito)
    assert original["total"] is None and original["subtotal"] is None and original["comercio"] == "Sonda NaN"


def test_telegram_reprocesar_con_pie_de_foto_no_duplica_la_justificacion(anonimo, monkeypatch, nuevo_viaje, ejemplos):
    from app import config
    from app.servicios import telegram
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRETO", "secreto-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: {})
    monkeypatch.setattr(telegram, "descargar", lambda file_id: _foto(ejemplos, "telegram con pie"))
    resumen, fallos = telegram._resumen_gasto, []

    def falla_una_vez(*a, **k):   # cae después de registrar el gasto y de guardar la justificación del pie
        if not fallos:
            fallos.append(1)
            raise RuntimeError("caída después de justificar")
        return resumen(*a, **k)

    monkeypatch.setattr(telegram, "_resumen_gasto", falla_una_vez)
    v = nuevo_viaje()
    db.actualizar("usuarios", v["usuario_id"], telegram_chat_id=880666)
    entrega = {"update_id": 880666, "message": {"chat": {"id": 880666, "type": "private"}, "caption": "Taxi del aeropuerto al hotel",
                                                "photo": [{"file_id": "f", "file_size": 1000}]}}
    ultimo = db.uno("select coalesce(max(id),0) i from gastos")["i"]
    try:
        for _ in range(2):
            anonimo.post("/telegram/webhook", json=entrega, headers={"X-Telegram-Bot-Api-Secret-Token": "secreto-de-pruebas"})
        nuevos = db.todos("select id from gastos where id>:i and usuario_id=:u", i=ultimo, u=v["usuario_id"])
        assert fallos and len(nuevos) == 1
        assert db.uno("select count(*) n from justificaciones where gasto_id=:g", g=nuevos[0]["id"])["n"] == 1
    finally:
        db.actualizar("usuarios", v["usuario_id"], telegram_chat_id=None)
        db.ejecutar("update gastos set creado=:c where id>:i and usuario_id=:u", c=_hace(24 * 60), i=ultimo, u=v["usuario_id"])
