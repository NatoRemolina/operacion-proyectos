"""Exportaciones CSV que se pueden abrir sin riesgo en una hoja de cálculo.

Algunos textos los escribe cualquiera (un comercio leído de un recibo, el correo de un intento de ingreso fallido). Si
uno empieza por «=», «+», «-», «@», tabulador o retorno, la hoja de cálculo lo ejecuta como fórmula: se le antepone un
apóstrofo. Los números y las celdas vacías van tal cual.
"""
import csv
import io

COMIENZO_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def celda(valor):
    if valor is None:
        return ""
    if isinstance(valor, int | float):
        return valor
    texto = str(valor)
    return "'" + texto if texto.startswith(COMIENZO_DE_FORMULA) else texto


def csv_de(filas: list[dict], columnas: list[str] | None = None) -> str:
    """Encabezado y filas, con BOM para que la hoja de cálculo lea bien las tildes. Sin filas ni columnas, solo el BOM."""
    columnas = columnas or (list(filas[0].keys()) if filas else [])
    salida = io.StringIO()
    if columnas:
        escritor = csv.DictWriter(salida, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows({c: celda(f[c]) for c in columnas} for f in filas)
    return "﻿" + salida.getvalue()
