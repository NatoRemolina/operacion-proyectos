"""API v1: leer la página de un vuelo en Google Flights al abrir su desglose. Contrato en `contracts/api-v1.md`.

La lectura la hace el analizador (`app/servicios/analizador.py`); aquí solo el permiso y la forma. La pide y la ve
quien ve la cotización (`acceso.puede_ver`); lo demás responde 404.
"""
import html
import json
import secrets

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import HTMLResponse, Response

from .. import api_v1, db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, escritura, persona
from ..api_v1.esquemas_cotizacion import ENTERO_MAXIMO, AnalisisVuelo, EnvioVendedor, PedidoIrA, errores_cotizacion
from ..servicios import acceso, analizador, consultas, cotizacion

router = APIRouter(prefix=PREFIJO, tags=["cotizaciones"])


def Id():  # noqa: N802 (un `Path` por parámetro: compartido, FastAPI le pone a todos el nombre del primero)
    return Path(ge=1, le=ENTERO_MAXIMO)


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _visible(yo: dict, sid: int):
    if not acceso.puede_ver(yo, db.uno("select usuario_id, viajero_id, proyecto_id from solicitudes where id=:i", i=sid)):
        raise _no_encontrado()


def _forma(sid: int, opcion_id: int, a: dict) -> dict:
    precio = (db.uno("select precio from opciones where id=:o", o=opcion_id) or {}).get("precio")
    return {"id": a["id"], "opcion_id": opcion_id, "estado": a["estado"], "motivo": a["motivo"], "url": a["url"],
            "leido": consultas.instante(a["terminado"]) if a.get("terminado") else None, "duracion_ms": a["duracion_ms"],
            "reutilizado": bool(a.get("reutilizado")), "precio_buscador_usd": consultas.dinero(precio),
            "aviso_precio": analizador.aviso_precio(a, precio) if a["estado"] == "listo" else None,
            "datos": a["datos"] if a["estado"] == "listo" else None,
            "extracto": (a["datos"] or {}).get("extracto") if a["estado"] == "fallido" else None,
            "captura_url": f"{PREFIJO}/cotizaciones/{sid}/analisis/{a['id']}/captura" if a.get("captura") else None}


@router.post("/cotizaciones/{id}/vuelos/{opcion_id}/analisis", response_model=AnalisisVuelo,
             responses=errores_cotizacion(401, 403, 404, 422))
def pedir(id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(escritura)):
    """Lee la página del vuelo en Google Flights (tarda unos segundos) o devuelve la lectura de menos de 60 minutos.

    Tarifas y qué incluye cada una, equipaje, cambios y reembolso, escalas, precio por vendedor y una captura. Con los
    topes del día alcanzados, apagado o sin analizador: `estado: no_disponible` y el motivo, sin leer nada."""
    _visible(yo, id)
    try:
        analizador.clave_de(id, opcion_id)   # 404 solo si el vuelo no es de la cotización
    except LookupError as e:
        raise _no_encontrado() from e
    return _forma(id, opcion_id, analizador.solicitar(yo, id, opcion_id))


@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/analisis", response_model=AnalisisVuelo,
            responses=errores_cotizacion(401, 404, 422))
def ver(id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona)):
    """La última lectura del vuelo (para seguir una en curso). 404 si nunca se leyó."""
    _visible(yo, id)
    try:
        a = analizador.ultimo(id, opcion_id)
    except LookupError as e:
        raise _no_encontrado() from e
    if not a:
        raise _no_encontrado()
    return _forma(id, opcion_id, {**a, "reutilizado": True})


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


@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/ir", response_class=HTMLResponse, responses={
    **errores_cotizacion(401, 403, 404, 422),
    200: {"description": "Página que prepara el envío al vendedor y lo hace", "content": {"text/html": {}}}})
def pagina_ir(request: Request, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona),
              vendedor: str = Query(min_length=1, max_length=60, pattern=r"^[\w .,&'()+/-]+$"),
              tarifa: str = Query(min_length=1, max_length=60, pattern=r"^[\w .,&'()+/-]+$")):
    """La abre «Ir a…» en otra pestaña. Muestra «Preparando tu enlace…», pide `POST …/ir` con la sesión y envía el
    formulario a Google (o va a Google Flights). Si falla, lo explica y ofrece Google Flights."""
    if request.headers.get("sec-fetch-site", "none") not in SITIOS_PERMITIDOS:
        raise ErrorApi(403, "FORBIDDEN", "Abre el enlace del vendedor desde la plataforma.")
    _visible(yo, id)
    try:
        sol = db.uno("select * from solicitudes where id=:i", i=id)
        vuelo = db.de_json(db.uno("select datos from opciones where id=:o and solicitud_id=:s and tipo='vuelo'",
                                  o=opcion_id, s=id)["datos"], {})
    except TypeError as e:
        raise _no_encontrado() from e
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
