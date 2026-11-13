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
