"""B4: lo que corre la integración continua en cada push a main y dev y en cada pull request."""
from pathlib import Path

import yaml

FLUJO = yaml.safe_load((Path(__file__).resolve().parents[2] / ".github/workflows/pruebas.yml").read_text(encoding="utf-8"))
TRABAJOS = FLUJO["jobs"]


def ordenes(trabajo: str) -> str:
    return "\n".join(str(p.get("run", "")) for p in TRABAJOS[trabajo]["steps"])


def test_python_con_su_revision_sus_pruebas_y_las_de_infraestructura():
    texto = ordenes("calidad")
    assert "ruff check ." in texto and "pytest -q" in texto and "pytest -q infra/pruebas" in texto


def test_un_trabajo_con_postgresql_de_servicio_corre_la_migracion_y_la_suite():
    pg = TRABAJOS["postgres"]
    (servicio,) = pg["services"].values()
    assert servicio["image"].startswith("postgres:17") and "@sha256:" in servicio["image"]
    texto = ordenes("postgres")
    assert texto.count("python -m datos.semilla") == 2, "la migración se corre dos veces: es idempotente"
    assert "python -m datos.comprobar_supabase" in texto
    assert "PRUEBAS_DATABASE_URL=" in texto and "pytest" in texto


def test_la_imagen_del_analizador_se_construye_y_se_prueba_sin_red():
    texto = ordenes("analizador")
    assert "--target pruebas" in texto and "--network none" in texto and "analizador/pruebas" in texto
    assert "--target produccion" in texto


def test_la_web_pasa_tipos_revision_pruebas_y_compilacion():
    texto = ordenes("web")
    for orden in ("npm ci", "npm run typecheck", "npm run lint", "npm test", "npm run build"):
        assert orden in texto, orden


def test_la_infraestructura_pasa_sus_pruebas_y_se_sintetiza_con_y_sin_dominio():
    texto = ordenes("infra")
    assert "npm test" in texto
    sintesis = [linea for linea in texto.splitlines() if "cdk synth" in linea]
    assert any("dominio=" in s for s in sintesis) and any("dominio=" not in s for s in sintesis)
    assert any("waf=1" in s for s in sintesis)


def test_corre_en_main_dev_y_pull_requests_con_permisos_de_solo_lectura():
    disparadores = FLUJO.get("on", FLUJO.get(True))   # YAML 1.1 lee «on» como verdadero
    assert disparadores["push"]["branches"] == ["main", "dev"] and "pull_request" in disparadores
    assert FLUJO["permissions"] == {"contents": "read"}
