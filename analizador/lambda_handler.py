"""El analizador en AWS: una función Lambda con su propia imagen. La invoca solo la función de la API."""
from .servidor import atender


def handler(evento, _contexto):
    return atender(evento if isinstance(evento, dict) else {})
