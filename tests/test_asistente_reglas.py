"""El asistente explica las reglas a quien reporta: por qué un gasto quedó en revisión (con los motivos reales de la
validación), cuánto queda del presupuesto del viaje y qué falta (justificación, un recibo legible…).

Todo con el modo determinista: sin modelo, sin claves y sin servicios externos.
"""
import json

import pytest

from app import db
from app.servicios import asistente, justificaciones, validacion, viajes


def _usuario(correo: str) -> dict:
    return db.uno("select * from usuarios where correo=:c", c=correo)


def _gasto(u: dict, viaje: dict, comercio: str, total: float, estado: str, motivos=(), alertas=()) -> int:
    return db.insertar("gastos", usuario_id=u["id"], viaje_id=viaje["id"], proyecto_id=viaje["proyecto_id"], viajero_id=viaje["viajero_id"],
                       comercio=comercio, fecha="2026-12-09", categoria="comida", total=total, moneda="USD", total_usd=total,
                       estado=estado, confianza=0.95, creado=db.ahora(), motivos=json.dumps(list(motivos)),
                       alertas=json.dumps(list(alertas), ensure_ascii=False))


@pytest.fixture(scope="module", autouse=True)
def _sin_rastro_propio():
    desde = db.uno("select coalesce(max(id), 0) m from asistente_consultas")["m"]
    yield
    db.ejecutar("update asistente_consultas set momento='2000-01-01T00:00:00' where id>:d", d=desde)


@pytest.fixture(autouse=True)
def _sin_tope(monkeypatch):
    monkeypatch.setattr(asistente, "tope_diario", lambda: 10_000)


@pytest.fixture(scope="module")
def caso(nuevo_viaje):
    """Un viaje de Andrés con un gasto aprobado, uno en revisión por recibo borroso y presupuesto superado, y uno
    justificado; Laura tiene un gasto sin justificar que Andrés nunca debe ver."""
    andres, laura = _usuario("piloto@demo.local"), _usuario("piloto2@demo.local")
    v = nuevo_viaje(viajero_id=1)
    vl = nuevo_viaje(viajero_id=2)
    c = {"andres": andres, "v": v,
         "aprobado": _gasto(andres, v, "Almuerzo Reglas Aprobado", 30.0, "aprobado_auto"),
         "revision": _gasto(andres, v, "Taxi Reglas Borroso", 45.5, "revision", ("ilegible", "presupuesto_superado"),
                            ("Confianza de lectura 40%, por debajo del 70%.", "Con este gasto el viaje llega a 999.00 USD.")),
         "justificado": _gasto(andres, v, "Cena Reglas Justificada", 20.0, "aprobado_auto"),
         "ajeno": _gasto(laura, vl, "Hotel Reglas de Laura", 300.0, "revision", ("atipico",))}
    justificaciones.registrar(c["justificado"], andres, "web", "Cena con el cliente después de grabar.")
    return c


# ---------- herramientas ----------
def test_cada_motivo_de_la_validacion_tiene_una_explicacion_para_quien_reporta():
    assert set(asistente.EXPLICACION) == set(validacion.MOTIVOS)
    for que_paso, que_hacer in asistente.EXPLICACION.values():
        assert que_paso.endswith(".") and que_hacer.endswith(".")


def test_detalle_gasto_explica_los_motivos_reales_y_lo_que_falta(caso):
    d = asistente.ejecutar(asistente.Rastro(caso["andres"]), "detalle_gasto", {"id": caso["revision"]})
    assert [m["motivo"] for m in d["motivos_explicados"]] == [validacion.MOTIVOS["ilegible"], validacion.MOTIVOS["presupuesto_superado"]]
    assert all(m["que_paso"] == asistente.EXPLICACION[c][0] and m["que_puedes_hacer"] == asistente.EXPLICACION[c][1]
               for m, c in zip(d["motivos_explicados"], ("ilegible", "presupuesto_superado"), strict=True))
    assert d["justificado"] is False
    assert any("justificación" in f for f in d["falta"]) and any("foto" in f for f in d["falta"])
    otro = asistente.ejecutar(asistente.Rastro(caso["andres"]), "detalle_gasto", {"id": caso["justificado"]})
    assert otro["motivos_explicados"] == [] and otro["justificado"] is True and otro["falta"] == []


