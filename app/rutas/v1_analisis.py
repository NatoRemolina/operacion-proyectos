"""API v1: leer la página de un vuelo en Google Flights al abrir su desglose. Contrato en `contracts/api-v1.md`.

La lectura la hace el analizador (`app/servicios/analizador.py`); aquí solo el permiso y la forma. La pide y la ve
quien ve la cotización (`acceso.puede_ver`); lo demás responde 404.
"""
import html
import json
import re
import secrets

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import HTMLResponse, Response

from .. import api_v1, db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, persona
from ..api_v1.esquemas_cotizacion import (
    ENTERO_MAXIMO,
    AnalisisVuelo,
    EnvioVendedor,
    Evidencia,
    OpcionesBuscador,
    PedidoIrA,
    errores_cotizacion,
)
from ..servicios import acceso, almacen, analizador, capturas, consultas, cotizacion, precios
from . import v1_cotizaciones

router = APIRouter(prefix=PREFIJO, tags=["cotizaciones"])


def Id():  # noqa: N802 (un `Path` por parámetro: compartido, FastAPI le pone a todos el nombre del primero)
    return Path(ge=1, le=ENTERO_MAXIMO)


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _visible(yo: dict, sid: int):
    if not acceso.puede_ver(yo, db.uno("select usuario_id, viajero_id, proyecto_id from solicitudes where id=:i", i=sid)):
        raise _no_encontrado()


def _con_enlaces(tarifas: list, sesion: str, sid: int, opcion_id: int) -> list:
    """Cada tarifa con su «Ir a…» firmado para esta sesión (sin sesión, sin enlace)."""
    return [{**t, "ir_url": v1_cotizaciones.url_ir(sesion, sid, opcion_id, str(t.get("vendedor") or ""), str(t.get("nombre") or ""))
             if sesion and t.get("vendedor") and t.get("nombre") else None} for t in tarifas if isinstance(t, dict)]


def _forma(sid: int, opcion_id: int, a: dict, sesion: str = "") -> dict:
    precio = (db.uno("select precio from opciones where id=:o", o=opcion_id) or {}).get("precio")
    return {"id": a["id"], "opcion_id": opcion_id, "estado": a["estado"], "motivo": a["motivo"], "url": a["url"],
            "leido": consultas.instante(a["terminado"]) if a.get("terminado") else None, "duracion_ms": a["duracion_ms"],
            "reutilizado": bool(a.get("reutilizado")), "precio_buscador_usd": consultas.dinero(precio),
            "aviso_precio": analizador.aviso_precio(a, precio) if a["estado"] == "listo" else None,
            "datos": {**a["datos"], "tarifas": _con_enlaces(a["datos"].get("tarifas") or [], sesion, sid, opcion_id)}
            if a["estado"] == "listo" and isinstance(a.get("datos"), dict) else None,
            "extracto": (a["datos"] or {}).get("extracto") if a["estado"] == "fallido" else None,
            "captura_url": f"{PREFIJO}/cotizaciones/{sid}/analisis/{a['id']}/captura" if a.get("captura") else None}


@router.post("/cotizaciones/{id}/vuelos/{opcion_id}/analisis", response_model=AnalisisVuelo,
             responses=errores_cotizacion(401, 403, 404, 422))
def pedir(request: Request, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(escritura)):
    """Lee la página del vuelo en Google Flights (tarda unos segundos) o devuelve la lectura de menos de 60 minutos.

    Tarifas y qué incluye cada una, equipaje, cambios y reembolso, escalas, precio por vendedor y una captura. Con los
    topes del día alcanzados, apagado o sin analizador: `estado: no_disponible` y el motivo, sin leer nada."""
    _visible(yo, id)
    try:
        analizador.clave_de(id, opcion_id)   # 404 solo si el vuelo no es de la cotización
    except LookupError as e:
        raise _no_encontrado() from e
    return _forma(id, opcion_id, analizador.solicitar(yo, id, opcion_id), v1_cotizaciones._sesion(request))


@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/analisis", response_model=AnalisisVuelo,
            responses=errores_cotizacion(401, 404, 422))
