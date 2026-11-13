"""Reto 1: crear una cotización y buscar, armar la comparación por costo total esperado y decidir.

Lo usan las pantallas (`app/rutas/cotizaciones.py`) y la API v1 (`app/rutas/v1_cotizaciones.py`). Quien llama
comprueba antes el permiso sobre la cotización: `acceso.puede_ver` para leerla y `acceso.es_propio` para decidirla.
Los errores de datos salen como excepciones con el texto para la persona; cada canal los presenta a su manera.
"""
import hashlib
import json
import math
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.exc import IntegrityError

from .. import aeropuertos, config, db
from . import acceso, costo, eventos, geografia, modelo, monitoreo_vuelos, precios, viajes

# Un pedido de cotización con `Idempotency-Key` por la API: la misma clave de la misma persona da la misma cotización
envios_cotizacion = db._tabla(
    "envios_cotizacion",  # una fila por (persona, clave); solo la usa el servidor
    Column("usuario_id", Integer, ForeignKey("usuarios.id", name="fk_envios_cotizacion_usuario_id"), nullable=False),
    Column("clave", Text, nullable=False), Column("huella", Text, nullable=False), Column("estado", Text, nullable=False),
    db._ref("envios_cotizacion", "solicitud_id", "solicitudes"), Column("expira", Text), Column("creado", Text),
    UniqueConstraint("usuario_id", "clave", name="ux_envios_cotizacion_persona_clave"),
)
VIGENCIA_ENVIO = timedelta(minutes=5)   # más que una búsqueda en vivo; pasado esto, quien la tenía ya no va a terminar
DECISIONES_EN_VIVO_DIA = 10   # la regla `decisiones_en_vivo_dia` lo cambia
# El buscador trae unos 20 por página: se guardan todos y se recorta solo después de ordenar por costo total
TOPE_HOTELES_GUARDADOS = 40
HOTELES_A_MOSTRAR = 12
AVISO_TOPE_DECISION = ("Se alcanzó el tope de decisiones con consulta en vivo de hoy: el regreso y la tarifa salen de lo "
                       "guardado o quedan supuestos.")


NO_DECIDE = "Esta cotización la decide quien viaja, quien la creó (si es de un proyecto que gestiona) o administración."


class CotizacionInvalida(ValueError):
    """Un dato de la cotización no sirve. `campo` dice cuál; el mensaje, qué hacer."""

    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo


class DecisionInvalida(CotizacionInvalida):
    """Falta el vuelo o el porqué de apartarse de la recomendación."""


class DecisionBloqueada(ValueError):
    """El viaje ya tiene el presupuesto aprobado o está cerrado: la decisión no cambia sin reabrirlo."""


class ConflictoEnvio(ValueError):
    """La clave ya se usó con otro pedido."""


class EnvioEnCurso(ValueError):
    """El primer pedido con esa clave todavía está buscando."""


class FueraDeAlcance(PermissionError):
    """Cotizar o decidir para otra persona fuera de los proyectos que se gestionan."""


class TopeAlcanzado(ValueError):
    """La persona ya hizo hoy las cotizaciones nuevas que permite la regla `tope_cotizaciones_persona_dia`."""


TOPE_COTIZACIONES_DIA = 20   # si la regla no existe
AVISO_TOPE_COTIZACIONES = ("Llegaste al tope de cotizaciones nuevas de hoy. Retoma una de las que ya tienes o pide a "
                           "administración que amplíe el tope.")


def tope_cotizaciones_dia() -> int:
    return int(costo.supuesto(costo.catalogo(), "tope_cotizaciones_persona_dia", TOPE_COTIZACIONES_DIA))


def cotizaciones_de_hoy(usuario: dict) -> int:
    return db.uno("select count(*) n from solicitudes where usuario_id=:u and creado>=:h", u=usuario["id"], h=db.ahora()[:10])["n"]


# ---------- quién cotiza y decide para otra persona (la misma regla en las pantallas y en la API) ----------
def proyectos_para_otros(usuario: dict) -> set[int] | None:
    """Dónde puede cotizar y decidir para otra persona: administración en todos (None); el gestor, en los que gestiona."""
    if acceso.es_admin(usuario):
        return None
    return acceso.proyectos_de(usuario) if usuario.get("rol") == "gestor" else set()


def para_otros_en(usuario: dict, proyecto_id: int | None) -> bool:
    permitidos = proyectos_para_otros(usuario)
    return permitidos is None or proyecto_id in permitidos


def puede_decidir(usuario: dict, fila: dict | None) -> bool:
    """Decide quien la creó, quien viaja o administración; para otra persona, solo dentro de su alcance."""
    if not acceso.es_propio(usuario, fila):
        return False
    para_otro = fila.get("viajero_id") != usuario.get("viajero_id")
    return not para_otro or para_otros_en(usuario, fila.get("proyecto_id"))


