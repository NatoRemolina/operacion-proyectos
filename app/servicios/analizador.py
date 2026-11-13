"""Lectura de la página del vuelo en Google Flights, bajo demanda, para verificar lo que dio el buscador.

La API no abre el navegador: llama al analizador (`analizador/`), un servicio aparte con Playwright. En local es el
servicio `analizador` de `docker compose` (`ANALIZADOR_URL`); en AWS, una función Lambda con su propia imagen
(`ANALIZADOR_FUNCION`). Sin ninguno de los dos, o con `ANALIZADOR=apagado`, no se lee nada y el desglose muestra solo
lo del buscador.

Reglas:
- un análisis por itinerario (sus números de vuelo y la fecha de salida) y fechas de la cotización; se reutiliza
  mientras tenga menos de 60 minutos;
- topes editables por día: `analisis_persona_dia` (10) y `analisis_vuelo_dia` (40 en total);
- uno a la vez: si otra lectura está en curso, se pide esperar un minuto;
- lo leído no reemplaza el precio del buscador: si difiere, se avisa.
"""
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from sqlalchemy import Column, Integer, Text, text

from .. import config, db
from . import almacen, compras, costo, eventos, precios

analisis_vuelo = db._tabla(
    "analisis_vuelo",   # una fila por lectura de la página de un vuelo; solo la usa el servidor
    db._ref("analisis_vuelo", "opcion_id", "opciones"), db._ref("analisis_vuelo", "solicitud_id", "solicitudes"),
    db._ref("analisis_vuelo", "usuario_id", "usuarios"),
    Column("clave", Text, nullable=False),      # itinerario y fechas: «AA1851_2026-12-08_2026-12-08_2026-12-11»
    Column("url", Text, nullable=False),
    Column("estado", Text, nullable=False),     # pendiente | listo | fallido
    Column("motivo", Text), Column("datos", Text), Column("captura", Text),   # captura: ruta en el almacenamiento
    Column("duracion_ms", Integer), Column("creado", Text), Column("terminado", Text),
    # «ir a» (pieza 3b): la misma tabla y el mismo turno; nunca guarda el envío al vendedor
    Column("accion", Text), Column("vendedor", Text), Column("tarifa", Text), Column("camino", Text),
)
LEER = "coalesce(accion, 'leer')='leer'"
cupos_buscador = db._tabla(
    "cupos_buscador",   # el cupo de búsquedas pagas, reservado antes de buscar (bajo cerrojo): ningún pedido lo pasa
    db._ref("cupos_buscador", "usuario_id", "usuarios"), Column("tipo", Text, nullable=False), Column("clave", Text),
    Column("unidades", Integer, nullable=False), Column("creado", Text),
)
BLOQUEO_CUPO = 7_311_804
TOPE_ENLACE_VENDEDOR = 20   # la regla `enlace_vendedor_persona_dia` (la crea cotizacion.asegurar_reglas_vendedor)   # las lecturas de la página; «ir a» tiene su propio tope

VIGENCIA = timedelta(minutes=60)
EN_CURSO = timedelta(minutes=2)      # una lectura que no terminó en este tiempo ya no va a terminar
FUNCION = timedelta(seconds=70)      # lo que puede seguir viva la función (60 s en infra) más un margen: una llamada sin
#                                      respuesta retiene el turno hasta entonces, para no arrancar dos Chromium a la vez
SIN_RESPUESTA = "el analizador no respondió"
ESPERA_S = 54   # la lectura cabe en 45 s (analizador/navegador.py); el margen cubre el arranque en frío de la función, siempre
#                 por debajo de los 60 s de CloudFront
TOPE_PERSONA, TOPE_TOTAL = 10, 40     # si las reglas no existen
REGLAS = (
    ("analisis_persona_dia", str(TOPE_PERSONA), "Lecturas de la página del vuelo en Google Flights por persona y día. "
                                                "Alcanzado, el desglose muestra solo lo del buscador."),
    ("analisis_vuelo_dia", str(TOPE_TOTAL), "Lecturas de la página del vuelo en Google Flights por día, en total. "
                                            "Alcanzado, el desglose muestra solo lo del buscador."),
    ("ir_a_persona_dia", "20", "Veces por persona y día que el analizador lleva a la tarifa elegida de un vendedor («Ir a…»). "
                               "Alcanzado, el enlace sale del buscador o de Google Flights."),
    ("ir_a_dia", "60", "Veces por día, en total, que el analizador lleva a la tarifa elegida de un vendedor («Ir a…»). "
                       "Alcanzado, el enlace sale de Google Flights."),
)
TOPE_IR_A, TOPE_IR_A_TOTAL = 20, 60
APAGADO = "La lectura de Google Flights está apagada: el desglose muestra solo lo del buscador."
SIN_ANALIZADOR = "Este entorno no tiene el analizador de Google Flights: el desglose muestra solo lo del buscador."
TOPE_PERSONA_TEXTO = "Llegaste al tope de lecturas de Google Flights de hoy: el desglose muestra solo lo del buscador."
TOPE_TOTAL_TEXTO = "Se alcanzó el tope de lecturas de Google Flights de hoy: el desglose muestra solo lo del buscador."
OCUPADO = "Se está leyendo la página de otro vuelo. Intenta de nuevo en un minuto."
SIN_TRAMOS = "Este vuelo no trae sus tramos completos: no se puede abrir su página en Google Flights."