def ver(request: Request, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona)):
    """La última lectura del vuelo (para seguir una en curso). 404 si nunca se leyó."""
    _visible(yo, id)
    try:
        a = analizador.ultimo(id, opcion_id)
    except LookupError as e:
        raise _no_encontrado() from e
    if not a:
        raise _no_encontrado()
    return _forma(id, opcion_id, {**a, "reutilizado": True}, v1_cotizaciones._sesion(request))


@router.get("/cotizaciones/{id}/analisis/{analisis_id}/captura", response_class=Response, responses={
    **errores_cotizacion(401, 404, 422), 200: {"description": "La captura de la página leída", "content": {"image/png": {}}}})
def captura(id: int = Id(), analisis_id: int = Id(), yo: dict = Depends(persona)):
    _visible(yo, id)
    a = analizador.de_la_cotizacion(id, analisis_id)
    contenido = analizador.captura(a) if a else None
    if contenido is None:
        raise _no_encontrado()
    return Response(contenido, media_type="image/png",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


# ---------- pieza 5: la evidencia guardada de la decisión ----------
def evidencia(sid: int) -> dict:
    """Las capturas de la decisión vigente (al decidir, el seguimiento y la compra) y la línea de precios del vuelo."""
    d = db.uno("select id from decisiones where solicitud_id=:s order by id desc limit 1", s=sid)
    filas = [f for f in capturas.de_la_cotizacion(sid) if d and f["decision_id"] == d["id"]]
    base = f"{PREFIJO}/cotizaciones/{sid}/evidencia"
    lista = [{"id": f["id"], "tipo": f["tipo"], "motivo": f["motivo"], "estado": f["estado"], "fallo": f["fallo"],
              "intentos": f["intentos"], "creado": consultas.instante(f["creado"]), "terminado": consultas.instante(f["terminado"]),
              "datos": f["datos"] if f["estado"] == "lista" else None,
              "imagenes": [f"{base}/{f['id']}/imagen/{n}" for n in range(len(f["imagenes"]))] if f["estado"] == "lista" else [],
              "texto_url": f"{base}/{f['id']}/texto" if f["estado"] == "lista" and f["texto"] else None} for f in filas]
    listas = [c for c in lista if c["estado"] == "lista"]
    seguimiento = [{"momento": c["terminado"], "motivo": c["motivo"],
                    "precio_google_usd": consultas.dinero(((c["datos"] or {}).get("google") or {}).get("precio_total")),
                    "total_aerolinea_usd": consultas.dinero(((c["datos"] or {}).get("aerolinea") or {}).get("total"))}
                   for c in listas if c["tipo"] == "vuelo"]
    estado = "guardando" if any(c["estado"] in ("pendiente", "en_curso") for c in lista) else \
        "guardada" if listas else "sin_evidencia"
    return {"estado": estado, "guardada": max((c["terminado"] for c in listas if c["terminado"]), default=None),
            "capturas": lista, "seguimiento": sorted(seguimiento, key=lambda p: p["momento"] or "")}


def _captura_de(sid: int, captura_id: int) -> dict:
    f = db.uno("select * from capturas where id=:c and solicitud_id=:s and estado='lista'", c=captura_id, s=sid)
    if not f:
        raise _no_encontrado()
    return f


PRIVADO = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}


@router.get("/cotizaciones/{id}/evidencia", response_model=Evidencia, responses=errores_cotizacion(401, 404, 422))
def ver_evidencia(id: int = Id(), yo: dict = Depends(persona)):
    """La evidencia completa de lo decidido (pieza 5): capturas del vuelo (Google Flights y la aerolínea) y del hotel,
    al decidir, cada día hasta la compra y al comprar. Las hace el trabajador; mientras tanto, `guardando`."""
    _visible(yo, id)
    return evidencia(id)


@router.get("/cotizaciones/{id}/evidencia/{captura_id}/imagen/{n}", response_class=Response, responses={
    **errores_cotizacion(401, 404, 422), 200: {"description": "Captura de página completa", "content": {"image/png": {}}}})
def imagen_evidencia(id: int = Id(), captura_id: int = Id(), n: int = Path(ge=0, le=9), yo: dict = Depends(persona)):
    _visible(yo, id)
    claves = db.de_json(_captura_de(id, captura_id)["imagenes"], []) or []
    contenido = almacen.leer(claves[n]) if n < len(claves) else None
    if contenido is None:
        raise _no_encontrado()
    return Response(contenido, media_type="image/png", headers=PRIVADO)


