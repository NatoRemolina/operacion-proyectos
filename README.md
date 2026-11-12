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

## Cotizar desde y hacia cualquier lugar del mundo

El origen y el destino son un solo campo, como en Google Flights. Se puede escribir un país, una ciudad, un pueblo o un código de aeropuerto (`moab`, `Lisboa`, `LIS`, `Portugal`).

- **Búsqueda local.** Los datos viven en la base (unos 4.000 aeropuertos con servicio regular, 171.838 ciudades y pueblos de más de 1.000 habitantes y 249 países), así que sugerir no llama a ningún servicio externo. Dos lugares con el mismo nombre se distinguen por región y país (Moab, Utah; Moab, Jordania). Ruta: `GET /lugares/buscar`.
- **Aeropuertos cercanos.** Al elegir un lugar se marcan sus aeropuertos con servicio regular dentro de un radio (400 km por defecto, hasta 4); la persona puede quitar alguno. Al elegir un país se proponen sus aeropuertos principales.
- **Autocompletado de Google, combinado.** Con clave del buscador y tras una pausa de 400 ms con al menos 3 letras, las ciudades y aeropuertos de Google se suman a la lista, marcados como «Google». Solo se envía el texto del campo de lugar. Cada respuesta se guarda y el mismo texto no se paga dos veces. Topes (editables en «Reglas y supuestos»): 60 consultas al mes y 15 por persona al día; alcanzado un tope, o sin clave, sigue solo con los datos locales. `PROVEEDOR_LUGARES=local` lo apaga.
- **Varios aeropuertos por búsqueda.** Comparar varios aeropuertos de origen y de destino gasta **una** consulta del buscador (los códigos van unidos por coma y ordenados).
- **Traslado por carretera en el costo.** Cada opción suma el traslado entre el aeropuerto real y el lugar: línea recta × 1,3 como distancia, 70 km/h como velocidad, 0,35 USD por km ida y vuelta (0,12 con carro de alquiler, solo combustible y peajes). También cuenta para la hora límite y para el presupuesto del viaje. A menos de 30 km no hay línea extra. Todos esos valores son reglas editables y la distancia es una estimación, no una ruta de un servicio de mapas.

## Cargos y permisos

- **El permiso** dice qué se puede hacer: *colaborador* (antes «piloto»: cotiza y reporta lo suyo), *gestor de proyecto* (además ve sus proyectos) y *administración* (ve todo y aprueba). La migración convierte las cuentas «piloto» en colaboradores sin cambiar sus viajes ni sus gastos.
- **El cargo** dice qué hace la persona en la empresa (pilotaje de dron, edición de video, desarrollo de software, ingeniería de datos, producción u otros). Es un dato aparte, sin permisos propios; administración mantiene la lista en la pantalla de Usuarios y asigna el cargo a cada cuenta. Aparece en la ficha, en la lista de usuarios y en la analítica.
- **Todos viajan:** colaboradores, gestores y administración cotizan, reciben viajes a su nombre y reportan gastos.
- **Nadie aprueba lo suyo:** el presupuesto de un viaje y los gastos de una persona de administración los aprueba otra persona de administración. El servicio lo impide y deja el intento en la bitácora.

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
| `PROVEEDOR_LUGARES` | `local+google` (por defecto) combina los datos locales con el autocompletado de Google; `local` usa solo los datos locales |
| `PREPARAR_BASE_LOCAL` | Con una base local que no es SQLite (por ejemplo PostgreSQL en Docker), `1` permite migrarla y sembrarla al arrancar; sin ese permiso la aplicación no la toca. `docker-compose.yml` ya lo pone |
| `DIRECTORIO_ARCHIVOS` | Carpeta donde se guardan los archivos originales cuando no se usa Supabase Storage (por defecto `datos/archivos`) |
| `GEOGRAFIA_DIR` | Carpeta de datos geográficos a cargar en lugar de `datos/geografia/`; las pruebas la apuntan a un subconjunto pequeño |

## Pruebas y datos geográficos

```bash
make probar            # las pruebas con SQLite, sin internet y sin claves
make entorno           # PostgreSQL y la plataforma en Docker
make probar-postgres   # las 301 pruebas contra una base nueva en ese PostgreSQL
make geografia         # vuelve a descargar OurAirports y GeoNames y rehace datos/geografia/
```

Los archivos de `datos/geografia/` están versionados: la demostración y la carga inicial no dependen de internet. La semilla los carga y cada carga queda en `cargas_datos` (fuente, archivo, huella, filas, momento y quién). `datos/geografia/FUENTES.md` lista las huellas de lo descargado.

## Estructura

| Ruta | Contenido |
|---|---|
| `app/main.py` | Rutas |
| `app/servicios/precios.py` | Búsqueda de vuelos, tarifas y hoteles, con respaldo guardado |
| `app/servicios/costo.py` | Costo total esperado, traslado por carretera y descarte de opciones |
| `app/servicios/geografia.py`, `app/rutas/lugares.py` | Búsqueda de lugares, aeropuertos cercanos y autocompletado de Google |
| `datos/geografia.py`, `datos/geografia/` | Preparación y archivos de los datos geográficos |
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

## Atribución de datos

- **Aeropuertos y países:** [OurAirports](https://ourairports.com/data/), de dominio público.
- **Ciudades, pueblos y regiones:** [GeoNames](https://www.geonames.org/), datos `cities1000` y `admin1CodesASCII`, bajo licencia [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Se conservan nombre, nombres alternativos en alfabeto latino, país, región, coordenadas y población. La fuente también se cita en el pie del buscador.
- **Nombres de países en español:** estándar ICU (`Intl.DisplayNames`).

## Limitaciones conocidas

- La distancia y el tiempo por carretera son una estimación (línea recta × factor ÷ velocidad), sin mapas ni rutas reales, y no hay tren, bus ni ferri.
- La cotización con el buscador mundial está en las pantallas actuales; la web Next.js todavía no la ofrece.

- El ahorro que muestra la analítica es un valor esperado bajo supuestos editables, no dinero ya ahorrado.
- El agente con modelo de lenguaje no se ha probado en vivo; el modo determinista sí.
- Los precios son una foto del momento de la captura; cada opción muestra su origen.
- Las tarifas reales de un vuelo cuestan dos consultas adicionales; se piden bajo demanda.
- Varias reglas del catálogo vienen de fuentes secundarias o están sin verificar; la página **Reglas** lo indica en cada una.
- La probabilidad de cambio, el valor de la milla y las tasas de cambio son supuestos editables.
- Extraer precios de buscadores puede ir contra sus términos de uso. Para producción corresponde una API con licencia.
- Las personas, clientes, comercios y membresías de los datos de ejemplo son inventados.
