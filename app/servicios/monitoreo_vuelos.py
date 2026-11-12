"""Monitoreo del vuelo: los tramos del vuelo elegido, registrados al decidir, y su estado el día del viaje."""
from sqlalchemy import Column, Integer, Text

from .. import db
from . import eventos

tramos_vuelo = db._tabla(
    "tramos_vuelo",  # un tramo por número de vuelo; guarda el último estado conocido
    db._ref("tramos_vuelo", "viaje_id", "viajes"), Column("sentido", Text), Column("orden", Integer),
    Column("aerolinea", Text), Column("numero", Text), Column("fecha", Text), Column("desde", Text), Column("hasta", Text),
    Column("sale_programada", Text), Column("llega_programada", Text), Column("estado", Text, default="programado"),
    Column("retraso_salida", Integer), Column("retraso_llegada", Integer), Column("terminal", Text), Column("puerta", Text),
    Column("llega_estimada", Text), Column("actualizado", Text), Column("consultas", Integer, default=0),
    Column("ultimo_aviso", Text),
)


def _tramos_de(vuelo: dict | None) -> list[dict]:
    """Los tramos de un vuelo de la respuesta del buscador. Las opciones guardadas antes de conservar los tramos solo
    tienen los números: se registra cada uno con lo que se sabe (salida del primero y llegada del último)."""
    if not vuelo:
        return []
    if vuelo.get("tramos"):
        return [t for t in vuelo["tramos"] if t.get("numero")]
    numeros = [n for n in vuelo.get("numeros") or [] if n and n != "s/n"]
    return [{"aerolinea": vuelo.get("aerolinea"), "numero": n, "desde": vuelo.get("desde") if i == 0 else None,
             "hasta": vuelo.get("hasta") if i == len(numeros) - 1 else None,
             "sale": vuelo.get("sale") if i == 0 else None, "llega": vuelo.get("llega") if i == len(numeros) - 1 else None}
            for i, n in enumerate(numeros)]


def registrar_tramos(viaje_id: int, vuelo_ida: dict, vuelo_regreso: dict | None) -> int:
    """Registra los tramos de ida y de regreso del viaje. Idempotente: reemplaza los que tuviera. Devuelve cuántos."""
    filas = []
    for sentido, vuelo in (("ida", vuelo_ida), ("regreso", vuelo_regreso)):
        for i, t in enumerate(_tramos_de(vuelo), 1):
            filas.append({"viaje_id": viaje_id, "sentido": sentido, "orden": i, "aerolinea": t.get("aerolinea"),
                          "numero": t["numero"], "fecha": (t.get("sale") or (vuelo or {}).get("sale") or "")[:10] or None,
                          "desde": t.get("desde"), "hasta": t.get("hasta"), "sale_programada": t.get("sale"),
                          "llega_programada": t.get("llega"), "estado": "programado", "consultas": 0})
    db.ejecutar("delete from tramos_vuelo where viaje_id=:v", v=viaje_id)
    db.insertar_varios("tramos_vuelo", filas)
    por_sentido = {s: [f["numero"] for f in filas if f["sentido"] == s] for s in ("ida", "regreso")}
    eventos.registrar("viaje", viaje_id, "tramos registrados",
                      f"ida: {', '.join(por_sentido['ida']) or 'sin tramos'} · regreso: {', '.join(por_sentido['regreso']) or 'sin datos'}",
                      "decisión")
    return len(filas)


def de_viaje(viaje_id: int) -> list[dict]:
    return db.todos("select * from tramos_vuelo where viaje_id=:v order by case sentido when 'ida' then 0 else 1 end, orden",
                    v=viaje_id)
