# Operación de proyectos: viajes y gastos

Aplicación web con dos herramientas que comparten datos:

1. **Planear un viaje de grabación.** Compara vuelos y hoteles por su costo total esperado (precio, equipaje, riesgo de cambio de fecha, millas), no por el precio más bajo, y guarda una ficha de decisión contra el proyecto.
2. **Recoger los gastos de cada proyecto.** Recibe fotos, PDF y correos, lee los datos, aprueba sola lo que está claro y deja a una persona solo las excepciones.

Sobre esos datos hay cuatro piezas más:

- **Tablero por proyecto:** previsto frente a real y soportes faltantes.
- **Analítica:** frecuencia de consultas, ahorro identificado, historial de precios de las rutas y estado del modelo.
- **Agente de recomendación:** explica cuál opción conviene, por qué y qué dato la cambiaría. Es un grafo de estados con herramientas; sin clave del modelo de lenguaje responde un análisis determinista.
- **Flujo de la información:** recorrido y origen de cada dato.

Cada búsqueda de vuelos queda registrada como datos tabulares (`observaciones`), que alimentan un modelo de precio esperado.

## Ejecutar

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000
```

O con Docker:

```bash
docker build -t operacion . && docker run -p 8080:8080 --env-file .env operacion
```

**No hace falta ninguna clave.** Sin configuración, la aplicación usa SQLite, precios reales guardados (Miami a Las Vegas, capturados el 11 de noviembre de 2026) y lecturas guardadas de los soportes de ejemplo. La barra superior indica siempre qué está en vivo y qué es guardado.

## Recorrido sugerido (5 minutos)

1. **Planear viaje** → dejar los valores de ejemplo → *Buscar y comparar*. Ver el aviso "lo más barato no es lo mejor" y abrir un desglose.
2. Guardar la **ficha de decisión**.
3. **Gastos → Cargar soportes** → procesar los ejemplos y leer el buzón simulado.
4. Abrir la bandeja **En revisión**: un recibo ilegible y un duplicado. Corregir y aprobar uno.
5. Abrir el proyecto **Las Vegas**: previsto frente a real y soportes faltantes.
6. **Flujo de la información**: recorrido de cada dato.

## Datos y modelo de precio esperado

```bash
.venv/bin/python -m datos.recolectar --simular   # muestra qué buscaría, sin gastar consultas
.venv/bin/python -m datos.recolectar --max 40    # una consulta del buscador por búsqueda nueva
.venv/bin/python -m datos.entrenar               # entrena y publica métricas en datos/modelo/ficha.json
```

El modelo (XGBoost) predice el precio de un vuelo a partir de ruta, aerolínea, escalas, duración, horario, anticipación y rango típico de la ruta. Se valida dejando búsquedas completas fuera del entrenamiento y se compara con una línea base (mediana de la ruta). **Solo se muestra en las comparaciones si tiene al menos 200 filas y supera a la línea base**; el estado actual se ve en la página Analítica.

Los pesos de la decisión (riesgo de cambio, valor de la milla) no son aprendidos: son reglas y supuestos explícitos, porque no existe un historial de viajes con su resultado. La aplicación empieza a registrarlo.

## API

Rutas de solo lectura bajo `/api` (analítica, solicitudes, gastos, observaciones, eventos), documentadas en `/docs`. Es el contrato para conectar un front aparte.

## Configuración opcional

Copiar `.env.example` a `.env`. Cada bloque activa una parte:

| Variable | Efecto |
|---|---|
| `SERPAPI_KEY` | Precios en vivo para cualquier ruta y fechas |
| `MODELO_API_URL`, `MODELO_API_KEY`, `MODELO_NOMBRE` | Lectura en vivo de cualquier soporte |
| `DATABASE_URL` | Guarda en Postgres (Supabase) en lugar de SQLite |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Guarda los archivos originales en Supabase Storage |
| `APP_CLAVE` | Pide contraseña para entrar (obligatoria si se publica) |

## Estructura

| Ruta | Contenido |
|---|---|
| `app/main.py` | Rutas |
| `app/servicios/precios.py` | Búsqueda de vuelos, tarifas y hoteles, con respaldo guardado |
| `app/servicios/costo.py` | Costo total esperado y descarte de opciones |
| `app/servicios/extraccion.py` | Soporte → datos |
| `app/servicios/validacion.py` | Reglas de aprobación automática |
| `app/servicios/eventos.py` | Bitácora que alimenta el flujo de la información |
| `app/servicios/agente.py` | Agente de recomendación (grafo de estados con herramientas) |
| `app/servicios/modelo.py`, `datos/entrenar.py` | Modelo de precio esperado |
| `app/servicios/analitica.py` | Indicadores del tablero de analítica |
| `datos/recolectar.py` | Recolector de precios reales |
| `datos/respaldo/` | Respuestas reales guardadas del buscador |
| `datos/ejemplos/` | Soportes ficticios y sus valores esperados |
| `datos/esquema.sql`, `datos/semilla.py` | Esquema y datos iniciales |
| `EXPLORACION.md` | Bitácora de análisis, decisiones y fuentes |

## Limitaciones conocidas

- El ahorro que muestra la analítica es un valor esperado bajo supuestos editables, no dinero ya ahorrado.
- El agente con modelo de lenguaje no se ha probado en vivo; el modo determinista sí.
- Los precios son una foto del momento de la captura; cada opción muestra su origen.
- Las tarifas reales de un vuelo cuestan dos consultas adicionales; se piden bajo demanda.
- Varias reglas del catálogo vienen de fuentes secundarias o están sin verificar; la página **Reglas** lo indica en cada una.
- La probabilidad de cambio, el valor de la milla y las tasas de cambio son supuestos editables.
- Extraer precios de buscadores puede ir contra sus términos de uso. Para producción corresponde una API con licencia.
- Las personas, clientes, comercios y membresías de los datos de ejemplo son inventados.
