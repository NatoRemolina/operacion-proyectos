"""Usuarios, permisos, cargos y catálogo de reglas."""
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
        cargos=acceso.cargos(solo_activos=False), cargos_activos=acceso.cargos(),
        miembros={m["usuario_id"]: m["proyectos"] for m in _proyectos_por_gestor()},
        usuarios=db.todos("""select u.id, u.correo, u.nombre, u.rol, u.activo, u.creado, v.nombre viajero, u.telegram_usuario, u.telegram_chat_id,
                             u.cargo_id, c.nombre cargo, (select max(ultima) from sesiones s where s.usuario_id=u.id) ultima
                             from usuarios u left join viajeros v on v.id=u.viajero_id left join cargos c on c.id=u.cargo_id
                             order by u.id""")))


def _proyectos_por_gestor() -> list[dict]:
    salida: dict[int, list[int]] = {}
    for m in db.todos("select usuario_id, proyecto_id from proyecto_miembros order by proyecto_id"):
        salida.setdefault(m["usuario_id"], []).append(m["proyecto_id"])
    return [{"usuario_id": u, "proyectos": p} for u, p in salida.items()]


def _admins_activos(excepto: int = 0) -> int:
    return db.uno("select count(*) n from usuarios where rol='admin' and activo=1 and id<>:i", i=excepto)["n"]


@router.post("/admin/usuarios")
def usuario_crear(correo: str = Form(...), nombre: str = Form(""), rol: str = Form("colaborador"), clave: str = Form(...),
                  viajero_id: int = Form(0), cargo_id: int = Form(0)):
    try:
        uid = acceso.crear_usuario(correo, nombre, rol, clave, viajero_id or None, cargo_id or None)
    except ValueError as e:
        return RedirectResponse(f"/admin/usuarios?aviso={quote(str(e))}", status_code=303)
    cargo = db.uno("select c.nombre from usuarios u join cargos c on c.id=u.cargo_id where u.id=:i", i=uid)
    eventos.registrar("usuario", uid, "cuenta creada", f"{correo.strip().lower()} · {rol} · {cargo['nombre'] if cargo else 'sin cargo'}",
                      _yo()["nombre"])
    return RedirectResponse("/admin/usuarios?aviso=Cuenta+creada.", status_code=303)


@router.post("/admin/usuarios/{uid}")
def usuario_cambiar(uid: int, accion: str = Form(...), rol: str = Form(""), clave: str = Form(""),
                    proyectos_ids: list[int] = Form([]), activo: str = Form(""), cargo_id: int = Form(0)):
    u = db.uno("select * from usuarios where id=:i", i=uid)
    if not u:
        return NO_ENCONTRADO
    aviso = "Hecho."
    if accion == "rol" and rol in acceso.ROLES:
        if u["rol"] == "admin" and rol != "admin" and (uid == _yo()["id"] or not _admins_activos(uid)):
            aviso = "No puedes quitarte tu propio rol ni dejar la plataforma sin administradores."
        else:
            db.actualizar("usuarios", uid, rol=rol)
            if u["rol"] == "gestor" and rol != "gestor":   # deja de gestionar: pierde también sus proyectos
                db.ejecutar("delete from proyecto_miembros where usuario_id=:u", u=uid)
            acceso.cerrar_todas(uid)
            eventos.registrar("usuario", uid, "rol cambiado", f"{u['correo']}: {u['rol']} → {rol}", _yo()["nombre"])
    elif accion == "estado":
        quiere = (0 if u["activo"] else 1) if activo not in ("0", "1") else int(activo)   # el formulario dice el estado deseado
        if quiere == u["activo"]:
            aviso = f"Sin cambios: la cuenta de {u['nombre']} ya estaba {'activa' if quiere else 'desactivada'}."
        elif not quiere and (uid == _yo()["id"] or (u["rol"] == "admin" and not _admins_activos(uid))):
            aviso = "No puedes desactivar tu propia cuenta ni al último administrador."
        else:
            db.actualizar("usuarios", uid, activo=quiere, fallos=0, bloqueado_hasta=None)
            acceso.cerrar_todas(uid)
            eventos.registrar("usuario", uid, "cuenta reactivada" if quiere else "cuenta desactivada", u["correo"], _yo()["nombre"])
            aviso = f"Cuenta de {u['nombre']} {'reactivada' if quiere else 'desactivada'}; sus sesiones abiertas se cerraron."
    elif accion == "cargo":   # el cargo no da permisos: no hace falta cerrar las sesiones
        try:
            acceso.asignar_cargo(uid, cargo_id or None)
            aviso = f"Cargo de {u['nombre']} actualizado."
        except ValueError as e:
            aviso = str(e)
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


