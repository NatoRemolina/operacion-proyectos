# Operación de proyectos: viajes y gastos

Plataforma para una empresa que graba con drones y cuyos pilotos viajan a cada proyecto. Resuelve dos problemas sobre un mismo eje, **el viaje**:

1. **Cotizar el viaje** (reto 1). Compara vuelos y hoteles por su **costo total esperado** (precio, equipaje del equipo, baterías, riesgo de cambio de fecha, millas, traslado por carretera), no por el precio más bajo. La persona decide y explica por qué; la decisión crea el viaje con su presupuesto, y administración lo aprueba.
2. **Recoger los gastos del viaje** (reto 2). Fotos, PDF, correos o mensajes de Telegram se leen solos, se validan contra el viaje y su presupuesto, se aprueban solos cuando todo está claro y llegan a una persona solo las excepciones.

```
persona (P-0007) ─► cotización ─► decisión ─► VIAJE (V-2026-0012, presupuesto, estado) ─► gastos y evidencias
                                                  ▲
                                       aprobación de administración
```

## Qué hay

| Pieza | Para qué |
|---|---|
| Cuentas, permisos y cargos | Colaborador (lo suyo), gestor de proyecto (además, sus proyectos, en lectura) y administración (todo). El cargo (pilotaje, edición, desarrollo…) es un dato aparte. Todos viajan y nadie aprueba lo suyo |
| Cotización y decisión | Origen y destino en cualquier lugar del mundo, varios aeropuertos por búsqueda, traslado por carretera, precios en vivo o guardados, descarte de opciones que no sirven, agente que explica la recomendación, decisión con su porqué |
| Viajes | Código propio, presupuesto, aprobación, rechazo con motivo, reapertura y cierre |
| Monitoreo del vuelo | El día del viaje, estado de cada tramo y aviso por Telegram si hay retraso, cancelación o cambio de puerta |
| Gastos | Lectura automática, 20 motivos de revisión, bandeja de revisión, aprobación con excepción justificada, envíos idempotentes y revisión versionada |
| Justificaciones | Para qué fue cada gasto, por escrito o con nota de voz transcrita |
| Telegram | Recibos por chat, vinculados a la cuenta con un código de un solo uso (apagado si no se configura) |
| Tablero por proyecto | Presupuesto de los viajes frente a gasto real |
| Indicadores (KPIs) | Metas y semáforo para los dos retos, rastro de cada consulta al buscador y ficha por persona |
| Asistente de administración | Preguntas en lenguaje natural sobre lo que reportó cada persona, con cifras exactas y fuentes citadas por su código; opcionalmente con un asesor (agente alojado) que también lee justificaciones y cotizaciones |
| Monitoreo | Catálogo único de métricas, auditoría, errores con identificador, calidad de los datos |
| API JSON v1 | Contrato para la web nueva (`contracts/api-v1.md`) |
| Web nueva (Next.js) | Recorrido mínimo sobre la API v1: entrar, mis viajes, mis gastos, enviar un recibo (`web/`) |

## Ejecutar

### Lo más rápido: sin claves y sin Docker

```bash
make instalar
make ejecutar        # http://localhost:8000
```

Usa SQLite, precios reales guardados (Miami → Las Vegas, Miami → Moab) y lecturas guardadas de los recibos de ejemplo. La pantalla de ingreso muestra las cuentas de demostración.

### Entorno completo con Docker

```bash
make entorno         # PostgreSQL local y la plataforma en http://127.0.0.1:8000
make entorno-web     # además la web nueva y el gateway en http://127.0.0.1:8088
make entorno-abajo   # detener (los datos de demostración se conservan)
```

Es el mismo motor de base que en la nube, con datos de demostración. **No lee `.env`**: ninguna variable de este entorno apunta a la base real.

En `127.0.0.1:8088` el gateway publica un solo origen: `/api/v1/*` va a la API y el resto a la web nueva. La plataforma actual sigue en `127.0.0.1:8000`; las dos comparten la misma base. Abre una en `127.0.0.1` y la otra en `localhost` si quieres tener dos sesiones distintas a la vez (las cookies no se separan por puerto).

### Cuentas de demostración

| Permiso | Correo | Contraseña |
|---|---|---|
| Administración | `admin@demo.local` | `demo-admin-2026` |
| Colaborador (Andrés Molina) | `piloto@demo.local` | `demo-piloto-2026` |
| Colaborador (Laura Pérez) | `piloto2@demo.local` | `demo-piloto2-2026` |
| Gestor de proyecto | `gestor@demo.local` | `demo-gestor-2026` |

Solo existen en local (SQLite, o PostgreSQL con `CUENTAS_DEMO=1`). En una base compartida la primera cuenta de administración sale de `ADMIN_INICIAL_CORREO` y `ADMIN_INICIAL_CLAVE`.

