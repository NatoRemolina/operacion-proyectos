FROM public.ecr.aws/docker/library/python:3.12-slim
# Adaptador que permite ejecutar este mismo servidor web dentro de una función Lambda.
# Fuera de Lambda no hace nada: la imagen sirve igual en local o en un servicio de contenedores.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter
WORKDIR /srv
# Biblioteca que necesita XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY datos ./datos
ENV PORT=8080 AWS_LWA_READINESS_CHECK_PATH=/salud AWS_LWA_ASYNC_INIT=true PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
