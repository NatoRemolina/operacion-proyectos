"""Excel contable desde la consola: el mismo libro que se descarga en la plataforma, sin abrirla.

Uso:  python -m datos.exportar_contable --desde 2026-11-01 --hasta 2026-11-30 [--proyecto ID] [--salida libro.xlsx]

Sin fechas, el mes en curso; sin `--salida`, `libro_contable_<desde>_<hasta>.xlsx` en la carpeta actual.
Lee la base de DATABASE_URL como administración (todos los gastos aprobados del periodo) y en solo lectura: no
crea tablas, no siembra y no deja evento. Nunca imprime la conexión.
"""
import argparse
import io
import sys
from contextlib import contextmanager
from pathlib import Path

from openpyxl import load_workbook

from app import config, db
from app.servicios import contable

ADMINISTRACION = {"id": None, "rol": "admin", "nombre": "Guion de consola (administración)", "viajero_id": None}


@contextmanager
def solo_lectura():
    """Todas las consultas de `app.db` hechas dentro van por una sola transacción que no puede escribir.

    En PostgreSQL es `SET TRANSACTION READ ONLY`, comprobado, en una foto fija de la base (REPEATABLE READ: el
    resumen cuadra con las filas aunque alguien apruebe un gasto mientras tanto). Vale solo para esa transacción,
    que se deshace al final: con el agrupador de conexiones de Supabase no queda nada pegado a una conexión que
    después use la plataforma. En SQLite, `PRAGMA query_only`, que se quita antes de devolver la conexión.
    """
    with db.motor.connect() as conexion:
        if config.ES_SQLITE:
            conexion.exec_driver_sql("PRAGMA query_only=ON")
        else:
            conexion = conexion.execution_options(isolation_level="REPEATABLE READ")
            conexion.begin()
            conexion.exec_driver_sql("SET TRANSACTION READ ONLY")
            if conexion.exec_driver_sql("SHOW transaction_read_only").scalar() != "on":
                conexion.rollback()
                raise SystemExit("No se pudo abrir la base en solo lectura: no se sigue.")
        # La misma marca que usa `db.transaccion()`: así `db.uno`, `db.todos`, etc. pasan por esta conexión
        marca = db._en_transaccion.set(conexion)
        try:
            yield conexion
        finally:
            db._en_transaccion.reset(marca)
            conexion.rollback()
            if config.ES_SQLITE:
                conexion.exec_driver_sql("PRAGMA query_only=OFF")


def main(argv: list[str] | None = None) -> int:
    desde, hasta = contable.mes_en_curso()
    opciones = argparse.ArgumentParser(description="Excel contable de los gastos aprobados de un periodo")
    opciones.add_argument("--desde", default=desde, help="AAAA-MM-DD, por la fecha del recibo (por omisión, el primer día del mes en curso)")
    opciones.add_argument("--hasta", default=hasta, help="AAAA-MM-DD, incluido (por omisión, el último día del mes en curso)")
    opciones.add_argument("--proyecto", type=int, help="solo los gastos de ese proyecto (su número)")
    opciones.add_argument("--salida", help="el .xlsx que se escribe (por omisión, libro_contable_<desde>_<hasta>.xlsx aquí)")
    a = opciones.parse_args(argv)
    try:
        with solo_lectura():
            contenido = contable.libro(ADMINISTRACION, a.desde, a.hasta, a.proyecto, enlace_base=contable.origen_publico())
    except ValueError as e:   # fecha ilegible, periodo al revés o proyecto que no existe
        print(e, file=sys.stderr)
        return 1
    salida = Path(a.salida or contable.nombre_archivo(a.desde, a.hasta, a.proyecto))
    salida.write_bytes(contenido)
    gastos = load_workbook(io.BytesIO(contenido))["Gastos"].max_row - 1
    inicio, fin = contable.periodo(a.desde, a.hasta)
    print(f"Libro contable escrito en {salida}: {gastos} gastos aprobados del {inicio} al {fin}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
