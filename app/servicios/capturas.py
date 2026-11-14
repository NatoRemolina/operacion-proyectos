"""Evidencia completa de lo decidido (pieza 5): el vuelo (Google Flights y la página de la aerolínea) y el hotel elegido
(Google Hotels), leídos por el analizador y guardados con sus datos, su texto visible y capturas de página completa.

Cuándo se encola una captura (la cola es la tabla `capturas`; nunca se espera al analizador):
- al decidir: el vuelo y el hotel de la decisión (una nueva decisión deja las pendientes de la anterior como fallidas);
- cada día, por cada vuelo decidido y no comprado, hasta la compra o la fecha de ida (regla `seguimiento_diario`);
- al registrar la compra: una captura final del vuelo como evidencia.

La procesa el trabajador (`app/tareas.py`), de a una y con el turno del analizador, hasta `capturas_dia` por día. El
envío de un solo uso que lleva a la aerolínea pasa de una invocación a la otra en memoria: nunca se guarda.
"""
import base64
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import Column, Integer, Text, text
from sqlalchemy.exc import IntegrityError

from .. import config, db
from . import almacen, analizador, costo, eventos, precios, tiempo

capturas = db._tabla(
    "capturas",
    db._ref("capturas", "solicitud_id", "solicitudes"), db._ref("capturas", "decision_id", "decisiones"),
    db._ref("capturas", "compra_id", "compras"), db._ref("capturas", "opcion_id", "opciones"),
    Column("tipo", Text, nullable=False),        # vuelo | hotel
    Column("motivo", Text, nullable=False),      # decision | seguimiento | compra
    Column("clave", Text, nullable=False, unique=True),   # la cola no duplica: una por decisión, por día o por compra
    Column("url", Text),                         # armada por el servidor (Google Flights o Google Hotels)
    Column("estado", Text, nullable=False),      # pendiente | en_curso | lista | fallida
    Column("fallo", Text),
    Column("datos", Text), Column("texto", Text), Column("imagenes", Text),   # imagenes: claves del almacenamiento privado
    Column("duracion_ms", Integer), Column("intentos", Integer, nullable=False),
    Column("creado", Text), Column("empezado", Text), Column("terminado", Text), Column("proximo", Text),
)

TOPE_DIA = 60
REGLAS = (
    ("seguimiento_diario", "1", "Una captura al día de cada vuelo decidido y no comprado, hasta la compra o la fecha de ida "
                                "(1 encendido, 0 apagado)."),
    ("capturas_dia", str(TOPE_DIA), "Capturas completas (vuelo, aerolínea u hotel) que el trabajador hace por día, en total."),
)
INTENTOS = 3
ESPERA_REINTENTO = timedelta(minutes=30)
EN_CURSO_MAX = timedelta(minutes=4)   # tres invocaciones de un minuto como máximo y un margen
TOPE_TEXTO = 300_000                  # bytes del texto visible que se guardan por captura
REEMPLAZADA = "la decisión cambió"
NO_TERMINO = "la captura no terminó"
ESTADOS = ("pendiente", "en_curso", "lista", "fallida")


def asegurar_reglas() -> int:
    """Las dos reglas como supuestos editables. La migración lo llama; no pisa un valor ya editado."""
    nuevas = 0
    for clave, valor, nota in REGLAS:
        if not db.uno("select id from reglas where ambito='supuesto' and clave=:c", c=clave):
            db.insertar("reglas", ambito="supuesto", entidad="", tarifa="", clave=clave, valor=valor, nota=nota,
                        fuente="Supuesto editable", confianza="supuesto", verificado="2026-11-13")
            nuevas += 1
    return nuevas


def _encolar(**fila) -> int | None:
    """Inserta la captura si su clave no está en la cola. Devuelve el id nuevo, o None si ya estaba (la clave es por
    decisión, por día o por compra: dos pedidos a la vez chocan en la clave única y el segundo no hace nada)."""
    if db.uno("select id from capturas where clave=:c", c=fila["clave"]):
        return None
    try:
        return db.insertar("capturas", estado="pendiente", intentos=0, creado=db.ahora(), **fila)
    except IntegrityError:   # la clave única: otra petición la encoló en el mismo instante
        return None


