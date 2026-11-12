"""Carga la configuración sensible en el secreto de la nube, desde `.env`.

Uso (desde la raíz del repositorio):  AWS_PROFILE=operacion python infra/poblar_secreto.py

Lee `.env`, arma un JSON, lo sube desde un archivo temporal y lo borra: la clave nunca queda
en el historial de la terminal ni se imprime. Si falta la contraseña de acceso, genera una
y la guarda en `.env`.
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
CLAVES = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_BUCKET", "SERPAPI_KEY", "MODELO_API_URL",
          "MODELO_API_KEY", "MODELO_NOMBRE", "MODELO_CABECERAS", "MODELO_PARAMETROS", "MODELO_FORMATO", "APP_CLAVE",
          "TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRETO", "TELEGRAM_BOT_NOMBRE"]


def aws(*args: str) -> str:
    return subprocess.run(["aws", *args, "--region", "us-east-1"], check=True, capture_output=True, text=True).stdout.strip()


def main():
    env = dotenv_values(RAIZ / ".env")
    if not env.get("APP_CLAVE"):
        env["APP_CLAVE"] = secrets.token_urlsafe(18)
        with open(RAIZ / ".env", "a") as f:
            f.write(f"\nAPP_CLAVE={env['APP_CLAVE']}\n")
        print("Se generó APP_CLAVE y quedó guardada en .env (ábrelo para verla).")
    base = (env.get("DATABASE_URL") or "").replace("[YOUR-PASSWORD]", quote(env.get("DATABASE_PASSWORD") or "", safe=""))
    if not base.startswith("postgres"):
        sys.exit("Falta DATABASE_URL de Postgres en .env")
    # En funciones sin servidor se usa el agrupador en modo transacción (puerto 6543)
    valores = {"DATABASE_URL": base.replace(":5432/", ":6543/")}
    valores.update({k: env[k] for k in CLAVES if env.get(k)})
    arn = aws("cloudformation", "describe-stacks", "--stack-name", "OperacionBase",
              "--query", "Stacks[0].Outputs[?OutputKey=='SecretoArn'].OutputValue", "--output", "text")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        os.chmod(f.name, 0o600)
        json.dump(valores, f)
    try:
        aws("secretsmanager", "put-secret-value", "--secret-id", arn, "--secret-string", f"file://{f.name}")
    finally:
        os.unlink(f.name)
    print("Secreto actualizado con:", ", ".join(sorted(valores)))


if __name__ == "__main__":
    main()
