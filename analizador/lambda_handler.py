"""El analizador en AWS: una función Lambda con su propia imagen. La invoca solo la función de la API."""
from . import navegador


def handler(evento, _contexto):
    evento = evento if isinstance(evento, dict) else {}
    return navegador.analizar(evento.get("url"), elegir_regreso=evento.get("elegir_regreso") is not False)