def _url_hotel(sol: dict, hotel: dict) -> str:
    return precios.enlace_hoteles(sol.get("ciudad") or sol.get("destino") or "", sol["ida"], sol["regreso"], hotel=hotel.get("nombre"))


# ---------- cuándo se encola ----------
def al_decidir(decision_id: int) -> list[int]:
    """El vuelo y el hotel de la decisión. Las pendientes de una decisión anterior de la misma cotización ya no sirven."""
    d = db.uno("select * from decisiones where id=:i", i=decision_id)
    sol = db.uno("select * from solicitudes where id=:i", i=d["solicitud_id"])
    db.ejecutar("""update capturas set estado='fallida', fallo=:f, terminado=:t where solicitud_id=:s and motivo='decision'
                   and decision_id<>:d and estado='pendiente'""", f=REEMPLAZADA, t=db.ahora(), s=sol["id"], d=decision_id)
    hechas = []
    vuelo = db.uno("select datos from opciones where id=:o", o=d["vuelo_id"])
    try:
        url = analizador.enlace_itinerario(sol, db.de_json(vuelo["datos"], {}) or {}) if vuelo else None
    except ValueError:
        url = None   # sin tramos completos no hay página que leer
    if url:
        hechas.append(_encolar(tipo="vuelo", motivo="decision", clave=f"vuelo:decision:{decision_id}", url=url,
                               solicitud_id=sol["id"], decision_id=decision_id, opcion_id=d["vuelo_id"]))
    if d["hotel_id"]:
        hotel = db.uno("select datos from opciones where id=:o", o=d["hotel_id"])
        if hotel:
            hechas.append(_encolar(tipo="hotel", motivo="decision", clave=f"hotel:decision:{decision_id}",
                                   url=_url_hotel(sol, db.de_json(hotel["datos"], {}) or {}), solicitud_id=sol["id"],
                                   decision_id=decision_id, opcion_id=d["hotel_id"]))
    return [h for h in hechas if h]


def al_comprar(compra_id: int) -> int | None:
    """La captura final del vuelo comprado, como evidencia del precio y de la página en ese momento."""
    c = db.uno("select * from compras where id=:i", i=compra_id)
    d = db.uno("select * from decisiones where id=:i", i=c["decision_id"]) if c and c["decision_id"] else None
    if not d:
        return None
    sol = db.uno("select * from solicitudes where id=:i", i=d["solicitud_id"])
    vuelo = db.uno("select datos from opciones where id=:o", o=d["vuelo_id"])
    try:
        url = analizador.enlace_itinerario(sol, db.de_json(vuelo["datos"], {}) or {})
    except (ValueError, TypeError):
        return None
    return _encolar(tipo="vuelo", motivo="compra", clave=f"vuelo:compra:{compra_id}", url=url, solicitud_id=sol["id"],
                    decision_id=d["id"], compra_id=compra_id, opcion_id=d["vuelo_id"])


def seguimiento_encendido() -> bool:
    return costo.supuesto(costo.catalogo(), "seguimiento_diario", 1) >= 1


