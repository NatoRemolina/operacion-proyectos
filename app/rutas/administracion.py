"""Usuarios, permisos, cargos y catálogo de reglas."""
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db
from ..servicios import acceso, eventos, usuarios, viajes
from ..web import (
    NO_ENCONTRADO,
    _ctx,
    _yo,
    plantillas,
)

router = APIRouter()

MENU = [{"texto": "Usuarios y roles", "href": "/admin/usuarios", "orden": 91, "rol": "admin", "grupo": "Administración"},
        {"texto": "Reglas y supuestos", "href": "/reglas", "orden": 92, "rol": "admin", "grupo": "Administración"}]


# ---------- administración de usuarios: la regla vive en `app/servicios/usuarios.py` ----------
@router.get("/admin/usuarios", response_class=HTMLResponse)
def usuarios_pagina(request: Request, aviso: str = ""):
    return plantillas.TemplateResponse(request, "usuarios.html", _ctx(
        aviso=aviso[:200], roles=acceso.ROLES,
        nombre_rol=acceso.NOMBRE_ROL, codigo=viajes.codigo_persona,
        cargos=acceso.cargos(solo_activos=False), cargos_activos=acceso.cargos(),
        miembros=usuarios.proyectos_por_gestor(), usuarios=usuarios.lista()))


@router.post("/admin/usuarios")
def usuario_crear(correo: str = Form(...), nombre: str = Form(""), rol: str = Form("colaborador"), clave: str = Form(...),
                  viajero_id: int = Form(0), cargo_id: int = Form(0)):
    try:
        usuarios.crear(correo, nombre, rol, clave, viajero_id or None, cargo_id or None, _yo())
    except ValueError as e:
        return RedirectResponse(f"/admin/usuarios?aviso={quote(str(e))}", status_code=303)
    return RedirectResponse("/admin/usuarios?aviso=Cuenta+creada.", status_code=303)


@router.post("/admin/usuarios/{uid}")
def usuario_cambiar(uid: int, accion: str = Form(...), rol: str = Form(""), clave: str = Form(""),
                    proyectos_ids: list[int] = Form([]), activo: str = Form(""), cargo_id: int = Form(0)):
    u = db.uno("select * from usuarios where id=:i", i=uid)
    if not u:
        return NO_ENCONTRADO
    aviso = "Hecho."
    try:
        if accion == "rol" and rol in acceso.ROLES:
            usuarios.cambiar_rol(u, rol, _yo())
        elif accion == "estado":
            quiere = (0 if u["activo"] else 1) if activo not in ("0", "1") else int(activo)   # el formulario dice el estado deseado
            aviso = usuarios.cambiar_estado(u, bool(quiere), _yo())
        elif accion == "cargo":
            aviso = usuarios.cambiar_cargo(u, cargo_id or None)
        elif accion == "proyectos":
            usuarios.asignar_proyectos(u, proyectos_ids, _yo())
        elif accion == "clave":
            usuarios.restablecer_clave(u, clave, _yo())
    except ValueError as e:
        aviso = str(e)
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
