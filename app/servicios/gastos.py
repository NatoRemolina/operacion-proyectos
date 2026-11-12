"""Registro de soportes y gastos, igual para todos los canales (web, celular, correo, Telegram).

Recibe a la persona como parámetro: no depende de que haya una sesión de navegador.
"""
import hashlib
import re
from pathlib import Path

from .. import config, db
from . import almacen, eventos, extraccion, llm, validacion


class SoporteRechazado(ValueError):
    """El archivo no se acepta; el mensaje se le muestra a quien lo envió."""


def tipo_real(contenido: bytes, nombre: str) -> tuple[str, str] | None:
    """Tipo según el contenido, no según lo que declara quien sube. Devuelve (tipo, extensión) o None."""
    if contenido[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp", "webp"
    if contenido[:5] == b"%PDF-":
        return "application/pdf", "pdf"
    if nombre.lower().endswith(".eml"):
        cabecera = contenido[:4000].decode("utf-8", "ignore").lower()
        if not cabecera.lstrip().startswith("<") and sum(c in cabecera for c in ("from:", "subject:", "date:", "to:")) >= 2:
            return "message/rfc822", "eml"
    return None


def tipo_audio(contenido: bytes) -> tuple[str, str] | None:
    if contenido[:4] == b"OggS":
        return "audio/ogg", "ogg"
    if contenido[:3] == b"ID3" or contenido[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "audio/mpeg", "mp3"
    if contenido[4:8] == b"ftyp":
        return "audio/mp4", "m4a"
    return None


def nombre_visible(nombre: str) -> str:
    """Nombre original solo para mostrarlo: sin rutas ni caracteres de control."""
    limpio = re.sub(r"[\x00-\x1f\\/]", "_", Path(nombre or "soporte").name)[:120]
    return limpio or "soporte"


def _guardar(contenido: bytes, mime: str, extension: str) -> tuple[str, str]:
    huella = hashlib.sha256(contenido).hexdigest()
    try:
        return almacen.guardar(almacen.clave(huella, extension), contenido, mime), huella
    except Exception as e:
        raise SoporteRechazado(f"No se pudo guardar el archivo ({type(e).__name__}). Intenta de nuevo.") from e


def _campos_de(gasto: dict) -> dict:
    """Los campos de un gasto ya guardado, con la confianza y las dudas de su lectura original."""
    original = db.de_json(gasto.get("extraido"), {}) or {}
    return {**{c: gasto.get(c) for c in extraccion.CAMPOS if c != "ciudad"},
            "confianza": gasto.get("confianza") or 0, "dudas": original.get("dudas", [])}


def registrar(contenido: bytes, nombre: str, canal: str, usuario: dict | None, viaje: dict | None = None,
              proyecto_id: int | None = None, viajero_id: int | None = None, rapido: bool = False,
              clave_idempotencia: str | None = None) -> int:
    """Guarda el soporte, lo lee, lo valida contra la regla del viaje y devuelve el identificador del gasto.

    `clave_idempotencia`: la misma clave y el mismo contenido de la misma persona devolverán el mismo gasto.
    Pendiente de implementar (frente de integridad); hoy se acepta y se ignora.
    """
    if not contenido:
        raise SoporteRechazado("El archivo está vacío.")
    if len(contenido) > config.MAX_BYTES_SOPORTE:
        raise SoporteRechazado(f"El archivo pesa {len(contenido) / 1e6:.1f} MB; el máximo es {config.MAX_BYTES_SOPORTE / 1e6:.1f} MB.")
    tipo = tipo_real(contenido, nombre)
    if not tipo:
        raise SoporteRechazado("Tipo de archivo no admitido. Se aceptan fotos (JPG, PNG, WebP), PDF y correos (.eml).")
    mime, extension = tipo
    nombre = nombre_visible(nombre)
    ruta, huella = _guardar(contenido, mime, extension)
    if viaje:   # el viaje define el proyecto y la persona que viaja
        proyecto_id, viajero_id = viaje["proyecto_id"], viaje["viajero_id"] or viajero_id
    yo = usuario["id"] if usuario else None
    vid = viaje["id"] if viaje else None
    doc = db.insertar("documentos", nombre=nombre, mime=mime, canal=canal, ruta=ruta, huella=huella, creado=db.ahora(),
                      usuario_id=yo, viaje_id=vid, tipo="soporte")
    gid = db.insertar("gastos", documento_id=doc, proyecto_id=proyecto_id, viajero_id=viajero_id, viaje_id=vid,
                      estado="procesando", creado=db.ahora(), usuario_id=yo)
    eventos.registrar("gasto", gid, "documento recibido", f"{nombre} ({mime})" + (f" · {viaje['codigo']}" if viaje else ""),
                      f"canal: {canal}")
    # Un archivo idéntico ya leído no se vuelve a pagar: se reutiliza su lectura
    previo = db.uno("""select g.extraido from gastos g join documentos d on d.id=g.documento_id
                       where d.huella=:h and g.id<>:i and g.extraido is not null order by g.id limit 1""", h=huella, i=gid)
    marca = llm.RAPIDO.set(rapido)
    try:
        with eventos.cronometro() as t:
            x = {**db.de_json(previo["extraido"], {}), "origen_dato": "reutilizado", "error": None} if previo else \
                extraccion.extraer(contenido, mime, nombre, gid)
    finally:
        llm.RAPIDO.reset(marca)
    eventos.registrar("gasto", gid, "datos extraídos", x.get("error") or f"{x['comercio']} · {x['total']} {x['moneda']} · confianza {x['confianza']:.0%}",
                      f"modelo ({x['origen_dato']})", t())
    proyecto = db.uno("select * from proyectos where id=:i", i=proyecto_id) if proyecto_id else None
    r = validacion.revisar(x, proyecto, gid, viaje)
    if x.get("error"):
        # Una lectura fallida nunca se aprueba sola
        r["alertas"].insert(0, x["error"])
        r["motivos"].insert(0, "lectura_fallida")
        r["estado"] = "revision"
    original = {c: x.get(c) for c in extraccion.CAMPOS} | {"confianza": x["confianza"], "dudas": x.get("dudas", [])}
    db.actualizar("gastos", gid, **{c: x[c] for c in extraccion.CAMPOS if c != "ciudad"}, confianza=x["confianza"],
                  origen_dato=x["origen_dato"], estado=r["estado"], alertas=r["alertas"], motivos=r["motivos"],
                  total_usd=r["total_usd"], extraido=None if x.get("error") else original)
    eventos.registrar("gasto", gid, "aprobado sin intervención" if r["estado"] == "aprobado_auto" else "enviado a revisión",
                      " ".join(r["alertas"]) or "Todas las validaciones en verde", "reglas de validación")
    return gid


def asignar_viaje(gasto_id: int, viaje: dict) -> dict:
    """Enlaza un gasto con su viaje y lo vuelve a validar. Lo que una persona ya aprobó o rechazó no cambia de estado."""
    g = db.uno("select * from gastos where id=:i", i=gasto_id)
    proyecto = db.uno("select * from proyectos where id=:i", i=viaje["proyecto_id"]) if viaje["proyecto_id"] else None
    cambios = {"viaje_id": viaje["id"], "proyecto_id": viaje["proyecto_id"], "viajero_id": viaje["viajero_id"] or g["viajero_id"]}
    if g["estado"] in ("revision", "procesando", "aprobado_auto"):
        r = validacion.revisar(_campos_de(g), proyecto, gasto_id, viaje)
        if "lectura_fallida" in (db.de_json(g["motivos"], []) or []):
            r["estado"], r["motivos"] = "revision", ["lectura_fallida"] + r["motivos"]
            r["alertas"] = (db.de_json(g["alertas"], []) or [])[:1] + r["alertas"]
        cambios.update(estado=r["estado"], alertas=r["alertas"], motivos=r["motivos"], total_usd=r["total_usd"])
    db.actualizar("gastos", gasto_id, **cambios)
    if g["documento_id"]:
        db.actualizar("documentos", g["documento_id"], viaje_id=viaje["id"])
    eventos.registrar("gasto", gasto_id, "asignado a viaje", viaje["codigo"])
    return db.uno("select * from gastos where id=:i", i=gasto_id)


def guardar_evidencia(usuario: dict, viaje: dict | None, canal: str, tipo: str, contenido: bytes | None = None,
                      nombre: str = "", texto: str = "") -> int:
    """Audios y notas: se conservan ligados al viaje como evidencia. No originan gasto ni se envían al modelo."""
    ruta = mime = huella = None
    if contenido is not None:
        if len(contenido) > config.MAX_BYTES_SOPORTE:
            raise SoporteRechazado(f"El audio pesa {len(contenido) / 1e6:.1f} MB; el máximo es {config.MAX_BYTES_SOPORTE / 1e6:.1f} MB.")
        clase = tipo_audio(contenido)
        if not clase:
            raise SoporteRechazado("Formato de audio no admitido.")
        mime = clase[0]
        ruta, huella = _guardar(contenido, mime, clase[1])
    doc = db.insertar("documentos", nombre=nombre_visible(nombre or tipo), mime=mime, canal=canal, ruta=ruta, huella=huella,
                      creado=db.ahora(), usuario_id=usuario["id"], viaje_id=viaje["id"] if viaje else None, tipo=tipo,
                      texto=(texto or "")[:2000] or None)
    eventos.registrar("viaje" if viaje else "documento", viaje["id"] if viaje else doc, f"{tipo} guardado como evidencia",
                      (texto or nombre or "")[:120], f"canal: {canal}")
    return doc
