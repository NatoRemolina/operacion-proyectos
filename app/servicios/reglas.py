"""Catálogo de reglas y supuestos: lo que ningún buscador entrega (equipaje, programas de hotel, metas, cuentas
contables...). Cada regla tiene fuente, confianza y fecha de verificación, y se edita sin tocar el código.

La misma lógica para la pantalla de administración (`/reglas`) y la API v1 (`/api/v1/reglas`):
- una regla numérica sigue siendo numérica: «1,08» se guarda como 1.08; «80 USD», un negativo o un no finito se rechazan;
- cada edición deja el evento «regla editada» con el valor anterior y el nuevo.
"""
import math

from .. import db
from . import eventos

PREFIJO_CUENTA = "cuenta_contable_"   # el mismo de `contable.PREFIJO_CUENTA`: son supuestos con su propio grupo
# Orden y nombre de los grupos; un ámbito que no esté aquí va al final con su propio nombre
GRUPOS = {"aerolinea": "Aerolíneas", "hotel": "Programas de hotel", "bateria": "Baterías", "supuesto": "Supuestos",
          "kpi": "Metas de los KPI", "cuenta_contable": "Cuentas contables"}


class ReglaInvalida(ValueError):
    """El valor no sirve para esa regla. El texto se le muestra a quien edita."""


def es_numero(texto) -> bool:
    try:
        return math.isfinite(float(str(texto)))
    except ValueError:
        return False


def _con_tipo(regla: dict) -> dict:
    return {**regla, "numerica": es_numero(regla["valor"])}


def grupo_de(regla: dict) -> str:
    if regla["ambito"] == "supuesto" and (regla["clave"] or "").startswith(PREFIJO_CUENTA):
        return "cuenta_contable"
    return regla["ambito"] or "otros"


def todas() -> list[dict]:
    """Todas las reglas, por ámbito, a quién aplican y clave, y si son numéricas."""
    return [_con_tipo(r) for r in db.todos("select * from reglas order by ambito, entidad, clave")]


def catalogo() -> list[dict]:
    """Las reglas agrupadas por ámbito, en el orden de `GRUPOS`: [{clave, titulo, reglas}]."""
    grupos: dict[str, list[dict]] = {}
    for r in todas():
        grupos.setdefault(grupo_de(r), []).append(r)
    orden = [g for g in GRUPOS if g in grupos] + sorted(g for g in grupos if g not in GRUPOS)
    return [{"clave": g, "titulo": GRUPOS.get(g, g.replace("_", " ").capitalize()), "reglas": grupos[g]} for g in orden]


def membresias() -> list[dict]:
    """Membresías de fidelización (de la persona o de la empresa), en solo lectura. `ejemplo`: inventada para la demostración."""
    filas = db.todos("select m.*, v.nombre viajero from membresias m left join viajeros v on v.id=m.viajero_id order by m.id")
    return [{**m, "titular": m["viajero"] or "Empresa", "de_empresa": m["viajero_id"] is None, "ejemplo": bool(m.get("ejemplo"))}
            for m in filas]


def editar(rid: int, valor: str, quien: str) -> dict:
    """Guarda el valor nuevo y devuelve la regla. Lanza LookupError (no existe) o ReglaInvalida."""
    actual = db.uno("select * from reglas where id=:i", i=rid)
    if not actual:
        raise LookupError("No existe esa regla.")
    valor = (valor or "").strip()
    if es_numero(actual["valor"]):
        normal = valor.replace(",", ".")
        if not es_numero(normal) or float(normal) < 0:
            raise ReglaInvalida(f"«{valor[:30]}» no es un número válido para {actual['clave']}. No se guardó.")
        valor = normal
    db.actualizar("reglas", rid, valor=valor, verificado=db.ahora()[:10])
    eventos.registrar("regla", rid, "regla editada", f"{actual['clave']}: {actual['valor']} → {valor[:80]}", quien)
    return _con_tipo(db.uno("select * from reglas where id=:i", i=rid))