try:
    ZONA_EMPRESA = ZoneInfo("America/Bogota")
except ZoneInfoNotFoundError:   # sin base de zonas: Bogotá no cambia de hora (UTC−5 todo el año)
    ZONA_EMPRESA = timezone(timedelta(hours=-5), "America/Bogota")


def inicio_del_dia(ahora: datetime | None = None) -> str:
    """Desde cuándo cuentan los topes «por día»: la medianoche de hoy en Bogotá, en UTC (como se guardan los momentos)."""
    local = (ahora or datetime.now(UTC)).astimezone(ZONA_EMPRESA)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def tope_enlace_vendedor() -> int:
    return int(costo.supuesto(costo.catalogo(), "enlace_vendedor_persona_dia", TOPE_ENLACE_VENDEDOR))


def reservar_cupo(usuario: dict, clave_busqueda: str, unidades: int) -> bool:
    """Reserva `unidades` búsquedas pagas del cupo diario del enlace al vendedor antes de hacerlas, en fila con las
    demás reservas (cerrojo de transacción; en SQLite, el de escritura). False si no alcanza: no se busca nada."""
    with db.transaccion() as c:
        if not config.ES_SQLITE:
            c.execute(text("select pg_advisory_xact_lock(:k)"), {"k": BLOQUEO_CUPO})
        usadas = db.uno("""select coalesce(sum(unidades), 0) n from cupos_buscador where tipo='enlace_vendedor'
                           and usuario_id=:u and creado>=:h""", u=usuario["id"], h=inicio_del_dia())["n"]
        if usadas + unidades > tope_enlace_vendedor():
            return False
        db.insertar("cupos_buscador", usuario_id=usuario["id"], tipo="enlace_vendedor", clave=clave_busqueda,
                    unidades=unidades, creado=db.ahora())
        return True


def unidades_busqueda(sol: dict, vuelo: dict) -> int:
    """Búsquedas pagas de una apertura: las opciones de reserva y, si el regreso no está guardado, el regreso."""
    lado = lambda nombre: precios.codigos(sol.get(f"{nombre}_aeropuertos") or sol[nombre])  # noqa: E731
    guardado = precios.regreso_guardado(vuelo, lado("origen"), lado("destino"), sol["ida"], sol["regreso"])
    return 1 if guardado else 2


def _hace(delta: timedelta) -> str:
    return (datetime.now(UTC) - delta).strftime("%Y-%m-%d %H:%M:%S")


def _modo() -> tuple[str, str] | None:
    if os.environ.get("ANALIZADOR_URL"):
        return "http", os.environ["ANALIZADOR_URL"].rstrip("/")
    if os.environ.get("ANALIZADOR_FUNCION"):
        return "lambda", os.environ["ANALIZADOR_FUNCION"]
    return None


def apagado() -> bool:
    return os.environ.get("ANALIZADOR", "").strip().lower() == "apagado"


def topes() -> tuple[int, int]:
    cat = costo.catalogo()
    return (int(costo.supuesto(cat, "analisis_persona_dia", TOPE_PERSONA)),
            int(costo.supuesto(cat, "analisis_vuelo_dia", TOPE_TOTAL)))


