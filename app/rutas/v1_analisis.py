"""API v1: leer la página de un vuelo en Google Flights al abrir su desglose. Contrato en `contracts/api-v1.md`.

La lectura la hace el analizador (`app/servicios/analizador.py`); aquí solo el permiso y la forma. La pide y la ve
quien ve la cotización (`acceso.puede_ver`); lo demás responde 404.
"""
import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import HTMLResponse, Response

from .. import api_v1, config, db
from ..api_v1 import MENSAJE_HTTP, PREFIJO, ErrorApi, comun, escritura, formas, persona
from ..api_v1.esquemas_cotizacion import (
    ENTERO_MAXIMO,
    AnalisisVuelo,
    EnvioVendedor,
    Evidencia,
    OpcionesBuscador,
    PedidoIrA,
    errores_cotizacion,
)
from ..servicios import acceso, almacen, analizador, capturas, consultas, cotizacion, enlaces, tiempo

router = APIRouter(prefix=PREFIJO, tags=["cotizaciones"])


def Id():  # noqa: N802 (un `Path` por parámetro: compartido, FastAPI le pone a todos el nombre del primero)
    return Path(ge=1, le=ENTERO_MAXIMO)


def _no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NOT_FOUND", MENSAJE_HTTP[404])


def _visible(yo: dict, sid: int):
    if not acceso.puede_ver(yo, cotizacion.fila_de_acceso(sid)):
        raise _no_encontrado()


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
    return formas.analisis(id, opcion_id, analizador.solicitar(yo, id, opcion_id), comun.sesion(request))


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
    return formas.analisis(id, opcion_id, {**a, "reutilizado": True}, comun.sesion(request))


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
def _captura(sid: int, captura_id: int) -> dict:
    f = capturas.lista(sid, captura_id)
    if not f:
        raise _no_encontrado()
    return f


PRIVADO = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}


@router.get("/cotizaciones/{id}/evidencia", response_model=Evidencia, responses=errores_cotizacion(401, 404, 422))
def ver_evidencia(id: int = Id(), yo: dict = Depends(persona)):
    """La evidencia completa de lo decidido (pieza 5): capturas del vuelo (Google Flights y la aerolínea) y del hotel,
    al decidir, cada día hasta la compra y al comprar. Las hace el trabajador; mientras tanto, `guardando`."""
    _visible(yo, id)
    return formas.evidencia(id)


@router.get("/cotizaciones/{id}/evidencia/{captura_id}/imagen/{n}", response_class=Response, responses={
    **errores_cotizacion(401, 404, 422), 200: {"description": "Captura de página completa", "content": {"image/png": {}}}})
def imagen_evidencia(id: int = Id(), captura_id: int = Id(), n: int = Path(ge=0, le=9), yo: dict = Depends(persona)):
    _visible(yo, id)
    claves = db.de_json(_captura(id, captura_id)["imagenes"], []) or []
    contenido = almacen.leer(claves[n]) if n < len(claves) else None
    if contenido is None:
        raise _no_encontrado()
    return Response(contenido, media_type="image/png", headers=PRIVADO)


@router.get("/cotizaciones/{id}/evidencia/{captura_id}/texto", response_class=Response, responses={
    **errores_cotizacion(401, 404, 422), 200: {"description": "El texto visible completo", "content": {"text/plain": {}}}})
def texto_evidencia(id: int = Id(), captura_id: int = Id(), yo: dict = Depends(persona)):
    _visible(yo, id)
    texto = _captura(id, captura_id)["texto"]
    if not texto:
        raise _no_encontrado()
    return Response(texto, media_type="text/plain; charset=utf-8", headers=PRIVADO)


# ---------- primera capa del desglose: lo del buscador ----------
@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/reserva", response_model=OpcionesBuscador,
            responses=errores_cotizacion(401, 404, 422))
