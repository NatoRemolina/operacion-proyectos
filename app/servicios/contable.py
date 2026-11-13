"""Excel contable: los gastos de un periodo, listos para contabilidad, sin copiar nada a mano.

Hoja «Gastos», una fila por gasto con su cuenta contable, y hoja «Resumen» con los totales y los parámetros del libro.
Lo que entra al libro lo decide el permiso de quien lo pide (`acceso.alcance`, y `acceso.puede_ver` para el filtro de
proyecto), nunca un parámetro sin comprobar. Todo texto pasa por `exportacion.celda()`: el libro no lleva fórmulas.
Solo lee: lo usa también el guion de consola, que corre en solo lectura.
"""
import calendar
import io
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .. import config, db
from . import acceso, consultas, eventos, exportacion, viajes

ESTADOS_LIBRO = ("aprobado", "aprobado_auto")
# Supuesto: el mes y el año en curso se cuentan en la hora del este de EE. UU. (la de Miami). En UTC, la hora de la nube,
# desde las 19:00 o 20:00 de Miami del último día del mes ya sería el mes siguiente.
ZONA_EMPRESA = ZoneInfo("America/New_York")
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Mapa categoría → cuenta. Es un supuesto: se edita en «Reglas y supuestos» (claves `cuenta_contable_<categoría>`)
# y contabilidad debe confirmarlo con su plan de cuentas. Estos valores solo siembran la regla y la suplen si falta.
PREFIJO_CUENTA = "cuenta_contable_"
CUENTAS = {
    "vuelo": "6110 Viajes: pasajes aéreos",
    "hotel": "6120 Viajes: alojamiento",
    "alquiler_carro": "6130 Viajes: alquiler de vehículos",
    "transporte_terrestre": "6135 Viajes: transporte terrestre",
    "combustible": "6140 Viajes: combustible",
    "comida": "6150 Viajes: alimentación",
    "parqueo_peajes": "6160 Viajes: parqueaderos y peajes",
    "compras_proyecto": "6210 Proyectos: compras y materiales",
    "otros": "6190 Viajes: otros gastos de viaje",
}
SIN_CUENTA = "Sin cuenta asignada"

# Pasos de la bitácora que dejan un gasto aprobado, según quién lo aprobó
APROBADO_EN_REVISION = ("corregido y aprobado", "aprobado con excepción")
APROBADO_POR_REGLAS = ("aprobado sin intervención", "asignado a viaje")
APROBACION_AUTOMATICA = "Automática (reglas de validación)"

IMPORTE, TASA, FECHA, INSTANTE = "#,##0.00", "0.00####", "yyyy-mm-dd", "yyyy-mm-dd hh:mm"
COLUMNAS = [
    {"titulo": "N.º gasto", "ancho": 10},
    {"titulo": "Fecha", "ancho": 12, "formato": FECHA},
    {"titulo": "Viaje", "ancho": 14},
    {"titulo": "Proyecto", "ancho": 30},
    {"titulo": "Código persona", "ancho": 14},
    {"titulo": "Persona", "ancho": 24},
    {"titulo": "Proveedor o comercio", "ancho": 30},
    {"titulo": "Categoría", "ancho": 18},
    {"titulo": "Cuenta contable", "ancho": 34},
    {"titulo": "Base", "ancho": 12, "formato": IMPORTE},
    {"titulo": "Impuesto", "ancho": 12, "formato": IMPORTE},
    {"titulo": "Propina", "ancho": 12, "formato": IMPORTE},
    {"titulo": "Total", "ancho": 13, "formato": IMPORTE},
    {"titulo": "Moneda", "ancho": 9},
    {"titulo": "Tasa a USD", "ancho": 12, "formato": TASA},
    {"titulo": "Total USD", "ancho": 13, "formato": IMPORTE},
    {"titulo": "Estado", "ancho": 20},
    {"titulo": "Aprobado por", "ancho": 30},
    {"titulo": "Aprobado el (UTC)", "ancho": 18, "formato": INSTANTE},
    {"titulo": "Alertas o excepción", "ancho": 50},
    {"titulo": "Soporte en la plataforma", "ancho": 42},
]
ALCANCE = {"admin": "Administración: todos los gastos",
           "gestor": "Gestión de proyecto: sus gastos y los de los proyectos que gestiona",
           "colaborador": "Colaborador: solo sus gastos"}
