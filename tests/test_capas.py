"""Rutas delgadas: la lógica, el SQL y el HTML con JavaScript viven en servicios y plantillas; las rutas validan,
autorizan y llaman. Ninguna ruta importa otra ruta ni un servicio importa una ruta."""
import ast
from pathlib import Path

from sqlalchemy import event

from app import config, db
from app.servicios import analitica

APP = Path(config.RAIZ) / "app"


def _importa(archivo: Path) -> set[str]:
    """Los módulos de `app` que importa un archivo, con su nombre completo (app.rutas.v1_gastos, app.servicios.viajes...)."""
    paquete = ".".join(archivo.relative_to(config.RAIZ).with_suffix("").parts[:-1])
    nombres = set()
    for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.ImportFrom):
            base = paquete.rsplit(".", nodo.level - 1)[0] if nodo.level else ""
            modulo = ".".join(x for x in (base, nodo.module or "") if x)
            nombres |= {f"{modulo}.{a.name}" for a in nodo.names} | {modulo}
        elif isinstance(nodo, ast.Import):
            nombres |= {a.name for a in nodo.names}
    return nombres


def _rutas() -> set[str]:
    return {f"app.rutas.{p.stem}" for p in (APP / "rutas").glob("*.py") if p.stem != "__init__"}


def test_ninguna_ruta_importa_otra_ruta():
    rutas = _rutas()
    cruces = {p.name: sorted(_importa(p) & (rutas - {f"app.rutas.{p.stem}"})) for p in (APP / "rutas").glob("*.py")}
    assert {k: v for k, v in cruces.items() if v} == {}


def test_ningun_servicio_importa_una_ruta():
    cruces = {p.name: sorted(n for n in _importa(p) if n.startswith("app.rutas")) for p in (APP / "servicios").glob("*.py")}
    assert {k: v for k, v in cruces.items() if v} == {}


def test_las_rutas_no_arman_html_con_javascript():
    con_script = [p.name for p in (APP / "rutas").glob("*.py") if "<script" in p.read_text(encoding="utf-8")]
    assert con_script == []


def test_el_historial_de_las_rutas_se_lee_en_una_sola_consulta():
    lecturas = []

    def anotar(_conexion, _cursor, sql, *_):
        if "from historial_ruta" in " ".join(sql.split()):
            lecturas.append(sql)
    ids = [db.insertar("solicitudes", origen="ZHA", destino=f"ZH{n}", ida="2031-07-01", regreso="2031-07-04",
                       estado="comparando", creado="2031-06-01 10:00:00") for n in "BCD"]
    db.insertar("historial_ruta", busqueda="ZHA_ZHB_2031-07-01_2031-07-04", origen="ZHA", destino="ZHB", fecha="2031-05-01",
                precio=300)
    event.listen(db.motor, "before_cursor_execute", anotar)
    try:
        r = analitica.resumen()
    finally:
        event.remove(db.motor, "before_cursor_execute", anotar)
        db.ejecutar("delete from historial_ruta where busqueda like 'ZHA_%'")
        for i in ids:
            db.ejecutar("delete from solicitudes where id=:i", i=i)
    assert len(lecturas) == 1   # una sola consulta, no una por cotización
    assert any(h["clave"] == "ZHA_ZHB_2031-07-01_2031-07-04" for h in r["historiales"])
