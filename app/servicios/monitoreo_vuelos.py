"""Monitoreo del vuelo: los tramos del vuelo elegido, registrados al decidir, y su estado el día del viaje.

Cuidar el plan del buscador (250 búsquedas al mes): solo se consulta dentro de la ventana del vuelo, una respuesta se
reutiliza un rato y hay topes por tramo, por viaje y por día. Al viajero solo se le avisa cuando algo cambia y lo afecta.
"""
import json
import math
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Column, Integer, Text

from .. import db
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


# ---------- zona horaria de cada aeropuerto ----------
_zonas_cache: dict = {}


def _coordenada(texto: str, grados: int) -> float:
    signo = -1 if texto[0] == "-" else 1
    cifras = texto[1:]
    g, m, s = int(cifras[:grados]), int(cifras[grados:grados + 2]), int(cifras[grados + 2:grados + 4] or 0)
    return signo * (g + m / 60 + s / 3600)


def _zonas() -> list[tuple[set, float, float, str]]:
    """Zonas de la base de datos de zonas horarias (IANA), con el país y las coordenadas de su ciudad principal."""
    if "lista" in _zonas_cache:
        return _zonas_cache["lista"]
    rutas = [Path("/usr/share/zoneinfo/zone1970.tab"), Path("/usr/share/zoneinfo/zone.tab")]
    try:
        import tzdata
        rutas = [Path(tzdata.__file__).parent / "zoneinfo" / n for n in ("zone1970.tab", "zone.tab")] + rutas
    except ImportError:
        pass
    lista = []
    for ruta in rutas:
        if not ruta.is_file():
            continue
        for linea in ruta.read_text().splitlines():
            if linea.startswith("#") or not linea.strip():
                continue
            partes = linea.split("\t")
            coord = partes[1]
            corte = max(coord.rfind("+"), coord.rfind("-"))
            lat = _coordenada(coord[:corte], 2)
            lon = _coordenada(coord[corte:], 3)
            lista.append((set(partes[0].split(",")), lat, lon, partes[2]))
        break
    _zonas_cache["lista"] = lista
    return lista


def zona(iata: str | None):
    """Zona horaria de un aeropuerto: la de la ciudad principal más cercana del mismo país en la base de zonas horarias.
    Sin datos del aeropuerto, UTC; sin la base de zonas, la hora solar aproximada por la longitud."""
    if iata in _zonas_cache:
        return _zonas_cache[iata]
    a = geografia.aeropuerto(iata)
    resultado = UTC
    if a and a.get("lat") is not None:
        candidatas = [z for z in _zonas() if a.get("pais") in z[0]] or _zonas()
        if candidatas:
            nombre = min(candidatas, key=lambda z: geografia.distancia_km(a["lat"], a["lon"], z[1], z[2]))[3]
            try:
                resultado = ZoneInfo(nombre)
            except ZoneInfoNotFoundError:
                resultado = timezone(timedelta(hours=round(a["lon"] / 15)))
        else:
            resultado = timezone(timedelta(hours=round(a["lon"] / 15)))
    _zonas_cache[iata] = resultado
    return resultado


def _en_utc(local: str | None, iata: str | None) -> datetime | None:
    """Una hora local del buscador («2026-12-13 09:05», hora del aeropuerto) en UTC."""
    try:
        return datetime.fromisoformat(local).replace(tzinfo=zona(iata)).astimezone(UTC)
    except (TypeError, ValueError):
        return None


# ---------- cuándo se consulta ----------
def _regla(clave: str, defecto: float) -> float:
    return costo.supuesto(costo.catalogo(), clave, defecto)