NOTA_CUENTAS = ("Supuesto editable en «Reglas y supuestos» (claves cuenta_contable_…): contabilidad debe confirmarlo "
                "con su plan de cuentas.")
NOTA_TASA = "Total en USD ÷ total: la tasa que se aplicó al validar el gasto."

_NEGRITA = Font(bold=True)
_FONDO_ENCABEZADO = PatternFill("solid", start_color="E8ECEF")
_ENLACE = Font(color="0563C1", underline="single")
_MAXIMO_TEXTO = 32000   # una celda de Excel admite 32.767 caracteres


class SinPermiso(Exception):
    """La persona pidió el libro de un proyecto que no gestiona (o que no existe: no se le revela cuál de las dos)."""


class ProyectoInexistente(ValueError):
    """Administración pidió el libro de un proyecto que no existe."""


class FechaInvalida(ValueError):
    """Una fecha del periodo no se entiende o el periodo está al revés. `campo` es 'desde' o 'hasta'."""

    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo


# ---------- mapa de cuentas ----------
def asegurar_cuentas():
    """Siembra la cuenta de cada categoría como supuesto editable; lo que ya existe no se toca."""
    for categoria, cuenta in CUENTAS.items():
        clave = PREFIJO_CUENTA + categoria
        if not db.uno("select id from reglas where ambito='supuesto' and clave=:c", c=clave):
            db.insertar("reglas", ambito="supuesto", entidad="", tarifa="", clave=clave, valor=cuenta,
                        nota=f"Cuenta contable de la categoría «{config.CATEGORIAS[categoria]}» en el Excel contable. "
                             "Supuesto: confirmar con contabilidad.",
                        fuente="Supuesto editable", confianza="supuesto", verificado=date.today().isoformat())


def cuentas() -> dict[str, str]:
    """La cuenta vigente de cada categoría: la regla editada o, si no está sembrada, el supuesto de este módulo."""
    leidas = {r["clave"].removeprefix(PREFIJO_CUENTA): (r["valor"] or "").strip() or SIN_CUENTA
              for r in db.todos("select clave, valor from reglas where ambito='supuesto'")
              if r["clave"].startswith(PREFIJO_CUENTA)}
    return {**CUENTAS, **leidas}


# ---------- parámetros ----------
def _ahora() -> datetime:
    return datetime.now(UTC)


def mes_en_curso(hoy: date | None = None) -> tuple[str, str]:
    """Del primero al último día del mes de `hoy`; sin él, el mes en curso en la zona de la empresa."""
    hoy = hoy or _ahora().astimezone(ZONA_EMPRESA).date()
    ultimo = calendar.monthrange(hoy.year, hoy.month)[1]
    return date(hoy.year, hoy.month, 1).isoformat(), date(hoy.year, hoy.month, ultimo).isoformat()


def anio_en_curso(hoy: date | None = None) -> tuple[str, str]:
    """Del 1 de enero al 31 de diciembre del año de `hoy`; sin él, el año en curso en la zona de la empresa. Es el
    periodo por omisión del libro: con un mes, los recibos del mes siguiente (un viaje próximo) quedaban fuera."""
    hoy = hoy or _ahora().astimezone(ZONA_EMPRESA).date()
    return date(hoy.year, 1, 1).isoformat(), date(hoy.year, 12, 31).isoformat()


def _fecha(valor, campo: str, cual: str) -> date:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor or "").strip())
    except ValueError as e:
        raise FechaInvalida(campo, f"La fecha {cual} debe tener la forma AAAA-MM-DD, por ejemplo 2026-11-01.") from e


