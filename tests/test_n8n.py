"""Integración con n8n: clave de servicio, aviso firmado `gasto.registrado` y enlace temporal al soporte."""
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from app import db
from app.servicios import avisos, claves_servicio
from datos import avisos as consola_avisos
from datos import claves_servicio as consola

SECRETO = "secreto-de-prueba-n8n"


@pytest.fixture(autouse=True)
def _secreto(monkeypatch):
    """Secreto para firmar; sin N8N_WEBHOOK_URL el aviso sigue apagado salvo en las pruebas que lo encienden."""
    monkeypatch.setenv("N8N_WEBHOOK_SECRETO", SECRETO)
    monkeypatch.delenv("N8N_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("URL_PUBLICA", "http://testserver")


def _ruta(enlace: str) -> str:
    partes = urlsplit(enlace)
    return f"{partes.path}?{partes.query}"


def _url(gid: int) -> str:
    return _ruta(avisos.enlace_soporte(gid))

V1 = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _gasto_con_soporte(cliente=None, contenido: bytes = PNG + b"n8n") -> int:
    from app.servicios import gastos
    admin = db.uno("select * from usuarios where correo='admin@demo.local'")
    return gastos.registrar(contenido, "n8n.png", "web", admin, proyecto_id=1, viajero_id=1)


# ---------- clave de servicio ----------
def test_la_clave_se_guarda_como_huella_y_se_muestra_una_vez(capsys):
    assert consola.main(["crear", "n8n", "--permiso", "soportes:leer"]) == 0
    clave = capsys.readouterr().out.strip().splitlines()[-1]
    assert clave.startswith("isk_") and len(clave) > 40
    fila = db.uno("select * from claves_servicio where prefijo=:p", p=clave[:10])
    assert fila["nombre"] == "n8n" and fila["permisos"] == "soportes:leer"
    assert clave not in str(fila.values())   # solo la huella
    assert consola.main(["listar"]) == 0
    assert clave not in capsys.readouterr().out


def test_permiso_desconocido_no_crea_clave():
    with pytest.raises(ValueError):
        claves_servicio.crear("n8n", ["gastos:borrar"])


def test_la_clave_entra_sin_cookie_ni_csrf_y_queda_en_la_bitacora(cliente, anonimo):
    gid = _gasto_con_soporte(cliente)
    _, clave = claves_servicio.crear("n8n", ["soportes:leer"])
    r = anonimo.get(_url(gid), headers={"X-Clave-Servicio": clave})
    assert r.status_code == 200 and r.content.startswith(PNG)
    assert r.headers["content-disposition"] == "attachment" and "no-store" in r.headers["cache-control"]
    ev = db.uno("select fuente, usuario_id from eventos where entidad='gasto' and entidad_id=:i and paso like 'soporte descargado%'", i=gid)
    assert ev == {"fuente": "n8n", "usuario_id": None}


def test_sin_clave_revocada_o_sin_permiso_no_entra(cliente, anonimo, monkeypatch):
    gid = _gasto_con_soporte(cliente)
    url = _url(gid)
    assert anonimo.get(url).status_code == 401
    assert anonimo.get(url, headers={"X-Clave-Servicio": "isk_inventada"}).json()["error"]["code"] == "UNAUTHENTICATED"
    cid, clave = claves_servicio.crear("n8n", ["soportes:leer"])
    claves_servicio.revocar(cid)
    assert anonimo.get(url, headers={"X-Clave-Servicio": clave}).status_code == 401
    # Una clave con otro permiso: 403 (se simula un segundo permiso para no depender de la lista actual)
    monkeypatch.setitem(claves_servicio.PERMISOS, "gastos:leer", "prueba")
    _, otra = claves_servicio.crear("otra", ["gastos:leer"])
    r = anonimo.get(url, headers={"X-Clave-Servicio": otra})
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    # La sesión de administración no sirve en lugar de la clave
    assert cliente.get(url).status_code == 401


def test_soporte_inexistente_responde_404(anonimo):
    _, clave = claves_servicio.crear("n8n", ["soportes:leer"])
    assert anonimo.get(_url(999999), headers={"X-Clave-Servicio": clave}).status_code == 404


# ---------- enlace firmado ----------
def test_enlace_alterado_vencido_o_ausente_no_sirve(cliente, anonimo, monkeypatch):
    gid = _gasto_con_soporte(cliente)
    _, clave = claves_servicio.crear("n8n", ["soportes:leer"])
    cab = {"X-Clave-Servicio": clave}
    bueno = _url(gid)
    q = parse_qs(urlsplit(bueno).query)
    vence, firma = int(q["vence"][0]), q["firma"][0]
    base = f"{V1}/servicio/gastos/{gid}/soporte"

    def codigo(url):
        r = anonimo.get(url, headers=cab)
        return r.status_code, r.json()["error"]["code"]

    assert codigo(base) == (403, "LINK_INVALID")                                               # sin enlace
    assert codigo(f"{base}?vence={vence}&firma={'0' * 64}") == (403, "LINK_INVALID")           # firma cambiada
    assert codigo(f"{base}?vence={vence + 600}&firma={firma}") == (403, "LINK_INVALID")        # vencimiento estirado
    otro = _gasto_con_soporte(cliente, PNG + b"otro")
    assert codigo(f"{V1}/servicio/gastos/{otro}/soporte?vence={vence}&firma={firma}") == (403, "LINK_INVALID")  # otro gasto
    vencido = _ruta(avisos.enlace_soporte(gid, ahora=int(time.time()) - avisos.VIGENCIA_ENLACE - 1))
    assert codigo(vencido) == (403, "LINK_EXPIRED")
    monkeypatch.setenv("N8N_WEBHOOK_SECRETO", "otro-secreto")                                  # rotar el secreto los invalida
    assert codigo(bueno) == (403, "LINK_INVALID")
    monkeypatch.setenv("N8N_WEBHOOK_SECRETO", SECRETO)
    assert anonimo.get(bueno, headers=cab).status_code == 200
    assert anonimo.get(bueno).status_code == 401                                               # el enlace sin la clave no basta


# ---------- aviso gasto.registrado ----------
class _Receptor(BaseHTTPRequestHandler):
    recibidos: list = []
    estado = 200

    def do_POST(self):  # noqa: N802
        cuerpo = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).recibidos.append((dict(self.headers), cuerpo))
        self.send_response(type(self).estado)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture()
