"""Extrae a `ofertas_tarifa` las tarifas que aún no estén: lecturas de la página de Google Flights y respuestas del
buscador con opciones de reserva. No consulta nada: solo lee lo que la plataforma ya guardó.

Uso:  python -m datos.ofertas
"""
import json

from app import db
from app.servicios import ofertas


def main():
    db.crear_tablas()
    print(json.dumps(ofertas.actualizar(), ensure_ascii=False))
    total = db.uno("select count(*) n, count(distinct origen_fila) o from ofertas_tarifa")
    print(f"ofertas_tarifa: {total['n']} tarifas de {total['o']} respuestas o lecturas.")


if __name__ == "__main__":
    main()
