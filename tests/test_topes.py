"""Topes sin carrera: una sola forma de reservar (`topes.reservar`) bajo el cerrojo común (`db.cerrojo`).

Varias peticiones a la vez no pasan juntas un tope: cada una reserva su unidad en fila, antes de gastar.
"""
import threading
import time
import uuid

import pytest

from app import db
from app.servicios import acceso, cotizacion, topes

REGLA = "prueba_topes_persona_dia"
TOTAL = "prueba_topes_dia"


def _fijar(clave: str, valor: int):
    db.ejecutar("delete from reglas where ambito='supuesto' and clave=:c", c=clave)
    db.insertar("reglas", ambito="supuesto", entidad="", tarifa="", clave=clave, valor=str(valor), nota="Regla de prueba",
                fuente="pruebas", confianza="supuesto", verificado="2026-11-13")


def _persona() -> dict:
    uid = acceso.crear_usuario(f"topes-{uuid.uuid4().hex[:8]}@demo.local", "Persona de los topes", "colaborador",
                               "clave-de-los-topes-2026")
    return db.uno("select * from usuarios where id=:i", i=uid)


@pytest.fixture
def reglas_de_prueba():
    yield
    db.ejecutar("delete from reglas where ambito='supuesto' and clave in (:a, :b)", a=REGLA, b=TOTAL)
    db.ejecutar("delete from topes_reservas where regla in (:a, :b)", a=REGLA, b=TOTAL)


def _a_la_vez(n: int, funcion) -> list:
    """Corre `funcion` en `n` hilos que arrancan juntos; devuelve lo que devolvió (o lanzó) cada uno."""
    salida, salida_lock, salida_juntos = [], threading.Lock(), threading.Barrier(n)

    def correr():
        salida_juntos.wait()
        try:
            r = funcion()
        except Exception as e:   # noqa: BLE001  la prueba mira qué lanzó cada hilo
            r = e
        with salida_lock:
            salida.append(r)
    hilos = [threading.Thread(target=correr) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(30)
    return salida


def test_el_cerrojo_va_dentro_de_una_transaccion():
    with pytest.raises(RuntimeError):
        db.cerrojo("fuera de una transacción")
    with db.transaccion():
        db.cerrojo("dentro")
        db.cerrojo(("compuesta", 7))   # cualquier clave: texto, número o tupla


def test_reservar_respeta_el_tope_por_persona_y_el_total(reglas_de_prueba):
    _fijar(REGLA, 2)
    _fijar(TOTAL, 3)
    a, b = _persona(), _persona()
    assert topes.reservar(REGLA, a, total=TOTAL) and topes.reservar(REGLA, a, total=TOTAL)
    assert not topes.reservar(REGLA, a, total=TOTAL)            # tope de la persona
    assert topes.usadas(REGLA, a) == 2
    assert topes.reservar(REGLA, b, total=TOTAL)
    assert not topes.reservar(REGLA, b, total=TOTAL)            # tope total del día, aunque b tenga cupo propio
    assert topes.usadas(REGLA) == 3


def test_reservas_simultaneas_no_pasan_el_tope(reglas_de_prueba):
    _fijar(REGLA, 3)
    p = _persona()
    resultados = _a_la_vez(8, lambda: topes.reservar(REGLA, p))
    assert sorted(resultados) == [False] * 5 + [True] * 3
    assert topes.usadas(REGLA, p) == 3


def test_cotizaciones_simultaneas_no_pasan_el_tope(monkeypatch):
    """Antes se contaba al empezar y la solicitud se guardaba después: varias a la vez veían cupo y pasaban todas."""
    p = _persona()
    regla = db.uno("select id, valor from reglas where ambito='supuesto' and clave='tope_cotizaciones_persona_dia'")
    db.ejecutar("update reglas set valor='1' where id=:i", i=regla["id"])
    lado = cotizacion.lado
    monkeypatch.setattr(cotizacion, "lado", lambda *a, **k: time.sleep(0.2) or lado(*a, **k))   # la validación tarda
    datos = dict(proyecto_id=1, origen="Miami (MIA)", destino="las vegas", ida="2026-12-08", regreso="2026-12-11")
    try:
        resultados = _a_la_vez(4, lambda: cotizacion.crear(p, **datos))
    finally:
        db.ejecutar("update reglas set valor=:v where id=:i", v=regla["valor"], i=regla["id"])
    creadas = [r for r in resultados if isinstance(r, int)]
    assert len(creadas) == 1, resultados
    assert all(isinstance(r, cotizacion.TopeAlcanzado) for r in resultados if not isinstance(r, int))
    assert db.uno("select count(*) n from solicitudes where usuario_id=:u", u=p["id"])["n"] == 1
