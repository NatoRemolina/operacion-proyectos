"""Usuarios, roles y catálogo de reglas."""
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db
from ..servicios import acceso, eventos, viajes
from ..web import (
    NO_ENCONTRADO,
    _ctx,
    _yo,
    plantillas,
)

router = APIRouter()

MENU = [{"texto": "Usuarios y roles", "href": "/admin/usuarios", "orden": 91, "rol": "admin", "grupo": "Administración"},
        {"texto": "Reglas y supuestos", "href": "/reglas", "orden": 92, "rol": "admin", "grupo": "Administración"}]


# ---------- administración de usuarios ----------
@router.get("/admin/usuarios", response_class=HTMLResponse)
def usuarios_pagina(request: Request, aviso: str = ""):
    return plantillas.TemplateResponse(request, "usuarios.html", _ctx(
        aviso=aviso[:200], roles=acceso.ROLES,
        nombre_rol=acceso.NOMBRE_ROL, codigo=viajes.codigo_persona,
        miembros={m["usuario_id"]: m["proyectos"] for m in _proyectos_por_gestor()},
        usuarios=db.todos("""select u.id, u.correo, u.nombre, u.rol, u.activo, u.creado, v.nombre viajero, u.telegram_usuario, u.telegram_chat_id,
                             (select max(ultima) from sesiones s where s.usuario_id=u.id) ultima
                             from usuarios u left join viajeros v on v.id=u.viajero_id order by u.id""")))


def _proyectos_por_gestor() -> list[dict]:
    salida: dict[int, list[int]] = {}
    for m in db.todos("select usuario_id, proyecto_id from proyecto_miembros order by proyecto_id"):
        salida.setdefault(m["usuario_id"], []).append(m["proyecto_id"])
    return [{"usuario_id": u, "proyectos": p} for u, p in salida.items()]


def _admins_activos(excepto: int = 0) -> int:
    return db.uno("select count(*) n from usuarios where rol='admin' and activo=1 and id<>:i", i=excepto)["n"]


@router.post("/admin/usuarios")
def usuario_crear(correo: str = Form(...), nombre: str = Form(""), rol: str = Form("piloto"), clave: str = Form(...),
                  viajero_id: int = Form(0)):
    try:
        uid = acceso.crear_usuario(correo, nombre, rol, clave, viajero_id or None)
    except ValueError as e:
        return RedirectResponse(f"/admin/usuarios?aviso={quote(str(e))}", status_code=303)
    eventos.registrar("usuario", uid, "cuenta creada", f"{correo.strip().lower()} · {rol}", _yo()["nombre"])
    return RedirectResponse("/admin/usuarios?aviso=Cuenta+creada.", status_code=303)


@router.post("/admin/usuarios/{uid}")
def usuario_cambiar(uid: int, accion: str = Form(...), rol: str = Form(""), clave: str = Form(""),
                    proyectos_ids: list[int] = Form([])):
    u = db.uno("select * from usuarios where id=:i", i=uid)
    if not u:
        return NO_ENCONTRADO
    aviso = "Hecho."
    if accion == "rol" and rol in acceso.ROLES:
        if u["rol"] == "admin" and rol != "admin" and (uid == _yo()["id"] or not _admins_activos(uid)):
            aviso = "No puedes quitarte tu propio rol ni dejar la plataforma sin administradores."
        else:
            db.actualizar("usuarios", uid, rol=rol)
            acceso.cerrar_todas(uid)
            eventos.registrar("usuario", uid, "rol cambiado", f"{u['correo']}: {u['rol']} → {rol}", _yo()["nombre"])
    elif accion == "estado":
        if u["activo"] and (uid == _yo()["id"] or (u["rol"] == "admin" and not _admins_activos(uid))):
            aviso = "No puedes desactivar tu propia cuenta ni al último administrador."
        else:
            db.actualizar("usuarios", uid, activo=0 if u["activo"] else 1, fallos=0, bloqueado_hasta=None)
            acceso.cerrar_todas(uid)
            eventos.registrar("usuario", uid, "cuenta desactivada" if u["activo"] else "cuenta reactivada", u["correo"], _yo()["nombre"])
    elif accion == "proyectos":
        validos = {p["id"] for p in db.todos("select id from proyectos")}
        db.ejecutar("delete from proyecto_miembros where usuario_id=:u", u=uid)
        db.insertar_varios("proyecto_miembros", [{"usuario_id": uid, "proyecto_id": p, "papel": "gestor", "creado": db.ahora()}
                                                 for p in sorted(set(proyectos_ids) & validos)])
        eventos.registrar("usuario", uid, "proyectos asignados", f"{u['correo']}: {sorted(set(proyectos_ids) & validos)}", _yo()["nombre"])
    elif accion == "clave":
        if len(clave) < 10:
            aviso = "La contraseña debe tener al menos 10 caracteres."
        else:
            db.actualizar("usuarios", uid, clave_hash=acceso.hash_clave(clave), fallos=0, bloqueado_hasta=None)
            acceso.cerrar_todas(uid)
            eventos.registrar("usuario", uid, "contraseña restablecida", u["correo"], _yo()["nombre"])
    return RedirectResponse(f"/admin/usuarios?aviso={quote(aviso)}", status_code=303)


# ---------- catálogo de reglas ----------
@router.get("/reglas", response_class=HTMLResponse)
def reglas(request: Request):
    return plantillas.TemplateResponse(request, "reglas.html", _ctx(
        reglas=db.todos("select * from reglas order by ambito, entidad, clave"),
        membresias=db.todos("select m.*, v.nombre viajero from membresias m left join viajeros v on v.id=m.viajero_id order by m.id")))


@router.post("/reglas/{rid}")
def regla_guardar(rid: int, valor: str = Form(...)):
    db.actualizar("reglas", rid, valor=valor.strip(), verificado=db.ahora()[:10])
    eventos.registrar("regla", rid, "regla editada", f"nuevo valor: {valor.strip()[:80]}", _yo().get("nombre", "usuario"))
    return RedirectResponse("/reglas", status_code=303)
