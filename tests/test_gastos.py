"""Recorrido de gastos sin claves: lectura guardada, validación, revisión, subidas hostiles."""
import pytest

from app import db
from app.main import _numero

BASE = {"proyecto_id": 1, "viajero_id": 1, "canal": "web"}


@pytest.fixture(autouse=True)
def _con_viaje(viaje_aprobado):
    """La regla exige que cada gasto pertenezca a un viaje aprobado: las cargas de este archivo van a ese viaje."""
    BASE["viaje_id"] = viaje_aprobado["id"]


def _subir(cliente, nombre, contenido, tipo="application/octet-stream"):
    return cliente.post("/gastos/cargar", data=BASE, files={"archivos": (nombre, contenido, tipo)},
                        headers={"X-Envio": "pagina"})


def _gasto(gid):
    return db.uno("select * from gastos where id=:i", i=gid)


def test_ejemplo_legible_se_aprueba_solo(cliente, ejemplos):
    r = _subir(cliente, "recibo.png", (ejemplos / "recibo_gasolina.png").read_bytes(), "image/png")
    g = _gasto(r.json()["gastos"][0])
    assert g["estado"] == "aprobado_auto" and g["total"] == 38.40 and g["extraido"]


def test_ejemplo_ilegible_va_a_revision(cliente, ejemplos):
    r = _subir(cliente, "x.png", (ejemplos / "recibo_parqueo_borroso.png").read_bytes(), "image/png")
    assert _gasto(r.json()["gastos"][0])["estado"] == "revision"


def test_duplicado_va_a_revision_y_se_aprueba_con_excepcion(cliente, ejemplos):
    foto = (ejemplos / "recibo_diner.png").read_bytes()
    _subir(cliente, "a.png", foto, "image/png")
    gid = _subir(cliente, "b.png", foto, "image/png").json()["gastos"][0]
    g = _gasto(gid)
    assert g["estado"] == "revision" and g["origen_dato"] == "reutilizado"   # no se paga otra lectura
    campos = dict(proyecto_id=1, viajero_id=1, comercio=g["comercio"], fecha=g["fecha"], categoria=g["categoria"],
                  total=str(g["total"]), moneda=g["moneda"])
    cliente.post(f"/gastos/{gid}", data={**campos, "accion": "aprobar"})
    assert _gasto(gid)["estado"] == "revision"                               # las reglas siguen bloqueando
    cliente.post(f"/gastos/{gid}", data={**campos, "accion": "excepcion", "motivo_excepcion": "corto"})
    assert _gasto(gid)["estado"] == "revision"                               # sin motivo real no pasa
    cliente.post(f"/gastos/{gid}", data={**campos, "accion": "excepcion", "motivo_excepcion": "Dos comidas del mismo día"})
    assert _gasto(gid)["estado"] == "aprobado"


def test_nombre_igual_a_un_ejemplo_no_hereda_su_lectura(cliente):
    """Un archivo cualquiera llamado como un ejemplo no debe aprobarse con los datos del ejemplo."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    g = _gasto(_subir(cliente, "recibo_diner.png", png, "image/png").json()["gastos"][0])
    assert g["estado"] == "revision" and g["total"] is None


def test_subidas_hostiles_se_rechazan(cliente):
    html = b"<html><script>alert(1)</script></html>"
    assert _subir(cliente, "recibo.html", html, "text/html").status_code == 400
    assert _subir(cliente, "foto.png", html, "image/png").status_code == 400          # tipo declarado falso
    assert _subir(cliente, "correo.eml", html, "message/rfc822").status_code == 400
    grande = b"\xff\xd8\xff" + b"0" * 4_600_000
    assert "MB" in _subir(cliente, "grande.jpg", grande, "image/jpeg").json()["errores"][0]


def test_nombre_con_rutas_no_escapa_del_almacen(cliente, ejemplos, tmp_path_factory):
    from app import config
    contenido = (ejemplos / "factura_hotel.pdf").read_bytes()
    r = _subir(cliente, "../../../../app/templates/base.html", contenido, "application/pdf")
    assert r.status_code == 200
    d = db.uno("select d.* from documentos d join gastos g on g.documento_id=d.id where g.id=:i", i=r.json()["gastos"][0])
    assert ".." not in d["ruta"] and "/" not in d["nombre"]
    assert (config.DIR_ARCHIVOS / d["ruta"].split(":", 1)[1]).is_file()


def test_soporte_se_sirve_aislado(cliente, ejemplos):
    gid = _subir(cliente, "c.eml", (ejemplos / "correo_tiquete.eml").read_bytes()).json()["gastos"][0]
    r = cliente.get(f"/gastos/{gid}/soporte")
    assert r.headers["x-content-type-options"] == "nosniff" and "sandbox" in r.headers["content-security-policy"]
    assert r.headers["content-type"].startswith("text/plain")


def test_numeros_con_coma_y_miles():
    assert _numero("1.234,56") == 1234.56 and _numero("1,234.56") == 1234.56
    assert _numero("23,50") == 23.5 and _numero("45.000") == 45000 and _numero("0.500") == 0.5
    assert _numero("abc") is None and _numero("") is None


def test_paginas_de_gastos_responden(cliente):
    for ruta in ("/gastos", "/gastos/cargar", "/gastos?estado=revision", "/proyectos/1", "/proyectos/1/exportar.csv", "/flujo", "/analitica"):
        assert cliente.get(ruta).status_code == 200, ruta
