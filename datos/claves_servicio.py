"""Claves de servicio para integraciones (por ejemplo, n8n). Las administra quien opera la plataforma.

Uso:
    python -m datos.claves_servicio crear n8n --permiso soportes:leer
    python -m datos.claves_servicio listar
    python -m datos.claves_servicio revocar 3

La clave se muestra una sola vez, al crearla: en la base solo queda su huella. Si se pierde, se revoca y se crea otra.
"""
import argparse
import sys

from app import db
from app.servicios import claves_servicio


def main(argumentos: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m datos.claves_servicio", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("crear", help="Crea una clave y la muestra una sola vez.")
    c.add_argument("nombre", help="Cómo aparecerá en la bitácora, por ejemplo «n8n».")
    c.add_argument("--permiso", action="append", required=True, choices=sorted(claves_servicio.PERMISOS),
                   help="Permiso de la clave; se puede repetir.")
    sub.add_parser("listar", help="Lista las claves, sin mostrarlas.")
    r = sub.add_parser("revocar", help="Revoca una clave por su número.")
    r.add_argument("id", type=int)
    a = p.parse_args(argumentos)
    db.crear_tablas()
    try:
        if a.orden == "crear":
            cid, clave = claves_servicio.crear(a.nombre, a.permiso, creado_por="consola")
            print(f"Clave {cid} creada para «{a.nombre}» con {', '.join(sorted(set(a.permiso)))}.")
            print("Cópiala ahora: no se volverá a mostrar.")
            print(clave)
        elif a.orden == "listar":
            for k in claves_servicio.listar():
                estado = f"revocada {k['revocado']}" if k["revocado"] else "vigente"
                print(f"{k['id']:>3}  {k['nombre']:<20} {k['prefijo']}…  {k['permisos']:<20} {estado}  último uso: {k['ultimo_uso'] or '—'}")
        else:
            print("Clave revocada." if claves_servicio.revocar(a.id, revocado_por="consola") else "Esa clave ya estaba revocada.")
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