def _momento(texto: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(texto).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _motivo(t: dict, ahora: datetime, forzar: bool) -> str | None:
    """Por qué no se consulta ahora, o None si se puede. La ventana y los topes nunca se saltan; la caché, al forzar."""
    sale = _en_utc(t["sale_programada"], t["desde"])
    llegadas = [x for x in (_en_utc(t["llega_programada"], t["hasta"]), _en_utc(t["llega_estimada"], t["hasta"])) if x]
    if not sale or not llegadas:
        return "sin hora programada"
    if not (sale - timedelta(hours=_regla("monitoreo_horas_antes", 3)) <= ahora <= max(llegadas)):
        return "fuera de la ventana"
    tope = int(_regla("monitoreo_tope_tramo", 6))
    if (t["consultas"] or 0) >= tope:
        return f"tope de {tope} consultas"
    tope = int(_regla("monitoreo_tope_viaje", 12))
    if db.uno("select coalesce(sum(consultas), 0) n from tramos_vuelo where viaje_id=:v", v=t["viaje_id"])["n"] >= tope:
        return f"tope de {tope} consultas del viaje"
    tope = int(_regla("monitoreo_tope_dia", 30))
    hoy = datetime.now(UTC).strftime("%Y-%m-%d")
    if db.uno("select count(*) n from consultas_buscador where tipo='estado_vuelo' and origen='en vivo' and momento>=:d",
              d=hoy)["n"] >= tope:
        return f"tope de {tope} consultas del día"
    minimo = _regla("cupo_minimo_monitoreo", 25)
    try:
        cupo = precios.cupo()
    except Exception:
        cupo = None
    if cupo and cupo.get("restantes") is not None and cupo["restantes"] < minimo:
        return f"cupo del buscador bajo ({cupo['restantes']} búsquedas restantes)"
    cache = _regla("monitoreo_cache_min", 60)
    previo = _momento(t["actualizado"])
    if not forzar and previo and ahora - previo < timedelta(minutes=cache):
        return f"consultado hace menos de {cache:g} min"
    return None


# ---------- avisos ----------
def _retraso(t: dict) -> int:
    return max(t.get("retraso_salida") or 0, t.get("retraso_llegada") or 0)


def aviso(antes: dict, despues: dict, umbral: int = 15) -> str | None:
    """Texto del aviso al viajero, o None si nada cambió que lo afecte. Avisa: cancelación, retraso nuevo de `umbral`
    minutos o más (o que crece `umbral` minutos más desde el último aviso), cambio de terminal o de puerta."""
    if despues.get("estado") == "cancelado":
        partes = [] if antes.get("estado") == "cancelado" else ["el vuelo fue CANCELADO. Administración te ayudará a reprogramarlo"]
    else:
        partes = []
        ultimo = db.de_json(antes.get("ultimo_aviso"), None) if isinstance(antes.get("ultimo_aviso"), str) else antes.get("ultimo_aviso")
        base = (ultimo or {}).get("retraso", _retraso(antes))
        nuevo = _retraso(despues)
        if nuevo >= umbral and (base < umbral or nuevo - base >= umbral):
            hora = (despues.get("sale_estimada") or "")[11:16]
            partes.append(f"retraso de {nuevo} min" + (f" (sale hacia las {hora})" if hora else ""))
        for campo, nombre in (("terminal", "terminal"), ("puerta", "puerta")):
            if antes.get(campo) and despues.get(campo) and antes[campo] != despues[campo]:
                partes.append(f"cambio de {nombre}: ahora {despues[campo]} (antes {antes[campo]})")
    if not partes:
        return None
    t = {**antes, **{k: v for k, v in despues.items() if v is not None}}
    return f"Vuelo {t.get('numero')} ({t.get('desde') or '?'} → {t.get('hasta') or '?'}, {t.get('fecha')}): " + "; ".join(partes) + "."


def _avisar(t: dict, texto: str, retraso: int, ahora: datetime) -> dict:
    """Envía el aviso al titular por Telegram si lo tiene vinculado; si no, queda solo en el tablero. Siempre deja rastro."""
    v = db.uno("select usuario_id from viajes where id=:v", v=t["viaje_id"]) or {}
    u = db.uno("select telegram_chat_id from usuarios where id=:u and activo=1", u=v.get("usuario_id") or 0) or {}
    enviado = telegram.activo() and bool(u.get("telegram_chat_id"))
    if enviado:
        telegram.avisar(v["usuario_id"], texto)
    eventos.registrar("viaje", t["viaje_id"], "aviso de vuelo enviado" if enviado else "aviso de vuelo sin Telegram", texto,
                      "Telegram" if enviado else "tablero")
    return {"texto": texto, "momento": ahora.strftime("%Y-%m-%d %H:%M:%S"), "retraso": retraso, "enviado": enviado}


def consultar(tramo_id: int, ahora: datetime | None = None, forzar: bool = False) -> dict:
    """Consulta el estado de un tramo si corresponde y avisa al viajero si algo cambió. Devuelve el tramo actualizado más
    "consultado" y, si no consultó, "motivo". `forzar` («Actualizar ahora») salta la caché, nunca el tope ni la ventana."""
    ahora = ahora or datetime.now(UTC)
    ahora = ahora if ahora.tzinfo else ahora.replace(tzinfo=UTC)
    t = db.uno("select * from tramos_vuelo where id=:i", i=tramo_id)
    if not t:
        return {"consultado": False, "motivo": "tramo inexistente"}
    motivo = _motivo(t, ahora, forzar)
    if motivo:
        if motivo != t["omitida"]:   # cada motivo una vez: el tablero pregunta cada 15 s
            db.actualizar("tramos_vuelo", tramo_id, omitida=motivo)
            eventos.registrar("viaje", t["viaje_id"], "consulta de estado omitida", f"{t['numero']}: {motivo}", "monitoreo")
        return {**t, "omitida": motivo, "consultado": False, "motivo": motivo}
    solicitud = db.uno("select solicitud_id from viajes where id=:v", v=t["viaje_id"]) or {}
    r = precios.estado_vuelo(t["numero"], t["fecha"], solicitud.get("solicitud_id"))
    cambios = {"consultas": (t["consultas"] or 0) + 1, "actualizado": ahora.strftime("%Y-%m-%d %H:%M:%S"), "omitida": None}
    if r:
        cambios.update(estado=r["estado"], retraso_salida=r["retraso_salida"], retraso_llegada=r["retraso_llegada"],
                       terminal=r["terminal_salida"], puerta=r["puerta_salida"], llega_estimada=r["llega_estimada"])
    else:
        cambios["estado"] = "sin datos"
    despues = {**t, **cambios, "sale_estimada": (r or {}).get("sale_estimada")}
    texto = aviso(t, despues, int(_regla("monitoreo_retraso_aviso_min", 15))) if r else None
    if texto:
        cambios["ultimo_aviso"] = json.dumps(_avisar(t, texto, _retraso(despues), ahora), ensure_ascii=False)
    db.actualizar("tramos_vuelo", tramo_id, **cambios)
    return {**db.uno("select * from tramos_vuelo where id=:i", i=tramo_id), "consultado": True}


# ---------- tablero del día ----------
ESTADOS = {"programado": "Programado", "a tiempo": "A tiempo", "retrasado": "Retrasado", "cancelado": "Cancelado",
           "aterrizado": "Aterrizado", "desviado": "Desviado", "sin datos": "Sin datos"}


def del_dia(fecha: str) -> list[dict]:
    """Tramos que vuelan ese día, con su viaje y su persona. En el último tramo de ida se compara la llegada estimada
    (o la programada) más el traslado con la hora límite de la grabación."""
    filas = db.todos("""select t.*, v.creado viaje_creado, v.estado viaje_estado, v.solicitud_id, u.nombre titular,
                               s.llegar_antes, s.destino_lugar, s.carro_dia,
                               (select max(o.orden) from tramos_vuelo o where o.viaje_id=t.viaje_id and o.sentido='ida') ultimo_ida
                        from tramos_vuelo t join viajes v on v.id=t.viaje_id left join usuarios u on u.id=v.usuario_id
                        left join solicitudes s on s.id=v.solicitud_id
                        where t.fecha=:f and v.estado in ('aprobado', 'pendiente_aprobacion')
                        order by t.sale_programada, t.id""", f=fecha)
    cat = costo.catalogo()
    ahora = datetime.now(UTC)
    for f in filas:
        f["codigo"] = viajes.codigo_viaje({"id": f["viaje_id"], "creado": f["viaje_creado"]})
        f["estado_texto"] = ESTADOS.get(f["estado"], f["estado"] or "Programado")
        f["retraso"] = _retraso(f)
        previo = _momento(f["actualizado"])
        f["hace_min"] = math.floor((ahora - previo).total_seconds() / 60) if previo else None
        f["no_llega"], f["en_destino"] = False, None
        if f["sentido"] == "ida" and f["orden"] == f["ultimo_ida"] and f["llegar_antes"]:
            try:
                llegada = datetime.fromisoformat((f["llega_estimada"] or f["llega_programada"]).replace(" ", "T"))
                lugar = db.de_json(f["destino_lugar"], None) if isinstance(f["destino_lugar"], str) else f["destino_lugar"]
                tr = costo.traslado(geografia.aeropuerto(f["hasta"]), lugar, (f["carro_dia"] or 0) > 0, cat)
                en_destino = llegada + timedelta(hours=tr["horas"] if tr else 0)
                f["en_destino"] = en_destino.strftime("%Y-%m-%d %H:%M")
                f["no_llega"] = en_destino > datetime.fromisoformat(f["llegar_antes"])
            except (AttributeError, TypeError, ValueError):
                pass
    return filas
