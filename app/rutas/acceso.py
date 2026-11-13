"""Ingreso, inicio según el rol y la cuenta de cada persona."""
import os
from urllib.parse import quote, quote_plus

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import config, db
from ..servicios import acceso, eventos, telegram, usuarios, viajes
from ..web import (
    _ctx,
    _indicadores,
    _yo,
    plantillas,
)

router = APIRouter()

MENU = [{"texto": "Inicio", "href": "/", "orden": 10}]


@router.get("/salud")
def salud():
    return {"estado": "ok"}


@router.get("/entrar", response_class=HTMLResponse)
def entrar(request: Request, error: str = "", siguiente: str = ""):
    if request.state.usuario:
        return RedirectResponse(_destino_seguro(siguiente), status_code=303)
    return plantillas.TemplateResponse(request, "entrar.html", {"error": error[:120], "siguiente": _destino_seguro(siguiente),
                                                                "demo": config.LOCAL and (config.ES_SQLITE or os.getenv("CUENTAS_DEMO") == "1")})


def _destino_seguro(siguiente: str) -> str:
    """Solo rutas de esta misma plataforma: nada de «//otro-sitio» ni direcciones completas."""
    s = (siguiente or "").strip()
    return s if s.startswith("/") and not s.startswith("//") and not s.startswith("/entrar") and "\\" not in s else "/"


@router.post("/entrar")
def entrar_enviar(correo: str = Form(""), clave: str = Form(""), siguiente: str = Form("")):
    usuario, mensaje = acceso.autenticar(correo, clave)
    destino = _destino_seguro(siguiente)
    if not usuario:
        eventos.registrar("acceso", None, "ingreso fallido", correo.strip().lower()[:80], "formulario")
        return RedirectResponse(f"/entrar?error={quote(mensaje)}" + (f"&siguiente={quote(destino)}" if destino != "/" else ""), status_code=303)
    acceso.fijar(usuario)
    eventos.registrar("acceso", usuario["id"], "ingreso", usuario["correo"], "formulario")
    return acceso.abrir_sesion(RedirectResponse(destino, status_code=303), usuario["id"])


@router.post("/salir")
def salir(request: Request):
    return acceso.cerrar_sesion(RedirectResponse("/entrar", status_code=303), request.cookies.get(acceso.COOKIE))


# ---------- inicio ----------
@router.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    yo, admin = _yo(), acceso.es_admin(_yo())
    donde, p = acceso.alcance(yo, "s")
    donde_g, pg = acceso.alcance(yo, "g")
    donde_v, pv = acceso.alcance(yo, "v")
    return plantillas.TemplateResponse(request, "inicio.html", _ctx(
        ind=_indicadores() if admin else None,
        en_curso=viajes.lista("v.estado='aprobado'")[:6] if admin else [],
        activo=None if admin else viajes.resolver_para_gasto(yo)[0],
        mis_viajes=[] if admin else viajes.lista(donde_v, **pv)[:6],
        solicitudes=db.todos(f"""select s.*, p.nombre proyecto, vj.nombre viajero, v.id viaje_id, v.creado viaje_creado
                                from solicitudes s left join proyectos p on p.id=s.proyecto_id
                                left join viajeros vj on vj.id=s.viajero_id left join viajes v on v.solicitud_id=s.id
                                where {donde} order by s.id desc limit 10""", **p),
        mis_gastos=[] if admin else db.todos(f"""select g.id, g.comercio, g.fecha, g.total, g.moneda, g.estado from gastos g
                                                where {donde_g} order by g.id desc limit 6""", **pg)))


# ---------- el viaje: historial de la persona, aprobación y seguimiento ----------
@router.get("/mi-cuenta", response_class=HTMLResponse)
def mi_cuenta(request: Request, aviso: str = ""):
    return _mi_cuenta(request, aviso)


def _mi_cuenta(request: Request, aviso: str = "", vinculo: dict | None = None):
    yo = _yo()
    donde_s, ps = acceso.alcance(yo, "s")
    donde_v, pv = acceso.alcance(yo, "v")
    donde_g, pg = acceso.alcance(yo, "g")
    mis_viajes = viajes.lista(donde_v, **pv)
    return plantillas.TemplateResponse(request, "mi_cuenta.html", _ctx(
        aviso=aviso[:200], vinculo=vinculo, mis_viajes=mis_viajes, activo_hoy=viajes.resolver_para_gasto(yo)[0],
        cotizaciones=db.todos(f"""select s.*, p.nombre proyecto, vj.nombre viajero, v.id viaje_id, v.estado estado_viaje, v.creado viaje_creado
                                  from solicitudes s left join proyectos p on p.id=s.proyecto_id
                                  left join viajeros vj on vj.id=s.viajero_id left join viajes v on v.solicitud_id=s.id
                                  where {donde_s} order by s.id desc limit 50""", **ps),
        sin_viaje=db.todos(f"""select g.id, g.comercio, g.fecha, g.total, g.moneda, g.estado from gastos g
                               where {donde_g} and g.viaje_id is null order by g.id desc limit 20""", **pg),
        codigo_viaje=viajes.codigo_viaje, estados=viajes.ESTADOS))


@router.post("/mi-cuenta/telegram")
def mi_cuenta_telegram(request: Request, accion: str = Form("vincular")):
    if accion == "desvincular":
        usuarios.desvincular_telegram(_yo())
        return RedirectResponse("/mi-cuenta?aviso=Chat+desvinculado.", status_code=303)
    if not telegram.activo():
        return RedirectResponse("/mi-cuenta?aviso=El+canal+de+Telegram+no+est%C3%A1+configurado.", status_code=303)
    return _mi_cuenta(request, vinculo=telegram.nuevo_vinculo(_yo()["id"]))


@router.post("/mi-cuenta/clave")
def mi_cuenta_clave(request: Request, actual: str = Form(""), nueva: str = Form("")):
    """Exige la contraseña actual. Al cambiarla se cierran las demás sesiones y esta se renueva."""
    yo = _yo()
    try:
        usuarios.cambiar_mi_clave(yo, actual, nueva)
    except (usuarios.DatosInvalidos, usuarios.DemasiadosIntentos) as e:
        return RedirectResponse(f"/mi-cuenta?aviso={quote_plus(str(e))}", status_code=303)
    return acceso.abrir_sesion(RedirectResponse("/mi-cuenta?aviso=Contrase%C3%B1a+cambiada.+Se+cerraron+tus+otras+sesiones.", status_code=303), yo["id"])
