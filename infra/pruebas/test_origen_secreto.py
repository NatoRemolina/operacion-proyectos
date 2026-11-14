"""ORIGEN_SECRETO en el secreto (B1): el valor de la cabecera X-Origen-CloudFront que CloudFront añade hacia la API.

Nadie necesita conocerlo: si ni el archivo ni el secreto lo traen, poblar_secreto lo genera. Una vez en el secreto no
se cambia solo, porque CloudFront lo copió al desplegar OperacionWeb. AWS es siempre un doble.
(Junto a tests/test_poblar_secreto.py, que es del frente de backend; esta prueba corre con `pytest infra/pruebas`.)"""
import json

import pytest

from infra import poblar_secreto as ps

ARN = "arn:aws:secretsmanager:us-east-1:000000000000:secret:Configuracion-abc123"
PRODUCCION = "produccionabcdefghijk"


@pytest.fixture(autouse=True)
def proyecto_de_pruebas(tmp_path, monkeypatch):
    archivo = tmp_path / ".env.supabase-pruebas"
    archivo.write_text("DATABASE_URL=postgresql://postgres.pruebasinventadoabcde:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres\n")
    monkeypatch.setattr(ps, "ARCHIVOS_PRUEBAS", [archivo])


class Nube:
    def __init__(self, actual: dict):
        self.actual, self.subido = actual, None

    def client(self, nombre, **_):
        return self

    def describe_stacks(self, StackName):  # noqa: N803
        return {"Stacks": [{"Outputs": [{"OutputKey": "SecretoArn", "OutputValue": ARN}]}]}

    def get_secret_value(self, SecretId):  # noqa: N803
        return {"SecretString": json.dumps(self.actual)}

    def put_secret_value(self, SecretId, SecretString):  # noqa: N803
        self.subido = json.loads(SecretString)


def _archivo(tmp_path, **valores) -> str:
    base = {"DATABASE_URL": f"postgresql://postgres.{PRODUCCION}:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
            "DATABASE_PASSWORD": "clave-inventada", "SUPABASE_URL": f"https://{PRODUCCION}.supabase.co",
            "SUPABASE_SERVICE_KEY": "servicio-secreta"}
    ruta = tmp_path / ".env.produccion"
    ruta.write_text("".join(f"{k}={v}\n" for k, v in {**base, **valores}.items()))
    return str(ruta)


def test_es_una_clave_del_secreto():
    assert "ORIGEN_SECRETO" in ps.CLAVES


def test_si_falta_se_genera_larga_y_no_se_imprime(tmp_path, capsys):
    nube = Nube(actual={})
    ps.main(["--env", _archivo(tmp_path), "--sin-telegram"], sesion=nube)
    valor = nube.subido["ORIGEN_SECRETO"]
    assert len(valor) >= 32
    salida = capsys.readouterr().out
    assert "ORIGEN_SECRETO" in salida and valor not in salida


def test_la_que_ya_tiene_el_secreto_se_conserva(tmp_path):
    nube = Nube(actual={"ORIGEN_SECRETO": "x" * 40})
    ps.main(["--env", _archivo(tmp_path), "--sin-telegram"], sesion=nube)
    assert nube.subido["ORIGEN_SECRETO"] == "x" * 40


def test_la_del_archivo_manda(tmp_path):
    nube = Nube(actual={"ORIGEN_SECRETO": "x" * 40})
    ps.main(["--env", _archivo(tmp_path, ORIGEN_SECRETO="y" * 40), "--sin-telegram"], sesion=nube)
    assert nube.subido["ORIGEN_SECRETO"] == "y" * 40


def test_el_ensayo_avisa_que_se_generaria_sin_tocar_aws(tmp_path, capsys):
    ps.main(["--env", _archivo(tmp_path), "--sin-telegram", "--ensayo"])
    assert "ORIGEN_SECRETO" in capsys.readouterr().out