def asegurar_reglas() -> int:
    """Los dos topes como reglas editables (Reglas y supuestos). La migración lo llama; no pisa un valor ya editado."""
    nuevas = 0
    for clave, valor, nota in REGLAS:
        if not db.uno("select id from reglas where ambito='supuesto' and clave=:c", c=clave):
            db.insertar("reglas", ambito="supuesto", entidad="", tarifa="", clave=clave, valor=valor, nota=nota,
                        fuente="Supuesto editable", confianza="supuesto", verificado="2026-11-13")
            nuevas += 1
    return nuevas


# ---------- el itinerario ----------
def _opcion(sid: int, opcion_id: int) -> tuple[dict, dict, dict]:
    """(cotización, opción, datos del vuelo). LookupError si el vuelo no es de la cotización."""
    sol = db.uno("select * from solicitudes where id=:i", i=sid)
    o = db.uno("select * from opciones where id=:o and solicitud_id=:s and tipo='vuelo'", o=opcion_id, s=sid) if sol else None
    if not o:
        raise LookupError(opcion_id)
    return sol, o, db.de_json(o["datos"], {}) or {}


def enlace_itinerario(sol: dict, vuelo: dict) -> str:
    """La página de Google Flights con la ida de este vuelo ya elegida (la misma búsqueda de la cotización).
    ValueError si el vuelo no trae sus tramos completos."""
    lado = lambda nombre: precios.codigos(sol.get(f"{nombre}_aeropuertos") or sol[nombre])  # noqa: E731
    return precios.construir_enlace_vuelos(lado("origen"), lado("destino"), sol["ida"], sol["regreso"], vuelo.get("tramos") or [])


def clave(sol: dict, vuelo: dict) -> str:
    numeros = "".join((n or "").replace(" ", "") for n in vuelo.get("numeros") or [])
    return f"{numeros}_{(vuelo.get('sale') or '')[:10]}_{sol['ida']}_{sol['regreso']}"


# ---------- leer y guardar ----------
def _fila(f: dict | None) -> dict | None:
    if not f:
        return None
    return {**f, "datos": db.de_json(f["datos"], None)}


REUSO_FALLIDO = timedelta(minutes=10)   # una lectura fallida no se repite enseguida: ni golpea a Google ni gasta el tope


def vigente(clave_lectura: str) -> dict | None:
    """La última lectura de este itinerario y fechas (de cualquier cotización) que todavía vale: `listo` de menos de 60
    minutos, `fallido` de menos de 10 o una `pendiente` en curso."""
    f = db.uno(f"""select * from analisis_vuelo where clave=:k and {LEER} and ((estado='listo' and creado>=:v)
                  or (estado='fallido' and creado>=:f) or (estado='pendiente' and creado>=:c)) order by id desc limit 1""",
               k=clave_lectura, v=_hace(VIGENCIA), f=_hace(REUSO_FALLIDO), c=_hace(EN_CURSO))
    return _fila(f)


def clave_de(sid: int, opcion_id: int) -> str:
    """La clave de lectura de un vuelo de la cotización. LookupError si el vuelo no es de ella."""
    sol, _, vuelo = _opcion(sid, opcion_id)
    return clave(sol, vuelo)


def ultimo(sid: int, opcion_id: int) -> dict | None:
    return _fila(db.uno(f"select * from analisis_vuelo where clave=:k and {LEER} order by id desc limit 1", k=clave_de(sid, opcion_id)))


def de_la_cotizacion(sid: int, analisis_id: int) -> dict | None:
    """Una lectura que se puede ver desde la cotización: la de alguno de sus vuelos (aunque la pidiera otra)."""
    a = db.uno("select * from analisis_vuelo where id=:a", a=analisis_id)
    if not a:
        return None
    sol = db.uno("select * from solicitudes where id=:i", i=sid)
    vuelos = db.todos("select datos from opciones where solicitud_id=:s and tipo='vuelo'", s=sid) if sol else []
    return a if any(clave(sol, db.de_json(v["datos"], {}) or {}) == a["clave"] for v in vuelos) else None