def encolar_seguimiento(hoy: str | None = None) -> int:
    """Una captura del día por cada vuelo decidido cuya compra sigue abierta (ni comprada, ni descartada, ni cancelada)
    y cuya ida no pasó. Idempotente en el día. Devuelve cuántas encoló."""
    hoy = hoy or tiempo.hoy().isoformat()
    if not seguimiento_encendido():
        return 0
    hechas = 0
    for f in db.todos("""select d.id decision_id, d.vuelo_id, s.id sid, c.id compra_id from compras c
                         join decisiones d on d.id=c.decision_id join solicitudes s on s.id=d.solicitud_id
                         where c.activa=1 and c.estado in ('solicitada', 'en_analisis', 'se_comprara') and s.ida>=:h
                         order by c.id""", h=hoy):
        sol = db.uno("select * from solicitudes where id=:i", i=f["sid"])
        vuelo = db.uno("select datos from opciones where id=:o", o=f["vuelo_id"])
        try:
            url = analizador.enlace_itinerario(sol, db.de_json(vuelo["datos"], {}) or {})
        except (ValueError, TypeError):
            continue
        if _encolar(tipo="vuelo", motivo="seguimiento", clave=f"vuelo:seguimiento:{f['decision_id']}:{hoy}", url=url,
                    solicitud_id=f["sid"], decision_id=f["decision_id"], compra_id=f["compra_id"], opcion_id=f["vuelo_id"]):
            hechas += 1
    return hechas


# ---------- tomar el turno y hacer una captura ----------
def _hace(delta: timedelta) -> str:
    return (datetime.now(UTC) - delta).strftime("%Y-%m-%d %H:%M:%S")


def tope_dia() -> int:
    return int(costo.supuesto(costo.catalogo(), "capturas_dia", TOPE_DIA))


def tomar() -> dict | None:
    """La siguiente captura pendiente, con el turno del analizador (mismo cerrojo que las lecturas: una a la vez) y dentro
    del tope del día. La deja `en_curso` con un intento más. None si no hay, si se alcanzó el tope o si está ocupado."""
    with db.transaccion() as c:
        if not config.ES_SQLITE:
            c.execute(text("select pg_advisory_xact_lock(:k)"), {"k": analizador.BLOQUEO_TURNO})
        # una captura que se quedó a medias (caída del trabajador) vuelve a la cola o se da por fallida
        for f in db.todos("select id, intentos from capturas where estado='en_curso' and empezado<:h", h=_hace(EN_CURSO_MAX)):
            db.actualizar("capturas", f["id"], estado="fallida" if f["intentos"] >= INTENTOS else "pendiente",
                          fallo=NO_TERMINO, terminado=db.ahora())
        if analizador._ocupado():
            return None
        if db.uno("select count(*) n from capturas where empezado>=:h", h=tiempo.inicio_del_dia())["n"] >= tope_dia():
            return None
        f = db.uno("""select * from capturas where estado='pendiente' and (proximo is null or proximo<=:a)
                      order by id limit 1""", a=db.ahora())
        if not f:
            return None
        db.actualizar("capturas", f["id"], estado="en_curso", intentos=f["intentos"] + 1, empezado=db.ahora(), fallo=None)
    return db.uno("select * from capturas where id=:i", i=f["id"])


def _guardar_png(b64) -> str | None:
    if not isinstance(b64, str) or not b64:
        return None
    try:
        png = base64.b64decode(b64, validate=True)
    except ValueError:
        return None
    if not png.startswith(b"\x89PNG"):
        return None
    return almacen.guardar(almacen.clave(hashlib.sha256(png).hexdigest(), "png"), png, "image/png")


def _recortar(texto: str) -> str:
    return texto.encode()[:TOPE_TEXTO].decode(errors="ignore")


def _pedido(f: dict) -> list[dict]:
    """Lo que se le pide al analizador para esta captura (el vuelo, con la tarifa decidida de la aerolínea)."""
    if f["tipo"] == "hotel":
        hotel = db.de_json((db.uno("select datos from opciones where id=:o", o=f["opcion_id"]) or {}).get("datos"), {}) or {}
        return [{"accion": "captura_hotel", "url": f["url"], "hotel": str(hotel.get("nombre") or "")[:120]}]
    d = db.uno("select * from decisiones where id=:i", i=f["decision_id"]) if f["decision_id"] else None
    vuelo = db.de_json((db.uno("select datos from opciones where id=:o", o=f["opcion_id"]) or {}).get("datos"), {}) or {}
    sol = db.uno("select * from solicitudes where id=:i", i=f["solicitud_id"])
    return [{"accion": "captura_vuelo", "url": f["url"], "vendedor": str(vuelo.get("aerolinea") or "")[:60],
             "tarifa": str((d or {}).get("tarifa") or "")[:60], "regreso": analizador.regreso_de(sol, vuelo) if sol else None}]


