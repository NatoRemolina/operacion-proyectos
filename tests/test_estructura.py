"""Puntos de extensión: un área nueva se añade con archivos propios, sin editar los compartidos."""
from sqlalchemy import Column, Text

from app import db, web
from app.main import app


def test_cada_modulo_de_rutas_queda_cargado():
    rutas = {r.path for r in app.routes}
    for esperada in ("/", "/viajes/nuevo", "/gastos/cargar", "/viaje/{vid}", "/admin/viajes", "/admin/proyectos",
                     "/admin/monitoreo", "/api/metricas", "/admin/usuarios", "/reglas", "/telegram/webhook", "/mi-cuenta"):
        assert esperada in rutas, esperada


def test_el_menu_sale_de_lo_que_declara_cada_modulo(cliente, piloto):
    textos = [e["texto"] for e in web.menu_para({"rol": "admin"})]
    assert textos.index("Inicio") < textos.index("Cotizar viaje") < textos.index("Viajes") < textos.index("Gastos") < textos.index("Monitoreo")
    assert "Mis viajes" not in textos and "Mis viajes" in [e["texto"] for e in web.menu_para({"rol": "piloto"})]
    web.MENU.append({"texto": "Área de prueba", "href": "/admin/area-de-prueba", "orden": 65, "rol": "admin"})
    try:
        assert "Área de prueba" in cliente.get("/").text and "Área de prueba" not in piloto.get("/").text
    finally:
        web.MENU.pop()


def test_un_servicio_puede_declarar_su_propia_tabla():
    db._tabla("zz_tabla_de_prueba", Column("nota", Text))
    db.crear_tablas()
    fila = db.insertar("zz_tabla_de_prueba", nota="hola")
    assert db.uno("select nota from zz_tabla_de_prueba where id=:i", i=fila)["nota"] == "hola"


def test_los_contadores_del_menu_salen_en_todas_las_pantallas(cliente, nuevo_viaje):
    """Dos pantallas usan «pendientes» para sus propios datos; el contador del menú no debe depender de ese nombre."""
    nuevo_viaje(aprobar=False)
    for pagina in ("/", "/admin/viajes", "/proyectos/1", "/gastos"):
        assert 'class="cuenta"' in cliente.get(pagina).text, pagina
