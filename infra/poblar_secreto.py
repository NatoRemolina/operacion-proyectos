"""Carga la configuración sensible en el secreto de producción (pila OperacionBase).

Uso, desde la raíz del repositorio:

    python infra/poblar_secreto.py --env .env.produccion --ensayo      # qué claves subiría: sin valores y sin AWS
    AWS_PROFILE=operacion python infra/poblar_secreto.py --env .env.produccion

- El archivo de origen es obligatorio: nunca se lee `.env` por omisión, que en desarrollo apunta a la base de pruebas.
- El destino es siempre producción, así que se detiene si la base o el almacenamiento son el proyecto de pruebas de
  Supabase, venga del archivo o de lo que ya tenía el secreto. Cuál es ese proyecto lo dice el archivo local
  `.env.supabase-pruebas` (de esta carpeta o de la principal); de él solo se toma el identificador, y sin él no sigue.
- Fusiona: lee el secreto actual, reemplaza las claves que el archivo trae con valor y conserva las demás (una clave
  puesta a mano no se pierde). Retira APP_CLAVE, que nadie lee.
- Nunca imprime valores, solo nombres de claves. La función lee el secreto al arrancar: el cambio entra en las
  instancias que arranquen después (las encendidas siguen con el valor anterior hasta apagarse, o hasta que se
  despliegue una versión nueva de la función).
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:   # al correrlo como `python infra/poblar_secreto.py`
    sys.path.insert(0, str(RAIZ))
from datos.importar_entorno import _proyectos as proyectos_de  # noqa: E402
from datos.importar_entorno import _raiz_principal  # noqa: E402

PILA = "OperacionBase"
REGION = "us-east-1"
# Describen el proyecto de pruebas de Supabase, que nunca es producción. Están fuera de git: el identificador no se versiona
ARCHIVOS_PRUEBAS = [carpeta / ".env.supabase-pruebas" for carpeta in dict.fromkeys((RAIZ, _raiz_principal()))]
RETIRADAS = ("APP_CLAVE",)
# Lo que la función lee del secreto (app/config.py y los servicios), aparte de DATABASE_URL, que se arma abajo.
# tests/test_poblar_secreto.py comprueba que toda variable que lee la aplicación esté aquí o tenga su razón para no estar.
CLAVES = [
    "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_BUCKET",
    "SERPAPI_KEY",
    "MODELO_API_URL", "MODELO_API_KEY", "MODELO_NOMBRE", "MODELO_FORMATO", "MODELO_CABECERAS",
    "ASESOR_API_URL", "ASESOR_API_KEY", "ASESOR_AGENTE_ID", "ASESOR_ENTORNO_ID", "ASESOR_AGENTE_VERSION", "ASESOR_CABECERAS",
    "PINECONE_API_KEY", "PINECONE_INDICE", "PINECONE_HOST",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRETO", "TELEGRAM_BOT_NOMBRE",
    "ORIGENES_WEB",
    "PROVEEDOR_LUGARES",
]
OBLIGATORIAS = ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")   # sin ellas la función no arranca (app/config.py)
# Tienen que venir en el archivo: el webhook (paso 6 de docs/despliegue.md) se registra con ese mismo archivo, y si
# faltaran, app/config.py las completaría con las del .env de desarrollo. `--sin-telegram` lo salta a propósito.
TELEGRAM = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRETO")


def comprobar_telegram(valores: dict, archivo: str, sin_telegram: bool):
    if sin_telegram:
        return
    faltan = [k for k in TELEGRAM if not valores.get(k)]
    if faltan:
        sys.exit(f"Faltan {', '.join(faltan)} en {archivo}: el webhook de Telegram quedaría con otras claves. "
                 "Agrégalas, o usa --sin-telegram si Telegram no se publica ahora. No se cambió nada.")


def leer(archivo: str) -> dict:
    """Valores del archivo de origen, listos para el secreto. Las claves vacías no se suben."""
    if not Path(archivo).is_file():
        sys.exit(f"No existe el archivo de origen {archivo}.")
    env = {k: (v or "").strip() for k, v in dotenv_values(archivo).items()}
    base = env.get("DATABASE_URL", "").replace("[YOUR-PASSWORD]", quote(env.get("DATABASE_PASSWORD", ""), safe=""))
    if not base.startswith("postgres"):
        sys.exit(f"{archivo}: falta DATABASE_URL de PostgreSQL.")
    # En funciones sin servidor se usa el agrupador en modo transacción (puerto 6543), no el de sesión (5432)
    valores = {"DATABASE_URL": base.replace(":5432/", ":6543/")}
    valores.update({k: env[k] for k in CLAVES if env.get(k)})
    return valores


def proyectos_de_pruebas() -> set[str]:
    """Los identificadores del proyecto de pruebas, sacados de su archivo local. No se imprime nada de él."""
    for archivo in ARCHIVOS_PRUEBAS:
        if Path(archivo).is_file():
            v = dotenv_values(archivo)
            proyectos = proyectos_de(v.get("DATABASE_URL") or "") | proyectos_de(v.get("SUPABASE_URL") or "")
            if proyectos:
                return proyectos
    sys.exit("No se encontró .env.supabase-pruebas (en esta carpeta ni en la principal): sin él no se puede comprobar que "
             "el destino no sea el proyecto de pruebas. No se cambió nada.")


def comprobar(valores: dict, donde: str, pruebas: set[str]):
    """El destino es producción: ni la base ni el almacenamiento pueden ser el proyecto de pruebas."""
    for clave in ("DATABASE_URL", "SUPABASE_URL"):
        if proyectos_de(valores.get(clave, "")) & pruebas:
            sys.exit(f"{clave} de {donde} es el proyecto de pruebas de Supabase: no se sube a producción. No se cambió nada.")


def _arn(sesion) -> str:
    salidas = sesion.client("cloudformation", region_name=REGION).describe_stacks(StackName=PILA)["Stacks"][0]["Outputs"]
    return next(s["OutputValue"] for s in salidas if s["OutputKey"] == "SecretoArn")


def _actual(cliente, arn: str) -> dict:
    from botocore.exceptions import ClientError
    try:
        texto = cliente.get_secret_value(SecretId=arn)["SecretString"]
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":   # creado por CDK, aún sin valor
            return {}
        raise
    try:
        actual = json.loads(texto)
    except json.JSONDecodeError:   # la contraseña aleatoria que CDK pone al crear el secreto: aún no es configuración
        return {}
    return actual if isinstance(actual, dict) else {}


def main(argv: list[str] | None = None, sesion=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--env", required=True, help="archivo con la configuración de producción (por ejemplo .env.produccion)")
    a.add_argument("--ensayo", action="store_true", help="solo muestra qué claves subiría, sin valores y sin contactar AWS")
    a.add_argument("--sin-telegram", action="store_true",
                   help="Telegram no se publica ahora: no exige sus claves y no toca las que ya tenga el secreto")
    x = a.parse_args(argv)

    valores = leer(x.env)
    pruebas = proyectos_de_pruebas()
    comprobar(valores, x.env, pruebas)
    comprobar_telegram(valores, x.env, x.sin_telegram)
    if x.ensayo:
        print(f"Ensayo: subiría {len(valores)} claves desde {x.env}: {', '.join(sorted(valores))}.")
        faltan = [k for k in OBLIGATORIAS if k not in valores]
        if faltan:
            print(f"No están en el archivo (tendrían que estar ya en el secreto): {', '.join(faltan)}.")
        if x.sin_telegram:
            print("Telegram no se publica: se salta el paso 6; las claves de Telegram que ya tenga el secreto se conservan.")
        else:
            print(f"Telegram: {' y '.join(TELEGRAM)} vienen en el archivo; el paso 6 registra el webhook con ese mismo archivo.")
        print("Las demás claves del secreto se conservan; " + ", ".join(RETIRADAS) + " se retira si está. No se contactó AWS.")
        return 0

    if sesion is None:
        import boto3
        sesion = boto3.Session(region_name=REGION)
    arn = _arn(sesion)
    cliente = sesion.client("secretsmanager", region_name=REGION)
    antes = _actual(cliente, arn)
    final = {k: v for k, v in {**antes, **valores}.items() if k not in RETIRADAS}
    comprobar(final, f"el secreto de {PILA}", pruebas)
    faltan = [k for k in OBLIGATORIAS if not final.get(k)]
    if faltan:
        sys.exit(f"Faltan {', '.join(faltan)}: la función no arrancaría. No se cambió nada.")
    cliente.put_secret_value(SecretId=arn, SecretString=json.dumps(final))

    conservadas = sorted(set(antes) - set(valores) - set(RETIRADAS))
    retiradas = sorted(set(antes) & set(RETIRADAS))
    print(f"Secreto de {PILA} actualizado. Del archivo: {', '.join(sorted(valores))}.")
    if conservadas:
        print(f"Conservadas del secreto: {', '.join(conservadas)}.")
    if retiradas:
        print(f"Retiradas: {', '.join(retiradas)}.")
    print("La función lo lee al arrancar: entra en las instancias nuevas (tras desplegar una versión nueva, o al apagarse las encendidas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
