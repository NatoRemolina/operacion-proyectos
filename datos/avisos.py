"""Avisos salientes firmados (n8n): estado de la bandeja y reintento de los pendientes.

Uso:
    python -m datos.avisos estado
    python -m datos.avisos reintentar

`reintentar` entrega los avisos pendientes cuya espera ya pasó (1, 5, 30, 120 y 720 minutos tras cada fallo).
Los pendientes también se reintentan solos cuando se registra un gasto y el destino responde.
"""
import sys

from app import db
from app.servicios import avisos


def main(argumentos: list[str] | None = None) -> int:
    orden = (argumentos if argumentos is not None else sys.argv[1:]) or ["estado"]
    db.crear_tablas()
    if orden[0] == "reintentar":
        if not avisos.activo():
            print("Los avisos están apagados: faltan N8N_WEBHOOK_URL, N8N_WEBHOOK_SECRETO o URL_PUBLICA.")
            return 1
        print(f"Entregados: {avisos.reintentar_pendientes(limite=100)}")
    elif orden[0] != "estado":
        print(__doc__)
        return 1
    print("Avisos " + ("encendidos" if avisos.activo() else "apagados") + ".")
    for f in db.todos("select estado, count(*) n from avisos_salientes group by estado order by estado"):
        print(f"  {f['estado']}: {f['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