def periodo(desde, hasta) -> tuple[date, date]:
    inicio, fin = _fecha(desde, "desde", "inicial"), _fecha(hasta, "hasta", "final")
    if fin < inicio:
        raise FechaInvalida("hasta", "La fecha final no puede ser anterior a la inicial.")
    return inicio, fin


MAXIMO_ID = 2_147_483_647   # los id son INTEGER: un número mayor no existe y en PostgreSQL rompería la consulta


def proyecto_de_texto(texto: str | None) -> int | None:
    """El proyecto tal como llega en la dirección de la página: vacío o 0 es «todos»; si no, su número."""
    texto = (texto or "").strip()
    if texto in ("", "0"):
        return None
    if not re.fullmatch(r"[0-9]{1,10}", texto) or int(texto) > MAXIMO_ID:
        raise ValueError("El proyecto elegido no es válido: debe ser su número, por ejemplo 3.")
    return int(texto)


def nombre_archivo(desde, hasta, proyecto_id: int | None = None) -> str:
    inicio, fin = periodo(desde, hasta)
    return f"libro_contable_{inicio}_{fin}" + (f"_proyecto_{int(proyecto_id)}" if proyecto_id else "") + ".xlsx"


def origen_publico(de_la_peticion: str = "") -> str:
    """Dirección para el enlace al soporte: la web pública si está configurada; si no, la de la petición."""
    return (config.ORIGENES_WEB[0] if config.ORIGENES_WEB else de_la_peticion).rstrip("/")


