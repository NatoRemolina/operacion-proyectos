"""Lectura de recibos con tope: cada lectura con el modelo reserva su unidad (por persona y del total de la empresa)
antes de llamarlo, por todas las vías: API, buzón, carga anterior, Telegram y transcripción de notas de voz.

Pasado el tope el soporte se guarda y el gasto queda en revisión con el aviso «Lectura pendiente por tope» (motivo
`lectura_fallida`, origen «pendiente por tope»): no se pierde ni se paga.
Un PDF de más de 15 páginas no se lee. El modelo es un doble: ninguna prueba sale a internet.
"""
import json
import uuid
import zlib

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.main import app
from app.servicios import acceso, extraccion, gastos, justificaciones, llm, telegram, topes

V1 = "/api/v1"
PERSONA, TOTAL = "lecturas_recibo_persona_dia", "lecturas_recibo_dia"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
AUDIO = b"OggS" + b"\x00" * 64


@pytest.fixture()
def modelo(monkeypatch):
    """Doble del modelo de lectura: cuenta las llamadas y responde una lectura válida."""
    for nombre, valor in (("MODELO_API_URL", "http://modelo.test"), ("MODELO_API_KEY", "clave-de-prueba"),
                          ("MODELO_NOMBRE", "modelo-de-prueba"), ("MODELO_FORMATO", "gemini")):
        monkeypatch.setattr(config, nombre, valor)
    llamadas = []

    def generar(contenidos, **opciones):
        llamadas.append(opciones.get("uso"))
        lectura = {"comercio": f"Comercio {uuid.uuid4().hex[:8]}", "fecha": "2026-11-10", "categoria": "comida",
                   "total": 12.5, "moneda": "USD", "confianza": 0.99, "dudas": []}
        return {"content": {"parts": [{"text": json.dumps(lectura)}]}, "finishReason": "STOP"}

    monkeypatch.setattr(llm, "generar", generar)
    return llamadas


@pytest.fixture()
def topes_de_lectura():
    """Fija los dos topes para la prueba y los devuelve como estaban (la sesión de pruebas los amplía)."""
    previos = {c: db.uno("select valor from reglas where ambito='supuesto' and clave=:c", c=c)["valor"] for c in (PERSONA, TOTAL)}

    def fijar(persona: int, total: int | None = None):
        db.ejecutar("update reglas set valor=:v where ambito='supuesto' and clave=:c", v=str(persona), c=PERSONA)
        db.ejecutar("update reglas set valor=:v where ambito='supuesto' and clave=:c", v=str(total if total is not None else 10**6), c=TOTAL)
    yield fijar
    for clave, valor in previos.items():
        db.ejecutar("update reglas set valor=:v where ambito='supuesto' and clave=:c", v=valor, c=clave)


def _cuenta(rol: str = "colaborador") -> tuple[dict, TestClient]:
    correo, clave = f"lecturas-{uuid.uuid4().hex[:8]}@demo.local", "clave-de-lecturas-2026"
    acceso.crear_usuario(correo, "Persona de las lecturas", rol, clave)
    c = TestClient(app)
    c.post("/entrar", data={"correo": correo, "clave": clave})
    return db.uno("select * from usuarios where correo=:c", c=correo), c


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))}


def _gasto(gid: int) -> dict:
    g = db.uno("select * from gastos where id=:i", i=gid)
    return {**g, "motivos": db.de_json(g["motivos"], []), "alertas": db.de_json(g["alertas"], [])}


def _pendiente_por_tope(g: dict) -> bool:
    return g["estado"] == "revision" and g["motivos"][:1] == ["lectura_fallida"] and bool(g["documento_id"]) \
        and g["alertas"][0].startswith("Lectura pendiente por tope") and g["origen_dato"] == "pendiente por tope"


def _foto() -> bytes:
    return PNG + uuid.uuid4().bytes   # cada una distinta: nada se reutiliza


