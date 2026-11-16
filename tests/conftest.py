"""Arnés de pruebas: base SQLite temporal y ninguna clave real.

Las variables se fijan ANTES de importar la aplicación: `app.config` carga `.env`, y sin esto
las pruebas escribirían en la base real y gastarían cupo del buscador y del modelo.
"""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="pruebas_"))
# PRUEBAS_DATABASE_URL apunta a un PostgreSQL desechable y vacío (por ejemplo, una base nueva en el
# contenedor de docker-compose.yml) para correr las mismas pruebas con el motor de producción.
_pg = os.getenv("PRUEBAS_DATABASE_URL", "")
os.environ.update({
    "ENTORNO": "local", "DATABASE_URL": _pg or f"sqlite:///{_tmp / 'pruebas.db'}",
    "PREPARAR_BASE_LOCAL": "1" if _pg else "", "CUENTAS_DEMO": "1" if _pg else "",
    "SERPAPI_KEY": "", "MODELO_API_URL": "", "MODELO_API_KEY": "", "MODELO_NOMBRE": "",
    "ASESOR_API_URL": "", "ASESOR_API_KEY": "", "ASESOR_AGENTE_ID": "", "ASESOR_ENTORNO_ID": "",
    "ASESOR_CABECERAS": "", "ASESOR_AGENTE_VERSION": "", "MODELO_CABECERAS": "",
    "SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": "", "APP_CLAVE": "", "SECRETO_ARN": "",
    # La semilla carga un subconjunto pequeño de los datos geográficos, no el mundo entero
    "GEOGRAFIA_DIR": str(Path(__file__).parent / "datos" / "geografia_mini"),
})

import random  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


def pytest_addoption(parser):
    parser.addoption("--orden-aleatorio", action="store", default=None, metavar="SEMILLA",
                     help="Corre las pruebas en un orden aleatorio repetible (una semilla entera): comprueba que ninguna "
                          "dependa de otra. Sin dependencias nuevas.")


def pytest_collection_modifyitems(config, items):
    """Como pytest-randomly: baraja los módulos y, dentro de cada uno, sus pruebas (los datos de un módulo se preparan
    una vez por módulo)."""
    semilla = config.getoption("--orden-aleatorio")
    if semilla is None:
        return
    azar, modulos = random.Random(int(semilla)), {}  # noqa: S311  barajar pruebas, no cifrar
    for item in items:
        modulos.setdefault(item.module.__name__, []).append(item)
    orden = list(modulos.values())
    azar.shuffle(orden)
    for grupo in orden:
        azar.shuffle(grupo)
    items[:] = [item for grupo in orden for item in grupo]


def pytest_report_header(config):
    semilla = config.getoption("--orden-aleatorio")
    return f"orden aleatorio con la semilla {semilla}" if semilla is not None else None

from app import config  # noqa: E402

config.DIR_ARCHIVOS = _tmp / "archivos"

from app.main import app  # noqa: E402

# El «hoy» de las pruebas: las cotizaciones y recibos de ejemplo son de diciembre de 2026 y las respuestas guardadas del
# buscador van atadas a esas fechas. Con el reloj único fijo en este día, las fechas de ejemplo siempre quedan en el futuro
# cercano y la suite no caduca. Las pruebas del reloj fijan el suyo con monkeypatch, que manda sobre este.
HOY_DE_LAS_PRUEBAS = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True, scope="session")
def _reloj_de_las_pruebas():
    from app.servicios import tiempo
    real = tiempo.ahora
    tiempo.ahora = lambda: HOY_DE_LAS_PRUEBAS
    yield
    tiempo.ahora = real


@pytest.fixture(autouse=True, scope="session")
def _topes_diarios_amplios():
    """Las pruebas cotizan y leen recibos muchas veces al día con las mismas cuentas: los topes diarios
    (`tope_cotizaciones_persona_dia` y los de lecturas de recibos) no deben depender de cuántas llevan.
    Las pruebas de cada tope fijan el suyo."""
    from app import db
    db.ejecutar("""update reglas set valor='100000' where ambito='supuesto'
                   and clave in ('tope_cotizaciones_persona_dia', 'lecturas_recibo_persona_dia', 'lecturas_recibo_dia')""")


@pytest.fixture(scope="session")
def _ruta_candado(tmp_path_factory):
    return tmp_path_factory.mktemp("asesor") / "asesor_agente.json"


@pytest.fixture(autouse=True)
def _asistente_aislado(request, monkeypatch, _ruta_candado):
    """Lo compartido del asistente no se filtra de una prueba a otra.

    - El tope diario de preguntas y dictados: todas las pruebas preguntan como las mismas cuentas, y el conteo del día
      no debe depender de cuántas corrieron antes. Las pruebas del tope llevan `@pytest.mark.con_tope` (usan la regla
      de la base) o fijan el suyo con monkeypatch dentro de la prueba, que manda sobre este.
    - El candado del agente (app/asesor_agente.json): `--sincronizar` lo escribe, así que cada prueba usa uno
      temporal que empieza sin existir. El del repositorio solo lo lee su propia prueba."""
    from app.servicios import asesor, asistente
    monkeypatch.setattr(asesor, "CANDADO", _ruta_candado)
    if not request.node.get_closest_marker("con_tope"):
        monkeypatch.setattr(asistente, "tope_diario", lambda: 10_000)
        monkeypatch.setattr(asistente, "tope_dictados", lambda: 10_000)
    yield
    _ruta_candado.unlink(missing_ok=True)


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


@pytest.fixture(scope="session")
def revisor():
    """Segunda cuenta de administración: revisa lo que sube la primera, porque nadie revisa lo que subió (cuatro ojos)."""
    from app import db
    from app.servicios import acceso
    if not db.uno("select id from usuarios where correo='revisor@demo.local'"):
        acceso.crear_usuario("revisor@demo.local", "Rosalba Quintana", "admin", "demo-revisor-2026")
    db.ejecutar("update usuarios set activo=1 where correo='revisor@demo.local'")
    return _con_sesion("revisor@demo.local", "demo-revisor-2026")


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
