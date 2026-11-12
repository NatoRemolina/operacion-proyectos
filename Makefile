# Tareas habituales. `make` sin argumentos las lista.
PY := .venv/bin/python

.PHONY: ayuda instalar ejecutar probar revisar comprobar migrar entorno entorno-web entorno-abajo
ayuda:            ## Lista las tareas
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/'

instalar:         ## Crea el entorno e instala dependencias de desarrollo
	python3 -m venv .venv && $(PY) -m pip install -r requirements-dev.txt

ejecutar:         ## Arranca la plataforma en http://localhost:8000
	$(PY) -m uvicorn app.main:app --reload

probar:           ## Corre las pruebas (no usan claves ni la base real)
	$(PY) -m pytest -q

revisar:          ## Revisión estática del código
	$(PY) -m ruff check .

comprobar: revisar probar  ## Lo mismo que corre la integración continua

migrar:           ## Crea o actualiza las tablas de la base configurada en .env
	$(PY) -m datos.semilla

entorno:          ## Levanta PostgreSQL local y la plataforma en Docker (http://127.0.0.1:8000); no usa .env
	docker compose up -d --build db app

entorno-web:      ## Además la web nueva y el gateway (http://127.0.0.1:8088)
	docker compose --profile web up -d --build

entorno-abajo:    ## Detiene el entorno local; los datos de demostración se conservan
	docker compose --profile web down
