# Tareas habituales. `make` sin argumentos las lista.
PY := .venv/bin/python
# Python 3.12 o posterior: el código usa f-strings anidadas (PEP 701), que no compilan en 3.11 ni antes.
# Con otro ejecutable: make instalar PYTHON=/ruta/a/python3.13
PYTHON ?= python3.12

.PHONY: ayuda instalar ejecutar probar probar-postgres revisar comprobar migrar geografia entorno entorno-web entorno-abajo demo-monitoreo respaldar verificar-respaldo ganchos
ayuda:            ## Lista las tareas
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/'

instalar:         ## Crea el entorno e instala dependencias de desarrollo (requiere Python 3.12)
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else "Hace falta Python 3.12 o posterior (este es " + sys.version.split()[0] + "): make instalar PYTHON=python3.12")'
	$(PYTHON) -m venv .venv && $(PY) -m pip install -r requirements-dev.txt

ejecutar:         ## Arranca la plataforma en http://localhost:8000
	$(PY) -m uvicorn app.main:app --reload

probar:           ## Corre las pruebas (no usan claves ni la base real)
	$(PY) -m pytest -q

probar-postgres:  ## Las mismas pruebas contra una base nueva en el PostgreSQL de Docker (make entorno antes)
	docker compose exec -T db psql -U operacion -d operacion -q -c "drop database if exists pruebas_pg" -c "create database pruebas_pg"
	PRUEBAS_DATABASE_URL=postgresql://operacion:operacion-local@127.0.0.1:5433/pruebas_pg $(PY) -m pytest -q -p no:cacheprovider

revisar:          ## Revisión estática del código
	$(PY) -m ruff check .

comprobar: revisar probar  ## Linter y pruebas de Python (la integración continua además prueba la web, infra/ y las imágenes)

migrar:           ## Migra la base del archivo ENV (obligatorio): make migrar ENV=.env.supabase-pruebas (producción: docs/despliegue.md)
	@test -n "$(ENV)" || { echo "Indica el archivo de la base: make migrar ENV=<archivo> (ver docs/despliegue.md)"; exit 2; }
	.venv/bin/dotenv -f $(ENV) run -- $(PY) -m datos.semilla

geografia:        ## Descarga OurAirports y GeoNames y rehace datos/geografia/ (la semilla los carga al arrancar)
	$(PY) -m datos.geografia

entorno:          ## Levanta PostgreSQL local y la plataforma en Docker (http://127.0.0.1:8000); no usa .env
	docker compose up -d --build db app

entorno-web:      ## Además la web nueva y el gateway (http://127.0.0.1:8088)
	docker compose --profile web up -d --build

entorno-abajo:    ## Detiene el entorno local; los datos de demostración se conservan
	docker compose --profile web down

demo-monitoreo:   ## Prepara en el entorno local el viaje IB 5634 del 13 dic para ver el monitoreo (fijar MONITOREO_AHORA)
	docker compose exec app python -m datos.demo_monitoreo

respaldar:        ## Copia la base publicada y sus recibos (solo lectura) a ~/Respaldos; ver docs/respaldo.md
	$(PY) -m datos.respaldar respaldar --env $(or $(ENV),.env.supabase-publicada)

ganchos:          ## Instala los ganchos de git de scripts/ganchos/ (valen para todas las carpetas de trabajo)
	@d=$$(git rev-parse --git-common-dir)/hooks; for g in scripts/ganchos/*; do install -m 755 "$$g" "$$d/"; done; echo "Ganchos instalados en $$d"

verificar-respaldo: ## Restaura una copia en una base NUEVA del proyecto de pruebas: RESPALDO=carpeta BASE=nombre
	$(PY) -m datos.respaldar verificar --respaldo $(RESPALDO) --env $(or $(ENV),.env.supabase-pruebas) --base $(BASE)
