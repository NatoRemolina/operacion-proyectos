"""Monitoreo del vuelo: los tramos del vuelo elegido, registrados al decidir, y su estado el día del viaje.

Cuidar el plan del buscador (250 búsquedas al mes): solo se consulta dentro de la ventana del vuelo, una respuesta se
reutiliza un rato y hay topes por tramo, por viaje y por día. Al viajero solo se le avisa cuando algo cambia y lo afecta.
"""
import json
import math
import os
from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Column, Integer, Text, text

from .. import config, db
from . import costo, eventos, geografia, precios, telegram, viajes

tramos_vuelo = db._tabla(
    "tramos_vuelo",  # un tramo por número de vuelo; guarda el último estado conocido
    db._ref("tramos_vuelo", "viaje_id", "viajes"), Column("sentido", Text), Column("orden", Integer),
    Column("aerolinea", Text), Column("numero", Text), Column("fecha", Text), Column("desde", Text), Column("hasta", Text),
    Column("sale_programada", Text), Column("llega_programada", Text), Column("estado", Text, default="programado"),
    Column("retraso_salida", Integer), Column("retraso_llegada", Integer), Column("terminal", Text), Column("puerta", Text),
    Column("llega_estimada", Text), Column("actualizado", Text), Column("consultas", Integer, default=0),
    Column("ultimo_aviso", Text),
    Column("omitida", Text),   # último motivo para no consultar: se registra una vez, no en cada refresco del tablero
    Column("ultima_consulta", Text),   # «con datos» o «sin datos»: una respuesta sin el bloque no borra el estado conocido
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


# ---------- reglas y momento ----------
REGLAS = {"monitoreo_horas_antes": 3, "monitoreo_cache_min": 60, "monitoreo_tope_tramo": 6, "monitoreo_tope_viaje": 12,
          "monitoreo_tope_dia": 30, "monitoreo_retraso_aviso_min": 15, "cupo_minimo_monitoreo": 25}
MINIMO_FORZADO = timedelta(minutes=1)   # «Actualizar ahora» una vez por minuto: absorbe el doble clic


def reglas() -> dict:
    """Las reglas editables del monitoreo, leídas una vez por petición."""
    cat = costo.catalogo()
    return {clave: costo.supuesto(cat, clave, defecto) for clave, defecto in REGLAS.items()}


def momento_actual() -> datetime:
    """Ahora, en UTC. Solo en local, `MONITOREO_AHORA` (fecha y hora ISO en UTC, por ejemplo 2026-12-13T06:00) fija el
    momento para demostrar el monitoreo de un vuelo futuro; fuera de local se ignora."""
    fijo = (os.getenv("MONITOREO_AHORA") or "").strip()
    if fijo and config.LOCAL:
        try:
            d = datetime.fromisoformat(fijo)
            return d if d.tzinfo else d.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def _texto(momento: datetime) -> str:
    return momento.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _momento(texto: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(texto).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


# ---------- zona horaria de cada aeropuerto ----------
_zonas_cache: dict = {}


def zona(iata: str | None):
    """Zona horaria de un aeropuerto: la de GeoNames del lugar más cercano (su ciudad o pueblo). Sin datos del aeropuerto,
    UTC; sin lugar cercano con zona, o si el sistema no conoce esa zona, la hora solar aproximada por la longitud."""
    if iata in _zonas_cache:
        return _zonas_cache[iata]
    a = geografia.aeropuerto(iata)
    resultado = UTC
    if a and a.get("lat") is not None:
        nombre = geografia.zona_horaria(a["lat"], a["lon"])
        try:
            resultado = ZoneInfo(nombre) if nombre else timezone(timedelta(hours=round(a["lon"] / 15)))
        except (ZoneInfoNotFoundError, ValueError):
            resultado = timezone(timedelta(hours=round(a["lon"] / 15)))
    _zonas_cache[iata] = resultado
    return resultado


def _en_utc(local: str | None, iata: str | None) -> datetime | None:
    """Una hora local del buscador («2026-12-13 09:05», hora del aeropuerto) en UTC."""
    try:
        return datetime.fromisoformat(local).replace(tzinfo=zona(iata)).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def ventana(t: dict, horas_antes: float = 3) -> tuple[datetime, datetime] | None:
    """Desde unas horas antes de la salida programada hasta la llegada (programada o estimada, la más tarde), en UTC."""
    sale = _en_utc(t["sale_programada"], t["desde"])
    llegadas = [x for x in (_en_utc(t["llega_programada"], t["hasta"]), _en_utc(t.get("llega_estimada"), t["hasta"])) if x]
    if not sale or not llegadas:
        return None
    return sale - timedelta(hours=horas_antes), max(llegadas)


# ---------- cuándo se consulta ----------
def _motivo(t: dict, ahora: datetime, forzar: bool, r: dict) -> str | None:
    """Por qué no se consulta ahora, o None si se puede. La ventana y los topes nunca se saltan; la caché, al forzar."""
    v = ventana(t, r["monitoreo_horas_antes"])
    if not v:
        return "sin hora programada"
    if not (v[0] <= ahora <= v[1]):
        return "fuera de la ventana"
    tope = int(r["monitoreo_tope_tramo"])
    if (t["consultas"] or 0) >= tope:
        return f"tope de {tope} consultas"
    # El tope del viaje se aplica a cada sentido: agotarlo en la ida no deja sin monitoreo el regreso
    tope = int(r["monitoreo_tope_viaje"])
    if db.uno("select coalesce(sum(consultas), 0) n from tramos_vuelo where viaje_id=:v and sentido=:s",
              v=t["viaje_id"], s=t["sentido"])["n"] >= tope:
        return f"tope de {tope} consultas del {'regreso' if t['sentido'] == 'regreso' else 'viaje de ida'}"
    tope = int(r["monitoreo_tope_dia"])
    if db.uno("select count(*) n from consultas_buscador where tipo='estado_vuelo' and origen='en vivo' and momento>=:d and momento<:h",
              d=ahora.strftime("%Y-%m-%d"), h=(ahora + timedelta(days=1)).strftime("%Y-%m-%d"))["n"] >= tope:
        return f"tope de {tope} consultas del día"
    try:
        cupo = precios.cupo()
    except Exception:
        cupo = None
    if cupo and cupo.get("restantes") is not None and cupo["restantes"] < r["cupo_minimo_monitoreo"]:
        return f"cupo del buscador bajo ({cupo['restantes']} búsquedas restantes)"
    previo = _momento(t["actualizado"])
    espera = MINIMO_FORZADO if forzar else timedelta(minutes=r["monitoreo_cache_min"])
    if previo and ahora - previo < espera:
        return f"consultado hace menos de {espera.total_seconds() / 60:g} min"
    return None


def _reservar(t: dict, ahora: datetime, forzar: bool, r: dict) -> bool:
    """Toma el turno de consultar con una sola escritura condicional: si dos peticiones llegan a la vez (dos pestañas,
    un doble clic), solo una paga la consulta. Cuenta la consulta antes de hacerla."""
    espera = MINIMO_FORZADO if forzar else timedelta(minutes=r["monitoreo_cache_min"])
    with db.motor.begin() as c:
        hecho = c.execute(text("""update tramos_vuelo set actualizado=:a, consultas=coalesce(consultas, 0)+1, omitida=null
                                  where id=:i and coalesce(consultas, 0)<:tope and (actualizado is null or actualizado<=:limite)"""),
                          {"a": _texto(ahora), "i": t["id"], "tope": int(r["monitoreo_tope_tramo"]),
                           "limite": _texto(ahora - espera)})
        return hecho.rowcount == 1


# ---------- avisos ----------
def _retraso(t: dict) -> int:
    return max(t.get("retraso_salida") or 0, t.get("retraso_llegada") or 0)


def _ultimo(t: dict) -> dict:
    valor = t.get("ultimo_aviso")
    return (db.de_json(valor, None) if isinstance(valor, str) else valor) or {}


def aviso(antes: dict, despues: dict, umbral: int = 15) -> str | None:
    """Texto del aviso al viajero, o None si nada cambió que lo afecte. Avisa: cancelación (una sola vez), retraso nuevo
    de `umbral` minutos o más (o que crece `umbral` minutos más desde el último aviso), cambio de terminal o de puerta."""
    ultimo = _ultimo(antes)
    if despues.get("estado") == "cancelado":
        ya = antes.get("estado") == "cancelado" or ultimo.get("cancelado")
        partes = [] if ya else ["el vuelo fue CANCELADO. Administración te ayudará a reprogramarlo"]
    else:
        partes = []
        base = ultimo.get("retraso", _retraso(antes))
        nuevo = _retraso(despues)
        if nuevo >= umbral and (base < umbral or nuevo - base >= umbral):
            hora = (despues.get("sale_estimada") or "")[11:16]
            partes.append(f"retraso de {nuevo} min" + (f" (sale hacia las {hora})" if hora else ""))
        for campo in ("terminal", "puerta"):
            if antes.get(campo) and despues.get(campo) and antes[campo] != despues[campo]:
                partes.append(f"cambio de {campo}: ahora {despues[campo]} (antes {antes[campo]})")
    if not partes:
        return None
    t = {**antes, **{k: v for k, v in despues.items() if v is not None}}
    return f"Vuelo {t.get('numero')} ({t.get('desde') or '?'} → {t.get('hasta') or '?'}, {t.get('fecha')}): " + "; ".join(partes) + "."


def _avisar(t: dict, texto: str, despues: dict, ahora: datetime) -> None:
    """Marca el aviso de forma condicional (dos consultas no avisan dos veces) y lo envía al titular por Telegram si lo
    tiene vinculado; si no, queda en el tablero. «aviso de vuelo enviado» solo si Telegram respondió bien."""
    marca = {"texto": texto, "momento": _texto(ahora), "retraso": _retraso(despues),
             "cancelado": despues.get("estado") == "cancelado" or bool(_ultimo(t).get("cancelado")), "enviado": False}
    with db.motor.begin() as c:
        tomado = c.execute(text("update tramos_vuelo set ultimo_aviso=:n where id=:i and coalesce(ultimo_aviso, '')=:p"),
                           {"n": json.dumps(marca, ensure_ascii=False), "i": t["id"], "p": t["ultimo_aviso"] or ""}).rowcount == 1
    if not tomado:
        return
    v = db.uno("select usuario_id from viajes where id=:v", v=t["viaje_id"]) or {}
    u = db.uno("select telegram_chat_id from usuarios where id=:u and activo=1", u=v.get("usuario_id") or 0) or {}
    error = None
    if telegram.activo() and u.get("telegram_chat_id"):
        try:
            telegram.enviar(u["telegram_chat_id"], texto)
            marca["enviado"] = True
        except telegram.ErrorTelegram as e:
            error = str(e)
    paso = "aviso de vuelo enviado" if marca["enviado"] else "aviso de vuelo fallido" if error else "aviso de vuelo sin Telegram"
    eventos.registrar("viaje", t["viaje_id"], paso, texto + (f" · error: {error}" if error else ""),
                      "Telegram" if marca["enviado"] or error else "tablero")
    db.actualizar("tramos_vuelo", t["id"], ultimo_aviso={**marca, "error": error})


def consultar(tramo_id: int, ahora: datetime | None = None, forzar: bool = False, reglas_: dict | None = None) -> dict:
    """Consulta el estado de un tramo si corresponde y avisa al viajero si algo cambió. Devuelve el tramo actualizado más
    "consultado" y, si no consultó, "motivo". `forzar` («Actualizar ahora») salta la caché, nunca el tope ni la ventana.

    Demostración con la respuesta guardada de ejemplo (IB 5634, Madrid → Lisboa, 13 de diciembre de 2026, retrasado
    20 min, puerta J58), en local y sin clave del buscador:
      1. en `.env`, `MONITOREO_AHORA=2026-12-13T06:00` (UTC; la ventana de ese vuelo va de 05:05 a 09:48 UTC);
      2. un viaje aprobado con ese tramo, por ejemplo:
         insert into tramos_vuelo (viaje_id, sentido, orden, aerolinea, numero, fecha, desde, hasta, sale_programada,
         llega_programada, estado, consultas) values (<id del viaje>, 'ida', 1, 'Iberia', 'IB 5634', '2026-12-13', 'MAD',
         'LIS', '2026-12-13 09:05', '2026-12-13 09:30', 'programado', 0);
      3. abrir «Viajes» en administración: el tablero consulta el tramo (lee el ejemplo, no gasta búsquedas), lo muestra
         retrasado con terminal 4 y puerta J58 y deja el aviso al viajero (por Telegram si tiene el chat vinculado).
    """
    ahora = ahora or momento_actual()
    ahora = ahora if ahora.tzinfo else ahora.replace(tzinfo=UTC)
    r_ = reglas_ or reglas()
    t = db.uno("select * from tramos_vuelo where id=:i", i=tramo_id)
    if not t:
        return {"consultado": False, "motivo": "tramo inexistente"}
    motivo = _motivo(t, ahora, forzar, r_)
    if not motivo and not _reservar(t, ahora, forzar, r_):
        motivo = "otra consulta de este vuelo acaba de hacerse"
    if motivo:
        if motivo != t["omitida"]:   # cada motivo una vez: el tablero pregunta cada 15 s
            db.actualizar("tramos_vuelo", tramo_id, omitida=motivo)
            eventos.registrar("viaje", t["viaje_id"], "consulta de estado omitida", f"{t['numero']}: {motivo}", "monitoreo")
        return {**db.uno("select * from tramos_vuelo where id=:i", i=tramo_id), "consultado": False, "motivo": motivo}
    solicitud = db.uno("select solicitud_id from viajes where id=:v", v=t["viaje_id"]) or {}
    r = precios.estado_vuelo(t["numero"], t["fecha"], solicitud.get("solicitud_id"))
    cambios = {"ultima_consulta": "con datos" if r else "sin datos"}
    if r:   # el proveedor escribe «-» cuando no sabe la terminal o la puerta: se conserva la última conocida
        cambios.update(estado=r["estado"], retraso_salida=r["retraso_salida"], retraso_llegada=r["retraso_llegada"],
                       terminal=r["terminal_salida"] or t["terminal"], puerta=r["puerta_salida"] or t["puerta"],
                       llega_estimada=r["llega_estimada"] or t["llega_estimada"])
    elif t["estado"] in (None, "programado", "sin datos"):
        cambios["estado"] = "sin datos"
    db.actualizar("tramos_vuelo", tramo_id, **cambios)
    if r:
        despues = {**t, **cambios, "sale_estimada": r.get("sale_estimada")}
        texto = aviso(t, despues, int(r_["monitoreo_retraso_aviso_min"]))
        if texto:
            _avisar(t, texto, despues, ahora)
    return {**db.uno("select * from tramos_vuelo where id=:i", i=tramo_id), "consultado": True}


# ---------- tablero ----------
ESTADOS = {"programado": "Programado", "a tiempo": "A tiempo", "retrasado": "Retrasado", "cancelado": "Cancelado",
           "aterrizado": "Aterrizado", "desviado": "Desviado", "sin datos": "Sin datos"}


def _filas(fechas: list[str]) -> list[dict]:
    marcas = {f"f{i}": f for i, f in enumerate(fechas)}
    return db.todos(f"""select t.*, v.creado viaje_creado, v.estado viaje_estado, v.solicitud_id, u.nombre titular,
                               s.llegar_antes, s.destino_lugar, s.carro_dia,
                               (select max(o.orden) from tramos_vuelo o where o.viaje_id=t.viaje_id and o.sentido='ida') ultimo_ida
                        from tramos_vuelo t join viajes v on v.id=t.viaje_id left join usuarios u on u.id=v.usuario_id
                        left join solicitudes s on s.id=v.solicitud_id
                        where t.fecha in ({", ".join(":" + k for k in marcas)}) and v.estado = 'aprobado'
                        order by t.sale_programada, t.id""", **marcas)  # noqa: S608  solo marcadores fijos


def completar(f: dict, ahora: datetime, cat: dict | None = None) -> dict:
    """Lo que el tablero muestra de un tramo: código del viaje, estado en palabras, retraso, hace cuánto se consultó, el
    último aviso y, en el último tramo de ida, si la llegada estimada (o la programada) más el traslado supera la hora límite."""
    f["codigo"] = viajes.codigo_viaje({"id": f["viaje_id"], "creado": f["viaje_creado"]})
    f["estado_texto"] = ESTADOS.get(f["estado"], f["estado"] or "Programado")
    f["retraso"] = _retraso(f)
    previo = _momento(f["actualizado"])
    f["hace_min"] = max(math.floor((ahora - previo).total_seconds() / 60), 0) if previo else None
    f["aviso"] = _ultimo(f) or None
    f["no_llega"], f["en_destino"] = False, None
    if f["sentido"] == "ida" and f["orden"] == f["ultimo_ida"] and f["llegar_antes"]:
        try:
            llegada = datetime.fromisoformat((f["llega_estimada"] or f["llega_programada"]).replace(" ", "T"))
            lugar = db.de_json(f["destino_lugar"], None) if isinstance(f["destino_lugar"], str) else f["destino_lugar"]
            tr = costo.traslado(geografia.aeropuerto(f["hasta"]), lugar, (f["carro_dia"] or 0) > 0, cat or costo.catalogo())
            en_destino = llegada + timedelta(hours=tr["horas"] if tr else 0)
            f["en_destino"] = en_destino.strftime("%Y-%m-%d %H:%M")
            f["no_llega"] = en_destino > datetime.fromisoformat(f["llegar_antes"])
        except (AttributeError, TypeError, ValueError):
            pass
    return f


def tablero(fecha: str | None = None, ahora: datetime | None = None, reglas_: dict | None = None) -> list[dict]:
    """Tramos para el tablero. Con fecha, los de ese día. Sin ella, los de hoy (UTC) más los de ayer y mañana cuya
    ventana contiene este momento: un vuelo nocturno en América cambia de día en UTC y no debe desaparecer."""
    ahora = ahora or momento_actual()
    cat = costo.catalogo()
    if fecha:
        filas = _filas([fecha])
    else:
        r_ = reglas_ or reglas()
        hoy = ahora.astimezone(UTC).date()
        filas = []
        for f in _filas([(hoy + timedelta(days=d)).isoformat() for d in (-1, 0, 1)]):
            v = ventana(f, r_["monitoreo_horas_antes"])
            if f["fecha"] == hoy.isoformat() or (v and v[0] <= ahora <= v[1]):
                filas.append(f)
    return [completar(f, ahora, cat) for f in filas]


def del_dia(fecha: str) -> list[dict]:
    return tablero(fecha)


def hoy() -> str:
    return momento_actual().astimezone(UTC).date().isoformat()


def fecha_valida(texto: str | None) -> str | None:
    try:
        return date.fromisoformat(texto or "").isoformat()
    except ValueError:
        return None
