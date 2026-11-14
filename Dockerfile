# Imágenes por digest (B3): una etiqueta cambia de contenido sin aviso. Para actualizarlas, docs/despliegue.md.
FROM public.ecr.aws/docker/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
# Adaptador que permite ejecutar este mismo servidor web dentro de una función Lambda.
# Fuera de Lambda no hace nada: la imagen sirve igual en local o en un servicio de contenedores.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 /lambda-adapter /opt/extensions/lambda-adapter
WORKDIR /srv
# Biblioteca que necesita XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
# Exactamente lo que se probó: versiones y hashes de requirements.lock (make bloquear lo regenera)
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY app ./app
COPY datos ./datos
ENV PORT=8080 AWS_LWA_READINESS_CHECK_PATH=/salud AWS_LWA_ASYNC_INIT=true PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