def hacer(f: dict) -> dict:
    """Invoca al analizador para la captura `f` (ya en curso) y guarda lo que devuelva. Devuelve la fila final."""
    inicio = datetime.now(UTC)
    datos, textos, imagenes, fallo = {}, [], [], None
    try:
        pedido = _pedido(f)[0]
        r = analizador._invocar(pedido)
        lado = "hotel" if f["tipo"] == "hotel" else "google"
        if not isinstance(r, dict) or r.get("no_disponible") or r.get("estado") != "listo":
            fallo = (r.get("no_disponible") or r.get("motivo")) if isinstance(r, dict) else analizador.RESPUESTA_RARA
            fallo = str(fallo or "la captura no devolvió datos")[:300]
        else:
            datos[lado] = r.get("datos") if isinstance(r.get("datos"), dict) else {}
            textos.append(f"=== {lado} ===\n{r.get('texto') or ''}")
            imagenes += [k for k in (_guardar_png(b) for b in (r.get("capturas_png_b64") or [])[:4]) if k]
            envio = r.get("envio") if isinstance(r.get("envio"), dict) else None
            if f["tipo"] == "vuelo" and envio and precios.es_envio_google(envio.get("url")) and isinstance(envio.get("cuerpo"), str):
                a = analizador._invocar({"accion": "captura_aerolinea", "url": envio["url"], "cuerpo": envio["cuerpo"]})
                envio = None   # de un solo uso: no se guarda ni se vuelve a usar
                if isinstance(a, dict) and a.get("estado") == "listo":
                    datos["aerolinea"] = a.get("datos") if isinstance(a.get("datos"), dict) else {}
                    textos.append(f"=== aerolínea ===\n{a.get('texto') or ''}")
                    imagenes += [k for k in (_guardar_png(b) for b in (a.get("capturas_png_b64") or [])[:4]) if k]
                else:
                    datos["aerolinea"] = {"fallo": str((a or {}).get("motivo") or "no se llegó a la aerolínea")[:300]}
    except Exception as e:   # noqa: BLE001 (la captura es evidencia: un error no tumba al trabajador)
        print(f"capturas: la captura {f['id']} falló: {type(e).__name__}", flush=True)
        fallo = "la captura no se pudo guardar"
    ms = int((datetime.now(UTC) - inicio).total_seconds() * 1000)
    if fallo:
        ultimo = f["intentos"] >= INTENTOS
        db.actualizar("capturas", f["id"], estado="fallida" if ultimo else "pendiente", fallo=fallo, duracion_ms=ms,
                      terminado=db.ahora(), proximo=None if ultimo else (datetime.now(UTC) + ESPERA_REINTENTO).strftime("%Y-%m-%d %H:%M:%S"))
    else:
        db.actualizar("capturas", f["id"], estado="lista", fallo=None, datos=datos, texto=_recortar("\n\n".join(textos)),
                      imagenes=imagenes, duracion_ms=ms, terminado=db.ahora(), proximo=None)
    if f["solicitud_id"]:
        eventos.registrar("solicitud", f["solicitud_id"], "captura guardada" if not fallo else "captura fallida",
                          f"{f['tipo']} · {f['motivo']} · intento {f['intentos']}{' · ' + fallo if fallo else ''}"[:500], "trabajador", ms)
    return db.uno("select * from capturas where id=:i", i=f["id"])


# ---------- leer ----------
def de_la_cotizacion(sid: int) -> list[dict]:
    return [_publica(f) for f in db.todos("select * from capturas where solicitud_id=:s order by id", s=sid)]


def _publica(f: dict) -> dict:
    return {**f, "datos": db.de_json(f["datos"], None), "imagenes": db.de_json(f["imagenes"], []) or []}