## Recorrido sugerido (10 minutos)

1. **Como colaborador:** *Cotizar viaje* con los valores de ejemplo → ver por qué lo más barato no es lo mejor → elegir y *Guardar decisión*. Nace el viaje `V-…`, pendiente de aprobación.
2. **Como administración:** *Viajes* → aprobar el presupuesto.
3. **Como colaborador:** *Cargar gasto* con los recibos de ejemplo. Van solos al viaje; los claros se aprueban, el ilegible queda en revisión.
4. **Como administración:** *Gastos* → bandeja *En revisión* → corregir y aprobar, o aprobar con excepción.
5. *KPIs* → semáforos de los dos retos → ficha de la persona.
6. *Asistente* → «¿Qué ha reportado P-0002 en su viaje?».
7. *Monitoreo* → viajes, gastos, búsquedas, auditoría y calidad de datos.

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

## Pruebas y calidad

```bash
make comprobar         # linter y todas las pruebas (sin claves ni base real)
make entorno           # PostgreSQL y la plataforma en Docker
make probar-postgres   # las mismas pruebas contra una base nueva en ese PostgreSQL
make geografia         # vuelve a descargar OurAirports y GeoNames y rehace datos/geografia/
```

Las pruebas cubren permisos por rol (incluida una prueba de humo de cada página para cada rol), la regla del viaje, la validación de gastos, la integridad (envíos idempotentes, transacciones, revisión versionada), Telegram con un bot simulado, el buscador mundial, el monitoreo del vuelo, las métricas contra un conjunto conocido, el borde de la API v1, el asistente y su asesor con un servicio simulado. La integración continua corre lo mismo en cada envío a `main` o `dev`.

Los archivos de `datos/geografia/` están versionados: la demostración y la carga inicial no dependen de internet. La semilla los carga y cada carga queda en `cargas_datos` (fuente, archivo, huella, filas, momento y quién). `datos/geografia/FUENTES.md` lista las huellas de lo descargado.

## Arquitectura

Hoy es **una aplicación FastAPI con una base PostgreSQL**, en transición hacia la arquitectura objetivo: web Next.js, API Gateway y tres servicios con datos privados (Organización y acceso, Viajes y presupuestos, Gastos y evidencias). La migración va por anillos, sin reescribir; el contrato y el gateway ya existen.

| Documento | Contenido |
|---|---|
| `docs/adr/0001-arquitectura-objetivo.md` | La decisión: migrar por anillos y por qué en ese orden |
| `docs/adr/0002-hospedaje-de-la-web.md` | La web Next.js se hospeda en AWS detrás de un solo origen con la API |
| `docs/arquitectura_objetivo.md` | Dueño de cada tabla, lo que cruza entre dominios y los cortes más difíciles |
| `contracts/api-v1.md` | Contrato de la API v1 |
| `docs/datos.md` | Modelo relacional y regla de negocio del viaje |
| `docs/analitica.md`, `docs/kpis.md` | Métricas e indicadores |
| `docs/asistente.md` | Qué se indexa, qué sale hacia los servicios externos (índice y asesor) y límites |
| `docs/justificaciones.md` | Justificaciones escritas y notas de voz |
| `docs/trazabilidad.md` | Matriz de trazabilidad de la integridad de gastos |
| `docs/mejoras.md` | Mejoras de experiencia de uso e ingeniería y su estado |
| `EXPLORACION.md`, `ANALISIS.md` | Bitácora de análisis y decisiones |

### Estructura

| Ruta | Contenido |
|---|---|
| `app/main.py` | Arma la aplicación: control de acceso, errores y carga de rutas |
| `app/web.py` | Lo común a las pantallas: plantillas, contexto, páginas de error, cabeceras |
| `app/rutas/` | Una pantalla o área por archivo (se cargan solas); `v1_*.py` es la API v1 |
| `app/api_v1/` | Borde de la API v1: errores, token CSRF, dependencias de permiso |
| `app/servicios/` | Reglas de negocio por dominio: acceso, viajes, gastos, validación, precios, costo, geografía, monitoreo del vuelo, agente, KPIs, asistente, asesor, Telegram |
| `app/db.py` | Tablas, claves foráneas y acceso a datos (SQLite y PostgreSQL con el mismo código) |
| `datos/semilla.py`, `datos/migracion.py` | Datos iniciales y migración idempotente |
| `datos/geografia.py`, `datos/geografia/` | Preparación y archivos de los datos geográficos |
| `datos/asesor.py` | Mantenimiento del asesor: esquemas, verificación, sincronización y prueba en vivo |
| `datos/respaldo/`, `datos/ejemplos/` | Respuestas reales del buscador y recibos de ejemplo |
| `web/` | Web nueva en Next.js |
| `gateway/`, `docker-compose.yml` | Entorno local |
| `infra/` | Infraestructura como código en AWS (CDK) |
| `tests/` | Pruebas |