def test_gastos_de_dice_si_cada_gasto_esta_justificado_y_que_le_falta(caso):
    res = asistente.ejecutar(asistente.Rastro(caso["andres"]), "gastos_de", {"viaje": caso["v"]["codigo"]})
    por_id = {g["gasto"]: g for g in res["gastos"]}
    assert por_id[f"#{caso['justificado']}"]["justificado"] is True and por_id[f"#{caso['justificado']}"]["falta"] == []
    revision = por_id[f"#{caso['revision']}"]
    assert revision["justificado"] is False and revision["motivos"] == [validacion.MOTIVOS["ilegible"], validacion.MOTIVOS["presupuesto_superado"]]
    assert any("foto" in f for f in revision["falta"])
    aprobado = por_id[f"#{caso['aprobado']}"]   # aprobado y sin justificar: la justificación sigue sumando
    assert aprobado["motivos"] == [] and aprobado["falta"] == [asistente.FALTA_JUSTIFICACION]


def test_viajes_de_dice_cuanto_queda_del_presupuesto(caso):
    v = viajes.lista("v.id=:i", i=caso["v"]["id"])[0]
    res = asistente.ejecutar(asistente.Rastro(caso["andres"]), "viajes_de", {})
    fila = next(x for x in res["viajes"] if x["viaje"] == caso["v"]["codigo"])
    assert fila["queda_usd"] == round(v["presupuesto_usd"] - v["gastado"], 2)
    assert fila["queda_si_se_aprueba_lo_en_revision_usd"] == round(v["presupuesto_usd"] - v["gastado"] - v["en_revision"], 2)


# ---------- las preguntas del colaborador, sin modelo ----------
def test_cuanto_me_queda_del_presupuesto(caso):
    v = viajes.lista("v.id=:i", i=caso["v"]["id"])[0]
    r = asistente.responder("¿Cuánto me queda del presupuesto?", caso["andres"])
    assert f"quedan {v['presupuesto_usd'] - v['gastado']:.2f} USD" in r["texto"] and caso["v"]["codigo"] in r["texto"]
    assert "No encontré registros" not in r["texto"] and "Hotel Reglas de Laura" not in r["texto"]


def test_por_que_mi_gasto_quedo_en_revision(caso):
    r = asistente.responder("¿Por qué mi gasto quedó en revisión?", caso["andres"])
    texto = r["texto"]
    assert f"#{caso['revision']}" in texto and asistente.EXPLICACION["ilegible"][0] in texto
    assert asistente.EXPLICACION["presupuesto_superado"][1] in texto
    assert "no es un error" in texto
    assert "Hotel Reglas de Laura" not in texto and f"#{caso['ajeno']}" not in texto
    assert "No encontré registros" not in texto


def test_que_me_falta_por_justificar(caso):
    r = asistente.responder("¿Qué me falta por justificar?", caso["andres"])
    texto = r["texto"]
    assert texto.index(f"#{caso['revision']} ") < texto.index("Falta:")   # lo que está en revisión va primero
    assert f"#{caso['justificado']} " not in texto
    assert "Hotel Reglas de Laura" not in texto and f"#{caso['ajeno']}" not in texto
    assert "No encontré registros" not in texto


def test_si_hay_mas_gastos_de_los_que_se_revisan_lo_dice(caso, monkeypatch):
    monkeypatch.setattr(asistente, "MAX_GASTOS", 1)
    r = asistente.responder("¿Qué me falta por justificar?", caso["andres"])
    assert "pregunta por un viaje" in r["texto"]


# ---------- preguntas sugeridas por permiso ----------
def test_preguntas_sugeridas_segun_el_permiso():
    colaborador = asistente.preguntas_sugeridas(_usuario("piloto@demo.local"))
    assert colaborador == ["¿Cuánto me queda del presupuesto?", "¿Por qué mi gasto quedó en revisión?", "¿Qué me falta por justificar?"]
    assert asistente.preguntas_sugeridas(_usuario("gestor@demo.local")) == colaborador
    admin = asistente.preguntas_sugeridas(_usuario("admin@demo.local"))
    assert "¿Cómo van los indicadores?" in admin and not set(admin) & set(colaborador)
    assert asistente.preguntas_sugeridas({}) == []
