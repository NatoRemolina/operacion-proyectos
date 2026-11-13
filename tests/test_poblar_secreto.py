"""infra/poblar_secreto.py (H-35): archivo de origen explícito, nunca la base de pruebas, fusión con el secreto
existente y ensayo sin valores. AWS es siempre un doble: ninguna prueba sale del equipo, y el archivo que dice cuál es
el proyecto de pruebas es uno inventado (nunca el .env.supabase-pruebas de la carpeta principal)."""
import json
import re
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from infra import poblar_secreto as ps

RAIZ = Path(__file__).resolve().parent.parent
ARN = "arn:aws:secretsmanager:us-east-1:000000000000:secret:Configuracion-abc123"
PRUEBAS = "pruebasinventadoabcde"
PRODUCCION = "produccionabcdefghijk"


@pytest.fixture(autouse=True)
def proyecto_de_pruebas(tmp_path, monkeypatch):
    """El proyecto de pruebas sale de un archivo local; aquí, de uno inventado."""
    archivo = tmp_path / ".env.supabase-pruebas"
    archivo.write_text(f"DATABASE_URL=postgresql://postgres.{PRUEBAS}:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres\n")
    monkeypatch.setattr(ps, "ARCHIVOS_PRUEBAS", [tmp_path / "no-esta" / ".env.supabase-pruebas", archivo])
    return archivo

# Lo que la aplicación lee del entorno y no va en el secreto, con su razón
FUERA_DEL_SECRETO = {
    "DATABASE_URL": "se arma aparte, con la contraseña y el agrupador en modo transacción",
    "DATABASE_PASSWORD": "va dentro de DATABASE_URL",
    "SECRETO_ARN": "lo pone la pila en la función",
    "ENTORNO": "lo pone la pila en la función",
    "AWS_LAMBDA_FUNCTION_NAME": "lo pone Lambda",
    "APP_CLAVE": "nadie la lee; se retira del secreto",
    "PREPARAR_BASE_LOCAL": "solo en local",
    "CUENTAS_DEMO": "solo en local",
    "DIRECTORIO_ARCHIVOS": "solo en local: en la nube los archivos van a Supabase",
    "GEOGRAFIA_DIR": "solo en pruebas",
    "MONITOREO_AHORA": "solo en demostraciones locales",
    "ADMIN_INICIAL_CORREO": "lo usa la migración, que corre desde el equipo",
    "ADMIN_INICIAL_CLAVE": "lo usa la migración, que corre desde el equipo",
    "USUARIO_DEMO_CORREO": "lo usa la migración, que corre desde el equipo",
    "USUARIO_DEMO_CLAVE": "lo usa la migración, que corre desde el equipo",
}


class Nube:
    """Doble de boto3: una pila con su secreto. Anota qué se pidió y qué se subió."""

    def __init__(self, actual: dict | None = None):
        self.actual, self.subido, self.clientes = actual, None, []

    def client(self, nombre, **_):
        self.clientes.append(nombre)
        return self

    def describe_stacks(self, StackName):  # noqa: N803  nombres de la API de AWS
        assert StackName == "OperacionBase"
        return {"Stacks": [{"Outputs": [{"OutputKey": "SecretoArn", "OutputValue": ARN}]}]}

    def get_secret_value(self, SecretId):  # noqa: N803
        assert SecretId == ARN
        if self.actual is None:   # el secreto existe pero nunca se pobló
            raise ClientError({"Error": {"Code": "ResourceNotFoundException", "Message": "sin valor"}}, "GetSecretValue")
        return {"SecretString": json.dumps(self.actual)}

    def put_secret_value(self, SecretId, SecretString):  # noqa: N803
        assert SecretId == ARN
        self.subido = json.loads(SecretString)


def _archivo(tmp_path: Path, **valores) -> str:
    base = {"DATABASE_URL": f"postgresql://postgres.{PRODUCCION}:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
            "DATABASE_PASSWORD": "cl@ve/rara", "SUPABASE_URL": f"https://{PRODUCCION}.supabase.co",
            "SUPABASE_SERVICE_KEY": "servicio-secreta", "SERPAPI_KEY": "serp-secreta",
            "TELEGRAM_BOT_TOKEN": "bot-inventado", "TELEGRAM_WEBHOOK_SECRETO": "entrada-inventada"}
    ruta = tmp_path / ".env.produccion"
    ruta.write_text("".join(f"{k}={v}\n" for k, v in {**base, **valores}.items()))
    return str(ruta)


def test_el_archivo_de_origen_es_obligatorio():
    with pytest.raises(SystemExit) as e:
        ps.main([], sesion=Nube())
    assert e.value.code == 2   # argparse: falta --env