def receptor(monkeypatch):
    _Receptor.recibidos, _Receptor.estado = [], 200
    servidor = HTTPServer(("127.0.0.1", 0), _Receptor)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    monkeypatch.setenv("N8N_WEBHOOK_URL", f"http://127.0.0.1:{servidor.server_port}/webhook/inflight-soportes")
    yield _Receptor
    servidor.shutdown()


def test_sin_configuracion_no_se_avisa(cliente):
    antes = db.uno("select count(*) n from avisos_salientes")["n"]
    _gasto_con_soporte(cliente, PNG + b"apagado")
    assert db.uno("select count(*) n from avisos_salientes")["n"] == antes
    assert consola_avisos.main(["reintentar"]) == 1


def test_el_aviso_va_firmado_y_su_enlace_descarga_el_soporte(cliente, anonimo, receptor):
    gid = _gasto_con_soporte(cliente, PNG + b"firmado")
    assert len(receptor.recibidos) == 1
    cabeceras, cuerpo = receptor.recibidos[0]
    # La firma se verifica igual que en el nodo Code de n8n: HMAC-SHA256(secreto, "<t>.<cuerpo>")
    partes = dict(p.split("=", 1) for p in cabeceras["X-Inflight-Firma"].split(","))
    esperado = hmac.new(SECRETO.encode(), f"{partes['t']}.".encode() + cuerpo, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(partes["v1"], esperado) and abs(int(partes["t"]) - time.time()) < 60
    assert cabeceras["X-Inflight-Evento"] == "gasto.registrado"
    datos = json.loads(cuerpo)
    assert datos["entrega"] == cabeceras["X-Inflight-Entrega"] and datos["gasto_id"] == gid
    assert set(datos) == {"evento", "entrega", "gasto_id", "viaje", "proyecto", "fecha", "comercio", "total", "moneda",
                          "enlace_soporte", "enlace_vence_en_segundos"}
    assert cuerpo == json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode()   # lo mismo que JSON.stringify
    _, clave = claves_servicio.crear("n8n", ["soportes:leer"])
    r = anonimo.get(_ruta(datos["enlace_soporte"]), headers={"X-Clave-Servicio": clave})
    assert r.status_code == 200 and r.content == PNG + b"firmado"
    fila = db.uno("select estado, intentos, respuesta from avisos_salientes where gasto_id=:g", g=gid)
    assert fila == {"estado": "entregado", "intentos": 1, "respuesta": 200}


def test_destino_caido_no_afecta_el_registro_y_se_reintenta(cliente, receptor, monkeypatch):
    destino = __import__("os").environ["N8N_WEBHOOK_URL"]
    monkeypatch.setenv("N8N_WEBHOOK_URL", "http://127.0.0.1:9/webhook/caido")   # nadie escucha: conexión rechazada
    inicio = time.perf_counter()
    gid = _gasto_con_soporte(cliente, PNG + b"caido")
    assert time.perf_counter() - inicio < 2.5
    assert db.uno("select estado from gastos where id=:i", i=gid)["estado"] != "procesando"
    fila = db.uno("select * from avisos_salientes where gasto_id=:g", g=gid)
    assert fila["estado"] == "pendiente" and fila["intentos"] == 1 and fila["ultimo_error"] and fila["proximo"] > db.ahora()
    assert db.uno("select 1 x from eventos where entidad='gasto' and entidad_id=:i and paso='aviso no entregado'", i=gid)
    # Antes de su turno no se reintenta; vuelto el destino y pasada la espera, sale con la misma entrega
    monkeypatch.setenv("N8N_WEBHOOK_URL", destino)
    assert avisos.reintentar_pendientes() == 0
    db.ejecutar("update avisos_salientes set proximo='2000-01-01 00:00:00' where id=:i", i=fila["id"])
    assert consola_avisos.main(["reintentar"]) == 0
    assert db.uno("select estado, intentos from avisos_salientes where id=:i", i=fila["id"]) == {"estado": "entregado", "intentos": 2}
    assert json.loads(receptor.recibidos[-1][1])["entrega"] == fila["entrega"]


def test_destino_que_falla_siempre_termina_como_fallido(cliente, receptor):
    receptor.estado = 500
    gid = _gasto_con_soporte(cliente, PNG + b"siempre500")
    aid = db.uno("select id from avisos_salientes where gasto_id=:g", g=gid)["id"]
    for _ in avisos.ESPERAS:
        db.ejecutar("update avisos_salientes set proximo='2000-01-01 00:00:00' where id=:i", i=aid)
        avisos.reintentar_pendientes()
    fila = db.uno("select estado, intentos, respuesta, proximo from avisos_salientes where id=:i", i=aid)
    assert fila == {"estado": "fallido", "intentos": len(avisos.ESPERAS) + 1, "respuesta": 500, "proximo": None}


def test_destino_lento_corta_por_tiempo_y_el_gasto_queda(cliente, receptor, monkeypatch):
    def lento(*a, **k):
        assert k["timeout"].read <= 3 and k["timeout"].connect <= 2   # tiempo de espera corto
        raise avisos.httpx.ReadTimeout("sin respuesta")
    monkeypatch.setattr(avisos.httpx, "post", lento)
    gid = _gasto_con_soporte(cliente, PNG + b"lento")
    assert "ReadTimeout" in db.uno("select ultimo_error from avisos_salientes where gasto_id=:g", g=gid)["ultimo_error"]


def test_un_error_al_preparar_el_aviso_no_rompe_el_registro(cliente, receptor, monkeypatch):
    monkeypatch.setattr(avisos, "_cuerpo_gasto", lambda _: 1 / 0)
    gid = _gasto_con_soporte(cliente, PNG + b"roto")
    assert db.uno("select id from gastos where id=:i", i=gid)


def test_el_aviso_lleva_el_codigo_del_viaje_y_el_proyecto(cliente, receptor, viaje_aprobado):
    from app.servicios import gastos, viajes
    admin = db.uno("select * from usuarios where correo='admin@demo.local'")
    viaje = db.uno("select * from viajes where id=:i", i=viaje_aprobado["id"])
    viaje["codigo"] = viajes.codigo_viaje(viaje)
    gastos.registrar(PNG + b"con-viaje", "n8n.png", "web", admin, viaje)
    datos = json.loads(receptor.recibidos[-1][1])
    proyecto = db.uno("select nombre from proyectos where id=:i", i=viaje["proyecto_id"])["nombre"]
    assert datos["viaje"] == viajes.codigo_viaje(viaje) and datos["proyecto"] == proyecto