# ---------- cargos ----------
@router.post("/admin/cargos")
def cargo_crear(nombre: str = Form("")):
    try:
        acceso.crear_cargo(nombre)
        aviso = f"Cargo «{' '.join(nombre.split())}» creado."
    except ValueError as e:
        aviso = str(e)
    return RedirectResponse(f"/admin/usuarios?aviso={quote(aviso)}#cargos", status_code=303)


@router.post("/admin/cargos/{cid}")
def cargo_cambiar(cid: int, accion: str = Form(...), nombre: str = Form(""), activo: str = Form("")):
    c = db.uno("select * from cargos where id=:i", i=cid)
    if not c:
        return NO_ENCONTRADO
    aviso = "Hecho."
    try:
        if accion == "renombrar":
            acceso.cambiar_cargo(cid, nombre=nombre)
            aviso = "Cargo renombrado."
        elif accion == "estado":
            quiere = (not c["activo"]) if activo not in ("0", "1") else activo == "1"   # el formulario dice el estado deseado
            acceso.cambiar_cargo(cid, activo=quiere)
            aviso = f"Cargo «{c['nombre']}» {'reactivado' if quiere else 'desactivado'}; quien lo tiene lo conserva."
    except ValueError as e:
        aviso = str(e)
    return RedirectResponse(f"/admin/usuarios?aviso={quote(aviso)}#cargos", status_code=303)


# ---------- catálogo de reglas ----------
@router.get("/reglas", response_class=HTMLResponse)
def reglas(request: Request, aviso: str = ""):
    return plantillas.TemplateResponse(request, "reglas.html", _ctx(aviso=aviso[:200],
        reglas=db.todos("select * from reglas order by ambito, entidad, clave"),
        membresias=db.todos("select m.*, v.nombre viajero from membresias m left join viajeros v on v.id=m.viajero_id order by m.id")))


@router.post("/reglas/{rid}")
def regla_guardar(rid: int, valor: str = Form(...)):
    actual = db.uno("select * from reglas where id=:i", i=rid)
    if not actual:
        return NO_ENCONTRADO
    valor = valor.strip()
    if _es_numero(actual["valor"]):
        # Una regla numérica sigue siendo numérica: «1,08» se guarda como 1.08 y «80 USD» se rechaza
        normal = valor.replace(",", ".")
        if not _es_numero(normal) or float(normal) < 0:
            return RedirectResponse(f"/reglas?aviso={quote(f'«{valor[:30]}» no es un número válido para {actual['clave']}. No se guardó.')}#r{rid}", status_code=303)
        valor = normal
    db.actualizar("reglas", rid, valor=valor, verificado=db.ahora()[:10])
    eventos.registrar("regla", rid, "regla editada", f"{actual['clave']}: {actual['valor']} → {valor[:80]}", _yo().get("nombre", "usuario"))
    return RedirectResponse(f"/reglas?aviso={quote('Regla guardada: ' + actual['clave'] + '.')}#r{rid}", status_code=303)


def _es_numero(texto) -> bool:
    try:
        float(str(texto))
        return True
    except ValueError:
        return False