def test_un_archivo_que_no_existe_se_detiene(tmp_path):
    nube = Nube()
    with pytest.raises(SystemExit, match="No existe"):
        ps.main(["--env", str(tmp_path / "no-esta")], sesion=nube)
    assert nube.clientes == []


@pytest.mark.parametrize("clave,valor", [
    ("DATABASE_URL", f"postgresql://postgres.{PRUEBAS}:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres"),
    ("DATABASE_URL", f"postgresql://postgres:[YOUR-PASSWORD]@db.{PRUEBAS}.supabase.co:5432/postgres"),
    ("SUPABASE_URL", f"https://{PRUEBAS}.supabase.co"),
])
def test_nunca_sube_el_proyecto_de_pruebas_a_produccion(tmp_path, clave, valor):
    nube = Nube(actual={})
    with pytest.raises(SystemExit, match="pruebas"):
        ps.main(["--env", _archivo(tmp_path, **{clave: valor})], sesion=nube)
    assert nube.subido is None


def test_tampoco_si_el_proyecto_de_pruebas_ya_estaba_en_el_secreto(tmp_path):
    ruta = tmp_path / ".env.parcial"
    ruta.write_text(f"DATABASE_URL=postgresql://postgres.{PRODUCCION}:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres\n")
    nube = Nube(actual={"SUPABASE_URL": f"https://{PRUEBAS}.supabase.co"})
    with pytest.raises(SystemExit, match="pruebas"):
        ps.main(["--env", str(ruta), "--sin-telegram"], sesion=nube)
    assert nube.subido is None


def test_sin_el_archivo_del_proyecto_de_pruebas_no_se_sigue(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "ARCHIVOS_PRUEBAS", [tmp_path / "no-esta" / ".env.supabase-pruebas"])
    nube = Nube(actual={})
    with pytest.raises(SystemExit, match="supabase-pruebas"):
        ps.main(["--env", _archivo(tmp_path), "--ensayo"], sesion=nube)
    assert nube.clientes == []


def test_el_identificador_de_pruebas_no_esta_en_el_codigo():
    assert not hasattr(ps, "PROYECTO_PRUEBAS")
    assert re.search(r"[a-z]{20}", (RAIZ / "infra" / "poblar_secreto.py").read_text()) is None


def test_fusiona_con_lo_que_ya_tiene_el_secreto_y_retira_app_clave(tmp_path):
    nube = Nube(actual={"PUESTA_A_MANO": "conservar", "SERPAPI_KEY": "vieja", "APP_CLAVE": "nadie-la-lee"})
    ps.main(["--env", _archivo(tmp_path)], sesion=nube)
    assert nube.subido["PUESTA_A_MANO"] == "conservar"
    assert nube.subido["SERPAPI_KEY"] == "serp-secreta"
    assert "APP_CLAVE" not in nube.subido


def test_un_secreto_sin_valor_todavia_se_puebla(tmp_path):
    nube = Nube(actual=None)
    ps.main(["--env", _archivo(tmp_path)], sesion=nube)
    assert nube.subido["SUPABASE_SERVICE_KEY"] == "servicio-secreta"


def test_la_base_va_por_el_agrupador_en_modo_transaccion_con_la_contrasena(tmp_path):
    nube = Nube(actual={})
    ps.main(["--env", _archivo(tmp_path)], sesion=nube)
    assert nube.subido["DATABASE_URL"] == (f"postgresql://postgres.{PRODUCCION}:cl%40ve%2Frara"
                                           "@aws-0-us-east-1.pooler.supabase.com:6543/postgres")
    assert "DATABASE_PASSWORD" not in nube.subido


def test_incluye_asesor_pinecone_y_origenes_web(tmp_path):
    extra = {"ASESOR_API_URL": "https://asesor.example", "ASESOR_API_KEY": "a", "ASESOR_AGENTE_ID": "ag",
             "ASESOR_ENTORNO_ID": "en", "ASESOR_AGENTE_VERSION": "3", "ASESOR_CABECERAS": '{"x":"1"}',
             "PINECONE_API_KEY": "p", "PINECONE_INDICE": "asistente-fichas", "PINECONE_HOST": "h.pinecone.io",
             "ORIGENES_WEB": "https://software.nataliaremolinarodriguez.com"}
    nube = Nube(actual={})
    ps.main(["--env", _archivo(tmp_path, **extra)], sesion=nube)
    assert extra.items() <= nube.subido.items()


