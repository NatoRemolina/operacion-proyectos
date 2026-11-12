"""Arnés de pruebas: base SQLite temporal y ninguna clave real.

Las variables se fijan ANTES de importar la aplicación: `app.config` carga `.env`, y sin esto
las pruebas escribirían en la base real y gastarían cupo del buscador y del modelo.
"""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="pruebas_"))
os.environ.update({
    "ENTORNO": "local", "DATABASE_URL": f"sqlite:///{_tmp / 'pruebas.db'}",
    "SERPAPI_KEY": "", "MODELO_API_URL": "", "MODELO_API_KEY": "", "MODELO_NOMBRE": "",
    "SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": "", "APP_CLAVE": "", "SECRETO_ARN": "",
})

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402

config.DIR_ARCHIVOS = _tmp / "archivos"

from app.main import app  # noqa: E402


def _con_sesion(correo: str, clave: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/entrar", data={"correo": correo, "clave": clave}, follow_redirects=False).headers["location"] == "/"
    return c


@pytest.fixture(scope="session")
def cliente():
    """Administrador de demostración."""
    return _con_sesion("admin@demo.local", "demo-admin-2026")


@pytest.fixture(scope="session")
def piloto():
    """Usuario individual de demostración, vinculado al viajero 1."""
    return _con_sesion("piloto@demo.local", "demo-piloto-2026")


@pytest.fixture(scope="session")
def piloto2():
    """Segundo piloto de demostración (viajero 2): sirve para probar que nadie ve lo ajeno."""
    return _con_sesion("piloto2@demo.local", "demo-piloto2-2026")


@pytest.fixture(scope="session")
def gestor():
    """Gestor de demostración: gestiona el proyecto 1, sin aprobar nada."""
    return _con_sesion("gestor@demo.local", "demo-gestor-2026")


@pytest.fixture()
def anonimo():
    return TestClient(app)


FORM_VIAJE = dict(proyecto_id=1, viajero_id=1, origen="Miami (MIA)", destino="las vegas", ciudad="", ida="2026-12-08",
                  regreso="2026-12-11", llegar_antes="2026-12-08T18:00", baterias_n=4, baterias_wh=77, maleta="on",
                  prob_cambio=25, carro_dia=65, solicitado_por="Pruebas", para_otra_persona="1")


@pytest.fixture(scope="session")
def nuevo_viaje(cliente):
    """Devuelve una función que cotiza, decide y (si se pide) aprueba; entrega el viaje resultante."""
    from app.main import _comparacion
    from app.servicios import viajes

    def crear(aprobar: bool = True, **cambios) -> dict:
        r = cliente.post("/viajes", data={**FORM_VIAJE, **cambios}, follow_redirects=False)
        sid = int(r.headers["location"].rsplit("/", 1)[1])
        vuelo = _comparacion(sid)["vuelos"][0]["id"]
        cliente.post(f"/viajes/{sid}/decidir", data={"vuelo_id": vuelo, "razones": ["costo_total"]})
        v = viajes.de_solicitud(sid)
        if aprobar:
            cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "aprobar"})
        return viajes.de_solicitud(sid)
    return crear


@pytest.fixture(scope="session")
def viaje_aprobado(nuevo_viaje):
    """Un viaje del piloto de demostración con el presupuesto ya aprobado."""
    return nuevo_viaje()


@pytest.fixture(scope="session")
def ejemplos():
    return config.DIR_EJEMPLOS
