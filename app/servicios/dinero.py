"""Importes exactos para las reglas. Las columnas siguen en coma flotante; aquí se valida y se compara con Decimal."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MAXIMO = Decimal("999999999999.99")   # lo que cabe con dos decimales en una columna numeric(14,2)
CENTAVO = Decimal("0.01")


def decimal(valor, *, positivo: bool = False) -> Decimal:
    """El importe redondeado a centavos. Rechaza lo vacío, lo que no es número, NaN, infinito y lo desmesurado.

    Con `positivo`, además exige que sea mayor que cero después de redondear (0,004 no es un total).
    """
    if valor is None or isinstance(valor, bool):
        raise ValueError("Importe vacío o no numérico.")
    try:
        importe = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError) as e:
        raise ValueError("Importe no numérico.") from e
    if not importe.is_finite() or abs(importe) > MAXIMO:
        raise ValueError("Importe no finito o desmesurado.")
    importe = importe.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if positivo and importe <= 0:
        raise ValueError("El importe debe ser mayor que cero.")
    return importe