SIN_SERVICIO = "El analizador de Google Flights no está disponible en este momento: el desglose muestra solo lo del buscador."
# La invocación no llegó a leer nada: no es una lectura (no se guarda ni cuenta para los topes)
NO_LLEGO = {"TooManyRequestsException": OCUPADO, "ResourceNotFoundException": SIN_SERVICIO}


def _llamar(url: str, regreso: dict | None = None) -> dict:
    """Lectura de la página (con el regreso de la cotización, si se conoce)."""
    return _invocar({"url": url, "regreso": regreso})


def _invocar(pedido: dict) -> dict:
    """La respuesta del analizador; un fallo de la llamada se devuelve como lectura fallida, nunca como excepción.
    Si el servicio no está (conexión rechazada, función inexistente o sin turno): `{"no_disponible": motivo}`."""
    modo = _modo()
    try:
        if modo[0] == "http":
            try:
                return httpx.post(f"{modo[1]}/analizar", json=pedido, timeout=ESPERA_S).json()
            except httpx.ConnectError:
                return {"no_disponible": SIN_SERVICIO}   # docker compose sin el perfil «analizador»
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError
        cliente = boto3.client("lambda", config=Config(read_timeout=ESPERA_S, retries={"max_attempts": 0}))
        try:
            r = cliente.invoke(FunctionName=modo[1], Payload=json.dumps(pedido).encode())
        except ClientError as e:
            codigo = e.response.get("Error", {}).get("Code")
            if codigo in NO_LLEGO:
                return {"no_disponible": NO_LLEGO[codigo]}
            raise
        cuerpo = json.loads(r["Payload"].read() or b"{}")
        if r.get("FunctionError"):
            return {"estado": "fallido", "motivo": "el analizador falló al leer la página"}
        return cuerpo
    except Exception as e:   # red, tiempo agotado, respuesta que no es JSON
        print(f"analizador: la llamada falló: {type(e).__name__}", flush=True)   # el detalle, solo al registro
        return {"estado": "fallido", "motivo": SIN_RESPUESTA}


def _guardar_captura(b64: str | None) -> str | None:
    if not isinstance(b64, str) or not b64:
        return None
    try:
        png = base64.b64decode(b64, validate=True)
    except ValueError:
        return None
    if not png.startswith(b"\x89PNG"):
        return None
    return almacen.guardar(almacen.clave(hashlib.sha256(png).hexdigest(), "png"), png, "image/png")


def captura(analisis: dict) -> bytes | None:
    return almacen.leer(analisis["captura"]) if analisis.get("captura") else None


def no_disponible(motivo: str) -> dict:
    return {"id": None, "estado": "no_disponible", "motivo": motivo, "datos": None, "captura": None, "url": None,
            "creado": None, "terminado": None, "duracion_ms": None, "reutilizado": False}


BLOQUEO_TURNO = 7_311_803   # clave propia del cerrojo de transacción (PostgreSQL) que pone en fila las reservas de turno
NO_TERMINO = "la lectura no terminó"


def _reservar(usuario: dict, sid: int, opcion_id: int, sol: dict, vuelo: dict) -> dict:
    """Toma el turno de lectura en fila con las demás reservas: cuenta los topes, comprueba que no haya otra lectura en
    curso e inserta la fila `pendiente` en la misma transacción. En PostgreSQL con un cerrojo de transacción (nunca de
    sesión: el agrupador reparte las conexiones); en SQLite la transacción ya toma el cerrojo de escritura.

    Devuelve `{"id", "url"}` con el turno tomado; si no, la lectura reutilizada o `no_disponible` con su motivo."""
    try:
        url = enlace_itinerario(sol, vuelo)
    except ValueError:
        url = None
    with db.transaccion() as c:
        if not config.ES_SQLITE:
            c.execute(text("select pg_advisory_xact_lock(:k)"), {"k": BLOQUEO_TURNO})
        # una lectura que se quedó a medias (caída del proceso) no retiene el turno ni cuenta como en curso
        db.ejecutar("update analisis_vuelo set estado='fallido', motivo=:m, terminado=:t where estado='pendiente' and creado<:c",
                    m=NO_TERMINO, t=db.ahora(), c=_hace(EN_CURSO))
        previo = vigente(clave(sol, vuelo))
        if previo:
            return {**previo, "reutilizado": True}
        if apagado():
            return no_disponible(APAGADO)
        if not _modo():
            return no_disponible(SIN_ANALIZADOR)
        if not url:
            return no_disponible(SIN_TRAMOS)
        hoy = inicio_del_dia()
        por_persona, total = topes()
        if db.uno(f"select count(*) n from analisis_vuelo where usuario_id=:u and creado>=:h and {LEER}",
                  u=usuario["id"], h=hoy)["n"] >= por_persona:
            return no_disponible(TOPE_PERSONA_TEXTO)
        if db.uno(f"select count(*) n from analisis_vuelo where creado>=:h and {LEER}", h=hoy)["n"] >= total:
            return no_disponible(TOPE_TOTAL_TEXTO)
        if _ocupado():
            return no_disponible(OCUPADO)
        aid = db.insertar("analisis_vuelo", opcion_id=opcion_id, solicitud_id=sid, usuario_id=usuario["id"],
                          clave=clave(sol, vuelo), url=url, estado="pendiente", creado=db.ahora())
    return {"id": aid, "url": url}