def cabeceras_descarga(desde, hasta, proyecto_id: int | None = None) -> dict:
    """Las de la página y la API: se descarga con su nombre, sin adivinar el tipo y sin quedar en caché."""
    return {"Content-Disposition": f'attachment; filename="{nombre_archivo(desde, hasta, proyecto_id)}"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def registrar_descarga(desde, hasta, proyecto_id: int | None, canal: str):
    """Deja el hecho de la descarga. Lo llaman las rutas; el guion de consola no, porque corre en solo lectura."""
    inicio, fin = periodo(desde, hasta)
    p = db.uno("select nombre from proyectos where id=:i", i=proyecto_id) if proyecto_id else None
    eventos.registrar("contabilidad", proyecto_id, "libro contable descargado",
                      f"{inicio} a {fin} · {p['nombre'] if p else 'todos los proyectos a su alcance'} · {canal}")


def _proyecto(usuario: dict, proyecto_id: int | None) -> dict | None:
    if proyecto_id is None:
        return None
    # El permiso va antes que la existencia: a quien no gestiona el proyecto no se le dice si existe
    if not acceso.puede_ver(usuario, {"proyecto_id": proyecto_id}):
        raise SinPermiso("El libro contable de un proyecto lo descargan administración y quien gestiona el proyecto.")
    p = db.uno("select id, nombre from proyectos where id=:i", i=proyecto_id)
    if not p:
        raise ProyectoInexistente("Ese proyecto no existe.")
    return p


# ---------- datos ----------
def _lista_sql(valores) -> str:
    """Constantes de este módulo como lista SQL (nunca datos de quien pide el libro)."""
    return ", ".join("'" + v.replace("'", "''") + "'" for v in valores)


def _estados(estados) -> tuple:
    estados = tuple(estados)
    if not estados or any(e not in consultas.ESTADO_GASTO for e in estados):
        raise ValueError("Hay un estado de gasto que no existe.")
    return estados


def _filas(usuario: dict, inicio: date, fin: date, proyecto: dict | None, estados: tuple) -> list[dict]:
    """Los gastos del libro con lo que lleva cada columna, ya limitados al alcance de la persona. `proyecto` es el
    del filtro, ya comprobado contra el permiso (se lee una sola vez, en `libro`)."""
    proyecto_id = proyecto["id"] if proyecto else None
    donde, p = acceso.alcance(usuario, "g")
    marcas = {f"_e{i}": e for i, e in enumerate(estados)}
    donde += f" and g.fecha>=:_desde and g.fecha<=:_hasta and g.estado in ({', '.join(':' + m for m in marcas)})"
    if proyecto_id is not None:
        donde, p = donde + " and g.proyecto_id=:_proyecto", {**p, "_proyecto": proyecto_id}
    datos = db.todos(f"""
        select q.*, pu.nombre persona_nombre, rv.nombre revisor from (
          select g.id, g.fecha, g.comercio, g.categoria, g.subtotal, g.impuesto, g.propina, g.total, g.moneda, g.total_usd,
                 g.estado, g.alertas, g.usuario_id, g.viajero_id, g.proyecto_id, g.viaje_id, g.revisado_por,
                 p.nombre proyecto, vj.creado viaje_creado, vi.nombre viajero,
                 coalesce(vj.usuario_id, (select min(x.id) from usuarios x where x.viajero_id=g.viajero_id), g.usuario_id) persona_id,
                 (select max(e.momento) from eventos e where e.entidad='gasto' and e.entidad_id=g.id
                    and e.paso in ({_lista_sql(APROBADO_EN_REVISION)})) aprobado_en_revision,
                 (select max(e.momento) from eventos e where e.entidad='gasto' and e.entidad_id=g.id
                    and e.paso in ({_lista_sql(APROBADO_POR_REGLAS)})) aprobado_por_reglas
          from gastos g left join proyectos p on p.id=g.proyecto_id left join viajes vj on vj.id=g.viaje_id
          left join viajeros vi on vi.id=g.viajero_id
          where {donde}) q
        left join usuarios pu on pu.id=q.persona_id left join usuarios rv on rv.id=q.revisado_por
        order by q.fecha, q.id""", _desde=inicio.isoformat(), _hasta=fin.isoformat(), **marcas, **p)
    # El alcance ya limitó la consulta; cada fila se comprueba otra vez con la regla de `acceso.puede_ver`, pero con
    # los proyectos del gestor leídos una sola vez: preguntarlos en cada fila serían miles de consultas
    mios = acceso.proyectos_de(usuario) if usuario.get("rol") == "gestor" else set()
    return [f for f in datos if acceso.es_propio(usuario, f) or f["proyecto_id"] in mios]


def _decimal(valor) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


def _tasa(f: dict) -> float | None:
    if f["moneda"] == "USD":
        return 1.0
    total, usd = _decimal(f["total"]), _decimal(f["total_usd"])
    return float(round(usd / total, 6)) if total and usd is not None else None


def _aprobacion(f: dict) -> tuple[str | None, str | None]:
    if f["estado"] == "aprobado":
        quien = f"{viajes.codigo_persona(f['revisado_por'])} · {f['revisor']}" if f["revisado_por"] else None
        return quien, f["aprobado_en_revision"]
    if f["estado"] == "aprobado_auto":
        return APROBACION_AUTOMATICA, f["aprobado_por_reglas"]
    return None, None


def _fila(f: dict, mapa: dict[str, str], enlace_base: str) -> list:
    quien, cuando = _aprobacion(f)
    alertas = " | ".join(str(a) for a in db.de_json(f["alertas"], []) or [])
    return [
        f["id"], _como_fecha(f["fecha"]),
        viajes.codigo_viaje({"id": f["viaje_id"], "creado": f["viaje_creado"]}) if f["viaje_id"] else None,
        f["proyecto"], viajes.codigo_persona(f["persona_id"]) if f["persona_id"] else None,
        f["persona_nombre"] or f["viajero"], f["comercio"],
        config.CATEGORIAS.get(f["categoria"], f["categoria"]), mapa.get(f["categoria"], SIN_CUENTA),
        f["subtotal"], f["impuesto"], f["propina"], f["total"], f["moneda"], _tasa(f), f["total_usd"],
        consultas.ESTADO_GASTO.get(f["estado"], f["estado"]), quien, _como_instante(cuando), alertas or None,
        f"{enlace_base}/gastos/{f['id']}",
    ]


# ---------- escritura ----------
def _texto(valor) -> str | None:
    """Sin caracteres de control (la hoja no los admite) y neutralizado contra fórmulas."""
    if valor is None:
        return None
    limpio = ILLEGAL_CHARACTERS_RE.sub("", str(valor))[:_MAXIMO_TEXTO]
    return exportacion.celda(limpio) if limpio else None


def _como_fecha(valor):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return valor   # una fecha mal escrita se muestra tal cual, como texto


def _como_instante(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return valor


def _poner(hoja, fila: int, columna: int, valor, formato: str | None = None):
    if isinstance(valor, bool):
        valor = str(valor)
    if isinstance(valor, str):
        valor = _texto(valor)
    elif isinstance(valor, float | int | Decimal):
        valor = float(valor) if isinstance(valor, Decimal) else valor
    celda = hoja.cell(fila, columna, valor)
    if formato and valor is not None:
        celda.number_format = formato
    return celda


def _encabezado(hoja, fila: int, titulos: list[str]):
    for i, titulo in enumerate(titulos, start=1):
        celda = hoja.cell(fila, i, _texto(titulo))
        celda.font, celda.fill = _NEGRITA, _FONDO_ENCABEZADO
        celda.alignment = Alignment(vertical="center", wrap_text=True)


def _hoja_gastos(hoja, datos: list[dict], mapa: dict[str, str], enlace_base: str):
    _encabezado(hoja, 1, [c["titulo"] for c in COLUMNAS])
    for n, f in enumerate(datos, start=2):
        for i, (columna, valor) in enumerate(zip(COLUMNAS, _fila(f, mapa, enlace_base), strict=True), start=1):
            celda = _poner(hoja, n, i, valor, columna.get("formato"))
            if columna["titulo"] == "Soporte en la plataforma" and enlace_base:
                celda.hyperlink, celda.font = celda.value, _ENLACE
    for i, columna in enumerate(COLUMNAS, start=1):
        hoja.column_dimensions[get_column_letter(i)].width = columna["ancho"]
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNAS))}{max(hoja.max_row, 1)}"


