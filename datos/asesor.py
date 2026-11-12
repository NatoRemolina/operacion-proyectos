"""Herramientas de mantenimiento del asesor del asistente (agente alojado en el servicio de agentes).

Uso:  python -m datos.asesor --esquemas            imprime las herramientas en JSON, tal como van en la consola
      python -m datos.asesor --sistema             imprime el mensaje de sistema
      python -m datos.asesor --verificar           compara el agente de la consola con el código (solo lectura)
      python -m datos.asesor --sincronizar         sube al agente el mensaje de sistema y las herramientas del código
      python -m datos.asesor --probar "pregunta"   abre una sesión real y muestra cada paso (no escribe en la base)

Necesita ASESOR_API_URL, ASESOR_API_KEY, ASESOR_AGENTE_ID, ASESOR_ENTORNO_ID y ASESOR_CABECERAS en .env.
"""
import argparse
import json
import sys
import time

from app import config, db
from app.servicios import asesor, asistente


def _normal(esquema) -> str:
    """Forma comparable de un esquema: sin listas de obligatorios vacías y con las claves ordenadas."""
    def limpiar(x):
        if isinstance(x, dict):
            return {k: limpiar(v) for k, v in x.items() if not (k == "required" and v == [])}
        if isinstance(x, list):
            return [limpiar(v) for v in x]
        return x
    return json.dumps(limpiar(esquema), sort_keys=True, ensure_ascii=False)


def diferencias(agente: dict) -> list[str]:
    """Qué separa al agente guardado en el servicio del código. Vacío = coinciden."""
    salida = []
    if (agente.get("system") or "").strip() != asesor.SISTEMA.strip():
        salida.append("El mensaje de sistema del agente no es el del código.")
    propias = {e["name"]: e for e in asesor.ESQUEMAS}
    remotas = {}
    for t in agente.get("tools") or []:
        if t.get("type") == "custom":
            remotas[t.get("name")] = t
        else:
            salida.append(f"El agente tiene herramientas del servicio ({t.get('type')}): quítalas, el asesor solo usa las suyas.")
    for nombre in sorted(set(propias) - set(remotas)):
        salida.append(f"Falta la herramienta {nombre}.")
    for nombre in sorted(set(remotas) - set(propias)):
        salida.append(f"Sobra la herramienta {nombre}: la plataforma no la atiende.")
    for nombre in sorted(set(propias) & set(remotas)):
        if (remotas[nombre].get("description") or "").strip() != propias[nombre]["description"].strip():
            salida.append(f"La descripción de {nombre} no es la del código.")
        if _normal(remotas[nombre].get("input_schema")) != _normal(propias[nombre]["input_schema"]):
            salida.append(f"Los parámetros de {nombre} no son los del código.")
    if agente.get("mcp_servers"):
        salida.append("El agente tiene servidores MCP: el asesor no los usa.")
    return salida


def _leer(cli, ruta: str) -> dict:
    return asesor._peticion(cli, "GET", ruta, time.monotonic() + 30)


def verificar() -> int:
    with asesor._cliente() as cli:
        agente = _leer(cli, f"/v1/agents/{config.ASESOR_AGENTE_ID}")
        entorno = _leer(cli, f"/v1/environments/{config.ASESOR_ENTORNO_ID}")
    modelo = agente.get("model")
    print(f"Agente {agente.get('id')} · versión {agente.get('version')} · modelo {json.dumps(modelo, ensure_ascii=False)}")
    red = ((entorno.get("config") or {}).get("networking") or {})
    print(f"Entorno {entorno.get('id')} · red {json.dumps(red, ensure_ascii=False)}")
    problemas = diferencias(agente)
    for p in problemas:
        print(f"  ✗ {p}")
    if problemas:
        print("Para dejar el agente igual al código: python -m datos.asesor --sincronizar")
        return 1
    print("  ✓ El agente coincide con el código: mensaje de sistema y 12 herramientas.")
    return 0


def sincronizar() -> int:
    with asesor._cliente() as cli:
        actual = _leer(cli, f"/v1/agents/{config.ASESOR_AGENTE_ID}")
        cuerpo = {"version": actual.get("version"), "system": asesor.SISTEMA, "tools": asesor.ESQUEMAS, "mcp_servers": []}
        nuevo = asesor._peticion(cli, "POST", f"/v1/agents/{config.ASESOR_AGENTE_ID}", time.monotonic() + 30, cuerpo,
                                   reintentar_red=False)
    print(f"Agente actualizado: versión {actual.get('version')} → {nuevo.get('version')}.")
    problemas = diferencias(nuevo)
    for p in problemas:
        print(f"  ✗ {p}")
    return 1 if problemas else 0


def probar(pregunta: str) -> int:
    admin = db.uno("select * from usuarios where rol='admin' and activo order by id limit 1")
    if not admin:
        print("No hay ninguna cuenta de administración en la base configurada.")
        return 1
    r = asistente.Rastro()
    inicio = time.monotonic()
    try:
        texto = asesor.preguntar(pregunta, r, admin)
    except asesor.ErrorAsesor as e:
        print(f"El asesor no respondió: {e} (tras {e.segundos:.1f} s)")
        texto = None
    print(f"Sesión: {r.sesion.get('id', '—')} (se puede abrir en la consola del servicio)")
    print(f"Eventos: {' → '.join(r.sesion.get('tipos', [])) or '—'}")
    print(f"Herramientas: {', '.join(r.pasos) or 'ninguna'}")
    costo = f" · {r.sesion['centavos_usd'] / 100:.2f} USD a precio de lista" if "centavos_usd" in r.sesion else ""
    print(f"Tokens: {r.sesion.get('entrada', 0)} de entrada · {r.sesion.get('salida', 0)} de salida · "
          f"{time.monotonic() - inicio:.1f} s{costo}")
    print(f"Fuentes: {', '.join(f['codigo'] for f in r.fuentes.values()) or 'ninguna'}")
    if texto is not None:
        print(f"\n{texto}")
    return 0 if texto is not None else 1


def main(argv: list[str] | None = None) -> int:
    opciones = argparse.ArgumentParser(description="Asesor del asistente")
    grupo = opciones.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--esquemas", action="store_true", help="imprime las herramientas en JSON")
    grupo.add_argument("--sistema", action="store_true", help="imprime el mensaje de sistema")
    grupo.add_argument("--verificar", action="store_true", help="compara el agente del servicio con el código")
    grupo.add_argument("--sincronizar", action="store_true", help="sube el mensaje de sistema y las herramientas al agente")
    grupo.add_argument("--probar", metavar="PREGUNTA", help="abre una sesión real con esa pregunta y muestra cada paso")
    a = opciones.parse_args(argv)
    if a.esquemas:
        print(json.dumps(asesor.ESQUEMAS, ensure_ascii=False, indent=2))
        return 0
    if a.sistema:
        print(asesor.SISTEMA)
        return 0
    if not asesor.activo():
        print("Falta configurar el asesor: ASESOR_API_URL, ASESOR_API_KEY, ASESOR_AGENTE_ID, ASESOR_ENTORNO_ID y ASESOR_CABECERAS.")
        return 1
    try:
        if a.verificar:
            return verificar()
        if a.sincronizar:
            return sincronizar()
        return probar(a.probar)
    except asesor.ErrorAsesor as e:
        print(f"El servicio no respondió como se esperaba: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