def _ocupado() -> bool:
    """Si el analizador está en uso: una lectura, un «ir a» o una captura en curso, o una llamada que se quedó sin
    respuesta hace menos de lo que puede durar la función (sigue viva aunque la API ya no la espere)."""
    if db.uno("""select id from analisis_vuelo where estado='pendiente' or (motivo=:m and creado>=:h) limit 1""",
              m=SIN_RESPUESTA, h=_hace(FUNCION)):
        return True
    # las capturas del trabajador (pieza 5) usan el mismo analizador: una en curso, o sin respuesta hace poco, lo ocupa
    return bool(db.uno("""select id from capturas where estado='en_curso' or (fallo=:m and terminado>=:h) limit 1""",
                       m=SIN_RESPUESTA, h=_hace(FUNCION)))


SIN_CAPTURA = "no se pudo guardar la lectura"
RESPUESTA_RARA = "el analizador respondió algo que no se entiende"


def _resultado_de(r) -> dict:
    """Los cambios de la fila según la respuesta del analizador. Una respuesta que no es un objeto es una lectura fallida."""
    if not isinstance(r, dict):
        return {"estado": "fallido", "terminado": db.ahora(), "motivo": RESPUESTA_RARA, "captura": None, "datos": None}
    listo = r.get("estado") == "listo" and isinstance(r.get("datos"), dict)
    duracion = r.get("duracion_ms") if isinstance(r.get("duracion_ms"), int) else None
    return {"estado": "listo" if listo else "fallido", "terminado": db.ahora(), "duracion_ms": duracion,
            "motivo": None if listo else str(r.get("motivo") or "la lectura no devolvió datos")[:300],
            # una lectura fallida guarda lo que se vio (si el analizador lo trae): sirve para saber por qué falló
            "captura": _guardar_captura(r.get("captura_png_b64")),
            "datos": r["datos"] if listo else ({"extracto": str(r["extracto"])[:500]} if r.get("extracto") else None)}


def _no_dejar_pendiente(aid: int | None):
    """Al salir por cualquier camino (también por un error de la bitácora o de la base), la fila no queda «pendiente»:
    retendría el turno de todos durante 2 minutos."""
    if not aid:
        return
    try:
        db.ejecutar("update analisis_vuelo set estado='fallido', motivo=:m, terminado=:t where id=:i and estado='pendiente'",
                    m=SIN_CAPTURA, t=db.ahora(), i=aid)
    except Exception as e:  # noqa: BLE001 (si la base no responde, la limpieza de las pendientes viejas la cubre)
        print(f"analizador: no se pudo cerrar la lectura {aid}: {type(e).__name__}", flush=True)


