"""El ensayo de restauración se niega a pisar el origen o una base principal, y detecta un respaldo alterado.

Estas pruebas no se conectan a ninguna base: las protecciones se comprueban antes de conectar.
"""
import hashlib
import json

import pytest

from datos import respaldar

ORIGEN = "postgresql://postgres.origen:clave-a@aws-1-us-east-1.pooler.supabase.com:5432/postgres"
OTRO = "postgresql://postgres.pruebas:clave-b@aws-1-us-east-1.pooler.supabase.com:5432/postgres"


def _respaldo(tmp_path, origen=ORIGEN):
    carpeta = tmp_path / "respaldo"
    carpeta.mkdir()
    (carpeta / "base.dump").write_bytes(b"copia")
    manifiesto = {"origen": respaldar.identidad(origen), "filas": {"gastos": 1},
                  "archivos": {"base.dump": {"bytes": 5, "sha256": hashlib.sha256(b"copia").hexdigest()}}}
    (carpeta / "manifiesto.json").write_text(json.dumps(manifiesto))
    return carpeta


def _env(tmp_path, url, nombre="destino.env"):
    archivo = tmp_path / nombre
    archivo.write_text(f"DATABASE_URL={url}\n")
    return str(archivo)


def test_la_identidad_no_depende_de_la_contrasena():
    assert respaldar.identidad(ORIGEN) == respaldar.identidad(ORIGEN.replace("clave-a", "otra"))
    assert respaldar.identidad(ORIGEN) != respaldar.identidad(OTRO)
    assert "clave-a" not in respaldar.identidad(ORIGEN)


def test_no_restaura_sobre_el_mismo_origen(tmp_path):
    with pytest.raises(SystemExit, match="mismo servidor"):
        respaldar.verificar(str(_respaldo(tmp_path)), _env(tmp_path, ORIGEN), "ensayo")


@pytest.mark.parametrize("base", ["postgres", "template1", "mal-nombre;", ""])
def test_no_restaura_en_la_base_principal_ni_con_nombres_raros(tmp_path, base):
    with pytest.raises(SystemExit, match="base nueva"):
        respaldar.verificar(str(_respaldo(tmp_path)), _env(tmp_path, OTRO), base)


def test_detecta_un_respaldo_alterado(tmp_path):
    carpeta = _respaldo(tmp_path)
    (carpeta / "base.dump").write_bytes(b"cambiado")
    with pytest.raises(SystemExit, match="huella"):
        respaldar.verificar(str(carpeta), _env(tmp_path, OTRO), "ensayo")


def test_la_contrasena_aparte_se_inserta_codificada(tmp_path):
    archivo = tmp_path / "p.env"
    archivo.write_text("DATABASE_URL=postgresql://u:[YOUR-PASSWORD]@h:5432/postgres\nDATABASE_PASSWORD=a@b/c\n")
    assert respaldar._entorno(str(archivo))["url"] == "postgresql://u:a%40b%2Fc@h:5432/postgres"
    assert respaldar._partes(respaldar._entorno(str(archivo))["url"])["clave"] == "a@b/c"
