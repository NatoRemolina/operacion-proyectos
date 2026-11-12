"""Justificación de cada gasto: para qué fue, dicho por la persona, por escrito o en una nota de voz.

Se guarda aparte del gasto, una fila por justificación, con su canal y su transcripción. Es la materia prima de un
análisis futuro de lenguaje (temas, claridad, sentimiento por persona); ver docs/justificaciones.md. Hoy solo se
recoge, se muestra a quien revisa y la consulta el asistente. Ninguna regla de aprobación depende de su contenido.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, Integer, Text

from .. import db
from . import eventos, gastos, llm

justificaciones = db._tabla(
    "justificaciones",
    db._ref("justificaciones", "gasto_id", "gastos"), db._ref("justificaciones", "usuario_id", "usuarios"),
    db._ref("justificaciones", "documento_id", "documentos"),   # la nota de voz original, si la hay
    Column("canal", Text),           # web, celular, telegram o api
    Column("tipo", Text),            # texto o audio
    Column("texto", Text),           # lo escrito, o la transcripción del audio
    Column("transcripcion", Text),   # no_aplica, pendiente, hecha o fallida
    Column("palabras", Integer), Column("creado", Text),
)

MAXIMO = 2000
MINIMO = 3
VENTANA_TELEGRAM = timedelta(minutes=30)   # tiempo en que una respuesta del chat se toma como justificación del último gasto
PREGUNTA = "¿Para qué fue este gasto? Respóndeme con un mensaje o una nota de voz; queda guardado como su justificación."

TRANSCRIBIR = ("Transcribe literalmente esta nota de voz en el idioma en que se habla. Devuelve solo el texto dicho, "
               "sin comentarios ni resumen. Si no se entiende, devuelve una cadena vacía.")


class JustificacionRechazada(ValueError):
    """La justificación no se puede guardar; el mensaje se muestra tal cual a la persona."""


def puede_justificar(u: dict | None, g: dict | None) -> bool:
    """Solo justifica quien hizo el gasto o quien viaja: la justificación es su voz, no la de quien revisa."""
    if not u or not g:
        return False
    return g.get("usuario_id") == u["id"] or bool(u.get("viajero_id") and g.get("viajero_id") == u["viajero_id"])


def _limpio(texto: str | None) -> str:
    return " ".join((texto or "").split())[:MAXIMO]


def registrar(gasto_id: int, usuario: dict, canal: str, texto: str | None = None,
              audio: bytes | None = None, nombre_audio: str = "nota_de_voz") -> int:
    """Guarda una justificación del gasto. Quien llama ya comprobó que la persona puede ver ese gasto."""
    g = db.uno("select id, viaje_id from gastos where id=:i", i=gasto_id)
    if not g:
        raise JustificacionRechazada("El gasto no existe.")
    texto = _limpio(texto)
    doc, tipo, estado = None, "texto", "no_aplica"
    if audio is not None:
        viaje = {"id": g["viaje_id"]} if g["viaje_id"] else None
        try:
            doc = gastos.guardar_evidencia(usuario, viaje, canal, "audio", audio, nombre_audio, texto)
        except gastos.SoporteRechazado as e:
            raise JustificacionRechazada(str(e)) from e
        tipo, estado = "audio", "pendiente"
    elif len(texto) < MINIMO:
        raise JustificacionRechazada("Escribe para qué fue el gasto, aunque sea en pocas palabras.")
    jid = db.insertar("justificaciones", gasto_id=gasto_id, usuario_id=usuario["id"], documento_id=doc, canal=canal,
                      tipo=tipo, texto=texto or None, transcripcion=estado, palabras=len(texto.split()) or None,
                      creado=db.ahora())
    eventos.registrar("gasto", gasto_id, "justificación recibida", texto[:120] if tipo == "texto" else "nota de voz", f"canal: {canal}")
    if tipo == "audio":
        transcribir(jid, audio)
    return jid


def transcribir(jid: int, audio: bytes | None = None) -> str:
    """Pasa la nota de voz a texto con el modelo. Sin modelo configurado queda pendiente; un fallo queda como fallida."""
    j = db.uno("select * from justificaciones where id=:i", i=jid)
    if not j or j["tipo"] != "audio":
        return "no_aplica"
    if not llm.activo():
        return "pendiente"
    if audio is None:
        from . import almacen
        d = db.uno("select ruta from documentos where id=:i", i=j["documento_id"])
        audio = almacen.leer(d["ruta"]) if d and d["ruta"] else None
    d = db.uno("select mime from documentos where id=:i", i=j["documento_id"])
    if not audio or not d:
        db.actualizar("justificaciones", jid, transcripcion="fallida")
        return "fallida"
    try:
        r = llm.generar([{"role": "user", "parts": [llm.parte_archivo(audio, d["mime"]), llm.parte_texto(TRANSCRIBIR)]}],
                        uso="transcripcion", entidad_id=j["gasto_id"], tope_salida=2048)
        dicho = _limpio(llm.texto_de(r))
    except llm.ErrorDelModelo:
        db.actualizar("justificaciones", jid, transcripcion="fallida")
        return "fallida"
    previo = _limpio(j["texto"])   # el pie que acompañó al audio, si lo hubo
    completo = f"{previo} {dicho}".strip() if previo and dicho else (dicho or previo)
    db.actualizar("justificaciones", jid, texto=completo or None, transcripcion="hecha" if dicho else "fallida",
                  palabras=len(completo.split()) or None)
    if dicho:
        db.actualizar("documentos", j["documento_id"], texto=dicho[:2000])
    return "hecha" if dicho else "fallida"


def de_gasto(gasto_id: int) -> list[dict]:
    return db.todos("""select j.id, j.tipo, j.canal, j.texto, j.transcripcion, j.creado, j.documento_id, j.usuario_id, u.nombre persona
                       from justificaciones j left join usuarios u on u.id=j.usuario_id
                       where j.gasto_id=:g order by j.id""", g=gasto_id)


def gasto_por_justificar(usuario_id: int) -> int | None:
    """Último gasto que la persona envió por Telegram hace poco y que aún no tiene justificación."""
    g = db.uno("""select g.id, g.creado from gastos g join documentos d on d.id=g.documento_id
                  where g.usuario_id=:u and d.canal='telegram'
                  and not exists (select 1 from justificaciones j where j.gasto_id=g.id)
                  order by g.id desc limit 1""", u=usuario_id)
    if not g or not g["creado"]:
        return None
    creado = datetime.strptime(g["creado"][:19], "%Y-%m-%d %H:%M:%S")
    return g["id"] if datetime.now(UTC).replace(tzinfo=None) - creado <= VENTANA_TELEGRAM else None


def cobertura(donde: str = "1=1", **p) -> dict:
    """Cuántos gastos tienen justificación: el insumo que hará falta para cualquier análisis de lenguaje."""
    f = db.uno(f"""select count(*) total,
                   sum(case when exists (select 1 from justificaciones j where j.gasto_id=g.id) then 1 else 0 end) con
                   from gastos g where {donde}""", **p) or {}
    total, con = int(f.get("total") or 0), int(f.get("con") or 0)
    return {"gastos": total, "con_justificacion": con, "tasa": round(con / total, 3) if total else None}