@router.get("/cotizaciones/{id}/evidencia/{captura_id}/texto", response_class=Response, responses={
    **errores_cotizacion(401, 404, 422), 200: {"description": "El texto visible completo", "content": {"text/plain": {}}}})
def texto_evidencia(id: int = Id(), captura_id: int = Id(), yo: dict = Depends(persona)):
    _visible(yo, id)
    texto = _captura_de(id, captura_id)["texto"]
    if not texto:
        raise _no_encontrado()
    return Response(texto, media_type="text/plain; charset=utf-8", headers=PRIVADO)


# ---------- primera capa del desglose: lo del buscador ----------
@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/reserva", response_model=OpcionesBuscador,
            responses=errores_cotizacion(401, 404, 422))
def opciones_buscador(request: Request, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona)):
    """Las opciones de reserva del buscador para el itinerario, de lo guardado (sin consultar ni gastar cupo): cada
    vendedor con su precio, tarifa, equipaje, cambios y reembolso. Las trae el enlace a la página oficial."""
    _visible(yo, id)
    sol = db.uno("select * from solicitudes where id=:i", i=id)
    o = db.uno("select datos from opciones where id=:o and solicitud_id=:s and tipo='vuelo'", o=opcion_id, s=id)
    if not o:
        raise _no_encontrado()
    vuelo = db.de_json(o["datos"], {}) or {}
    lado = lambda nombre: precios.codigos(sol.get(f"{nombre}_aeropuertos") or sol[nombre])  # noqa: E731
    tarifas, creado = precios.opciones_guardadas(vuelo, lado("origen"), lado("destino"), sol["ida"], sol["regreso"])
    vendedores: dict[str, dict] = {}
    for t in tarifas:
        v = vendedores.setdefault(t["vendedor"], {"vendedor": t["vendedor"], "aerolinea": t["aerolinea"], "precio_desde": t["precio"]})
        v["precio_desde"] = min(v["precio_desde"], t["precio"])
    return {"estado": "listo" if tarifas else "sin_datos", "consultado": consultas.instante(creado) if creado else None,
            "tarifas": _con_enlaces(tarifas, v1_cotizaciones._sesion(request), id, opcion_id),
            "vendedores": list(vendedores.values())}


# ---------- «Ir a…» (pieza 3b) ----------
SITIOS_PERMITIDOS = {"same-origin", "same-site", "none"}


@router.post("/cotizaciones/{id}/vuelos/{opcion_id}/ir", response_model=EnvioVendedor,
             responses=errores_cotizacion(401, 403, 404, 422))
def ir(datos: PedidoIrA, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(escritura)):
    """Adónde enviar a la persona para comprar esa tarifa de ese vendedor: por la página (el analizador pulsa
    «Continue»), por el buscador (el pedido de esa tarifa) o, si no, la página del vuelo en Google Flights. Tope por
    persona y día `ir_a_persona_dia`. Los `campos` del envío no se guardan ni se registran."""
    _visible(yo, id)
    try:
        analizador.clave_de(id, opcion_id)   # 404 si el vuelo no es de la cotización (y solo eso: no tapa otros errores)
    except LookupError as e:
        raise _no_encontrado() from e
    return analizador.ir_a(yo, id, opcion_id, datos.vendedor, datos.tarifa)


NOMBRE_ENLACE = re.compile(r"[\w .,&'()+/-]{1,60}")
INCOMPLETO = ("El enlace no está completo", "Vuelve a abrir el desglose del vuelo y elige la tarifa otra vez.")


@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/ir", response_class=HTMLResponse, responses={
    **errores_cotizacion(401, 403, 404, 422),
    200: {"description": "Página que prepara el envío al vendedor y lo hace", "content": {"text/html": {}}}})