def solicitar(usuario: dict, sid: int, opcion_id: int, canal: str = "api v1") -> dict:
    """Lee la página del vuelo (o reutiliza una lectura de menos de 60 minutos) y devuelve el análisis.

    Quien llama comprueba antes que la persona ve la cotización. LookupError si el vuelo no es de ella. Si no se puede
    leer (apagado, sin analizador, topes, otra lectura en curso, vuelo sin tramos) devuelve `estado: no_disponible`
    con el motivo, sin guardar nada."""
    sol, o, vuelo = _opcion(sid, opcion_id)
    reserva = _reservar(usuario, sid, opcion_id, sol, vuelo)
    if "id" not in reserva or reserva.get("estado"):
        return reserva
    aid, url = reserva["id"], reserva["url"]
    try:
        nombre = " + ".join(vuelo.get("numeros") or [])
        eventos.registrar("solicitud", sid, "lectura de Google Flights pedida", f"{nombre}: {url}", f"{canal} · {usuario['nombre']}")
        r = _llamar(url, regreso_de(sol, vuelo))
        if isinstance(r, dict) and r.get("no_disponible"):
            db.ejecutar("delete from analisis_vuelo where id=:i and estado='pendiente'", i=aid)   # no fue una lectura
            return no_disponible(r["no_disponible"])
        try:
            cambios = _resultado_de(r)
        except Exception as e:  # noqa: BLE001 (lo que sea que falle aquí no puede dejar la lectura «pendiente»)
            print(f"analizador: la lectura {aid} no se pudo guardar: {type(e).__name__}", flush=True)
            cambios = {"estado": "fallido", "terminado": db.ahora(), "motivo": SIN_CAPTURA, "captura": None, "datos": None}
        db.actualizar("analisis_vuelo", aid, **cambios)
        listo = cambios["estado"] == "listo"
        eventos.registrar("solicitud", sid, "página del vuelo leída" if listo else "lectura de Google Flights fallida",
                          f"{nombre}: {'listo' if listo else cambios['motivo']}", "analizador", cambios.get("duracion_ms") or 0)
        return {**_fila(db.uno("select * from analisis_vuelo where id=:i", i=aid)), "reutilizado": False}
    finally:
        _no_dejar_pendiente(aid)


def regreso_de(sol: dict, vuelo: dict) -> dict | None:
    """El regreso de la cotización para que el analizador elija el mismo en la página: hora de salida como la muestra
    Google («1:43 PM») y aerolínea. Solo de lo guardado: no se paga una búsqueda para esto."""
    lado = lambda nombre: precios.codigos(sol.get(f"{nombre}_aeropuertos") or sol[nombre])  # noqa: E731
    r = precios.regreso_guardado(vuelo, lado("origen"), lado("destino"), sol["ida"], sol["regreso"])
    if not r or len(r.get("sale") or "") < 16:
        return None
    h, m = int(r["sale"][11:13]), int(r["sale"][14:16])
    return {"sale": f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}", "aerolinea": r.get("aerolinea")}


# ---------- «Ir a…»: la tarifa elegida, en la página del vendedor (pieza 3b) ----------
TOPE_IR_A_TEXTO = "Llegaste al tope de «Ir a…» de hoy: el enlace sale de Google Flights."
TOPE_IR_A_TOTAL_TEXTO = "Se alcanzó el tope de «Ir a…» de hoy: el enlace sale de Google Flights."


def _es_envio(url) -> bool:
    return precios.es_envio_google(url)


def _reservar_ir(usuario: dict, sid: int, opcion_id: int, sol: dict, vuelo: dict, url: str | None,
                 vendedor: str, tarifa: str) -> dict:
    """El turno del analizador para «ir a», en fila con las lecturas (mismo cerrojo y una a la vez), con su tope por
    persona. La fila se reserva aquí en todos los caminos que no son de tope (con o sin turno del analizador): ningún
    pedido simultáneo pasa el tope. Devuelve `{"id", "motivo", "turno"}` o `{"motivo", "tope"}`."""
    with db.transaccion() as c:
        if not config.ES_SQLITE:
            c.execute(text("select pg_advisory_xact_lock(:k)"), {"k": BLOQUEO_TURNO})
        db.ejecutar("update analisis_vuelo set estado='fallido', motivo=:m, terminado=:t where estado='pendiente' and creado<:c",
                    m=NO_TERMINO, t=db.ahora(), c=_hace(EN_CURSO))
        cat, hoy = costo.catalogo(), inicio_del_dia()
        if db.uno("select count(*) n from analisis_vuelo where accion='ir_a' and usuario_id=:u and creado>=:h",
                  u=usuario["id"], h=hoy)["n"] >= int(costo.supuesto(cat, "ir_a_persona_dia", TOPE_IR_A)):
            return {"motivo": TOPE_IR_A_TEXTO, "tope": True}
        if db.uno("select count(*) n from analisis_vuelo where accion='ir_a' and creado>=:h",
                  h=hoy)["n"] >= int(costo.supuesto(cat, "ir_a_dia", TOPE_IR_A_TOTAL)):
            return {"motivo": TOPE_IR_A_TOTAL_TEXTO, "tope": True}
        # la fila se reserva en todos los caminos: cuenta para el tope aunque no haya turno del analizador
        motivo = (APAGADO if apagado() else SIN_ANALIZADOR if not _modo() else SIN_TRAMOS if not url
                  else OCUPADO if _ocupado() else None)
        aid = db.insertar("analisis_vuelo", opcion_id=opcion_id, solicitud_id=sid, usuario_id=usuario["id"],
                          clave=clave(sol, vuelo), url=url or "", estado="sin_turno" if motivo else "pendiente",
                          motivo=motivo, creado=db.ahora(), accion="ir_a", vendedor=vendedor, tarifa=tarifa)
        return {"id": aid, "motivo": motivo, "turno": motivo is None}