def _sumar(datos: list[dict], clave) -> list[tuple]:
    """(clave, gastos, total en su moneda, total en USD) por grupo, con Decimal para no arrastrar errores de redondeo."""
    grupos: dict = {}
    for f in datos:
        g = grupos.setdefault(clave(f), [0, Decimal(0), Decimal(0)])
        g[0] += 1
        g[1] += _decimal(f["total"]) or 0
        g[2] += _decimal(f["total_usd"]) or 0
    return [(k, n, total, usd) for k, (n, total, usd) in sorted(grupos.items(), key=lambda x: tuple(str(p) for p in x[0]))]


def _tabla(hoja, fila: int, titulo: str, titulos: list[str], filas_tabla: list[list], formatos: list[str | None]) -> int:
    hoja.cell(fila, 1, _texto(titulo)).font = Font(bold=True, size=12)
    _encabezado(hoja, fila + 1, titulos)
    for n, valores in enumerate(filas_tabla, start=fila + 2):
        for i, (valor, formato) in enumerate(zip(valores, formatos, strict=True), start=1):
            celda = _poner(hoja, n, i, valor, formato)
            if valores[0] == "Total":
                celda.font = _NEGRITA
    return fila + 2 + len(filas_tabla) + 1


def _hoja_resumen(hoja, usuario: dict, datos: list[dict], mapa: dict[str, str], inicio: date, fin: date,
                  proyecto: dict | None, estados: tuple):
    total_usd = sum((_decimal(f["total_usd"]) or Decimal(0) for f in datos), Decimal(0))
    hoja.cell(1, 1, "Libro contable de gastos").font = Font(bold=True, size=14)
    hoja.cell(3, 1, "Parámetros").font = Font(bold=True, size=12)
    quien = (f"{viajes.codigo_persona(usuario['id'])} · {usuario['nombre']}" if usuario.get("id") else usuario.get("nombre", ""))
    parametros = [
        ("Desde", inicio, FECHA), ("Hasta", fin, FECHA),
        ("Proyecto", proyecto["nombre"] if proyecto else "Todos los proyectos a su alcance", None),
        ("Estados incluidos", ", ".join(consultas.ESTADO_GASTO[e] for e in estados), None),
        ("Alcance", ALCANCE.get(usuario.get("rol"), ""), None),
        ("Generado por", quien, None), ("Generado el (UTC)", _como_instante(db.ahora()), INSTANTE),
        ("Gastos incluidos", len(datos), None), ("Total en USD", total_usd, IMPORTE),
        ("Cuentas contables", NOTA_CUENTAS, None), ("Tasa a USD", NOTA_TASA, None),
    ]
    for n, (etiqueta, valor, formato) in enumerate(parametros, start=4):
        hoja.cell(n, 1, _texto(etiqueta)).font = _NEGRITA
        _poner(hoja, n, 2, valor, formato)
    fila = 4 + len(parametros) + 1

    por_proyecto = _sumar(datos, lambda f: (f["proyecto"] or "Sin proyecto",))
    fila = _tabla(hoja, fila, "Por proyecto", ["Proyecto", "Gastos", "Total USD"],
                  [[k[0], n, usd] for k, n, _, usd in por_proyecto] + [["Total", len(datos), total_usd]],
                  [None, None, IMPORTE])
    por_cuenta = _sumar(datos, lambda f: (mapa.get(f["categoria"], SIN_CUENTA),
                                          config.CATEGORIAS.get(f["categoria"], f["categoria"] or "Sin categoría")))
    fila = _tabla(hoja, fila, "Por cuenta contable", ["Cuenta contable", "Categoría", "Gastos", "Total USD"],
                  [[k[0], k[1], n, usd] for k, n, _, usd in por_cuenta] + [["Total", None, len(datos), total_usd]],
                  [None, None, None, IMPORTE])
    por_moneda = _sumar(datos, lambda f: (f["moneda"] or "Sin moneda",))
    # La suma de monedas distintas no tiene sentido: el total general solo va en USD
    _tabla(hoja, fila, "Por moneda", ["Moneda", "Gastos", "Total en la moneda", "Total USD"],
           [[k[0], n, total, usd] for k, n, total, usd in por_moneda] + [["Total", len(datos), None, total_usd]],
           [None, None, IMPORTE, IMPORTE])
    for letra, ancho in (("A", 28), ("B", 60), ("C", 18), ("D", 16)):
        hoja.column_dimensions[letra].width = ancho


def libro(usuario: dict, desde, hasta, proyecto_id: int | None = None, estados=ESTADOS_LIBRO, enlace_base: str = "") -> bytes:
    """El `.xlsx` del periodo [desde, hasta] (por la fecha del recibo) con lo que la persona puede ver.

    Lanza FechaInvalida, ProyectoInexistente (ambas ValueError, como un estado que no existe) o SinPermiso (proyecto
    que no gestiona), con un texto para la persona.
    """
    inicio, fin = periodo(desde, hasta)
    estados = _estados(estados)
    proyecto = _proyecto(usuario, proyecto_id)
    datos = _filas(usuario, inicio, fin, proyecto, estados)
    mapa = cuentas()
    enlace_base = (enlace_base or "").rstrip("/")
    wb = Workbook()
    wb.properties.creator = "Operación de proyectos"
    wb.properties.title = f"Libro contable de gastos {inicio} a {fin}"
    hoja = wb.active
    hoja.title = "Gastos"
    _hoja_gastos(hoja, datos, mapa, enlace_base)
    _hoja_resumen(wb.create_sheet("Resumen"), usuario, datos, mapa, inicio, fin, proyecto, estados)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()
