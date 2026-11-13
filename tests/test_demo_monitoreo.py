"""Preparador de la demostración del monitoreo: solo en local, idempotente y sin consultas en vivo."""
from app import config, db


def _conteos():
    return {t: db.uno(f"select count(*) n from {t}")["n"] for t in ("solicitudes", "viajes", "tramos_vuelo", "eventos")}  # noqa: S608


def test_no_escribe_fuera_de_local(cliente, monkeypatch):
    from datos import demo_monitoreo
    monkeypatch.setattr(config, "PREPARAR_BASE_LOCAL", False)
    antes = _conteos()
    r = demo_monitoreo.preparar()
    assert r["hecho"] is False and "base desechable" in r["mensaje"]
    assert _conteos() == antes
    assert demo_monitoreo.main() == 1


def test_idempotente_un_viaje_y_un_tramo(cliente, monkeypatch):
    from datos import demo_monitoreo
    monkeypatch.setattr(config, "PREPARAR_BASE_LOCAL", True)
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    primera = demo_monitoreo.preparar()
    # el tramo se consulta y queda con estado; al preparar otra vez vuelve a empezar
    db.ejecutar("update tramos_vuelo set consultas=3, estado='retrasado' where viaje_id=:v", v=primera["viaje_id"])
    segunda = demo_monitoreo.preparar()
    assert primera["hecho"] and segunda["hecho"] and segunda["creado"] is False
    assert primera["viaje_id"] == segunda["viaje_id"]
    assert db.uno("select count(*) n from solicitudes where solicitado_por=:f", f=demo_monitoreo.FUENTE)["n"] == 1
    tramos = db.todos("select * from tramos_vuelo where viaje_id=:v", v=primera["viaje_id"])
    assert len(tramos) == 1 and tramos[0]["numero"] == "IB 5634" and (tramos[0]["consultas"], tramos[0]["estado"]) == (0, "programado")
    v = db.uno("select v.*, s.llegar_antes, s.proyecto_id, u.correo from viajes v join solicitudes s on s.id=v.solicitud_id "
               "join usuarios u on u.id=v.usuario_id where v.id=:i", i=primera["viaje_id"])
    assert v["estado"] == "aprobado" and v["aprobado_por"] != v["usuario_id"] and v["correo"] == "piloto2@demo.local"
    assert db.uno("select ciudad from proyectos where id=:i", i=v["proyecto_id"])["ciudad"] == "Lisboa"
    assert v["llegar_antes"] == "2026-12-13T12:00" and v["ida"] == "2026-12-13"
    pasos = [e["paso"] for e in db.todos("select paso from eventos where entidad='viaje' and entidad_id=:v", v=v["id"])]
    assert pasos.count("preparado para la demostración") == 2 and "tramos registrados" in pasos
    assert demo_monitoreo.AHORA == "2026-12-13T06:00"


def test_si_la_colaboradora_ya_tiene_un_viaje_ese_dia_se_reutiliza(cliente, monkeypatch):
    """Dos viajes de la misma persona que salen el mismo día dejan sus recibos sin viaje: no se crea otro."""
    from datos import demo_monitoreo
    monkeypatch.setattr(config, "PREPARAR_BASE_LOCAL", True)
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    laura = db.uno("select * from usuarios where correo='piloto2@demo.local'")
    activos = "select id from viajes where usuario_id=:u and ida=:ida and estado not in ('rechazado', 'cerrado')"
    if not db.todos(activos, u=laura["id"], ida=demo_monitoreo.IDA):   # el viaje que ella misma cotizó y le aprobaron
        sid = db.insertar("solicitudes", proyecto_id=2, viajero_id=laura["viajero_id"], origen="MAD", destino="LIS",
                          ciudad="Lisboa", ida=demo_monitoreo.IDA, regreso=demo_monitoreo.REGRESO, estado="decidido",
                          creado=db.ahora(), solicitado_por=laura["nombre"], usuario_id=laura["id"])
        db.insertar("viajes", solicitud_id=sid, proyecto_id=2, usuario_id=laura["id"], viajero_id=laura["viajero_id"],
                    ida=demo_monitoreo.IDA, regreso=demo_monitoreo.REGRESO, presupuesto_usd=581.0, estado="aprobado",
                    creado=db.ahora())
    antes = {f["id"] for f in db.todos(activos, u=laura["id"], ida=demo_monitoreo.IDA)}
    monkeypatch.setattr(demo_monitoreo, "FUENTE", "otro preparador")   # como si el preparador nunca hubiera corrido
    r = demo_monitoreo.preparar()
    assert r["hecho"] and r["creado"] is False and r["viaje_id"] in antes
    assert {f["id"] for f in db.todos(activos, u=laura["id"], ida=demo_monitoreo.IDA)} == antes
    assert db.uno("select numero from tramos_vuelo where viaje_id=:v", v=r["viaje_id"])["numero"] == "IB 5634"


def test_el_tablero_con_ese_ahora_muestra_el_tramo_sin_no_llega(cliente, monkeypatch, capsys):
    from datos import demo_monitoreo
    monkeypatch.setattr(config, "PREPARAR_BASE_LOCAL", True)
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    assert demo_monitoreo.main() == 0
    salida = capsys.readouterr().out
    assert "MONITOREO_AHORA=2026-12-13T06:00" in salida and "de 05:05 a 09:30 UTC" in salida
    vid = db.uno("select v.id from viajes v join solicitudes s on s.id=v.solicitud_id where s.solicitado_por=:f",
                 f=demo_monitoreo.FUENTE)["id"]
    monkeypatch.setenv("MONITOREO_AHORA", demo_monitoreo.AHORA)
    fila = next(f for f in cliente.get("/admin/viajes/vuelos").json() if f["viaje_id"] == vid)   # sin fecha: el día de ese ahora
    assert fila["numero"] == "IB 5634" and fila["estado"] == "retrasado" and fila["puerta"] == "J58"
    assert fila["no_llega"] is False and fila["consultas"] == 1          # leyó la respuesta de ejemplo, sin consultas en vivo
    html = cliente.get("/admin/viajes").text
    assert fila["codigo"] in html and "IB 5634" in html


def test_fuera_de_docker_funciona_sobre_una_sqlite_nueva(tmp_path):
    """La guía lo ofrece con SQLite: sin la aplicación arrancada antes, la base todavía no tiene tablas ni cuentas."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    entorno = {**os.environ, "ENTORNO": "local", "DATABASE_URL": f"sqlite:///{tmp_path / 'nueva.db'}",
               "DIRECTORIO_ARCHIVOS": str(tmp_path / "archivos"), "PREPARAR_BASE_LOCAL": "", "CUENTAS_DEMO": ""}
    r = subprocess.run([sys.executable, "-m", "datos.demo_monitoreo"], cwd=Path(__file__).resolve().parent.parent,  # noqa: S603  guion fijo de esta prueba
                       env=entorno, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "IB 5634" in r.stdout and "MONITOREO_AHORA=2026-12-13T06:00" in r.stdout
