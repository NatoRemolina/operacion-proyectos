"""Lo que comparten todas las pantallas: plantillas, contexto común, páginas de error y cabeceras.

Un módulo de `app/rutas/` importa de aquí; nunca al revés.
"""
import hashlib
import traceback
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from . import config, db
from .servicios import acceso, telegram, viajes

AQUI = Path(__file__).parent
plantillas = Jinja2Templates(directory=AQUI / "templates")
# La hoja de estilos lleva la huella de su contenido en la dirección: al cambiarla, ningún navegador usa la copia vieja
ESTILO = "/static/estilo.css?v=" + hashlib.sha256((AQUI / "static" / "estilo.css").read_bytes()).hexdigest()[:10]
plantillas.env.globals.update(modo=config.modo, categorias=config.CATEGORIAS, codigo_viaje=viajes.codigo_viaje, estilo=ESTILO)
plantillas.env.filters["dinero"] = lambda v, m="USD": "—" if v is None else f"{v:,.2f} {m}"
plantillas.env.filters["json"] = db.de_json

# Entradas del menú. Cada módulo de rutas declara las suyas en `MENU` y `app/main.py` las reúne aquí.
# Campos: texto, href, orden; opcionales: rol ("admin" o "no_admin"), grupo (submenú), contador ("viajes" o "gastos"), prefijo.
MENU: list[dict] = []


def menu_para(usuario: dict) -> list[dict]:
    admin = acceso.es_admin(usuario)
    visibles = [e for e in MENU if e.get("rol") in (None, "admin" if admin else "no_admin")]
    return sorted(visibles, key=lambda e: e.get("orden", 99))


def _pagina_error(codigo: int, titulo: str, texto: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titulo} · Operación de proyectos</title><link rel="stylesheet" href="{ESTILO}"></head>
<body><main class="pagina-error"><div class="tarjeta"><h1>{titulo}</h1><p class="sub">{texto}</p>
<p><a class="boton" href="/">Volver al inicio</a></p></div></main></body></html>""", status_code=codigo)


NO_ENCONTRADO = _pagina_error(404, "No encontramos esa página", "Puede que el enlace esté incompleto o que no tengas acceso a ese viaje o gasto.")
SOLO_ADMIN = _pagina_error(403, "Esta sección es de administración", "Tu cuenta no tiene permiso para entrar aquí. Si lo necesitas, pídelo a un administrador.")

# Política de contenido: solo recursos propios, más la biblioteca de gráficas. Los soportes traen la suya, más estricta.
CABECERAS_SEGURAS = {
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN", "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(self)",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                               "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-ancestors 'self'; "
                               "form-action 'self'; base-uri 'self'",
}


def _asegurar(respuesta: Response) -> Response:
    for nombre, valor in CABECERAS_SEGURAS.items():
        if nombre not in respuesta.headers:
            respuesta.headers[nombre] = valor
    if not config.LOCAL:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
    if respuesta.headers.get("content-type", "").startswith("application/json") and "Cache-Control" not in respuesta.headers:
        respuesta.headers["Cache-Control"] = "no-store"   # datos de una persona: ni el navegador ni un intermediario los guardan
    return respuesta


def _error_registrado(request: Request, e: Exception) -> Response:
    pid = request.state.peticion
    traza = "".join(traceback.format_exception(e))[-4000:]
    print(f"ERROR peticion={pid} ruta={request.url.path} {type(e).__name__}: {e}\n{traza}", flush=True)
    try:
        u = request.state.usuario
        db.insertar("errores", momento=db.ahora(), peticion=pid, usuario_id=u["id"] if u else None, ruta=request.url.path,
                    tipo=type(e).__name__, mensaje=str(e)[:500], traza=traza)
    except Exception:  # noqa: S110  si la base es la que falla, el registro ya quedó en los logs (línea anterior)
        pass
    if request.url.path.startswith("/api/v1"):
        from .api_v1 import MENSAJE_HTTP, respuesta_error
        return respuesta_error(request, 500, "INTERNAL_ERROR", MENSAJE_HTTP[500])
    if request.url.path.startswith("/api"):
        return JSONResponse({"error": "Error interno", "peticion": pid}, status_code=500, headers={"X-Peticion": pid})
    return HTMLResponse(f"""<!doctype html><meta charset="utf-8"><title>Error</title>
