"""Vuelve a pasar por las reglas de hoy los gastos aprobados sin intervención.

Sirve para datos cargados antes de que existiera una regla: por ejemplo, un gasto que se aprobó solo cuando
todavía no se exigía un viaje con presupuesto aprobado. Solo mira los `aprobado_auto` (nunca lo que aprobó
una persona) y solo mueve a revisión: no aprueba nada ni borra nada. Cada cambio deja su evento.

    python -m datos.revalidar_gastos              # muestra qué cambiaría, sin escribir
    python -m datos.revalidar_gastos --aplicar    # lo aplica
"""
import argparse
import sys

from app import db
from app.servicios import eventos, revision, validacion, viajes


def candidatos() -> list[dict]:
    """Gastos aprobados sin intervención que, con las reglas de hoy, irían a revisión."""
    salida = []
    for g in db.todos("select * from gastos where estado='aprobado_auto' order by id"):
        viaje = viajes.uno(g["viaje_id"]) if g["viaje_id"] else None
        proyecto = db.uno("select * from proyectos where id=:i", i=g["proyecto_id"]) if g["proyecto_id"] else None
        campos = {k: g[k] for k in ("comercio", "fecha", "categoria", "subtotal", "impuesto", "propina", "total",
                                    "moneda", "metodo_pago", "canal_reserva")}
        campos["confianza"] = g["confianza"] if g["confianza"] is not None else 1.0
        r = validacion.revisar(campos, proyecto, g["id"], viaje)
        if r["estado"] == "revision":
            salida.append({"id": g["id"], "comercio": g["comercio"], "viaje": viaje["codigo"] if viaje else None,
                           "alertas": r["alertas"], "motivos": r["motivos"]})
    return salida


def aplicar(cambios: list[dict]) -> int:
    for c in cambios:
        with db.transaccion():
            actual = db.uno("select estado from gastos where id=:i", i=c["id"])
            if not actual or actual["estado"] != "aprobado_auto":
                continue   # alguien lo revisó mientras tanto
            db.actualizar("gastos", c["id"], estado="revision", alertas=c["alertas"], motivos=c["motivos"])
            revision.subir_version(c["id"])
            eventos.registrar("gasto", c["id"], "revalidado: pasa a revisión", " ".join(c["alertas"]),
                              "revalidación con las reglas vigentes")
    return len(cambios)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="escribe los cambios (sin esto solo los muestra)")
    a = p.parse_args(argv)
    cambios = candidatos()
    if not cambios:
        print("Todos los gastos aprobados sin intervención cumplen las reglas de hoy. No hay nada que cambiar.")
        return 0
    for c in cambios:
        print(f"Gasto #{c['id']} {c['comercio'] or 'sin comercio'} · {c['viaje'] or 'sin viaje'} → revisión: "
              f"{', '.join(c['motivos'])}")
    if a.aplicar:
        print(f"{aplicar(cambios)} gastos pasaron a revisión.")
    else:
        print(f"{len(cambios)} gastos pasarían a revisión. Repite con --aplicar para hacerlo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
