"""Revisión de un gasto por administración: la misma regla para la web y para la API v1.

- Versión esperada: quien revisa manda la versión que vio; si el gasto cambió mientras tanto, no se aplica nada.
- Nadie revisa ni aprueba lo suyo (`viajes.revision_permitida`), tampoco un administrador por la API.
- Aprobar vuelve a evaluar las reglas con los viajes bloqueados: dos aprobaciones a la vez no gastan el mismo saldo.
- Rechazar exige motivo; el motivo se guarda, queda en la auditoría y le llega a la persona por Telegram.
- Lo que la persona que revisa escribió mal (un motivo corto) se le responde a ella; no se guarda como alerta del gasto.
"""
from sqlalchemy import Column, Integer, Text

from .. import config, db
from . import acceso, eventos, validacion, viajes

# Columnas de la revisión. `crear_tablas` las añade a una base existente y `datos/migracion.py` alinea la restricción
db.gastos.append_column(Column("version", Integer, nullable=False, server_default="0"))
db.gastos.append_column(Column("motivo_rechazo", Text))

ACCIONES = ("guardar", "aprobar", "excepcion", "rechazar")
MINIMO_RECHAZO = 5
MINIMO_EXCEPCION = 8
EDITABLES = ("comercio", "fecha", "categoria", "subtotal", "impuesto", "propina", "total", "moneda", "metodo_pago", "canal_reserva")
CAMBIO = "Otra persona cambió este gasto mientras lo revisabas. Recarga la página para ver los datos actuales."
SIN_EXCEPCION = {"importe_invalido", "fecha_invalida"}   # ni con excepción se aprueba un importe o una fecha que no lo son


class ConflictoRevision(ValueError):
    """El gasto cambió desde que se vio, o todavía se está leyendo."""


class RevisionImpedida(PermissionError):
    """Quien revisa no puede hacerlo: no es administración, o el gasto es suyo."""


def subir_version(gasto_id: int):
    """Cada cambio del gasto que vería quien revisa sube su versión."""
    db.ejecutar("update gastos set version=coalesce(version,0)+1 where id=:i", i=gasto_id)


def guardar(gasto_id: int, quien: dict, version: int | None, accion: str, campos: dict | None = None, motivo: str = "",
            viaje_id: int | None = None, proyecto_id: int | None = None, viajero_id: int | None = None) -> dict:
    """Aplica una revisión y devuelve {estado, paso}. `version` None solo la usan formularios antiguos sin el campo.

    `campos`: los datos corregidos (solo los que se mandan; el resto se conserva). `viaje_id`: None conserva el viaje,
    0 lo quita. Lanza LookupError (no existe), RevisionImpedida, ConflictoRevision o ValueError (con el texto para
    quien revisa).
    """
    if accion not in ACCIONES:
        raise ValueError("Acción de revisión no válida.")
    if not acceso.es_admin(quien):
        raise RevisionImpedida("Solo administración revisa gastos.")
    previo = db.uno("select * from gastos where id=:i", i=gasto_id)
    if not previo:
        raise LookupError("No existe ese gasto.")
    impedido, resultado = None, None
    with db.transaccion() as conexion:
        destino = previo["viaje_id"] if viaje_id is None else (viaje_id or None)
        vigentes = {vid: db.bloquear_viaje(conexion, vid) for vid in sorted({previo["viaje_id"], destino} - {None})}
        g = db.uno("select * from gastos where id=:i" + ("" if config.ES_SQLITE else " for update"), i=gasto_id)
        if g["viaje_id"] != previo["viaje_id"]:   # se bloquearon los viajes de antes: si cambió, se vuelve a empezar
            raise ConflictoRevision(CAMBIO)
        el_viaje = {**viajes.uno(destino), **vigentes[destino]} if destino and vigentes.get(destino) else None
        if destino and not el_viaje:
            raise ValueError("Ese viaje no existe.")
        if el_viaje:   # el viaje define el proyecto y quién viaja
            proyecto_id, viajero_id = el_viaje["proyecto_id"] or proyecto_id, el_viaje["viajero_id"] or viajero_id
        proyecto_id = g["proyecto_id"] if proyecto_id is None else (proyecto_id or None)
        viajero_id = g["viajero_id"] if viajero_id is None else (viajero_id or None)
        despues = g if accion == "rechazar" else {"usuario_id": g["usuario_id"], "viajero_id": viajero_id,
                                                  "viaje_id": el_viaje["id"] if el_viaje else None}
        # Primero la regla de no revisar lo propio: el intento queda en la auditoría aunque falte algo más
        impedido = viajes.revision_permitida(gasto_id, g, despues, quien, accion)
        if not impedido:
            resultado = _aplicar(g, quien, version, accion, campos or {}, (motivo or "").strip(), el_viaje, proyecto_id, viajero_id)
    if impedido:
        raise RevisionImpedida(impedido)
    _avisar(g, resultado, (motivo or "").strip())
    return resultado


