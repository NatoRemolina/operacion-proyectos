# Analizador de la página del vuelo: imagen oficial de Playwright para Python (trae Chromium y sus dependencias), fijada
# por digest. En local corre como servicio interno (`docker compose`, servicio `analizador`); en AWS, como función Lambda
# con la etapa `produccion` y el punto de entrada de Lambda (infra/lib/app-stack.ts).
#
#   etapa `produccion` (la última, la que se construye por omisión): sin herramientas de prueba, como `pwuser`
#   etapa `pruebas`: lo mismo más pytest, para `analizador/pruebas` sin red:
#     docker build --target pruebas -t analizador-pruebas analizador
#     docker run --rm --network none --shm-size 1g analizador-pruebas python -m pytest -q analizador/pruebas
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy@sha256:6bbd515848db4042068571135979b6ee6d330a794b28e037e3a6ccd7f2abfa26 AS base

WORKDIR /srv
COPY requirements.txt analizador/requirements.txt
RUN pip install --no-cache-dir -r analizador/requirements.txt
COPY . analizador/
# Chromium escribe su perfil en HOME: en Lambda solo /tmp se puede escribir
ENV PYTHONUNBUFFERED=1 HOME=/tmp PUERTO=8090

FROM base AS pruebas
RUN pip install --no-cache-dir -r analizador/requirements-pruebas.txt
USER pwuser

FROM base AS produccion
USER pwuser
EXPOSE 8090
CMD ["python", "-m", "analizador.servidor"]