## Configuración

Copiar `.env.example` a `.env`. Cada bloque activa una parte; sin ninguno la plataforma funciona con datos guardados.

| Variable | Efecto |
|---|---|
| `SERPAPI_KEY` | Precios en vivo para cualquier ruta y fechas, autocompletado de lugares y estado del vuelo |
| `MODELO_API_URL`, `MODELO_API_KEY`, `MODELO_NOMBRE` | Lectura en vivo de recibos y notas de voz, agente y asistente con modelo de lenguaje |
| `ASESOR_API_URL`, `ASESOR_API_KEY`, `ASESOR_AGENTE_ID`, `ASESOR_ENTORNO_ID`, `ASESOR_CABECERAS` | Asesor del asistente: un agente alojado cuyas herramientas responde la plataforma (ver `docs/asistente.md`) |
| `DATABASE_URL` | PostgreSQL (Supabase) en lugar de SQLite |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Archivos originales en almacenamiento privado |
| `ADMIN_INICIAL_CORREO`, `ADMIN_INICIAL_CLAVE` | Primera cuenta de administración en una base compartida |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_NOMBRE`, `TELEGRAM_WEBHOOK_SECRETO` | Canal de Telegram |
| `PINECONE_API_KEY`, `PINECONE_HOST` | Índice del asistente en un servicio externo (si no, índice local) |
| `ORIGENES_WEB` | Orígenes desde los que la web nueva puede escribir en la API v1 |
| `PROVEEDOR_LUGARES` | `local+google` (por defecto) combina los datos locales con el autocompletado de Google; `local` usa solo los datos locales |
| `PREPARAR_BASE_LOCAL` | Con una base local que no es SQLite (por ejemplo PostgreSQL en Docker), `1` permite migrarla y sembrarla al arrancar; sin ese permiso la aplicación no la toca. `docker-compose.yml` ya lo pone |
| `DIRECTORIO_ARCHIVOS` | Carpeta donde se guardan los archivos originales cuando no se usa Supabase Storage (por defecto `datos/archivos`) |
| `GEOGRAFIA_DIR` | Carpeta de datos geográficos a cargar en lugar de `datos/geografia/`; las pruebas la apuntan a un subconjunto pequeño |

## Despliegue

`infra/` describe el despliegue en AWS: una función con imagen de contenedor, secretos gestionados, alarmas y presupuesto. La migración de la base es un paso aparte (`make migrar` con la configuración de la nube). Cada despliegue se revisa con `cdk diff` antes de aplicarse.

## Atribución de datos

- **Aeropuertos y países:** [OurAirports](https://ourairports.com/data/), de dominio público.
- **Ciudades, pueblos y regiones:** [GeoNames](https://www.geonames.org/), datos `cities1000` y `admin1CodesASCII`, bajo licencia [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Se conservan nombre, nombres alternativos en alfabeto latino, país, región, coordenadas y población. La fuente también se cita en el pie del buscador.
- **Nombres de países en español:** estándar ICU (`Intl.DisplayNames`).

## Limitaciones conocidas

- **Etapa de transición:** una sola aplicación y una sola base. Los servicios con datos privados, la mensajería y la saga de presupuesto están diseñados (`docs/adr/0001`) y no construidos.
- El dinero se guarda en coma flotante; las reglas validan y comparan con decimales exactos y la API lo entrega como cadenas de dos decimales. Pasar las columnas a decimales exactos está pendiente.
- Con pocos gastos y pocas decisiones, varios indicadores muestran el método, no conclusiones; sus metas son supuestos editables.
- El ahorro que muestra la analítica es un valor esperado bajo supuestos editables, no dinero ya ahorrado.
- Los precios son una foto del momento de la consulta; cada opción muestra su origen.
- La distancia y el tiempo por carretera son una estimación (línea recta × factor ÷ velocidad), sin mapas ni rutas reales, y no hay tren, bus ni ferri.
- La cotización con el buscador mundial está en las pantallas actuales; la web Next.js todavía no la ofrece.
- Con el asesor, una respuesta del asistente tarda alrededor de 15 s; si el asesor falla, responde el asistente sin él.
- Varias reglas de aerolíneas vienen de fuentes secundarias o están sin verificar; la página *Reglas* lo indica.
- El canal de Telegram se probó con un bot simulado.
- Extraer precios de buscadores puede ir contra sus términos de uso; para producción corresponde una API con licencia.
- Las personas, clientes, comercios y membresías de los datos de ejemplo son inventados.