def _pdf(paginas: int, comprimido: bool = False) -> bytes:
    """Un PDF mínimo con `paginas` páginas; comprimido, las páginas van en un flujo de objetos (PDF 1.5)."""
    objetos = b"".join(b"%d 0 obj << /Type /Page /Parent 2 0 R >> endobj\n" % (10 + i) for i in range(paginas))
    if comprimido:
        datos = zlib.compress(objetos)
        objetos = b"3 0 obj << /Type /ObjStm /Filter /FlateDecode /Length %d >>\nstream\n" % len(datos) + datos + b"\nendstream endobj\n"
    return (b"%PDF-1.7\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Count " + str(paginas).encode()
            + b" >> endobj\n" + objetos + uuid.uuid4().hex.encode() + b"\n%%EOF")


# ---------- las reglas ----------
def test_los_topes_son_reglas_editables_con_su_valor_inicial():
    from datos.semilla import SUPUESTOS_NUEVOS
    valores = {clave: valor for clave, valor, _ in SUPUESTOS_NUEVOS}
    assert valores[PERSONA] == "40" and valores[TOTAL] == "400"
    for clave in (PERSONA, TOTAL):
        assert db.uno("select id from reglas where ambito='supuesto' and clave=:c", c=clave)


# ---------- por cada vía ----------
def test_por_la_api_pasado_el_tope_se_guarda_y_queda_pendiente(modelo, topes_de_lectura):
    yo, c = _cuenta()
    topes_de_lectura(1)
    primero = c.post(f"{V1}/gastos", files={"archivo": ("a.png", _foto(), "image/png")}, headers=_csrf(c))
    assert primero.status_code == 201, primero.text
    assert modelo == ["recibo"] and topes.usadas(PERSONA, yo) == 1
    segundo = c.post(f"{V1}/gastos", files={"archivo": ("b.png", _foto(), "image/png")}, headers=_csrf(c))
    assert segundo.status_code == 201, segundo.text
    assert modelo == ["recibo"]                     # no se llamó al modelo
    g = _gasto(segundo.json()["id"])
    assert _pendiente_por_tope(g) and g["total"] is None
    assert db.uno("select ruta from documentos where id=:d", d=g["documento_id"])["ruta"]   # el soporte quedó guardado


def test_el_tope_total_de_la_empresa_tambien_corta(modelo, topes_de_lectura):
    yo, c = _cuenta()
    topes_de_lectura(40, total=topes.usadas(PERSONA))   # la empresa ya llegó a su tope, aunque esta persona no
    r = c.post(f"{V1}/gastos", files={"archivo": ("a.png", _foto(), "image/png")}, headers=_csrf(c))
    assert r.status_code == 201 and _pendiente_por_tope(_gasto(r.json()["id"])) and modelo == []


def test_por_el_buzon_pasado_el_tope_queda_pendiente(modelo, topes_de_lectura, viaje_aprobado):
    yo, c = _cuenta("admin")
    topes_de_lectura(0)
    r = c.post(f"{V1}/buzon/lectura", json={"nombres": ["reserva_hotel.eml"], "viaje_id": viaje_aprobado["id"]}, headers=_csrf(c))
    assert r.status_code == 200, r.text
    assert _pendiente_por_tope(_gasto(r.json()["leidos"][0]["id"])) and modelo == []


def test_por_la_carga_anterior_pasado_el_tope_queda_pendiente(modelo, topes_de_lectura):
    yo, c = _cuenta()
    topes_de_lectura(0)
    r = c.post("/gastos/cargar", data={"canal": "web"}, headers={"X-Envio": "pagina"},
               files={"archivos": ("a.png", _foto(), "image/png")})
    assert r.status_code == 200, r.text
    assert _pendiente_por_tope(_gasto(r.json()["gastos"][0])) and modelo == []


