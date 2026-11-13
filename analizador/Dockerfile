# Analizador de la página del vuelo: imagen oficial de Playwright para Python (trae Chromium y sus dependencias).
# En local corre como servicio interno (`docker compose`, servicio `analizador`); en AWS, como función Lambda con esta
# misma imagen y el punto de entrada de Lambda (infra/lib/app-stack.ts).
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /srv
COPY requirements.txt analizador/requirements.txt
RUN pip install --no-cache-dir -r analizador/requirements.txt
COPY . analizador/

# Chromium escribe su perfil en HOME: en Lambda solo /tmp se puede escribir
ENV PYTHONUNBUFFERED=1 HOME=/tmp PUERTO=8090
EXPOSE 8090
CMD ["python", "-m", "analizador.servidor"]