# ---------- origen y destino ----------
def lugar(valor) -> dict | None:
    """El lugar elegido en el buscador, solo con los campos esperados y coordenadas válidas; si no, ninguno.
    Llega como texto JSON desde el formulario o ya como diccionario desde la API."""
    datos = valor if isinstance(valor, dict) else db.de_json(valor, None)
    if not isinstance(datos, dict) or not str(datos.get("nombre") or "").strip():
        return None
    try:
        lat, lon = float(datos["lat"]), float(datos["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"nombre": str(datos["nombre"]).strip()[:80], "region": str(datos.get("region") or "").strip()[:80],
            "pais": str(datos.get("pais") or "").strip()[:80], "lat": lat, "lon": lon}


def otros_nombres(sitio: dict | None) -> list[str]:
    """Los nombres alternos del lugar elegido («Lisbon» también es «lisboa»), del lugar con ese nombre más cercano a
    sus coordenadas. Sirven para encontrar una respuesta de hoteles guardada con el nombre en otro idioma."""
    if not sitio:
        return []
    filas = [f for f in db.todos("select buscable, lat, lon from lugares where nombre=:n", n=sitio["nombre"])
             if f["lat"] is not None and f["lon"] is not None]
    cerca = min(filas, key=lambda f: geografia.distancia_km(sitio["lat"], sitio["lon"], f["lat"], f["lon"]), default=None)
    if not cerca or geografia.distancia_km(sitio["lat"], sitio["lon"], cerca["lat"], cerca["lon"]) > 50:
        return []
    return [n for n in (cerca["buscable"] or "").split(" | ")[1:] if n]


def lado(texto: str, codigos: str, lugar_elegido) -> dict:
    """Origen o destino de la cotización. Con aeropuertos marcados en el buscador: el lugar, la lista ordenada y el
    principal (el marcado más cercano al lugar, o el primero). Sin ellos, como antes: un aeropuerto por nombre o código.
    Si algo no se reconoce, `malo` dice qué."""
    if not codigos.strip():
        r = aeropuertos.resolver(texto)
        return {"codigo": r[0], "ciudad": r[1], "lista": None, "lugar": None} if r else {"malo": texto}
    marcados = list(dict.fromkeys(c.strip().upper() for c in codigos.split(",") if c.strip()))[:8]
    conocidos = geografia.aeropuertos_conocidos(marcados)
    malo = next((c for c in marcados if c not in conocidos), None)
    if malo or not marcados:
        return {"malo": malo or codigos}
    sitio = lugar(lugar_elegido)
    principal = marcados[0]
    if sitio:
        con_distancia = [c for c in marcados if conocidos[c].get("lat") is not None]
        if con_distancia:
            principal = min(con_distancia, key=lambda c: geografia.distancia_km(sitio["lat"], sitio["lon"],
                                                                                 conocidos[c]["lat"], conocidos[c]["lon"]))
    return {"codigo": principal, "ciudad": sitio["nombre"] if sitio else (conocidos[principal].get("municipio") or principal),
            "lista": ",".join(sorted(marcados)), "lugar": sitio}


def texto_lado(un_lado: dict) -> str:
    """Para la bitácora: «Moab, Utah, Estados Unidos (CNY, GJT, SLC)» o el código cuando no hubo lugar."""
    if not un_lado["lista"]:
        return un_lado["codigo"]
    sitio = un_lado["lugar"] or {}
    nombre = ", ".join(x for x in (sitio.get("nombre"), sitio.get("region"), sitio.get("pais")) if x) or "sin lugar"
    return f"{nombre} ({un_lado['lista'].replace(',', ', ')})"


def codigos(sol: dict, un_lado: str) -> list[str]:
    """Los aeropuertos marcados de un lado de la cotización; las cotizaciones de antes tienen solo uno."""
    return precios.codigos(sol.get(f"{un_lado}_aeropuertos") or sol[un_lado])


# ---------- crear y buscar ----------
def primer_dia_posible() -> date:
    """La ida más temprana que se puede cotizar: hoy. El buscador rechaza fechas pasadas y la consulta se perdería.
    Se toma «hoy» con 12 horas de margen hacia atrás sobre la hora universal, para que en América el día local siga
    valiendo aunque en UTC ya sea mañana."""
    return (datetime.now(UTC) - timedelta(hours=12)).date()


def crear(usuario: dict, *, proyecto_id: int, ida: str, regreso: str, viajero_id: int = 0, origen: str = "",
          destino: str = "", ciudad: str = "", llegar_antes: str = "", baterias_n: int = 0, baterias_wh: float = 0,
          maleta: bool = False, prob_cambio: float = 0, carro_dia: float = 0, viajero_nuevo: str = "",
          para_otra_persona: bool = False, origen_aeropuertos: str = "", destino_aeropuertos: str = "",
          origen_lugar=None, destino_lugar=None, canal: str = "formulario") -> int:
    """Guarda la solicitud, busca vuelos y hoteles (una consulta para todos los aeropuertos marcados) y deja las
    opciones listas para comparar. `prob_cambio` va en porcentaje (0 a 100). Devuelve el id de la solicitud."""
    if cotizaciones_de_hoy(usuario) >= tope_cotizaciones_dia():   # cada cotización nueva puede gastar dos búsquedas pagas
        raise TopeAlcanzado(AVISO_TOPE_COTIZACIONES)
    sale, llega = lado(origen, origen_aeropuertos, origen_lugar), lado(destino, destino_aeropuertos, destino_lugar)
    if "malo" in sale or "malo" in llega:
        campo, malo = ("origen", sale["malo"]) if "malo" in sale else ("destino", llega["malo"])
        raise CotizacionInvalida(campo, f'No reconozco "{malo[:40]}". Elige una ciudad de la lista o escribe el código '
                                        "de tres letras del aeropuerto.")
    desde, hacia = (sale["codigo"], sale["ciudad"]), (llega["codigo"], llega["ciudad"])
    try:
        f_ida, f_regreso = date.fromisoformat(ida), date.fromisoformat(regreso)
    except ValueError as e:
        raise CotizacionInvalida("ida", "Las fechas no son válidas.") from e
    if f_ida < primer_dia_posible():
        raise CotizacionInvalida("ida", "La fecha de ida ya pasó: elige hoy o una fecha futura.")
    if f_regreso <= f_ida:
        raise CotizacionInvalida("regreso", "El regreso debe ser posterior a la ida.")
    ida, regreso = f_ida.isoformat(), f_regreso.isoformat()
    # La hora límite siempre se refiere al día de llegada: se conserva la hora y se ata a la fecha de ida
    hora = llegar_antes[11:16] if len(llegar_antes) >= 16 else ""
    llegar_antes = f"{ida}T{hora}" if re.fullmatch(r"\d\d:\d\d", hora) else ""
    # Los mismos límites que la API v1: un NaN o un infinito en el presupuesto rompe los listados y el control de saldo
    for campo, valor, tope, texto in (("carro_dia", carro_dia, 9999.99, "El carro de alquiler por día debe estar entre 0 y 9.999,99 USD."),
                                      ("baterias_wh", baterias_wh, 1000, "La capacidad de cada batería debe estar entre 0 y 1.000 Wh."),
                                      ("prob_cambio", prob_cambio, 100, "La probabilidad de cambio de fecha debe estar entre 0 y 100 %.")):
        if not (math.isfinite(valor) and 0 <= valor <= tope):
            raise CotizacionInvalida(campo, texto)
    baterias_n = max(baterias_n, 0)
    ciudad_escrita = bool(ciudad.strip())
    origen, destino, ciudad = desde[0], hacia[0], ciudad.strip() or hacia[1]
    solicitado_por, viajero_nuevo = usuario["nombre"], viajero_nuevo.strip()[:80]  # quien consulta sale de la sesión
    # Todos viajan: quien cotiza viaja, salvo que gestión o administración marquen que es para otra persona.
    # Así el titular no sale de un campo que se olvidó cambiar.
    para_otra = para_otra_persona and usuario.get("rol") in ("gestor", "admin")
    if usuario.get("viajero_id") and not para_otra:
        viajero_id, viajero_nuevo = usuario["viajero_id"], ""
    elif not acceso.es_admin(usuario):
        viajero_nuevo = ""   # registrar viajeros es tarea de administración
    if viajero_nuevo:
        existente = db.uno("select id from viajeros where lower(nombre)=lower(:n)", n=viajero_nuevo)
        viajero_id = existente["id"] if existente else db.insertar("viajeros", nombre=viajero_nuevo, base=desde[1], rol="Viajero")
    if not viajero_id or not db.uno("select id from viajeros where id=:i", i=viajero_id):
        raise CotizacionInvalida("viajero_id", "Elige quién viaja.")
    if viajero_id != usuario.get("viajero_id") and not para_otros_en(usuario, proyecto_id):
        raise FueraDeAlcance("Para cotizar para otra persona elige uno de los proyectos que gestionas.")
    sid = db.insertar("solicitudes", proyecto_id=proyecto_id, viajero_id=viajero_id, origen=origen,
                      destino=destino, ciudad=ciudad, ida=ida, regreso=regreso,
                      llegar_antes=llegar_antes or None, baterias_n=baterias_n, baterias_wh=baterias_wh,
                      maleta=1 if maleta else 0, prob_cambio=prob_cambio / 100, carro_dia=carro_dia,
                      estado="buscando", creado=db.ahora(), solicitado_por=solicitado_por, usuario_id=usuario["id"],
                      origen_lugar=sale["lugar"], destino_lugar=llega["lugar"],
                      origen_aeropuertos=sale["lista"], destino_aeropuertos=llega["lista"])
    eventos.registrar("solicitud", sid, "solicitud recibida", f"{origen}-{destino} {ida} a {regreso} · "
                      f"origen: {texto_lado(sale)} · destino: {texto_lado(llega)}", f"{canal} · {solicitado_por}")
    sol = db.uno("select * from solicitudes where id=:i", i=sid)
    desde_todos, hacia_todos = codigos(sol, "origen"), codigos(sol, "destino")
    vuelos, origen_v, _ = precios.buscar_vuelos(desde_todos, hacia_todos, ida, regreso, sid)   # una consulta, todos los marcados
    for v in vuelos:
        tarifas, origen_t = precios.tarifas_de_vuelo(desde_todos, hacia_todos, ida, regreso, v, sid)
        db.insertar("opciones", solicitud_id=sid, tipo="vuelo", titulo=" + ".join(v["numeros"]), precio=v["precio"],
                    moneda="USD", datos=v, tarifas={"lista": tarifas, "origen": origen_t}, origen_dato=origen_v, capturado=db.ahora())
    # Si la persona no escribió la ciudad del hotel, sirve cualquier nombre del lugar elegido para lo guardado
    alternos = [] if ciudad_escrita else otros_nombres(llega["lugar"])
    hoteles, origen_h = precios.buscar_hoteles(sol["ciudad"], ida, regreso, sid, otros_nombres=alternos)
    hoteles = hoteles[:TOPE_HOTELES_GUARDADOS]
    for h in hoteles:
        db.insertar("opciones", solicitud_id=sid, tipo="hotel", titulo=h["nombre"], precio=h["total"], moneda="USD",
                    datos=h, tarifas=None, origen_dato=origen_h, capturado=db.ahora())
    db.actualizar("solicitudes", sid, estado="comparando")
    eventos.registrar("solicitud", sid, "opciones guardadas", f"{len(vuelos)} vuelos y {len(hoteles)} hoteles", "aplicación")
    registrar_ahorro(sid)
    return sid


def registrar_ahorro(sid: int, c: dict | None = None):
    """Guarda con la consulta cuánto se evita al elegir por costo total y no por precio."""
    c = c or comparacion(sid)
    if c and c["vuelos"] and c["mas_barato"]:
        mejor, barato = c["vuelos"][0]["ev"]["total"], c["mas_barato"]["ev"]["total"]
        db.actualizar("solicitudes", sid, precio_min_buscador=c["mas_barato"]["v"]["precio"], costo_mas_barato=barato,
                      costo_mejor=mejor, ahorro_potencial=round(max(barato - mejor, 0), 2))
    elif c:
        db.actualizar("solicitudes", sid, ahorro_potencial=0)  # sin vuelos válidos: no hay nada que comparar


def completar_ahorros():
    for s in db.todos("select id from solicitudes where ahorro_potencial is null"):
        registrar_ahorro(s["id"])


# ---------- pedidos repetidos (Idempotency-Key) ----------
def huella_pedido(pedido: dict) -> str:
    return hashlib.sha256(json.dumps(pedido, sort_keys=True, default=str).encode()).hexdigest()


def _vence() -> str:
    return (datetime.now(UTC) + VIGENCIA_ENVIO).strftime("%Y-%m-%d %H:%M:%S")


def reclamar_envio(usuario_id: int, clave: str, huella: str) -> tuple[dict, int | None]:
    """Devuelve (envío, cotización). Con cotización, el pedido ya se atendió y no se vuelve a buscar.

    ConflictoEnvio si la clave se usó con otro pedido; EnvioEnCurso si el primero todavía está buscando.
    Un envío que quedó a medias más allá de su vigencia se retoma.
    """
    with db.transaccion() as c:
        try:
            with c.begin_nested():   # la clave puede existir ya: el error se atrapa y la transacción sigue
                nuevo = db.insertar("envios_cotizacion", usuario_id=usuario_id, clave=clave, huella=huella,
                                    estado="procesando", expira=_vence(), creado=db.ahora())
            return {"id": nuevo}, None
        except IntegrityError:
            pass
        fila = db.uno("select * from envios_cotizacion where usuario_id=:u and clave=:c" + ("" if config.ES_SQLITE else " for update"),
                      u=usuario_id, c=clave)
        if fila["huella"] != huella:
            raise ConflictoEnvio("Esa clave ya se usó con otra cotización.")
        if fila["solicitud_id"]:
            return fila, fila["solicitud_id"]
        if (fila["expira"] or "") > db.ahora():
            raise EnvioEnCurso("Esa cotización todavía se está buscando. Reintenta en un momento con la misma clave.")
        db.actualizar("envios_cotizacion", fila["id"], expira=_vence())
        return fila, None


def completar_envio(envio: dict, sid: int):
    db.actualizar("envios_cotizacion", envio["id"], estado="completado", solicitud_id=sid)


def soltar_envio(envio: dict):
    """El pedido no creó nada (datos que no sirven o un fallo): la clave queda libre para reintentar."""
    db.ejecutar("delete from envios_cotizacion where id=:i and solicitud_id is null", i=envio["id"])


# ---------- comparar ----------
def comparacion(sid: int) -> dict | None:
    sol = db.uno("""select s.*, p.nombre proyecto, v.nombre viajero from solicitudes s
                    left join proyectos p on p.id=s.proyecto_id left join viajeros v on v.id=s.viajero_id
                    where s.id=:i""", i=sid)
    if not sol:
        return None
    cat = costo.catalogo()
    membresias = db.todos_cache("select * from membresias where viajero_id=:v or viajero_id is null", v=sol["viajero_id"])
    vuelos, hoteles = [], []
    for o in db.todos("select * from opciones where solicitud_id=:i order by id", i=sid):
        datos = db.de_json(o["datos"], {})
        if o["tipo"] == "vuelo":
            t = db.de_json(o["tarifas"], {}) or {}
            ev = costo.mejor_tarifa(datos, t.get("lista") or [], sol, membresias, cat)
            vuelos.append({"id": o["id"], "v": datos, "ev": ev, "origen_dato": o["origen_dato"],
                           "origen_tarifas": t.get("origen"), "capturado": o["capturado"], "tarifas_lista": t.get("lista") or []})
        else:
            ev_h = costo.evaluar_hotel(datos, membresias, cat, costo.noches(sol["ida"], sol["regreso"]))
            # la calificación queda como número (o sin dato) para la página, la API, el asistente y la foto de lo mostrado
            hoteles.append({"id": o["id"], "h": {**datos, "calificacion": ev_h["calificacion"]}, "origen_dato": o["origen_dato"],
                            "programa": ev_h["programa"], "ev": ev_h,
                            "fuente_url": precios.enlace_hoteles(sol["ciudad"], sol["ida"], sol["regreso"], hotel=datos.get("nombre"))})
    # Precio esperado según el modelo (solo si hay un modelo utilizable)
    _, _, n_origen, n_destino = precios.ruta(codigos(sol, "origen"), codigos(sol, "destino"))
    ref = db.uno("select tipico_min, tipico_max from observaciones where busqueda=:b limit 1",
                 b=f"{n_origen}_{n_destino}_{sol['ida']}_{sol['regreso']}") or {}
    f_ida = date.fromisoformat(sol["ida"])
    # La ruta del modelo es la del vuelo real: con varios aeropuertos, cada opción llega a uno distinto
    filas = [{"ruta": f"{v['v'].get('desde') or sol['origen']}-{v['v'].get('hasta') or sol['destino']}", "aerolinea": v["v"]["aerolinea"], "escalas": v["v"]["escalas"],
              "duracion_min": v["v"]["duracion_min"], "hora_salida": int(v["v"]["sale"][11:13]) + int(v["v"]["sale"][14:16]) / 60,
              "dia_semana": f_ida.weekday(), "anticipacion": (f_ida - date.fromisoformat(sol["creado"][:10])).days,
              "noches": costo.noches(sol["ida"], sol["regreso"]), "tipico_min": ref.get("tipico_min"), "tipico_max": ref.get("tipico_max")}
             for v in vuelos]
    for v, esperado in zip(vuelos, modelo.precios_esperados(filas), strict=False):
        v["esperado"] = esperado
        v["frente_esperado"] = round((v["v"]["precio"] - esperado) / esperado * 100) if esperado else None
    validos = sorted([v for v in vuelos if not v["ev"]["descartada"]], key=lambda v: v["ev"]["total"])
    descartados = [v for v in vuelos if v["ev"]["descartada"]]
    # Hoteles por costo total (tarifa de miembro y puntos incluidos), no por tarifa; la calificación baja los descarta
    hoteles_descartados = [h for h in hoteles if h["ev"]["descartado"]]
    hoteles = sorted([h for h in hoteles if not h["ev"]["descartado"]], key=lambda h: (h["ev"]["total"], h["h"]["total"]))
    hotel_recomendado = hoteles[0] if hoteles else None
    hotel_barato = min(hoteles, key=lambda h: h["h"]["total"]) if hoteles else None
    hotel_mas_barato = hotel_barato if hotel_barato and hotel_barato["id"] != hotel_recomendado["id"] else None
    # Se muestran los mejores por costo total; el más barato por tarifa sigue a la vista aunque quede más abajo
    if len(hoteles) > HOTELES_A_MOSTRAR:
        hoteles = hoteles[:HOTELES_A_MOSTRAR] + ([hotel_mas_barato] if hotel_mas_barato in hoteles[HOTELES_A_MOSTRAR:] else [])
    for h in hoteles:
        h["recomendado"], h["mas_barato"] = h is hotel_recomendado, h is hotel_mas_barato
    # El viaje completo de cada vuelo con el hotel recomendado: una suma, no todas las combinaciones
    for v in vuelos:
        v["total_con_hotel"] = (round(v["ev"]["total"] + hotel_recomendado["ev"]["total"], 2)
                                if hotel_recomendado and not v["ev"]["descartada"] else None)
    # El más barato de la comparación es el más barato entre los que sirven: frente a uno descartado (llega tarde, el
    # equipo no cabe) no hay ahorro que contar. Si el más barato de todos está descartado, se dice aparte.
    mas_barato = min(validos, key=lambda v: v["v"]["precio"]) if validos else None
    de_todos = min(vuelos, key=lambda v: v["v"]["precio"]) if vuelos else None
    descartado = de_todos if mas_barato and de_todos["ev"]["descartada"] and de_todos["v"]["precio"] < mas_barato["v"]["precio"] else None
    partes = []
    if descartado:
        motivo = descartado["ev"]["descartada"]
        partes.append(f"La más barata del buscador, {descartado['v']['aerolinea']} {' + '.join(descartado['v']['numeros'])} por "
                      f"{descartado['v']['precio']:.0f} USD, está descartada: {motivo[:1].lower()}{motivo[1:]}")
    if mas_barato and validos[0]["id"] != mas_barato["id"]:
        m = validos[0]
        partes.append(f"{'La más barata que sirve' if descartado else 'La opción más barata del buscador'} es "
                      f"{mas_barato['v']['aerolinea']} por {mas_barato['v']['precio']:.0f} USD, "
                      f"pero con el equipo, el riesgo de cambio y las millas su costo esperado es {mas_barato['ev']['total']:.0f} USD. "
                      f"La mejor es {m['v']['aerolinea']} {m['v']['numeros'][0]} ({m['ev']['tarifa']['nombre']}): {m['ev']['total']:.0f} USD.")
    aviso = " ".join(partes) or None
    n = costo.noches(sol["ida"], sol["regreso"])
    return {"sol": sol, "vuelos": validos, "descartados": descartados, "hoteles": hoteles, "aviso": aviso,
            "hoteles_descartados": hoteles_descartados, "hotel_recomendado": hotel_recomendado, "hotel_mas_barato": hotel_mas_barato,
            "mas_barato": mas_barato, "mas_barato_descartado": descartado, "hay_modelo": modelo.utilizable(),
            "fuente_url": fuente_vuelos(sol), "fuente_hoteles_url": precios.enlace_hoteles(sol["ciudad"], sol["ida"], sol["regreso"]),
            "baterias": costo.baterias(sol["baterias_n"], sol["baterias_wh"]), "noches": n,
            "carro": round((sol["carro_dia"] or 0) * n, 2), "membresias": membresias,
            "fallos": db.todos("select detalle from eventos where entidad='solicitud' and entidad_id=:i and paso='consulta externa fallida'", i=sid),
            "decision": db.uno("select * from decisiones where solicitud_id=:i order by id desc", i=sid)}


# ---------- enlace a la fuente ----------
FUENTES = {"vuelos": "Google Flights", "hoteles": "Google Hotels"}


def fuente_vuelos(sol: dict) -> str:
    """La búsqueda de vuelos de la cotización en Google Flights (la misma que se le pidió al buscador)."""
    return precios.enlace_vuelos(codigos(sol, "origen"), codigos(sol, "destino"), sol["ida"], sol["regreso"])


def abrir_fuente(usuario: dict, sid: int, destino: str, hotel_id: int | None = None, canal: str = "api v1") -> str:
    """El enlace a la fuente que la persona abre, con su rastro en la bitácora (quién, qué cotización y adónde).

    La URL la arma siempre el servidor con los datos de la cotización: nunca llega del cliente. Quien llama comprueba
    antes que la persona ve la cotización. LookupError si no existe; CotizacionInvalida si el hotel no es de ella."""
    sol = db.uno("select * from solicitudes where id=:i", i=sid)
    if not sol:
        raise LookupError(sid)
    if destino == "vuelos":
        url, que = fuente_vuelos(sol), FUENTES["vuelos"]
    elif hotel_id:
        hotel = db.uno("select datos from opciones where id=:o and solicitud_id=:s and tipo='hotel'", o=hotel_id, s=sid)
        if not hotel:
            raise CotizacionInvalida("hotel_id", "Ese hotel no es de esta cotización.")
        nombre = (db.de_json(hotel["datos"], {}) or {}).get("nombre") or ""
        url, que = precios.enlace_hoteles(sol["ciudad"], sol["ida"], sol["regreso"], hotel=nombre), f"{FUENTES['hoteles']} ({nombre})"
    else:
        url, que = precios.enlace_hoteles(sol["ciudad"], sol["ida"], sol["regreso"]), FUENTES["hoteles"]
    eventos.registrar("solicitud", sid, "fuente abierta", f"{que}: {url}", f"{canal} · {usuario['nombre']}")
    return url


# ---------- decidir ----------
def _tope_decisiones_alcanzado(usuario: dict) -> bool:
    """Decisiones de hoy de la persona que consultaron el regreso en vivo (o lo intentaron), frente a la regla."""
    if not config.SERPAPI_KEY:
        return False
    hechas = db.uno("""select count(*) n from consultas_buscador where tipo='regreso' and origen in ('en vivo', 'fallida')
                       and usuario_id=:u and momento>=:h""", u=usuario["id"], h=db.ahora()[:10])["n"]
    return hechas >= int(costo.supuesto(costo.catalogo(), "decisiones_en_vivo_dia", DECISIONES_EN_VIVO_DIA))


def decidir(usuario: dict, sid: int, vuelo_id: int, hotel_id: int = 0, motivo: str = "", razones=()) -> dict:
    """Guarda la decisión y crea (o actualiza) el viaje de la cotización.

    Devuelve `{"repetida", "decision_id", "viaje"}`; `repetida` es el mismo envío otra vez, que no se duplica.
    LookupError si la cotización no existe; DecisionBloqueada o DecisionInvalida si no se puede guardar.
    """
    c = comparacion(sid)
    if not c:
        raise LookupError(sid)
    if not puede_decidir(usuario, c["sol"]):
        raise FueraDeAlcance(NO_DECIDE)
    previa = c["decision"]
    if previa and previa["vuelo_id"] == vuelo_id and (previa["hotel_id"] or 0) == hotel_id and (previa["motivo"] or "") == motivo.strip()[:300]:
        return {"repetida": True, "decision_id": previa["id"], "viaje": viajes.de_solicitud(sid)}
    bloqueo = viajes.bloquea_decision(sid)
    if bloqueo:
        raise DecisionBloqueada(bloqueo)
    aprobado_por = usuario["nombre"]
    vuelo = next((v for v in c["vuelos"] + c["descartados"] if v["id"] == vuelo_id), None)
    hotel = next((h for h in c["hoteles"] + c["hoteles_descartados"] if h["id"] == hotel_id), None)  # puede no haber hoteles
    if not vuelo:
        raise DecisionInvalida("vuelo_id", "Elige un vuelo para guardar la decisión.")
    orden = c["vuelos"] + c["descartados"]
    recomendado = c["vuelos"][0] if c["vuelos"] else None
    siguio = bool(recomendado and recomendado["id"] == vuelo["id"])
    razones = [r for r in razones if r in config.RAZONES]
    if not siguio and len(motivo.strip()) < 5:
        # Cuando la persona se aparta de la recomendación, el porqué es el dato más valioso
        raise DecisionInvalida("motivo", "Elegiste una opción distinta a la recomendada: cuéntanos por qué.")
    posicion = orden.index(vuelo) + 1
    # La opción elegida se carga completa: el regreso real y sus opciones de reserva (dos búsquedas; lo ya guardado no se paga)
    sol = c["sol"]
    desde_todos, hacia_todos = codigos(sol, "origen"), codigos(sol, "destino")
    # Pasado el tope del día, sin token ni reserva: precios solo lee lo guardado y no consulta en vivo
    aviso_tope = AVISO_TOPE_DECISION if _tope_decisiones_alcanzado(usuario) else None
    if aviso_tope:
        eventos.registrar("solicitud", sid, "tope de consultas al decidir", aviso_tope, "reglas editables")
    ida_consulta = {**vuelo["v"], "token": None} if aviso_tope else vuelo["v"]
    regreso = precios.vuelo_regreso(ida_consulta, desde_todos, hacia_todos, sol["ida"], sol["regreso"], sid)
    if regreso:
        regreso_consulta = {**regreso, "booking": None} if aviso_tope else regreso
        tarifas, origen_t, _ = precios.opciones_reserva(vuelo["v"], regreso_consulta, desde_todos, hacia_todos, sol["ida"],
                                                        sol["regreso"], sid)
        if tarifas:   # el presupuesto usa la tarifa real; sin ella queda la estimada, que ya dice «(supuesta)»
            db.actualizar("opciones", vuelo["id"], tarifas={"lista": tarifas, "origen": origen_t})
            vuelo = {**vuelo, "origen_tarifas": origen_t, "tarifas_lista": tarifas,
                     "ev": costo.mejor_tarifa(vuelo["v"], tarifas, sol, c["membresias"], costo.catalogo())}
            orden[posicion - 1] = vuelo
    else:
        eventos.registrar("solicitud", sid, "regreso sin datos",
                          f"{' + '.join(vuelo['v']['numeros'])}: sin vuelo de regreso; se registran solo los tramos de ida", "SerpApi")
    # Las líneas del vuelo van al grupo «vuelo»; las de traslado conservan el suyo (traslados o combustible)
    lineas = [{**l, "grupo": l.get("grupo") or "vuelo"} for l in vuelo["ev"]["lineas"]]
    if hotel:
        # Las líneas del hotel evaluado, para que el total sea el de la comparación. Los puntos son valor esperado, como
        # las millas: llevan `valor_esperado` y `viajes.presupuesto_de` no los cuenta como dinero
        lineas.append({"concepto": f"Hotel: {hotel['h']['nombre']} ({c['noches']} noches)", "valor": hotel["ev"]["tarifa"],
                       "origen": "buscador", "grupo": "hotel"})
        for l in hotel["ev"]["lineas"]:
            if l["concepto"].startswith("Tarifa de miembro"):
                lineas.append({**l, "grupo": "hotel", "concepto":
                               f"Hotel: tarifa de miembro {hotel['programa']} {l['concepto'].removeprefix('Tarifa de miembro ')}"})
            elif l["concepto"].startswith("Puntos del programa"):
                lineas.append({**l, "grupo": "hotel", "valor_esperado": True, "concepto":
                               f"Hotel: puntos de {hotel['programa']} {l['concepto'].removeprefix('Puntos del programa ')}"})
    if c["carro"]:
        lineas.append({"concepto": f"Carro de alquiler ({c['noches']} días x {c['sol']['carro_dia']:.0f})",
                       "valor": c["carro"], "origen": "supuesto", "grupo": "alquiler_carro"})
    total = round(sum(l["valor"] for l in lineas), 2)
    did = db.insertar("decisiones", solicitud_id=sid, proyecto_id=c["sol"]["proyecto_id"], vuelo_id=vuelo_id,
                      hotel_id=hotel["id"] if hotel else None, tarifa=vuelo["ev"]["tarifa"]["nombre"],
                      desglose={"lineas": lineas, "avisos": vuelo["ev"]["avisos"], "vuelo": vuelo["v"], "regreso": regreso,
                                "precio_tarifa": vuelo["ev"]["tarifa"]["precio"], "origen_tarifas": vuelo.get("origen_tarifas"),
                                "hotel": hotel["h"] if hotel else None, "hotel_evaluado": hotel["ev"] if hotel else None,
                                "origen_vuelo": vuelo["origen_dato"], "origen_hotel": hotel["origen_dato"] if hotel else None,
                                "aviso": c["aviso"], "baterias": c["baterias"], "aviso_tope": aviso_tope,
                                # lo que se evita frente a la opción más barata que sirve, por costo esperado
                                "ahorro": round(max(c["mas_barato"]["ev"]["total"] - vuelo["ev"]["total"], 0), 2) if c["mas_barato"] else 0},
                      total=total, motivo=motivo[:300], aprobado_por=aprobado_por, creado=db.ahora(), usuario_id=usuario["id"],
                      razones=razones, recomendado_id=recomendado["id"] if recomendado else None,
                      siguio_recomendacion=1 if siguio else 0, posicion_elegida=posicion)
    # Foto de todo lo que se mostró: las reglas y las tarifas pueden cambiar después
    db.insertar_varios("elecciones", [
        {"decision_id": did, "solicitud_id": sid, "opcion_id": o["id"], "tipo": "vuelo", "posicion": i + 1,
         "elegida": int(o["id"] == vuelo["id"]), "recomendada": int(bool(recomendado) and o["id"] == recomendado["id"]),
         "descartada": int(bool(o["ev"]["descartada"])), "precio": o["v"]["precio"], "costo_esperado": o["ev"]["total"],
         "rasgos": {"aerolinea": o["v"]["aerolinea"], "escalas": o["v"]["escalas"], "duracion_min": o["v"]["duracion_min"],
                    "sale": o["v"]["sale"][11:], "llega": o["v"]["llega"][11:], "tarifa": o["ev"]["tarifa"]["nombre"],
                    "permite_cambio": o["ev"]["tarifa"]["permite_cambio"], "tarifas_reales": o["ev"]["tarifas_reales"],
                    "frente_esperado": o.get("frente_esperado"), "prob_cambio": c["sol"]["prob_cambio"],
                    "baterias": c["sol"]["baterias_n"], "maleta": c["sol"]["maleta"]},
         "creado": db.ahora()} for i, o in enumerate(orden)] + [
        {"decision_id": did, "solicitud_id": sid, "opcion_id": h["id"], "tipo": "hotel", "posicion": i + 1,
         "elegida": int(bool(hotel) and h["id"] == hotel["id"]), "recomendada": int(h is c["hotel_recomendado"]),
         "descartada": int(bool(h["ev"]["descartado"])), "precio": h["h"]["total"], "costo_esperado": h["ev"]["total"],
         "rasgos": {"calificacion": h["h"]["calificacion"], "clase": h["h"]["clase"], "programa": h["programa"],
                    "socio": h["ev"]["socio"]},
         "creado": db.ahora()} for i, h in enumerate(c["hoteles"] + c["hoteles_descartados"])])
    # Origen y destino pasan a los aeropuertos reales del vuelo elegido
    reales = {k: vuelo["v"][campo] for k, campo in (("origen", "desde"), ("destino", "hasta")) if vuelo["v"].get(campo)}
    db.actualizar("solicitudes", sid, estado="decidido", **reales)
    eventos.registrar("solicitud", sid, "decisión guardada", f"Total previsto {total:.2f} USD (ficha #{did})", aprobado_por or "usuario")
    for l in lineas:
        if l.get("calculo"):   # cada traslado que entra al presupuesto deja su cuenta en la bitácora
            k = l["calculo"]
            eventos.registrar("solicitud", sid, "traslado calculado",
                              f"{l['concepto']}: {k['km_linea_recta']} km en línea recta x {k['factor']} = {k['km_carretera']} km "
                              f"a {k['usd_km']} USD/km ida y vuelta = {l['valor']:.2f} USD; {k['horas']} h a {k['velocidad_kmh']:g} km/h",
                              "reglas editables (supuesto)")
    # La decisión asigna el viaje a la persona: nace con su código y queda a la espera de que administración apruebe el presupuesto
    el_viaje = viajes.crear_desde_decision(did)
    monitoreo_vuelos.registrar_tramos(el_viaje["id"], vuelo["v"], regreso)
    return {"repetida": False, "decision_id": did, "viaje": el_viaje}