def _por_buscador(sol: dict, vuelo: dict, vendedor: str, tarifa: str, sid: int) -> dict | None:
    """El pedido de un solo uso de esa tarifa de ese vendedor, de las opciones de reserva del buscador."""
    lado = lambda nombre: precios.codigos(sol.get(f"{nombre}_aeropuertos") or sol[nombre])  # noqa: E731
    regreso = precios.vuelo_regreso(vuelo, lado("origen"), lado("destino"), sol["ida"], sol["regreso"], sid,
                                    tipo="vendedor_regreso")
    if not regreso:
        return None
    for o in precios.reserva_en_vivo(vuelo, regreso, lado("origen"), lado("destino"), sol["ida"], sol["regreso"], sid):
        if (o["vendedor"].lower(), o["tarifa"].lower()) == (vendedor.lower(), tarifa.lower()) and _es_envio(o["url"]):
            return {"url": o["url"], "campos": parse_qsl(o["post_data"] or "", keep_blank_values=True)}
    return None


def ir_a(usuario: dict, sid: int, opcion_id: int, vendedor: str, tarifa: str, canal: str = "api v1") -> dict:
    """Adónde enviar a la persona para comprar esa tarifa de ese vendedor. Tres caminos, en orden:
    `pagina` (el analizador pulsa «Continue» en Google Flights y devuelve el envío que Google iba a hacer), `buscador`
    (el pedido de un solo uso de esa tarifa) y `google` (la página del vuelo en Google Flights).

    Devuelve `{"camino", "url", "campos", "vendedor", "tarifa", "motivo"}`. Los `campos` del envío viajan solo en esta
    respuesta: no se guardan ni se registran. Quien llama comprueba antes que la persona ve la cotización.
    LookupError si el vuelo no es de ella."""
    sol, _, vuelo = _opcion(sid, opcion_id)   # LookupError si el vuelo no es de la cotización: solo aquí
    inicio = datetime.now(UTC)
    try:
        url = enlace_itinerario(sol, vuelo)
    except ValueError:
        url = None
    turno = _reservar_ir(usuario, sid, opcion_id, sol, vuelo, url, vendedor, tarifa)
    try:
        return _ir_con_turno(usuario, sid, opcion_id, sol, vuelo, url, vendedor, tarifa, turno, inicio, canal)
    finally:
        _no_dejar_pendiente(turno.get("id"))