def opciones_buscador(request: Request, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona)):
    """Las opciones de reserva del buscador para el itinerario, de lo guardado (sin consultar ni gastar cupo): cada
    vendedor con su precio, tarifa, equipaje, cambios y reembolso. Las trae el enlace a la página oficial. `en_vivo`
    dice si el clic que abrió el desglose consulta el buscador en vivo: entonces lo nuevo llega aquí."""
    _visible(yo, id)
    r = cotizacion.opciones_de_reserva(id, opcion_id)
    if r is None:
        raise _no_encontrado()

    def consulta_en_vivo() -> bool:
        """Lo mismo que decide si el clic consulta (`cotizacion._destino_vendedor`): la clave y el cupo de búsquedas pagas
        del día de la persona (con el tope en 0, apagado). El clic reserva su cupo antes de buscar: una reserva de hace
        un momento es la de este clic, aunque con ella se haya llegado al tope."""
        if config.modo()["precios"] != "en vivo":
            return False
        reservas = db.todos("""select unidades, creado from cupos_buscador where tipo='enlace_vendedor' and usuario_id=:u
                               and creado>=:h""", u=yo["id"], h=tiempo.inicio_del_dia())
        hace_poco = (datetime.now(UTC) - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
        if any(f["creado"] >= hace_poco for f in reservas):
            return True
        unidades = analizador.unidades_busqueda(cotizacion.solicitud(id), cotizacion.vuelo_de(id, opcion_id))
        return sum(f["unidades"] for f in reservas) + unidades <= analizador.tope_enlace_vendedor()

    return {"estado": "listo" if r["tarifas"] else "sin_datos", "consultado": consultas.instante(r["creado"]) if r["creado"] else None,
            "en_vivo": consulta_en_vivo(),
            "tarifas": formas.con_enlaces(r["tarifas"], comun.sesion(request), id, opcion_id), "vendedores": r["vendedores"]}


# ---------- «Ir a…» (pieza 3b) ----------


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


@router.get("/cotizaciones/{id}/vuelos/{opcion_id}/ir", response_class=HTMLResponse, responses={
    **errores_cotizacion(401, 403, 404, 422),
    200: {"description": "Página que prepara el envío al vendedor y lo hace; solo se detiene si cambió el vendedor", "content": {"text/html": {}}}})
def pagina_ir(request: Request, id: int = Id(), opcion_id: int = Id(), yo: dict = Depends(persona),
              vendedor: str | None = Query(None, description="Vendedor (1 a 60 caracteres: letras, números y . , & ' ( ) + / -)."),
              tarifa: str | None = Query(None, description="Tarifa (mismas reglas que el vendedor)."),
              t: str | None = Query(None, description="Token firmado del enlace (vence en 5 minutos).")):
    """La abre «Ir a…» en otra pestaña. Muestra «Preparando tu enlace…», pide `POST …/ir` con la sesión y envía el
    formulario a Google (o va a Google Flights) sin esperar: qué vuelo elegir ya se vio en el desglose. Única pausa: si
    otro vendedor lleva ahora ese tramo, muestra el aviso y la guía con la nota de la verificación y espera el clic en
    «Ir a {vendedor}». Si falla, lo explica y ofrece Google Flights. Con datos que no son
    válidos responde 422 con una página legible (no JSON): la pestaña la ve una persona."""
    if request.headers.get("sec-fetch-site", "none") not in comun.SITIOS_PERMITIDOS:
        return comun.pagina_aviso(403, *comun.OTRO_SITIO)
    if not all(isinstance(x, str) and NOMBRE_ENLACE.fullmatch(x) for x in (vendedor, tarifa)) or len(t or "") > 64:
        return comun.pagina_aviso(422, *comun.INCOMPLETO)
    vuelo = cotizacion.vuelo_de(id, opcion_id)
    if not acceso.puede_ver(yo, cotizacion.fila_de_acceso(id)) or vuelo is None:
        return comun.pagina_aviso(404, *comun.AJENO)
    if not enlaces.token_ir_valido(t, comun.sesion(request), id, opcion_id, vendedor, tarifa):
        # sin el token de esta sesión (enlace viejo, copiado o enviado por correo): no se hace el pedido ni se gasta nada
        return comun.pagina_aviso(403, "El enlace venció", "Vuelve a abrir el desglose del vuelo y elige la tarifa otra vez.")
    google = cotizacion.fuente_vuelo(cotizacion.solicitud(id), vuelo)
    return comun.pagina_ir(f"{vendedor} · {tarifa}", google, {
        "api": f"{PREFIJO}/cotizaciones/{id}/vuelos/{opcion_id}/ir", "vendedor": vendedor, "tarifa": tarifa,
        "csrf": api_v1.token_csrf(request.cookies.get(acceso.COOKIE)), "google": google})
