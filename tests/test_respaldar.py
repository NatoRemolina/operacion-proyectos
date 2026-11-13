"""El ensayo de restauración se niega a pisar el origen o una base principal, y detecta un respaldo alterado.

Estas pruebas no se conectan a ninguna base: las protecciones se comprueban antes de conectar.
"""
import hashlib
import json

import pytest

from datos import respaldar

# Cadenas armadas por partes: son de prueba y así no tienen la forma de una credencial real
SERVIDOR = "@aws-1-us-east-1.pooler.supabase.com:5432/postgres"
ORIGEN = "postgresql://postgres.origen:" + "clave-a" + SERVIDOR
OTRO = "postgresql://postgres.pruebas:" + "clave-b" + SERVIDOR


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
    assert respaldar._entorno(str(archivo))["url"] == "postgresql://u:" + "a%40b%2Fc" + "@h:5432/postgres"
    assert respaldar._partes(respaldar._entorno(str(archivo))["url"])["clave"] == "a@b/c"



def test_variables_pg_para_eval_sin_mostrar_la_clave_partida(tmp_path):
    import subprocess
    archivo = tmp_path / "base.env"
    clave = "cl@ve/ra'ra" + "!x"   # con caracteres que la terminal y la dirección interpretan
    archivo.write_text("DATABASE_URL=postgresql://postgres.proyecto:[YOUR-PASSWORD]" + "@servidor.example:5432/postgres\n"
                       + f"DATABASE_PASSWORD={clave}\n")
    orden = respaldar.variables_pg(str(archivo))
    guion = f"{orden}; printf '%s|%s|%s|%s' \"$PGHOST\" \"$PGPORT\" \"$PGUSER\" \"$PGPASSWORD\""
    salida = subprocess.run(["/bin/sh", "-c", guion], capture_output=True, text=True, check=True).stdout  # noqa: S603  orden fija de esta prueba
    assert salida == f"servidor.example|5432|postgres.proyecto|{clave}"