def _aplicar(g: dict, quien: dict, version: int | None, accion: str, campos: dict, motivo: str, el_viaje: dict | None,
             proyecto_id: int | None, viajero_id: int | None) -> dict:
    gid = g["id"]
    if version is not None and (g.get("version") or 0) != version:
        raise ConflictoRevision(CAMBIO)
    if g["estado"] == "procesando":
        from . import envios
        if not envios.recuperar_si_atascado(g):
            raise ConflictoRevision("El recibo todavía se está leyendo. Espera un momento y recarga la página.")
        g = db.uno("select * from gastos where id=:i", i=gid)   # recuperado: ahora está en revisión y se puede decidir
    nueva = (g.get("version") or 0) + 1
    if accion == "rechazar":
        if len(motivo) < MINIMO_RECHAZO:
            raise ValueError(f"Para rechazar hay que escribir el motivo (al menos {MINIMO_RECHAZO} caracteres).")
        motivo = motivo[:500]
        db.actualizar("gastos", gid, estado="rechazado", motivo_rechazo=motivo, revisado_por=quien["id"], version=nueva)
        eventos.registrar("gasto", gid, "rechazado en revisión", f"{motivo} · versión {nueva}", quien["nombre"])
        return {"estado": "rechazado", "paso": "rechazado en revisión"}
    if accion == "excepcion" and len(motivo) < MINIMO_EXCEPCION:
        raise ValueError(f"Para aprobar con excepción hay que escribir el motivo (al menos {MINIMO_EXCEPCION} caracteres).")
    valores = {c: campos[c] if c in campos else g.get(c) for c in EDITABLES}
    proyecto = db.uno("select * from proyectos where id=:i", i=proyecto_id) if proyecto_id else None
    # Una persona confirmó los datos: la confianza de lectura deja de ser el criterio
    r = validacion.revisar({**valores, "confianza": 1.0, "dudas": []}, proyecto, gid, el_viaje)
    estado = "aprobado" if accion == "aprobar" and r["estado"] == "aprobado_auto" else "revision"
    paso = "corregido y aprobado" if estado == "aprobado" else "corregido, sigue en revisión"
    if accion == "excepcion":
        if r["estado"] == "aprobado_auto":
            estado, paso = "aprobado", "corregido y aprobado"
        elif valores["total"] is not None and valores["moneda"] and r["total_usd"] is not None \
                and not SIN_EXCEPCION & set(r["motivos"]):
            estado, paso = "aprobado", "aprobado con excepción"
            r["alertas"].append(f"Aprobado con excepción: {motivo[:200]}")
        else:
            raise ValueError("Ni con excepción se aprueba un gasto sin total, moneda o tasa de cambio, o con un importe "
                             "o una fecha que no son válidos. Corrige los datos primero.")
    db.actualizar("gastos", gid, **valores, proyecto_id=proyecto_id, viajero_id=viajero_id,
                  viaje_id=el_viaje["id"] if el_viaje else None, estado=estado, alertas=r["alertas"], motivos=r["motivos"],
                  total_usd=r["total_usd"], revisado_por=quien["id"], version=nueva)
    eventos.registrar("gasto", gid, paso, (" ".join(r["alertas"]) + f" · versión {nueva}").strip(" ·"), quien["nombre"])
    return {"estado": estado, "paso": paso, "comercio": valores["comercio"], "total": valores["total"], "moneda": valores["moneda"]}


def _avisar(g: dict, resultado: dict, motivo: str):
    """Fuera de la transacción: el aviso por Telegram sale a la red y no debe retener el bloqueo."""
    from . import telegram
    if resultado["estado"] == "rechazado":
        telegram.avisar(g["usuario_id"], f"Tu gasto #{g['id']} ({g.get('comercio') or 'sin comercio'}) fue rechazado en la revisión."
                                         f"\nMotivo: {motivo[:500]}")
    elif resultado["estado"] == "aprobado":
        telegram.avisar(g["usuario_id"], f"Tu gasto #{g['id']} ({resultado['comercio'] or 'sin comercio'}, "
                                         f"{resultado['total'] or 0:.2f} {resultado['moneda'] or ''}) fue aprobado.")
