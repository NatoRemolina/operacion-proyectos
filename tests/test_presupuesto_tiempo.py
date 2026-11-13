"""Un solo presupuesto de tiempo para una pregunta al asistente.

CloudFront corta la respuesta de la API a los 60 s (infra/lib/web-stack.ts): lo que llegue después no lo ve nadie y,
si el asesor tardaba más, el respaldo con el modelo de lenguaje nunca alcanzaba a responder. Estas pruebas atan las
cifras de cada capa para que cambiar una sin la otra rompa la integración continua.
"""
import re
import time
from pathlib import Path

import httpx
import pytest

from app import db
from app.servicios import asesor, asistente, llm

RAIZ = Path(__file__).resolve().parent.parent
MARGEN_S = 5   # la base, el registro y la respuesta, después de que el asesor o el modelo terminan


def _espera_de_cloudfront() -> int:
    """La espera más corta de CloudFront ante la API, leída de la pila: la web y administración."""
    texto = (RAIZ / "infra" / "lib" / "web-stack.ts").read_text()
    esperas = [int(x) for x in re.findall(r"readTimeout:\s*Duration\.seconds\((\d+)\)", texto)]
    assert esperas, "no se encontró readTimeout en infra/lib/web-stack.ts"
    return min(esperas)


def test_el_presupuesto_de_una_pregunta_cabe_en_la_espera_de_cloudfront():
    assert asistente.PRESUPUESTO_S + MARGEN_S <= _espera_de_cloudfront()


def test_el_asesor_con_su_cierre_cabe_en_el_presupuesto():
    assert asesor.PLAZO_TOTAL_S + asesor.CIERRE_MAX_S <= asistente.PRESUPUESTO_S


class Reloj:
    """Reloj falso para `asistente.time`: avanza solo cuando la prueba lo dice."""
    def __init__(self):
        self.ahora = 1000.0

    def monotonic(self):
        return self.ahora


def _admin():
    return db.uno("select * from usuarios where correo='admin@demo.local'")


def test_el_asesor_recibe_lo_que_queda_tras_poner_al_dia_el_indice(monkeypatch):
    reloj, recibido = Reloj(), {}
    monkeypatch.setattr(asistente, "time", reloj)
    monkeypatch.setattr(asistente, "_indexar_si_toca", lambda: setattr(reloj, "ahora", reloj.ahora + 20))   # índice lento
    monkeypatch.setattr(asesor, "estado", lambda: ("listo", ""))
    monkeypatch.setattr(asesor, "preguntar", lambda *a, **k: recibido.update(k) or "Respuesta del asesor.")
    assert asistente.responder("¿Cuántos gastos hay en revisión?", _admin())["modo"] == "asesor"
    assert recibido["plazo_s"] == pytest.approx(asistente.PRESUPUESTO_S - 20)


def test_el_modelo_recibe_el_limite_de_la_pregunta(monkeypatch):
    recibido = {}
    monkeypatch.setattr(llm, "activo", lambda: True)
    monkeypatch.setattr(asistente, "_con_modelo", lambda pregunta, r, **k: recibido.update(k) or "Respuesta del modelo.")
    inicio = time.monotonic()
    assert asistente.responder("¿Cuántos gastos hay en revisión?", _admin())["modo"] == "modelo"
    assert inicio < recibido["limite"] <= time.monotonic() + asistente.PRESUPUESTO_S


def test_si_el_asesor_falla_rapido_el_modelo_aun_alcanza_a_responder():
    assert asesor.SEGUNDA_VIA_S + asistente.MIN_MODELO_S <= asistente.PRESUPUESTO_S


def test_el_modelo_nunca_recibe_mas_tiempo_que_el_que_queda(monkeypatch):
    plazos = []
    guion = iter([{"content": {"role": "model", "parts": [{"functionCall": {"name": "kpis", "args": {}}}]}},
                  {"content": {"role": "model", "parts": [{"text": "Listo."}]}}])
    monkeypatch.setattr(llm, "generar", lambda contenidos, **k: plazos.append(k["plazo_s"]) or next(guion))
    admin = db.uno("select * from usuarios where correo='admin@demo.local'")
    texto = asistente._con_modelo("¿Cómo vamos?", asistente.Rastro(admin), limite=time.monotonic() + 12)
    assert texto == "Listo." and len(plazos) == 2 and all(0 < p <= 12 for p in plazos)


def test_sin_tiempo_suficiente_no_se_empieza_con_el_modelo(monkeypatch):
    monkeypatch.setattr(asistente, "PRESUPUESTO_S", asistente.MIN_MODELO_S - 1)
    monkeypatch.setattr(llm, "activo", lambda: True)

    def no_debe_llamarse(*a, **k):
        raise AssertionError("sin tiempo no se empieza la conversación con el modelo")
    monkeypatch.setattr(asistente, "_con_modelo", no_debe_llamarse)
    admin = db.uno("select * from usuarios where correo='admin@demo.local'")
    assert asistente.responder("¿Cuántos gastos hay en revisión?", admin)["modo"] == "determinista"


@pytest.fixture()
def reloj(monkeypatch):
    """Reloj del cliente del modelo que avanza con cada espera: la de la red y las pausas entre intentos."""
    ahora = [1000.0]
    monkeypatch.setattr(llm, "_reloj", lambda: ahora[0])
    monkeypatch.setattr(llm.time, "sleep", lambda s: ahora.__setitem__(0, ahora[0] + s))
    return ahora


def test_con_plazo_los_reintentos_del_modelo_no_lo_pasan(monkeypatch, reloj):
    esperas = []

    def lento(url, *, timeout, **_):
        esperas.append(timeout)
        reloj[0] += timeout
        raise httpx.ReadTimeout("sin respuesta")
    monkeypatch.setattr(llm.httpx, "post", lento)
    inicio = reloj[0]
    with pytest.raises(llm.ErrorDelModelo):
        llm.generar([{"role": "user", "parts": [{"text": "hola"}]}], uso="asistente", plazo_s=20)
    assert reloj[0] - inicio <= 20 and all(e <= 20 for e in esperas)


def test_sin_plazo_el_modelo_conserva_sus_tres_intentos(monkeypatch, reloj):
    """La lectura de recibos no tiene a nadie mirando un reloj: sigue con sus reintentos de siempre."""
    intentos = []

    def caido(url, *, timeout, **_):
        intentos.append(timeout)
        raise httpx.ConnectError("caído")
    monkeypatch.setattr(llm.httpx, "post", caido)
    with pytest.raises(llm.ErrorDelModelo):
        llm.generar([{"role": "user", "parts": [{"text": "hola"}]}], uso="recibo")
    assert intentos == [llm.ESPERA_S] * 3
