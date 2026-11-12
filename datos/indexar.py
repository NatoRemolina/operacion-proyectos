"""Pone al día el índice del asistente: solo envía las fichas nuevas o cambiadas y borra las que ya no existen.

Uso:  python -m datos.indexar                  envía lo nuevo o cambiado
      python -m datos.indexar --todo           vuelve a enviar todas las fichas
      python -m datos.indexar --crear-indice   crea el índice en Pinecone (una sola vez) y muestra su dirección

Sin PINECONE_API_KEY y PINECONE_HOST solo se actualiza el índice local.
"""
import argparse

from app import config, db
from app.servicios import memoria


def main(argv: list[str] | None = None) -> int:
    opciones = argparse.ArgumentParser(description="Índice del asistente")
    opciones.add_argument("--todo", action="store_true", help="reenvía todas las fichas aunque no hayan cambiado")
    opciones.add_argument("--crear-indice", action="store_true", help="crea el índice en Pinecone con PINECONE_INDICE")
    a = opciones.parse_args(argv)
    db.crear_tablas()
    if a.crear_indice:
        if not config.PINECONE_API_KEY:
            print("Falta PINECONE_API_KEY en .env.")
            return 1
        try:
            host = memoria.crear_indice_pinecone()
        except memoria.ErrorIndice as e:
            print(f"No se pudo crear el índice: {e}")
            return 1
        print(f"Índice «{config.PINECONE_INDICE}» creado. Copia esta dirección en PINECONE_HOST: {host}")
        return 0
    print(f"Destinos: {', '.join(d.nombre for d in memoria.destinos())}")
    codigo = 0
    for destino, r in memoria.actualizar(todo=a.todo).items():
        if "error" in r:
            print(f"{destino}: falló ({r['error']})")
            codigo = 1
        else:
            print(f"{destino}: {r['enviadas']} enviadas, {r['borradas']} borradas, {r['total']} fichas en total")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
