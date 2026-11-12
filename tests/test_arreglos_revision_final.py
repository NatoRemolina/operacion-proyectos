"""Arreglos de la revisión final: orden de bloqueo, monitoreo solo de viajes aprobados y recibos PDF en la imagen."""
import fnmatch
from pathlib import Path

from app import db
from app.servicios import gastos, monitoreo_vuelos

RAIZ = Path(__file__).resolve().parents[1]


def test_leer_y_decidir_bloquea_el_viaje_antes_que_el_gasto(viaje_aprobado, monkeypatch):
    # El mismo orden que la revisión y la asignación de viaje (viaje, después gasto): con el orden cruzado,
    # dos operaciones a la vez en PostgreSQL pueden bloquearse entre sí.
    orden = []
    bloquear = db.bloquear_viaje
    uno = db.uno

    def bloquear_registrado(conexion, viaje_id):
        orden.append("viaje")
        return bloquear(conexion, viaje_id)

    def uno_registrado(sql, **kw):
        if sql.startswith("select estado from gastos where id="):
            orden.append("gasto")
        return uno(sql, **kw)

    monkeypatch.setattr(db, "bloquear_viaje", bloquear_registrado)
    monkeypatch.setattr(db, "uno", uno_registrado)
    ejemplo = RAIZ / "datos" / "ejemplos" / "recibo_gasolina.png"
    usuario = db.uno("select * from usuarios where id=:i", i=viaje_aprobado["usuario_id"])
    gid = gastos.registrar(ejemplo.read_bytes(), ejemplo.name, "web", usuario, viaje_aprobado)
    monkeypatch.undo()
    try:
        assert "viaje" in orden and "gasto" in orden
        assert orden.index("viaje") < orden.index("gasto")
    finally:   # la base es de toda la sesión de pruebas: este recibo no debe contar como duplicado en otras
        doc = db.uno("select documento_id from gastos where id=:g", g=gid)["documento_id"]
        for sql in ("delete from envios_soporte where gasto_id=:g", "delete from justificaciones where gasto_id=:g",
                    "delete from gastos where id=:g"):
            db.ejecutar(sql, g=gid)
        if doc:
            db.ejecutar("delete from documentos where id=:d", d=doc)


def test_el_monitoreo_no_consulta_viajes_sin_aprobar(viaje_aprobado):
    # Un tramo propio en el viaje de la prueba, con fecha fija: el tablero de ese día solo lo lista si el viaje está
    # aprobado, así que un viaje pendiente no gasta consultas del estado del vuelo
    fecha = "2027-03-03"
    tid = db.insertar("tramos_vuelo", viaje_id=viaje_aprobado["id"], sentido="ida", orden=1, aerolinea="Prueba",
                      numero="ZZ 9", fecha=fecha, desde="MIA", hasta="LAS", sale_programada=f"{fecha} 08:00",
                      llega_programada=f"{fecha} 11:00")
    estado = db.uno("select estado from viajes where id=:v", v=viaje_aprobado["id"])["estado"]
    try:
        db.ejecutar("update viajes set estado='pendiente_aprobacion' where id=:v", v=viaje_aprobado["id"])
        assert not [t for t in monitoreo_vuelos.tablero(fecha=fecha) if t["id"] == tid]
        db.ejecutar("update viajes set estado='aprobado' where id=:v", v=viaje_aprobado["id"])
        assert [t for t in monitoreo_vuelos.tablero(fecha=fecha) if t["id"] == tid]
    finally:
        db.ejecutar("update viajes set estado=:e where id=:v", e=estado, v=viaje_aprobado["id"])
        db.ejecutar("delete from tramos_vuelo where id=:t", t=tid)


def _excluido(ruta: str, reglas: list[str]) -> bool:
    """Semántica de .dockerignore: gana la última regla que coincide; «!» la invierte."""
    excluido = False
    for regla in reglas:
        negada = regla.startswith("!")
        patron = regla[1:] if negada else regla
        if fnmatch.fnmatch(ruta, patron) or fnmatch.fnmatch(Path(ruta).name, patron) and "/" not in patron:
            excluido = not negada
    return excluido


def test_los_recibos_pdf_de_ejemplo_entran_en_la_imagen():
    reglas = [l.strip() for l in (RAIZ / ".dockerignore").read_text().splitlines() if l.strip() and not l.startswith("#")]
    pdfs = sorted(p.relative_to(RAIZ).as_posix() for p in (RAIZ / "datos" / "ejemplos").glob("*.pdf"))
    assert pdfs, "no hay PDF de ejemplo"
    assert not [p for p in pdfs if _excluido(p, reglas)]
    assert _excluido("PERFIL_DEL_CARGO.pdf", reglas)      # los PDF personales de la raíz siguen fuera
