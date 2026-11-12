"""Configuración leída del entorno. Ninguna clave es obligatoria."""
import json
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

# En la nube la configuración llega en un único secreto; aquí solo se conoce su ARN.
# Se lee una vez por arranque del proceso.
if os.getenv("SECRETO_ARN"):
    import boto3

    _secreto = boto3.client("secretsmanager").get_secret_value(SecretId=os.environ["SECRETO_ARN"])["SecretString"]
    for _k, _v in json.loads(_secreto).items():
        os.environ.setdefault(_k, _v if isinstance(_v, str) else json.dumps(_v))

load_dotenv(RAIZ / ".env")


def _txt(nombre: str) -> str:
    return os.getenv(nombre, "").strip()


SERPAPI_KEY = _txt("SERPAPI_KEY")

MODELO_API_URL = _txt("MODELO_API_URL")
MODELO_API_KEY = _txt("MODELO_API_KEY")
MODELO_NOMBRE = _txt("MODELO_NOMBRE")
# Formato de la API del modelo: "gemini" (generateContent) o "mensajes"
MODELO_FORMATO = _txt("MODELO_FORMATO") or ("gemini" if "generativelanguage" in MODELO_API_URL else "mensajes")
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

# Canal de Telegram: sin estas variables queda apagado y el resto funciona igual
TELEGRAM_BOT_TOKEN = _txt("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRETO = _txt("TELEGRAM_WEBHOOK_SECRETO")
TELEGRAM_BOT_NOMBRE = _txt("TELEGRAM_BOT_NOMBRE").lstrip("@")

# Índice del asistente en Pinecone (opcional). Sin clave y dirección se usa el índice local por palabras
PINECONE_API_KEY = _txt("PINECONE_API_KEY")
PINECONE_INDICE = _txt("PINECONE_INDICE") or "asistente-fichas"
PINECONE_HOST = _txt("PINECONE_HOST").removeprefix("https://").removeprefix("http://").rstrip("/")

# "local" es el equipo de quien desarrolla o evalúa; cualquier otro valor es un despliegue.
ENTORNO = _txt("ENTORNO") or ("nube" if os.getenv("SECRETO_ARN") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") else "local")
LOCAL = ENTORNO == "local"
ES_SQLITE = not DATABASE_URL or DATABASE_URL.startswith("sqlite")

# Falla cerrado: un despliegue sin base, almacenamiento o control de acceso no arranca.
if not LOCAL:
    _faltan = [n for n, v in (("DATABASE_URL", DATABASE_URL and not ES_SQLITE), ("SUPABASE_URL", SUPABASE_URL),
                              ("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY)) if not v]
    if _faltan:
        raise RuntimeError("Configuración incompleta para un despliegue: faltan " + ", ".join(_faltan))

# Topes de una subida
MAX_BYTES_SOPORTE = 4_500_000
MAX_ARCHIVOS_POR_CARGA = 6

DIR_RESPALDO = RAIZ / "datos" / "respaldo"
DIR_EJEMPLOS = RAIZ / "datos" / "ejemplos"
DIR_ARCHIVOS = RAIZ / "datos" / "archivos"
# Fuera de local el disco del contenedor es de solo lectura salvo /tmp
DIR_RESPALDO_ESCRITURA = DIR_RESPALDO if not (os.getenv("SECRETO_ARN") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")) else Path("/tmp/respaldo")  # noqa: S108  único directorio escribible en la función

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


# Razones que una persona puede marcar al decidir un viaje
RAZONES = {"costo_total": "Menor costo total", "horario": "Mejor horario", "directo": "Vuelo directo",
           "flexibilidad": "Permite cambios", "equipaje": "Equipaje del equipo", "fidelizacion": "Millas o estatus",
           "cliente": "Exigencia del cliente o del proyecto", "hotel": "Ubicación del hotel", "otra": "Otra"}


def modo() -> dict:
    """Qué servicios externos están activos; se muestra en pantalla."""
    return {
        "precios": "en vivo" if SERPAPI_KEY else "guardado",
        "extraccion": "en vivo" if (MODELO_API_URL and MODELO_API_KEY and MODELO_NOMBRE) else "guardado",
        "datos": "SQLite local" if ES_SQLITE else "Supabase",
        "archivos": "Supabase" if (SUPABASE_URL and SUPABASE_SERVICE_KEY) else "carpeta local",
    }
