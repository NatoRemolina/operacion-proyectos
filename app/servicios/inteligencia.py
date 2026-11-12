"""Señales automáticas sobre los gastos. Todas son explicables y ninguna necesita entrenamiento.

Con pocos datos no opinan: cada función declara el mínimo que exige.
"""
from statistics import median

from .. import db

MIN_HISTORIA = 4   # gastos aprobados de la misma categoría y moneda para poder comparar


def _historia(categoria: str, moneda: str, excepto: int = 0) -> list[float]:
    return [f["total"] for f in db.todos(
        """select total from gastos where categoria=:c and moneda=:m and total is not null and id<>:i
           and estado in ('aprobado','aprobado_auto')""", c=categoria, m=moneda, i=excepto)]


def es_atipico(categoria: str | None, moneda: str | None, total: float | None, excepto: int = 0) -> str | None:
    """Compara un importe con lo habitual de su categoría usando la mediana y la desviación absoluta mediana.

    Son medidas robustas: un gasto enorme anterior no mueve la referencia. Devuelve la explicación o None.
    """
    if not categoria or not moneda or total is None:
        return None
    previos = _historia(categoria, moneda, excepto)
    if len(previos) < MIN_HISTORIA:
        return None
    centro = median(previos)
    dispersion = median(abs(x - centro) for x in previos) * 1.4826   # equivalente a una desviación estándar
    limite = centro + 3.5 * dispersion if dispersion else centro * 3
    if total > limite and total > centro * 2:
        return (f"Importe atípico: {total:.2f} {moneda} frente a una mediana de {centro:.2f} "
                f"en {len(previos)} gastos de la misma categoría.")
    return None


def calibracion() -> list[dict]:
    """¿La confianza que declara el modelo predice si habrá que corregir? Tasa de corrección por tramo."""
    tramos = [(0.0, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)]
    filas = db.todos("select g.*, 0 x from gastos g where extraido is not null and estado in ('aprobado','aprobado_auto','rechazado')")
    salida = []
    for a, b in tramos:
        grupo = [g for g in filas if a <= (g["confianza"] or 0) < b]
        corregidos = sum(1 for g in grupo if campos_corregidos(g))
        salida.append({"tramo": f"{a:.2f} a {min(b, 1):.2f}", "gastos": len(grupo), "corregidos": corregidos,
                       "tasa": round(100 * corregidos / len(grupo)) if grupo else None})
    return salida


CAMPOS_COMPARADOS = ["comercio", "fecha", "categoria", "subtotal", "impuesto", "propina", "total", "moneda"]


def campos_corregidos(g: dict) -> list[str]:
    """Campos en los que lo aprobado difiere de lo que leyó el modelo."""
    original = db.de_json(g.get("extraido"), None)
    if not original:
        return []
    return [c for c in CAMPOS_COMPARADOS if (original.get(c) or None) != (g.get(c) or None)]
