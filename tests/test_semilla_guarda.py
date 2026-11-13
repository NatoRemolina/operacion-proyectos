"""`python -m datos.semilla` sobre una base que no es local (H-34): pide confirmación escrita, exige el puerto de sesión
y un respaldo reciente de esa misma base. Nada se conecta de verdad: la semilla es un doble y las bases son inventadas."""
import json
from datetime import UTC, datetime, timedelta

import pytest

from app import config
from datos import importar_entorno, respaldar, semilla

PROYECTO = "destinoabcdefghijklm"
REMOTA = f"postgresql://postgres.{PROYECTO}:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres"


@pytest.fixture()
def entorno(monkeypatch, tmp_path):
    """Respaldos en una carpeta temporal, ninguna base publicada conocida y una semilla que solo anota."""
    llamadas = []
    monkeypatch.setattr(semilla, "sembrar", lambda: llamadas.append("sembrar") or {})
    monkeypatch.setattr(respaldar, "DIR_RESPALDOS", tmp_path / "respaldos")
    monkeypatch.setattr(importar_entorno, "ARCHIVOS_PUBLICADA", [])
    monkeypatch.setattr(config, "DATABASE_URL", REMOTA)
    return llamadas


def _respaldo(url: str = REMOTA, horas: float = 1, alterado: bool = False):
    momento = datetime.now(UTC) - timedelta(hours=horas)
    carpeta = respaldar.DIR_RESPALDOS / momento.strftime("%Y-%m-%d_%H%M%S")
    carpeta.mkdir(parents=True)
    (carpeta / "base.dump").write_bytes(b"copia")
    archivos = {"base.dump": {"bytes": 5, "sha256": respaldar._sha(carpeta / "base.dump")}}
    (carpeta / "manifiesto.json").write_text(json.dumps({"momento": momento.isoformat(timespec="seconds"),
                                                         "origen": respaldar.identidad(url.replace("[YOUR-PASSWORD]", "inventada")), "filas": {}, "archivos": archivos}))
    if alterado:
        (carpeta / "base.dump").write_bytes(b"otra")


def _nadie_responde(_):
    raise AssertionError("no debía preguntar")


@pytest.mark.parametrize("url", ["", "sqlite:///datos/local.db", "postgresql://operacion:[YOUR-PASSWORD]@127.0.0.1:5433/operacion",
                                 "postgresql://operacion:[YOUR-PASSWORD]@db:5432/operacion"])
def test_una_base_local_se_migra_sin_preguntar(entorno, monkeypatch, url):
    monkeypatch.setattr(config, "DATABASE_URL", url)
    assert semilla.main([], entrada=_nadie_responde) == 0
    assert entorno == ["sembrar"]


def test_sin_respaldo_no_se_migra(entorno):
    with pytest.raises(SystemExit, match="respaldo"):
        semilla.main(["--confirmar", PROYECTO], entrada=_nadie_responde)
    assert entorno == []


def test_un_respaldo_viejo_no_vale(entorno):
    _respaldo(horas=semilla.RESPALDO_VIGENTE.total_seconds() / 3600 + 1)
    with pytest.raises(SystemExit, match="respaldo"):
        semilla.main(["--confirmar", PROYECTO], entrada=_nadie_responde)
    assert entorno == []


def test_un_respaldo_de_otra_base_no_vale(entorno):
    _respaldo(url="postgresql://postgres.otroproyectoabcdefgh:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres")
    with pytest.raises(SystemExit, match="respaldo"):
        semilla.main(["--confirmar", PROYECTO], entrada=_nadie_responde)
    assert entorno == []


def test_un_respaldo_alterado_no_vale(entorno):
    _respaldo(alterado=True)
    with pytest.raises(SystemExit, match="huella"):
        semilla.main(["--confirmar", PROYECTO], entrada=_nadie_responde)
    assert entorno == []


def test_por_el_agrupador_de_transaccion_no_se_migra(entorno, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", REMOTA.replace(":5432/", ":6543/"))
    with pytest.raises(SystemExit, match="5432"):
        semilla.main(["--confirmar", PROYECTO], entrada=_nadie_responde)
    assert entorno == []


def test_pide_escribir_el_nombre_del_destino(entorno, capsys):
    _respaldo()
    preguntas = []
    assert semilla.main([], entrada=lambda p: preguntas.append(p) or PROYECTO) == 0
    assert entorno == ["sembrar"] and PROYECTO in preguntas[0]
    assert "[YOUR-PASSWORD]" not in capsys.readouterr().out


def test_una_respuesta_distinta_no_migra(entorno):
    _respaldo()
    with pytest.raises(SystemExit, match="No se migró"):
        semilla.main([], entrada=lambda _: "si")
    assert entorno == []


def test_la_confirmacion_puede_ir_en_la_orden(entorno):
    _respaldo()
    assert semilla.main(["--confirmar", PROYECTO], entrada=_nadie_responde) == 0
    assert entorno == ["sembrar"]


def test_avisa_cuando_el_destino_es_la_base_publicada(entorno, monkeypatch, tmp_path, capsys):
    publicada = tmp_path / ".env.supabase-publicada"
    publicada.write_text(f"DATABASE_URL={REMOTA}\n")
    monkeypatch.setattr(importar_entorno, "ARCHIVOS_PUBLICADA", [publicada])
    _respaldo()
    semilla.main(["--confirmar", PROYECTO], entrada=_nadie_responde)
    assert "base publicada" in capsys.readouterr().out.lower()