def test_por_telegram_pasado_el_tope_queda_pendiente(modelo, topes_de_lectura, monkeypatch):
    yo, _ = _cuenta()
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "clave-de-pruebas")
    monkeypatch.setattr(telegram, "_llamar", lambda metodo, **d: {})
    monkeypatch.setattr(telegram, "descargar", lambda file_id: _foto())
    chat = 880000 + int(uuid.uuid4().int % 99999)
    db.actualizar("usuarios", yo["id"], telegram_chat_id=chat)
    topes_de_lectura(0)
    estado = telegram.procesar({"update_id": chat * 10, "message": {"chat": {"id": chat, "type": "private"},
                                                                   "photo": [{"file_id": "x", "file_size": 900}]}})
    assert estado == "procesado"
    g = db.uno("select id from gastos where usuario_id=:u order by id desc limit 1", u=yo["id"])
    assert _pendiente_por_tope(_gasto(g["id"])) and modelo == []


def test_la_nota_de_voz_pasado_el_tope_queda_por_transcribir(modelo, topes_de_lectura):
    yo, _ = _cuenta()
    gid = db.insertar("gastos", usuario_id=yo["id"], estado="revision", creado=db.ahora())
    topes_de_lectura(1)
    j1 = justificaciones.registrar(gid, yo, "web", audio=AUDIO)
    assert db.uno("select transcripcion from justificaciones where id=:i", i=j1)["transcripcion"] == "hecha"
    assert modelo == ["transcripcion"] and topes.usadas(PERSONA, yo) == 1
    j2 = justificaciones.registrar(gid, yo, "web", audio=AUDIO)
    assert db.uno("select transcripcion from justificaciones where id=:i", i=j2)["transcripcion"] == "pendiente"
    assert modelo == ["transcripcion"]               # el audio quedó guardado y se puede transcribir mañana


def test_una_lectura_reutilizada_no_gasta_tope(modelo, topes_de_lectura):
    yo, c = _cuenta()
    topes_de_lectura(1)
    foto = _foto()
    for nombre in ("a.png", "b.png"):   # el mismo archivo dos veces: la segunda reutiliza la lectura
        assert c.post(f"{V1}/gastos", files={"archivo": (nombre, foto, "image/png")}, headers=_csrf(c)).status_code == 201
    assert modelo == ["recibo"] and topes.usadas(PERSONA, yo) == 1


def test_sin_modelo_configurado_no_se_reserva_nada(topes_de_lectura):
    yo, c = _cuenta()
    topes_de_lectura(0)
    r = c.post(f"{V1}/gastos", files={"archivo": ("a.png", _foto(), "image/png")}, headers=_csrf(c))
    assert r.status_code == 201 and _gasto(r.json()["id"])["origen_dato"] != "pendiente por tope"
    assert topes.usadas(PERSONA, yo) == 0


# ---------- páginas del PDF ----------
@pytest.mark.parametrize("comprimido", [False, True])
def test_un_pdf_de_mas_de_15_paginas_no_se_lee(modelo, comprimido):
    assert extraccion.paginas_pdf(_pdf(15, comprimido)) == 15
    assert extraccion.paginas_pdf(_pdf(16, comprimido)) == 16
    yo, c = _cuenta()
    antes = db.uno("select count(*) n from gastos")["n"]
    r = c.post(f"{V1}/gastos", files={"archivo": ("largo.pdf", _pdf(16, comprimido), "application/pdf")}, headers=_csrf(c))
    assert r.status_code == 422, r.text
    mensaje = r.json()["error"]["fields"]["archivo"]
    assert "16 páginas" in mensaje and "15" in mensaje
    assert modelo == [] and db.uno("select count(*) n from gastos")["n"] == antes
    assert c.post(f"{V1}/gastos", files={"archivo": ("ok.pdf", _pdf(15, comprimido), "application/pdf")},
                  headers=_csrf(c)).status_code == 201


def test_el_limite_de_paginas_vale_para_todas_las_vias():
    with pytest.raises(gastos.SoporteRechazado, match="16 páginas"):
        gastos.preparar(_pdf(16), "largo.pdf")
