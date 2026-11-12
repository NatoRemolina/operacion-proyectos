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

La guía completa, con Docker y el monitoreo del vuelo, está en «Guía de demostración» más abajo.

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

## La opción elegida completa y el monitoreo del vuelo

**Al decidir**, la plataforma carga completa la opción elegida: busca el vuelo de regreso real (el que sale del aeropuerto donde aterrizó la ida) y las opciones de reserva con su tarifa y equipaje. Con la tarifa real recalcula el costo y el presupuesto; sin ella queda la estimada, marcada «(supuesta)». Los tramos de ida y de regreso se guardan en `tramos_vuelo`. Decidir de nuevo la misma opción no paga nada: lee lo guardado.

**Al aprobar**, administración reconfirma el precio con el buscador (siempre en vivo): «precio confirmado», «precio cambió: antes X, ahora Y» o «precio no reconfirmado». Si sube más que la regla `tolerancia_precio_aprobacion` (5 % por defecto, editable en «Reglas y supuestos»), el viaje no se aprueba solo: el tablero muestra la diferencia y el botón «Confirmar precio y aprobar», que aprueba con el precio nuevo sin volver a pagar la consulta.

**El día del viaje**, el tablero «Viajes» de administración muestra el estado de cada vuelo (a tiempo, retrasado, cancelado, terminal, puerta, llegada estimada) y marca «No llega a la grabación» si la llegada más el traslado pasa de la hora límite. Si hay un retraso de 15 minutos o más (o que crece 15 más desde el último aviso), una cancelación o un cambio de terminal o de puerta, se avisa al viajero por Telegram si tiene el chat vinculado; si no, el aviso queda en el tablero. Nunca se avisa dos veces lo mismo.

| Momento | Búsquedas del plan que gasta |
|---|---|
| Cotizar | 1 de vuelos (aunque se comparen varios aeropuertos) y 1 de hoteles |
| Decidir | Hasta 2: el regreso real y las opciones de reserva. Lo que ya está guardado no se paga |
| «Traer tarifas» (bajo demanda) | Las mismas 2 |
| Aprobar | 1 (la reconfirmación). «Confirmar precio y aprobar» no gasta otra |
| Estado del vuelo | 1 por consulta en vivo, solo dentro de la ventana y bajo los topes |

Para cuidar el plan del buscador (250 búsquedas al mes), el estado del vuelo solo se consulta desde 3 horas antes de la salida hasta la llegada (cada hora en la zona horaria de su aeropuerto, que sale de GeoNames: columna `zona` de `lugares`), se reutiliza 60 minutos, y hay topes de 6 consultas por tramo, 12 por viaje y sentido y 30 en vivo por día. Si al plan le quedan menos de 25 búsquedas, el monitoreo se suspende. «Actualizar ahora» salta la caché (una vez por minuto como máximo), nunca la ventana ni los topes. Todos son reglas editables; ver `docs/kpis.md` para cómo se cuentan.

**Sin clave del buscador:** decidir carga lo guardado si existe y, si no, deja el evento «regreso sin datos» y registra solo los tramos de ida; aprobar funciona con el aviso «precio no reconfirmado»; el estado del vuelo usa la respuesta de ejemplo del IB 5634 y cualquier otro vuelo queda «sin datos».

## Integridad de los gastos

- Los importes se validan con `Decimal` (`app/servicios/dinero.py`): un total vacío, cero, negativo o no numérico va a revisión (`importe_invalido`), igual que una fecha que no es real (`fecha_invalida`). Una fecha posterior a hoy avisa (`fecha_futura`) pero no bloquea. El duplicado compara también la moneda.
- Registrar, asignar viaje y aprobar un gasto se hacen con el viaje bloqueado (`db.transaccion()`), así que dos aprobaciones a la vez no pasan el presupuesto.
- Reenviar un recibo no crea otro gasto: la carga web y la API aceptan una clave de envío (`Idempotency-Key`); repetida devuelve el mismo gasto, y con otro archivo, 409.
- La revisión es versionada (`gastos.version`): si otra persona cambió el gasto mientras se revisaba, no se pisa (409 `EDIT_CONFLICT` en la API). Rechazar exige un motivo de 5 caracteres o más, que se guarda en `gastos.motivo_rechazo` y se le avisa a la persona. Misma regla en la web y en `POST /api/v1/gastos/{id}/revision` (ver `contracts/api-v1.md`).
- Quién puede cambiar qué y qué queda registrado: `docs/trazabilidad.md`.

