"""Integración con n8n: clave de servicio, aviso firmado `gasto.registrado` y enlace temporal al soporte."""
from app import db
from app.servicios import claves_servicio
from datos import claves_servicio as consola

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
    import pytest
    with pytest.raises(ValueError):
        claves_servicio.crear("n8n", ["gastos:borrar"])


def test_la_clave_entra_sin_cookie_ni_csrf_y_queda_en_la_bitacora(cliente, anonimo):
    gid = _gasto_con_soporte(cliente)
    _, clave = claves_servicio.crear("n8n", ["soportes:leer"])
    r = anonimo.get(f"{V1}/servicio/gastos/{gid}/soporte", headers={"X-Clave-Servicio": clave})
    assert r.status_code == 200 and r.content.startswith(PNG)
    assert r.headers["content-disposition"] == "attachment" and "no-store" in r.headers["cache-control"]
    ev = db.uno("select fuente, usuario_id from eventos where entidad='gasto' and entidad_id=:i and paso like 'soporte descargado%'", i=gid)
    assert ev == {"fuente": "n8n", "usuario_id": None}


def test_sin_clave_revocada_o_sin_permiso_no_entra(cliente, anonimo, monkeypatch):
    gid = _gasto_con_soporte(cliente)
    url = f"{V1}/servicio/gastos/{gid}/soporte"
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
    assert anonimo.get(f"{V1}/servicio/gastos/999999/soporte", headers={"X-Clave-Servicio": clave}).status_code == 404
