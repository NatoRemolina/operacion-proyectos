# Tareas habituales. `make` sin argumentos las lista.
PY := .venv/bin/python

.PHONY: ayuda instalar ejecutar probar revisar comprobar migrar
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
