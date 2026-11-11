"""Configuración leída del entorno. Ninguna clave es obligatoria."""
import json
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _txt(nombre: str) -> str:
    return os.getenv(nombre, "").strip()


SERPAPI_KEY = _txt("SERPAPI_KEY")

MODELO_API_URL = _txt("MODELO_API_URL")
MODELO_API_KEY = _txt("MODELO_API_KEY")
MODELO_NOMBRE = _txt("MODELO_NOMBRE")
try:
    MODELO_CABECERAS = json.loads(_txt("MODELO_CABECERAS") or "{}")
except json.JSONDecodeError:
    MODELO_CABECERAS = {}

DATABASE_URL = _txt("DATABASE_URL")
# La cadena puede traer el marcador [YOUR-PASSWORD] tal como la entrega el proveedor;
# la contraseña va aparte y aquí se codifica para que los símbolos no rompan la conexión.
if "[YOUR-PASSWORD]" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("[YOUR-PASSWORD]", quote(_txt("DATABASE_PASSWORD"), safe=""))
SUPABASE_URL = _txt("SUPABASE_URL").rstrip("/")
SUPABASE_SERVICE_KEY = _txt("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = _txt("SUPABASE_BUCKET") or "soportes"

APP_CLAVE = _txt("APP_CLAVE")

DIR_RESPALDO = RAIZ / "datos" / "respaldo"
DIR_EJEMPLOS = RAIZ / "datos" / "ejemplos"
DIR_ARCHIVOS = RAIZ / "datos" / "archivos"

# Umbral de confianza para aprobar un gasto sin revisión humana
UMBRAL_CONFIANZA = 0.85

CATEGORIAS = {
    "vuelo": "Vuelo",
    "hotel": "Hotel",
    "alquiler_carro": "Alquiler de carro",
    "combustible": "Combustible",
    "comida": "Comida",
    "parqueo_peajes": "Parqueo y peajes",
    "otros": "Otros",
}


def modo() -> dict:
    """Qué servicios externos están activos; se muestra en pantalla."""
    return {
        "precios": "en vivo" if SERPAPI_KEY else "guardado",
        "extraccion": "en vivo" if (MODELO_API_URL and MODELO_API_KEY and MODELO_NOMBRE) else "guardado",
        "datos": "Supabase" if DATABASE_URL else "SQLite local",
        "archivos": "Supabase" if (SUPABASE_URL and SUPABASE_SERVICE_KEY) else "carpeta local",
    }