```bash
.venv/bin/python -m datos.comprobar_supabase   # solo lectura: tablas, columnas y permisos que espera esta versión
```

**Respaldo de la base publicada.** El plan gratuito de Supabase no hace respaldos automáticos. `make respaldar` copia la base y los recibos en solo lectura, con conteos y huellas, y `make verificar-respaldo` ensaya la restauración en una base nueva del proyecto de pruebas. Procedimiento, cifrado de la copia y vuelta atrás: `docs/respaldo.md`.

## Guía de demostración (en local, con Docker)

Todo corre en local con una base PostgreSQL desechable y **sin claves**: no toca la base ni los servicios publicados.

**Qué es simulado.** Sin clave del buscador, las cotizaciones usan respuestas reales guardadas en `datos/respaldo/` (Miami a Moab y Las Vegas, capturadas el 11 de noviembre de 2026), y la lectura de recibos usa las lecturas guardadas de los ejemplos. El estado del vuelo usa una respuesta de ejemplo escrita a mano con la forma que documenta el proveedor (no es una consulta real) y una fecha fija. Telegram no está conectado: los avisos quedan en el tablero. La reconfirmación del precio al aprobar necesita la clave: sin ella aprueba con el aviso «precio no reconfirmado».

1. **Levantar el entorno.** `make entorno` (plataforma en http://127.0.0.1:8000) o `make entorno-web` (además la web nueva en http://127.0.0.1:8088). `make entorno-abajo` lo detiene y conserva los datos; `docker compose down -v` los borra.
2. **Cuentas de demostración** (en `entrar`, la pantalla de ingreso las muestra con sus contraseñas): `admin@demo.local` (administración), `piloto@demo.local` y `piloto2@demo.local` (colaboradores) y `gestor@demo.local` (gestor de proyecto).
3. **Cotizar Miami → Moab** con `piloto@demo.local`: *Planear viaje*, origen Miami (MIA), destino «Moab», 8 a 11 de diciembre de 2026 (las fechas de la respuesta guardada), con los aeropuertos CNY, GJT y SLC marcados.
4. **Comparar CNY, GJT y SLC con traslado.** Cada opción suma el traslado por carretera entre el aeropuerto y Moab (CNY está a unos 27 km y no suma línea; desde SLC aparece «Combustible y peajes»). La recomendada es por costo total esperado, no la más barata.
5. **Decidir.** Elegir la recomendada (o otra, explicando por qué) y guardar. Se crea el viaje, pendiente de aprobación. Sin clave aparece «regreso sin datos» en la bitácora del viaje: es lo esperado.
6. **Aprobar con otra cuenta.** Entrar como `admin@demo.local`, *Viajes*, aprobar. Para ver que nadie aprueba lo suyo: con la cuenta de administración cotizar y decidir otro viaje e intentar aprobarlo; el servicio lo impide y lo deja en la bitácora. Una segunda cuenta de administración (se crea en *Usuarios*) sí puede aprobarlo.
7. **Cargar un recibo con justificación.** Como colaborador, *Gastos → Cargar soportes*: un archivo de `datos/ejemplos/` y el campo «¿Para qué fue este gasto?». El recibo queda aprobado solo o en revisión según el viaje y las reglas; el borroso (`recibo_parqueo_borroso.png`) va a revisión.
8. **Rechazar con motivo.** Como administración, abrir el gasto en revisión, escribir el motivo (5 caracteres o más) y *Rechazar*: queda guardado y la persona lo ve.
9. **Monitoreo del vuelo.** `make demo-monitoreo` crea un viaje aprobado de Madrid a Lisboa (13 a 16 de diciembre de 2026, llegar antes de las 12:00) con el tramo IB 5634. Después, en `docker-compose.yml` quitar el comentario de `MONITOREO_AHORA: "2026-12-13T06:00"` y recrear la plataforma con `docker compose up -d app`. Abrir *Viajes* como administración: el tablero lee la respuesta de ejemplo y muestra IB 5634 retrasado 20 minutos, terminal 4, puerta J58, con el aviso al viajero (sin Telegram vinculado, queda en el tablero). Repetirlo no gasta búsquedas ni duplica el aviso. Sin `MONITOREO_AHORA` el tablero dice «fuera de la ventana», porque ese vuelo es del 13 de diciembre. `MONITOREO_AHORA` solo se respeta con `ENTORNO=local`.

**Advertencias para quien presenta.**

- **Moab no tiene hoteles guardados.** La búsqueda de hoteles de Moab queda «fallida» y la decisión se guarda solo con el vuelo. Las respuestas de hoteles guardadas son de Las Vegas, Lisboa y Denver.
- **«Costo total esperado» (ficha de la decisión) y presupuesto del viaje no coinciden, y es correcto.** El costo esperado suma todas las líneas de la comparación, incluidos el riesgo de cambio de fecha y las millas del viajero (que restan), además del hotel, el carro y el traslado. El presupuesto es lo que se espera pagar (`viajes.presupuesto_de`): quita las líneas de valor esperado del vuelo (riesgo de cambio y millas, que no son desembolsos) y suma los viáticos (días del viaje por `viaticos_dia_usd`, 75 USD por defecto). Por eso un viaje con costo esperado de 980 USD puede tener un presupuesto de 1.153 USD. Conviene no mostrar las dos cifras juntas sin explicarlo.
- IB 5634 no sale de ninguna búsqueda guardada (Madrid a Lisboa del 13 de diciembre trae otros vuelos): por eso el viaje de la demostración lo prepara `make demo-monitoreo` y no se llega a él cotizando.
- Fuera de Docker: `.venv/bin/python -m datos.demo_monitoreo` con SQLite, y `MONITOREO_AHORA=2026-12-13T06:00 ENTORNO=local .venv/bin/uvicorn app.main:app`.

## Datos y modelo de precio esperado

```bash
.venv/bin/python -m datos.recolectar --simular   # muestra qué buscaría, sin gastar consultas
.venv/bin/python -m datos.recolectar --max 40    # una consulta del buscador por búsqueda nueva
.venv/bin/python -m datos.entrenar               # entrena y publica métricas en datos/modelo/ficha.json
```

El modelo (XGBoost) predice el precio de un vuelo a partir de ruta, aerolínea, escalas, duración, horario, anticipación y rango típico de la ruta. Se valida dejando búsquedas completas fuera del entrenamiento y se compara con una línea base (mediana de la ruta). **Solo se muestra en las comparaciones si tiene al menos 200 filas y supera a la línea base**; el estado actual se ve en la página Analítica.

Los pesos de la decisión (riesgo de cambio, valor de la milla) no son aprendidos: son reglas y supuestos explícitos, porque no existe un historial de viajes con su resultado. La aplicación empieza a registrarlo.

## API

Rutas de solo lectura bajo `/api` (analítica, solicitudes, gastos, observaciones, eventos), documentadas en `/docs`. Es el contrato para conectar un front aparte. La API versionada de la web nueva (`/api/v1`, con `Idempotency-Key` en la carga de recibos y la revisión de gastos) está en `contracts/api-v1.md`.

## Configuración opcional

Copiar `.env.example` a `.env`. Cada bloque activa una parte:

| Variable | Efecto |
|---|---|
| `SERPAPI_KEY` | Precios en vivo para cualquier ruta y fechas |
| `MODELO_API_URL`, `MODELO_API_KEY`, `MODELO_NOMBRE` | Lectura en vivo de cualquier soporte |
| `DATABASE_URL` | Guarda en Postgres (Supabase) en lugar de SQLite |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Guarda los archivos originales en Supabase Storage |
| `APP_CLAVE` | Pide contraseña para entrar (obligatoria si se publica) |
| `MONITOREO_AHORA` | Solo con `ENTORNO=local`: fija el «ahora» (UTC, por ejemplo `2026-12-13T06:00`) del monitoreo del vuelo para demostrarlo con un vuelo futuro. Fuera de local se ignora. En `docker-compose.yml` está comentada |
| `PROVEEDOR_LUGARES` | `local+google` (por defecto) combina los datos locales con el autocompletado de Google; `local` usa solo los datos locales |
| `PREPARAR_BASE_LOCAL` | Con una base local que no es SQLite (por ejemplo PostgreSQL en Docker), `1` permite migrarla y sembrarla al arrancar; sin ese permiso la aplicación no la toca. `docker-compose.yml` ya lo pone |
| `DIRECTORIO_ARCHIVOS` | Carpeta donde se guardan los archivos originales cuando no se usa Supabase Storage (por defecto `datos/archivos`) |
| `GEOGRAFIA_DIR` | Carpeta de datos geográficos a cargar en lugar de `datos/geografia/`; las pruebas la apuntan a un subconjunto pequeño |

## Pruebas y datos geográficos

```bash
make probar            # las pruebas con SQLite, sin internet y sin claves
make entorno           # PostgreSQL y la plataforma en Docker
make probar-postgres   # las mismas pruebas contra una base nueva en ese PostgreSQL
make demo-monitoreo     # prepara el viaje IB 5634 del 13 de diciembre (con make entorno en marcha)
make geografia         # vuelve a descargar OurAirports y GeoNames y rehace datos/geografia/
```

Los archivos de `datos/geografia/` están versionados: la demostración y la carga inicial no dependen de internet. La semilla los carga y cada carga queda en `cargas_datos` (fuente, archivo, huella, filas, momento y quién). `datos/geografia/FUENTES.md` lista las huellas de lo descargado.

## Estructura

| Ruta | Contenido |
|---|---|
| `app/main.py` | Rutas |
| `app/servicios/precios.py` | Búsqueda de vuelos, tarifas y hoteles, con respaldo guardado |
| `app/servicios/monitoreo_vuelos.py` | Tramos del vuelo elegido, estado el día del viaje, topes y avisos |
| `app/servicios/dinero.py`, `envios.py`, `revision.py` | Importes con `Decimal`, envíos idempotentes y revisión versionada de gastos |
| `datos/demo_monitoreo.py`, `datos/comprobar_supabase.py` | Preparador de la demostración del monitoreo y comprobación de la base en Supabase |
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
- El estado del vuelo se probó solo con una respuesta de ejemplo escrita a mano según la documentación del proveedor; falta comprobarlo con una consulta real. El vuelo de regreso que se carga es el más barato que sale del aeropuerto de llegada; no se elige otro horario.
- Los precios son una foto del momento de la captura; cada opción muestra su origen.
- Las tarifas reales de un vuelo cuestan dos consultas adicionales; se piden bajo demanda.
- Varias reglas del catálogo vienen de fuentes secundarias o están sin verificar; la página **Reglas** lo indica en cada una.
- La probabilidad de cambio, el valor de la milla y las tasas de cambio son supuestos editables.
- Extraer precios de buscadores puede ir contra sus términos de uso. Para producción corresponde una API con licencia.
- Las personas, clientes, comercios y membresías de los datos de ejemplo son inventados.
