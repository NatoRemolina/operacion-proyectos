"""Reglas de forma de la configuración que se escribe a mano.

Las usan el arranque (`app/config.py`, que registra lo que encuentre) y la carga del secreto de producción
(`infra/poblar_secreto.py`, que no sube nada si algo está mal). Un valor mal escrito en una variable opcional no tumba
la plataforma, pero tampoco puede quedar en silencio. Los mensajes nombran la variable y nunca muestran su valor.
"""
import json
from collections.abc import Mapping

VERSION_INVALIDA = "ASESOR_AGENTE_VERSION no es un número entero mayor que cero"
CABECERAS = ("ASESOR_CABECERAS", "MODELO_CABECERAS")
URLS_PUBLICAS = ("ASESOR_API_URL", "URL_PUBLICA", "N8N_WEBHOOK_URL")   # en producción, siempre por HTTPS
MIN_SECRETO_WEBHOOK = 32


def version_valida(texto: str) -> bool:
    return texto.isdigit() and int(texto) >= 1


def _objeto_json(valor) -> bool:
    if isinstance(valor, dict):   # el secreto ya guardado puede traerlo como objeto
        return True
    try:
        return isinstance(json.loads(str(valor)), dict)
    except json.JSONDecodeError:
        return False


def problemas(valores: Mapping, *, produccion: bool = False) -> list[str]:
    """Lo que está mal escrito en `valores`, una frase por variable. Las vacías no se revisan: son opcionales."""
    def v(clave: str) -> str:
        x = valores.get(clave)
        return x.strip() if isinstance(x, str) else ("" if x is None else str(x))

    salida = []
    if v("ASESOR_AGENTE_VERSION") and not version_valida(v("ASESOR_AGENTE_VERSION")):
        salida.append(VERSION_INVALIDA)
    salida += [f"{k} no es un objeto JSON" for k in CABECERAS if v(k) and not _objeto_json(valores.get(k))]
    if produccion:
        salida += [f"{k} no empieza por https://" for k in URLS_PUBLICAS if v(k) and not v(k).startswith("https://")]
        if v("N8N_WEBHOOK_SECRETO") and len(v("N8N_WEBHOOK_SECRETO")) < MIN_SECRETO_WEBHOOK:
            salida.append(f"N8N_WEBHOOK_SECRETO tiene menos de {MIN_SECRETO_WEBHOOK} caracteres")
    return salida