def pagina_ir(request: Request, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona),
              vendedor: str | None = Query(None, description="Vendedor (1 a 60 caracteres: letras, números y . , & ' ( ) + / -)."),
              tarifa: str | None = Query(None, description="Tarifa (mismas reglas que el vendedor)."),
              t: str | None = Query(None, description="Token firmado del enlace (vence en 5 minutos).")):
    """La abre «Ir a…» en otra pestaña. Muestra «Preparando tu enlace…», pide `POST …/ir` con la sesión y envía el
    formulario a Google (o va a Google Flights). Si falla, lo explica y ofrece Google Flights. Con datos que no son
    válidos responde 422 con una página legible (no JSON): la pestaña la ve una persona."""
    if request.headers.get("sec-fetch-site", "none") not in SITIOS_PERMITIDOS:
        return v1_cotizaciones.pagina_aviso(403, *v1_cotizaciones.OTRO_SITIO)
    if not all(isinstance(x, str) and NOMBRE_ENLACE.fullmatch(x) for x in (vendedor, tarifa)) or len(t or "") > 64:
        return v1_cotizaciones.pagina_aviso(422, *INCOMPLETO)
    fila = db.uno("select usuario_id, viajero_id, proyecto_id from solicitudes where id=:i", i=id)
    o = db.uno("select datos from opciones where id=:o and solicitud_id=:s and tipo='vuelo'", o=opcion_id, s=id)
    if not acceso.puede_ver(yo, fila) or not o:
        return v1_cotizaciones.pagina_aviso(404, *v1_cotizaciones.AJENO)
    if not v1_cotizaciones.token_ir_valido(t, v1_cotizaciones._sesion(request), id, opcion_id, vendedor, tarifa):
        # sin el token de esta sesión (enlace viejo, copiado o enviado por correo): no se hace el pedido ni se gasta nada
        return v1_cotizaciones.pagina_aviso(403, "El enlace venció", "Vuelve a abrir el desglose del vuelo y elige la tarifa otra vez.")
    sol = db.uno("select * from solicitudes where id=:i", i=id)
    vuelo = db.de_json(o["datos"], {}) or {}
    google = cotizacion.fuente_vuelo(sol, vuelo)
    nonce = secrets.token_urlsafe(16)
    datos = json.dumps({"api": f"{PREFIJO}/cotizaciones/{id}/vuelos/{opcion_id}/ir", "vendedor": vendedor, "tarifa": tarifa,
                        "csrf": api_v1.token_csrf(request.cookies.get(acceso.COOKIE)), "google": google})
    titulo = html.escape(f"{vendedor} · {tarifa}")
    cuerpo = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Preparando tu enlace a {titulo}</title></head>
<body><main><p id="estado" role="status">Preparando tu enlace a {titulo}…</p>
<p id="alterna" hidden><a href="{html.escape(google)}" rel="noopener noreferrer">Abrir el vuelo en Google Flights</a></p></main>
<script nonce="{nonce}">
(async function () {{
  const d = {datos.replace("</", "<\\/")};
  const estado = document.getElementById("estado");
  function fallo(texto) {{ estado.textContent = texto; document.getElementById("alterna").hidden = false; }}
  try {{
    const r = await fetch(d.api, {{ method: "POST", credentials: "same-origin",
      headers: {{ "Content-Type": "application/json", "X-CSRF-Token": d.csrf }},
      body: JSON.stringify({{ vendedor: d.vendedor, tarifa: d.tarifa }}) }});
    if (!r.ok) return fallo("No se pudo preparar el enlace al vendedor. Puedes abrir el vuelo en Google Flights.");
    const e = await r.json();
    if (!e.url) return fallo("No hay un enlace para esta tarifa. Puedes abrir el vuelo en Google Flights.");
    if (!e.campos.length) return location.replace(e.url);
    estado.textContent = "Abriendo la página de " + e.vendedor + "…";
    const f = document.createElement("form");
    f.method = "post"; f.action = e.url;
    for (const [k, v] of e.campos) {{
      const i = document.createElement("input"); i.type = "hidden"; i.name = k; i.value = v; f.appendChild(i);
    }}
    document.body.appendChild(f); f.submit();
  }} catch (_) {{ fallo("No hubo conexión con el servidor. Puedes abrir el vuelo en Google Flights."); }}
}})();
</script></body></html>"""
    return HTMLResponse(cuerpo, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": f"default-src 'none'; script-src 'nonce-{nonce}'; connect-src 'self'; form-action https:; "
                                   "base-uri 'none'; frame-ancestors 'none'"})