def _ir_con_turno(usuario: dict, sid: int, opcion_id: int, sol: dict, vuelo: dict, url: str | None, vendedor: str,
                  tarifa: str, turno: dict, inicio: datetime, canal: str) -> dict:
    destino, camino, motivo, captura, aid = None, None, turno.get("motivo"), None, turno.get("id")
    extracto = None
    if turno.get("turno"):
        r = _invocar({"accion": "ir_a", "url": url, "vendedor": vendedor, "tarifa": tarifa, "regreso": regreso_de(sol, vuelo)})
        if not isinstance(r, dict):
            motivo = RESPUESTA_RARA
        elif r.get("no_disponible"):
            motivo = r["no_disponible"]   # la fila queda: el pedido ya contó para el tope
        elif r.get("estado") == "listo" and _es_envio(r.get("url")) and isinstance(r.get("cuerpo"), str):
            destino, camino = {"url": r["url"], "campos": parse_qsl(r["cuerpo"], keep_blank_values=True)}, "pagina"
            try:
                captura = _guardar_captura(r.get("captura_previa_png_b64"))
            except Exception:  # noqa: BLE001 (la captura es evidencia: sin ella, el envío sigue valiendo)
                captura = None
        else:
            motivo = str(r.get("motivo") or "la página no devolvió el envío")[:300]
            # lo que vio el analizador (captura y comienzo del texto): sirve para saber por qué no llegó a la tarifa
            try:
                captura = _guardar_captura(r.get("captura_png_b64"))
            except Exception:  # noqa: BLE001 (la evidencia es secundaria)
                captura = None
            extracto = str(r["extracto"])[:500] if r.get("extracto") else None
    if not destino and not turno.get("tope") and config.SERPAPI_KEY:
        # el camino del buscador gasta búsquedas pagas: el cupo del enlace se reserva antes de buscar
        if reservar_cupo(usuario, f"ir_a_{clave(sol, vuelo)}", unidades_busqueda(sol, vuelo)):
            destino = _por_buscador(sol, vuelo, vendedor, tarifa, sid)
            camino = "buscador" if destino else None
        else:
            motivo = motivo or "se alcanzó el tope de búsquedas del día"
    if not destino:
        try:
            google = url or precios.enlace_vuelos(precios.codigos(sol.get("origen_aeropuertos") or sol["origen"]),
                                                  precios.codigos(sol.get("destino_aeropuertos") or sol["destino"]),
                                                  sol["ida"], sol["regreso"])
        except ValueError:
            google = None
        destino, camino = {"url": google, "campos": []}, "google"
    ms = int((datetime.now(UTC) - inicio).total_seconds() * 1000)
    cambios = {"estado": "listo" if camino == "pagina" else "fallido", "terminado": db.ahora(), "duracion_ms": ms,
               "camino": camino, "captura": captura, "motivo": None if camino == "pagina" else motivo,
               "datos": {"extracto": extracto} if extracto else None}
    if aid:
        db.actualizar("analisis_vuelo", aid, **cambios)
    dominio = urlsplit(destino["url"]).hostname if destino["url"] else "sin enlace"
    compras.registrar_clic(usuario, sid, opcion_id, "vendedor" if camino != "google" else "google_flights", destino["url"])
    eventos.registrar("solicitud", sid, "ir a vendedor",
                      f"{' + '.join(vuelo.get('numeros') or [])} (opción {opcion_id}): {vendedor} · {tarifa} · camino {camino} · "
                      f"{dominio} · {ms} ms{' · ' + motivo if motivo and camino != 'pagina' else ''}"[:500],
                      f"{canal} · {usuario['nombre']}", ms)
    return {"camino": camino, "url": destino["url"], "campos": destino["campos"], "vendedor": vendedor, "tarifa": tarifa,
            "motivo": None if camino == "pagina" else motivo}


def aviso_precio(analisis: dict | None, precio_buscador) -> str | None:
    """Si Google Flights muestra otro precio total que el buscador, lo dice. La comparación sigue con el del buscador."""
    try:
        leido = Decimal(str(((analisis or {}).get("datos") or {}).get("precio_total")))
        buscador = Decimal(str(precio_buscador))
    except (InvalidOperation, ValueError):
        return None
    if not (leido.is_finite() and buscador.is_finite()) or abs(leido - buscador) < 1:
        return None
    return (f"Google Flights muestra {leido:,.0f} USD y el buscador dio {buscador:,.0f} USD. "
            "La comparación sigue usando el precio del buscador.")


def para_decision(sid: int, opcion_id: int) -> dict | None:
    """El detalle vigente que se copia a la decisión: lo leído, de dónde y cuándo."""
    a = vigente(clave_de(sid, opcion_id))
    if not a or a["estado"] != "listo":
        return None
    return {"id": a["id"], "url": a["url"], "leido": a["terminado"] or a["creado"], "datos": a["datos"], "captura": a["captura"]}