def test_las_claves_vacias_del_archivo_no_borran_las_del_secreto(tmp_path):
    nube = Nube(actual={"SERPAPI_KEY": "puesta"})
    ps.main(["--env", _archivo(tmp_path, SERPAPI_KEY="")], sesion=nube)
    assert nube.subido["SERPAPI_KEY"] == "puesta"


@pytest.mark.parametrize("falta", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRETO"])
def test_sin_las_claves_de_telegram_el_ensayo_se_detiene(tmp_path, capsys, falta):
    # El webhook del paso 6 se registra con este mismo archivo: si faltaran, saldrían de otro lado
    nube = Nube(actual={})
    with pytest.raises(SystemExit, match=falta):
        ps.main(["--env", _archivo(tmp_path, **{falta: ""}), "--ensayo"], sesion=nube)
    assert nube.clientes == []
    assert "bot-inventado" not in capsys.readouterr().out


def test_sin_las_claves_de_telegram_tampoco_se_sube(tmp_path):
    nube = Nube(actual={"TELEGRAM_BOT_TOKEN": "de-antes", "TELEGRAM_WEBHOOK_SECRETO": "de-antes"})
    with pytest.raises(SystemExit, match="TELEGRAM_BOT_TOKEN"):
        ps.main(["--env", _archivo(tmp_path, TELEGRAM_BOT_TOKEN="")], sesion=nube)
    assert nube.subido is None


def test_el_ensayo_nombra_las_claves_de_telegram(tmp_path, capsys):
    ps.main(["--env", _archivo(tmp_path), "--ensayo"], sesion=Nube())
    salida = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN" in salida and "TELEGRAM_WEBHOOK_SECRETO" in salida
    assert "bot-inventado" not in salida and "entrada-inventada" not in salida


def test_sin_telegram_se_puede_saltar_a_proposito(tmp_path, capsys):
    nube = Nube(actual={"TELEGRAM_BOT_TOKEN": "de-antes"})
    ruta = _archivo(tmp_path, TELEGRAM_BOT_TOKEN="", TELEGRAM_WEBHOOK_SECRETO="")
    ps.main(["--env", ruta, "--ensayo", "--sin-telegram"], sesion=nube)
    assert "paso 6" in capsys.readouterr().out
    ps.main(["--env", ruta, "--sin-telegram"], sesion=nube)
    assert nube.subido["TELEGRAM_BOT_TOKEN"] == "de-antes"   # lo que ya tenía el secreto no se toca


def test_el_ensayo_dice_las_claves_sin_valores_y_no_toca_aws(tmp_path, capsys):
    nube = Nube(actual={})
    ps.main(["--env", _archivo(tmp_path, ORIGENES_WEB="https://software.nataliaremolinarodriguez.com"), "--ensayo"], sesion=nube)
    salida = capsys.readouterr().out
    assert nube.clientes == [] and nube.subido is None
    for clave in ("DATABASE_URL", "SUPABASE_SERVICE_KEY", "SERPAPI_KEY", "ORIGENES_WEB"):
        assert clave in salida
    for valor in ("servicio-secreta", "serp-secreta", "cl@ve", PRODUCCION, "software.nataliaremolinarodriguez.com"):
        assert valor not in salida


def test_la_carga_de_verdad_tampoco_imprime_valores(tmp_path, capsys):
    ps.main(["--env", _archivo(tmp_path)], sesion=Nube(actual={"PUESTA_A_MANO": "conservar"}))
    salida = capsys.readouterr().out
    assert "PUESTA_A_MANO" in salida
    for valor in ("servicio-secreta", "serp-secreta", "conservar", PRODUCCION, ARN):
        assert valor not in salida


def test_toda_variable_que_lee_la_aplicacion_va_en_el_secreto_o_tiene_su_razon():
    leidas = set()
    for archivo in (RAIZ / "app").rglob("*.py"):
        leidas |= set(re.findall(r'(?:_txt|os\.getenv|os\.environ\.get)\("([A-Z0-9_]+)"', archivo.read_text()))
    sin_destino = leidas - set(ps.CLAVES) - set(FUERA_DEL_SECRETO)
    assert not sin_destino, f"decidir si van en el secreto: {sorted(sin_destino)}"
    assert "APP_CLAVE" not in ps.CLAVES


def test_un_secreto_recien_creado_por_cdk_no_es_configuracion():
    """CDK crea el secreto con una contraseña aleatoria (GenerateSecretString): leerlo no debe romper la carga."""
    class Recien(Nube):
        def get_secret_value(self, SecretId):  # noqa: N803
            return {"SecretString": "aB3$kL9!qW7zR2#xV5"}
    assert ps._actual(Recien(), ARN) == {}