<body style="font-family:system-ui;max-width:520px;margin:80px auto;padding:0 16px">
<h1 style="font-size:20px">Algo falló al procesar la petición</h1>
<p>El error quedó registrado. Si necesitas ayuda, comparte este identificador: <b><code>{pid}</code></b></p>
<p><a href="/">Volver al inicio</a></p></body>""", status_code=500, headers={"X-Peticion": pid})


# ---------- utilidades ----------
def _yo() -> dict:
    return acceso.actual() or {}


def _solicitud_propia(sid: int, para_modificar: bool = False) -> bool:
    """Ver alcanza a quien gestiona el proyecto; modificar, solo a quien la creó, a quien viaja o a administración."""
    fila = db.uno("select usuario_id, viajero_id, proyecto_id from solicitudes where id=:i", i=sid)
    return acceso.es_propio(_yo(), fila) if para_modificar else acceso.puede_ver(_yo(), fila)


def _gasto_propio(gid: int) -> bool:
    return acceso.puede_ver(_yo(), db.uno("select usuario_id, viajero_id, proyecto_id from gastos where id=:i", i=gid))


def _viajes_para_cargar() -> list[dict]:
    """Viajes a los que la persona puede cargar gastos: los suyos; administración, todos los que siguen abiertos."""
    if acceso.es_admin(_yo()):
        return viajes.lista("v.estado in ('aprobado','pendiente_aprobacion')")
    return [v for v in viajes.de_persona(_yo(), ("aprobado", "pendiente_aprobacion"))]


def _pendientes() -> dict:
    """Lo que espera una decisión de administración; se muestra como contador en el menú."""
    if not acceso.es_admin(_yo()):
        return {"viajes": 0, "gastos": 0}
    return db.uno("""select (select count(*) from viajes where estado='pendiente_aprobacion') viajes,
                            (select count(*) from gastos where estado='revision') gastos""")


def _ctx(**extra):
    return {"yo": _yo(), "es_admin": acceso.es_admin(_yo()), "rol_texto": acceso.NOMBRE_ROL.get(_yo().get("rol"), ""),
            "por_atender": _pendientes(), "menu": menu_para(_yo()) if _yo() else [],
            "mis_proyectos": acceso.proyectos_de(_yo()) if _yo().get("rol") == "gestor" else set(),
            "mi_codigo": viajes.codigo_persona(_yo()["id"]) if _yo() else "", "telegram_activo": telegram.activo(),
            "proyectos": db.todos_cache("select * from proyectos order by id"),
            "viajeros": db.todos_cache("select * from viajeros order by id"), **extra}


def _indicadores() -> dict:
    """Cifras del inicio. El previsto es siempre el presupuesto de los viajes; el real, los gastos aprobados."""
    g = db.uno("""select count(*) n,
                  sum(case when estado='aprobado_auto' then 1 else 0 end) auto,
                  sum(case when estado='revision' then 1 else 0 end) revision,
                  sum(case when estado in ('aprobado','aprobado_auto') then total_usd else 0 end) real_usd
                  from gastos""")
    v = db.uno("""select count(*) n, coalesce(sum(case when estado in ('aprobado','cerrado') then presupuesto_usd else 0 end),0) previsto,
                  (select coalesce(sum(g.total_usd),0) from gastos g join viajes x on x.id=g.viaje_id
                   where x.estado in ('aprobado','cerrado') and g.estado in ('aprobado','aprobado_auto')) gastado
                  from viajes where estado<>'rechazado'""")
    ext = db.uno("select count(*) n from eventos where paso='consulta externa'")
    n = g["n"] or 0
    return {"gastos": n, "auto": g["auto"] or 0, "revision": g["revision"] or 0,
            "pct_auto": round(100 * (g["auto"] or 0) / n) if n else 0,
            "real": g["real_usd"] or 0, "viajes": v["n"], "previsto": v["previsto"],
            "ejecucion": round(100 * (v["gastado"] or 0) / v["previsto"]) if v["previsto"] else None, "externas": ext["n"]}
