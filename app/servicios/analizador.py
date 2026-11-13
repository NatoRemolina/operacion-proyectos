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
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import Column, Integer, Text, text

from .. import config, db
from . import almacen, costo, eventos, precios

analisis_vuelo = db._tabla(
    "analisis_vuelo",   # una fila por lectura de la página de un vuelo; solo la usa el servidor
    db._ref("analisis_vuelo", "opcion_id", "opciones"), db._ref("analisis_vuelo", "solicitud_id", "solicitudes"),
    db._ref("analisis_vuelo", "usuario_id", "usuarios"),
    Column("clave", Text, nullable=False),      # itinerario y fechas: «AA1851_2026-12-08_2026-12-08_2026-12-11»
    Column("url", Text, nullable=False),
    Column("estado", Text, nullable=False),     # pendiente | listo | fallido
    Column("motivo", Text), Column("datos", Text), Column("captura", Text),   # captura: ruta en el almacenamiento
    Column("duracion_ms", Integer), Column("creado", Text), Column("terminado", Text),
)

VIGENCIA = timedelta(minutes=60)
EN_CURSO = timedelta(minutes=2)      # una lectura que no terminó en este tiempo ya no va a terminar
ESPERA_S = 55                         # la función del analizador tiene 60 s; CloudFront espera 60 s a la API
TOPE_PERSONA, TOPE_TOTAL = 10, 40     # si las reglas no existen
REGLAS = (
    ("analisis_persona_dia", str(TOPE_PERSONA), "Lecturas de la página del vuelo en Google Flights por persona y día. "
                                                "Alcanzado, el desglose muestra solo lo del buscador."),
    ("analisis_vuelo_dia", str(TOPE_TOTAL), "Lecturas de la página del vuelo en Google Flights por día, en total. "
                                            "Alcanzado, el desglose muestra solo lo del buscador."),
)
APAGADO = "La lectura de Google Flights está apagada: el desglose muestra solo lo del buscador."
SIN_ANALIZADOR = "Este entorno no tiene el analizador de Google Flights: el desglose muestra solo lo del buscador."
TOPE_PERSONA_TEXTO = "Llegaste al tope de lecturas de Google Flights de hoy: el desglose muestra solo lo del buscador."
TOPE_TOTAL_TEXTO = "Se alcanzó el tope de lecturas de Google Flights de hoy: el desglose muestra solo lo del buscador."
OCUPADO = "Se está leyendo la página de otro vuelo. Intenta de nuevo en un minuto."
SIN_TRAMOS = "Este vuelo no trae sus tramos completos: no se puede abrir su página en Google Flights."


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


def vigente(opcion_id: int) -> dict | None:
    """El último análisis leído de este vuelo con menos de 60 minutos, o el que está en curso."""
    f = db.uno("""select * from analisis_vuelo where opcion_id=:o and ((estado='listo' and creado>=:v)
                  or (estado='pendiente' and creado>=:c)) order by id desc limit 1""",
               o=opcion_id, v=_hace(VIGENCIA), c=_hace(EN_CURSO))
    return _fila(f)


def ultimo(opcion_id: int) -> dict | None:
    return _fila(db.uno("select * from analisis_vuelo where opcion_id=:o order by id desc limit 1", o=opcion_id))


def _llamar(url: str) -> dict:
    """La respuesta del analizador; un fallo de la llamada se devuelve como lectura fallida, nunca como excepción."""
    modo = _modo()
    try:
        if modo[0] == "http":
            return httpx.post(f"{modo[1]}/analizar", json={"url": url}, timeout=ESPERA_S).json()
        import boto3
        from botocore.config import Config
        cliente = boto3.client("lambda", config=Config(read_timeout=ESPERA_S + 5, retries={"max_attempts": 0}))
        r = cliente.invoke(FunctionName=modo[1], Payload=json.dumps({"url": url}).encode())
        cuerpo = json.loads(r["Payload"].read() or b"{}")
        if r.get("FunctionError"):
            return {"estado": "fallido", "motivo": "el analizador falló al leer la página"}
        return cuerpo
    except Exception as e:   # red, tiempo agotado, respuesta que no es JSON
        return {"estado": "fallido", "motivo": f"el analizador no respondió ({type(e).__name__})"}


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
        previo = vigente(opcion_id)
        if previo:
            return {**previo, "reutilizado": True}
        if apagado():
            return no_disponible(APAGADO)
        if not _modo():
            return no_disponible(SIN_ANALIZADOR)
        if not url:
            return no_disponible(SIN_TRAMOS)
        hoy = db.ahora()[:10]
        por_persona, total = topes()
        if db.uno("select count(*) n from analisis_vuelo where usuario_id=:u and creado>=:h", u=usuario["id"], h=hoy)["n"] >= por_persona:
            return no_disponible(TOPE_PERSONA_TEXTO)
        if db.uno("select count(*) n from analisis_vuelo where creado>=:h", h=hoy)["n"] >= total:
            return no_disponible(TOPE_TOTAL_TEXTO)
        if db.uno("select id from analisis_vuelo where estado='pendiente' limit 1"):
            return no_disponible(OCUPADO)
        aid = db.insertar("analisis_vuelo", opcion_id=opcion_id, solicitud_id=sid, usuario_id=usuario["id"],
                          clave=clave(sol, vuelo), url=url, estado="pendiente", creado=db.ahora())
    return {"id": aid, "url": url}


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
    nombre = " + ".join(vuelo.get("numeros") or [])
    eventos.registrar("solicitud", sid, "lectura de Google Flights pedida", f"{nombre}: {url}", f"{canal} · {usuario['nombre']}")
    try:
        cambios = _resultado_de(_llamar(url))
    except Exception as e:  # noqa: BLE001 (lo que sea que falle aquí no puede dejar la lectura «pendiente»)
        print(f"analizador: la lectura {aid} no se pudo guardar: {type(e).__name__}", flush=True)
        cambios = {"estado": "fallido", "terminado": db.ahora(), "motivo": SIN_CAPTURA, "captura": None, "datos": None}
    db.actualizar("analisis_vuelo", aid, **cambios)
    listo = cambios["estado"] == "listo"
    eventos.registrar("solicitud", sid, "página del vuelo leída" if listo else "lectura de Google Flights fallida",
                      f"{nombre}: {'listo' if listo else cambios['motivo']}", "analizador", cambios.get("duracion_ms") or 0)
    return {**_fila(db.uno("select * from analisis_vuelo where id=:i", i=aid)), "reutilizado": False}


def aviso_precio(analisis: dict | None, precio_buscador) -> str | None:
    """Si Google Flights muestra otro precio total que el buscador, lo dice. La comparación sigue con el del buscador."""
    leido = ((analisis or {}).get("datos") or {}).get("precio_total")
    if leido is None or precio_buscador is None or abs(float(leido) - float(precio_buscador)) < 1:
        return None
    return (f"Google Flights muestra {float(leido):,.0f} USD y el buscador dio {float(precio_buscador):,.0f} USD. "
            "La comparación sigue usando el precio del buscador.")


def para_decision(opcion_id: int) -> dict | None:
    """El detalle vigente que se copia a la decisión: lo leído, de dónde y cuándo."""
    a = vigente(opcion_id)
    if not a or a["estado"] != "listo":
        return None
    return {"id": a["id"], "url": a["url"], "leido": a["terminado"] or a["creado"], "datos": a["datos"], "captura": a["captura"]}
