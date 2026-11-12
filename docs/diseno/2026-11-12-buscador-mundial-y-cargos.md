# Diseño: buscador mundial de origen y destino, cargos de la empresa y monitoreo del vuelo

Fecha: 12 de noviembre de 2026. Debe quedar funcionando para la entrega del viernes 13 por la mañana.

## Intención

1. **Cotizar desde y hacia cualquier lugar del mundo.** Hoy el autocompletado conoce 88 aeropuertos. Las grabaciones de la empresa ocurren a menudo en pueblos sin aeropuerto propio (por ejemplo, Moab, en Utah). La persona debe poder escribir un país, una ciudad, un pueblo o un código de aeropuerto, como en Google Flights, y la cotización debe encontrar el **mejor acceso**: no siempre el aeropuerto más cercano, sino el que deja el menor costo total contando el traslado por carretera.
2. **Que cualquier persona de la empresa pueda cotizar y reportar sus viajes.** Editores, desarrolladores, ingenieros de datos y otros viajan igual que los pilotos. Hoy el permiso se llama «piloto», lo que confunde el oficio con lo que se puede hacer en la plataforma.

## Qué se acordó

### Buscador de origen y destino

- **Un solo campo**, como Google Flights. Mientras se escribe, una lista sugiere:
  - lugares (ciudades y pueblos) con su región y país, y debajo sus aeropuertos cercanos con la distancia;
  - aeropuertos por nombre o código IATA;
  - países.
- Dos lugares con el mismo nombre se distinguen por región y país (Moab, Utah, Estados Unidos; Moab, Jordania).
- **Al elegir un lugar, se marcan los aeropuertos a comparar.** La plataforma propone los cercanos y la persona puede quitar alguno.
- **Al elegir un país**, se proponen sus aeropuertos principales para marcar.
- **Mejor acceso:** la comparación suma al costo total el traslado por carretera entre el aeropuerto y el lugar, igual que hoy suma equipaje y riesgo de cambio. El traslado también cuenta para la hora límite de llegada.
- Lo mismo vale para el origen: una persona que sale de un pueblo compara los aeropuertos cercanos a ese pueblo.

Boceto aprobado: un campo con sugerencias (lugar, región, país y aeropuertos cercanos con distancia) y, al elegir, la lista de aeropuertos con casillas y el tiempo estimado por carretera.

### Roles y cargos

- **El permiso** dice qué se puede hacer y sigue teniendo tres niveles:
  - *Colaborador* (hoy «piloto»): cotiza y reporta sus propios viajes y gastos.
  - *Gestor de proyecto*: además ve lo de sus proyectos.
  - *Administración*: ve todo y aprueba.
- **El cargo** dice qué hace la persona en la empresa (pilotaje de dron, edición de video, desarrollo de software, ingeniería de datos, producción y los que se agreguen). Es un dato aparte **sin permisos propios**.
- Administración mantiene la lista de cargos y elige el cargo al crear o editar una cuenta. Agregar un cargo no requiere tocar el código.
- El cargo aparece en la ficha de la persona, en la lista de usuarios y en la analítica (gasto y viajes por cargo).
- Las cuentas que hoy son «piloto» pasan a *colaborador* con el cargo «Pilotaje de dron». Sus viajes, gastos y justificaciones no cambian.
- **Todos viajan** (decisión de la dueña): colaboradores, gestores de proyecto y administración pueden cotizar, recibir un viaje a su nombre, reportar gastos y justificarlos. Toda cuenta tiene perfil de viajero y puede tener cargo.
- **Nadie aprueba lo suyo:** el presupuesto de un viaje y los gastos de una persona de administración los aprueba otra persona de administración. La plataforma lo impide (el botón no aparece y la ruta responde que no se puede), no solo lo oculta.

## Objetivos

- Autocompletado mundial con datos locales (sin llamar a servicios externos para sugerir).
- Comparación de varios aeropuertos de origen y de destino **en una sola búsqueda del plan**: el buscador de vuelos acepta varios códigos separados por coma en `departure_id` y `arrival_id` (verificado en su documentación).
- Traslado por carretera en el costo total, en la hora límite y en el presupuesto del viaje.
- Permiso *colaborador* y cargos administrables.

## No objetivos

- Mapas, rutas reales por carretera o servicios de enrutamiento: la distancia por carretera se estima.
- Tren, bus o ferri como alternativa al vuelo.
- Permisos distintos según el cargo.
- Pantalla de cotización en la web Next.js: la cotización sigue en las pantallas actuales (la API v1 no cubre cotizar).
- Registro abierto de cuentas: las sigue creando administración.
- Despliegue en la nube o migración de la base de la nube.

## Lo que no debe pasar (aunque funcione)

- Que comparar varios aeropuertos gaste más de una búsqueda del plan por consulta.
- Que se proponga un aeropuerto sin vuelos comerciales regulares (pistas privadas, helipuertos, bases militares).
- Que el autocompletado tarde más de lo que tarda en escribirse una letra (objetivo: menos de 300 ms en local).
- Que una cuenta existente pierda acceso o cambie lo que ve tras la migración.
- Que los datos de una persona salgan a un servicio externo al sugerir lugares.

## Restricciones

- Entrega el viernes 13 por la mañana; se demuestra en local (SQLite con `make ejecutar` y PostgreSQL con `make entorno`).
- El mismo código debe funcionar en SQLite y en PostgreSQL.
- Las pruebas corren sin internet y sin claves: usan un subconjunto pequeño de los datos.
- La demostración no puede depender de internet para el autocompletado: los datos quedan en la base local.
- Licencias: OurAirports es de dominio público; GeoNames es CC BY 4.0 y exige citar la fuente (en el README y en un pie discreto del buscador).
- Sin push ni despliegue sin pedirlo. Voz neutra en todo lo versionado.

## Datos

| Fuente | Qué aporta | Tamaño de descarga |
|---|---|---|
| OurAirports `airports.csv` y `countries.csv` | Aeropuertos con código IATA, tipo (grande, mediano, pequeño), si tiene servicio regular, coordenadas, país y municipio | 12,8 MB (se filtra a los que tienen IATA y servicio regular: unos 4.000) |
| GeoNames `cities1000.zip` | Ciudades y pueblos de más de 1.000 habitantes, con nombres alternativos (incluidos los en español), región, país, coordenadas y población | 11,1 MB |
| GeoNames `admin1CodesASCII.txt` | Nombre de la región (estado, departamento, provincia) | Pequeño |

Nombres de países en español: se generan una vez con los nombres de región del estándar ICU (por ejemplo, con `Intl.DisplayNames` de Node) y se guardan en un archivo junto a los datos.

Los datos se preparan con un script (`datos/geografia.py`) que descarga, filtra y escribe archivos compactos en `datos/geografia/`. Esos archivos se versionan para que la demostración y la carga inicial no dependan de internet. La carga a la base la hace la semilla, de forma idempotente.

## Cómo funciona la búsqueda

- Ruta de las pantallas actuales, con sesión: `GET /lugares/buscar?q=&limite=8`, que devuelve JSON.
- Normaliza mayúsculas y tildes. Coincide por inicio de palabra en el nombre, el nombre ASCII y los nombres alternativos; un código de 3 letras coincide exacto con IATA.
- Orden sugerido:
  1. aeropuerto con el código exacto;
  2. lugares con aeropuerto a menos del radio, ordenados por población;
  3. países;
  4. demás lugares.
- Aeropuertos cercanos a un lugar: con servicio regular, dentro de un radio (regla editable, por defecto 400 km), hasta 4, ordenados por distancia. Se marcan los grandes, porque suelen tener más vuelos.

## Cómo cambia la cotización

- El formulario guarda, para origen y destino: el lugar elegido (nombre, coordenadas) y los aeropuertos marcados.
- `precios.buscar_vuelos` acepta listas de códigos y hace **una** consulta con los códigos unidos por coma. La clave de la caché y de las respuestas guardadas usa los códigos ordenados.
- Para cada opción, con el aeropuerto real de salida y de llegada que trae la respuesta:
  - **Distancia por carretera** = distancia en línea recta × 1,3 (factor editable).
  - **Tiempo** = distancia por carretera ÷ 70 km/h (velocidad editable).
  - **Costo del traslado** = distancia por carretera × costo por km (regla editable, por defecto 0,35 USD/km), ida y vuelta. Va en el desglose como «Traslado por carretera desde GJT (225 km, unas 3 h)» con origen «supuesto».
  - La hora límite compara la llegada más el traslado. Si no alcanza, la opción se descarta con su motivo («Con el traslado llega a las 17:40»).
- Si el aeropuerto está a menos de 30 km del lugar, el traslado se trata como el de cualquier ciudad (sin línea extra).
- El presupuesto del viaje incluye el traslado, porque es dinero que se pagará.
- La búsqueda de hotel usa el lugar de destino, no la ciudad del aeropuerto.
- Las respuestas ya guardadas con un solo código (por ejemplo, Miami a Las Vegas) siguen funcionando igual.

### Lo que dice la documentación del buscador (revisada el 12 de noviembre)

- `departure_id` y `arrival_id` aceptan códigos IATA o el identificador de un lugar de Google (kgmid, como `/m/0vzm` para Austin), y varios separados por coma. El kgmid deja que Google elija los aeropuertos de una ciudad, pero no resuelve pueblos ni el traslado por carretera. Por eso se usa la lista de aeropuertos cercanos propia.
- **Ida y vuelta (`type=1`) devuelve solo los vuelos de ida.** Para conocer el vuelo de regreso hace falta otra consulta con el `departure_token` de la opción elegida. Para tener los números de vuelo del regreso, que el monitoreo necesita, al guardar la decisión se hace **una** consulta extra, solo para la opción elegida. Total: una búsqueda al cotizar y una al decidir.
- `deep_search=true` da resultados idénticos a los del navegador, pero tarda más. Queda desactivado por velocidad y como regla editable.
- **Caché del proveedor:** una consulta idéntica (mismos parámetros) dentro de la misma hora se sirve de su caché y **no cuenta** en las búsquedas del mes. Por eso la plataforma nunca envía `no_cache=true` y arma los parámetros siempre en el mismo orden y formato (códigos ordenados), para que un reintento no se cobre dos veces.
- Ideas anotadas para después, sin construir el viernes:
  - `bags=1` cuando viajan baterías, para que el precio ya incluya el equipaje de mano en vez de estimarlo con la regla;
  - `outbound_times` con el rango de llegada, para pedir solo vuelos que lleguen antes de la hora límite;
  - `json_restrictor`, para traer solo los campos que se usan;
  - `booking_token`, para mostrar las opciones de reserva del vuelo elegido;
  - `max_duration` y `layover_duration`, para descartar en origen itinerarios absurdos.
- Otros parámetros útiles para después, fuera de alcance del viernes: `stops` (máximo de escalas), `exclude_basic` (excluir tarifas básicas, solo vuelos nacionales de Estados Unidos), `travel_class`, `adults` (varias personas en el mismo viaje) y `type=3` (multiciudad).

## Roles: cambios concretos

- El valor guardado del rol pasa de `piloto` a `colaborador`, con una migración idempotente que actualiza filas y la restricción de la tabla. El contrato de la API v1 (`Rol`) y la web Next.js se actualizan en el mismo cambio; hoy no hay consumidores externos.
- Tabla `cargos` (nombre único, activo) con cinco cargos iniciales. `usuarios.cargo_id` es opcional.
- Al crear cualquier cuenta (colaborador, gestor o administración) se crea su perfil de viajero, con el cargo como descripción. La migración crea el perfil a las cuentas de gestor y administración que no lo tienen.
- La cotización asigna el viaje a quien cotiza para los tres permisos (hoy solo lo hace para «piloto»). Un gestor o administración puede seguir cotizando para otra persona, como hoy.
- Aprobar o rechazar el presupuesto de un viaje propio, y revisar un gasto propio, se rechaza en el servicio (`viajes.cambiar_estado` y la revisión de gastos), con prueba que lo cubra. Si solo hay una persona de administración, sus viajes y gastos quedan pendientes: se dice en pantalla en lugar de permitir la autoaprobación.
- Administración gestiona los cargos en la pantalla de Usuarios (crear, renombrar, desactivar). Un cargo con personas asignadas no se borra, se desactiva.
- La API v1 añade `cargo` (texto o nulo) a `Persona`; la web Next.js lo muestra bajo el nombre.
- Las vistas de analítica de viajes y gastos incluyen el cargo, y los KPIs muestran gasto y viajes por cargo.

## Monitoreo del vuelo el día del viaje

Lo pidió la dueña: apenas el viaje tiene número de vuelo, administración lo sigue en pantalla y el viajero recibe avisos por Telegram.

- **Tramos del vuelo.** Al guardar la decisión se registran los tramos del vuelo elegido (aerolínea, número de vuelo, fecha, aeropuertos de salida y llegada, horas programadas), tomados de la respuesta del buscador que ya trae `flight_number` por tramo. Tabla nueva `tramos_vuelo`, ligada al viaje, con el último estado conocido.
- **Qué se consulta.** El estado del vuelo con el buscador de Google por número de vuelo (`q = "Flight IB5634"`, bloque «flight result» de SerpAPI): estado, retraso de salida y de llegada en minutos, terminal, puerta y horas reales o estimadas. Los nombres exactos de los campos se confirman con la documentación del proveedor y con una respuesta real guardada en `datos/respaldo/`, que también sirve para la demostración y las pruebas sin gastar búsquedas.
- **Quién lo ve.** Administración, en el tablero de viajes: el día del viaje, cada tramo muestra estado (programado, a tiempo, retrasado, cancelado, aterrizado), minutos de retraso, terminal, puerta y hace cuánto se actualizó. Si la llegada estimada más el traslado supera la hora límite de la grabación, se marca.
- **Cuándo se consulta** (cuidar el plan del buscador: 250 búsquedas al mes):
  - solo el día del vuelo, desde 3 horas antes de la salida programada hasta la llegada;
  - una respuesta se reutiliza 30 minutos;
  - tope de 6 consultas por tramo;
  - la consulta ocurre cuando alguien tiene el tablero abierto (el tablero ya se refresca solo cada 15 s con la pestaña visible) o pulsa «Actualizar ahora», siempre dentro del tope;
  - cada consulta queda en `consultas_buscador` con el tipo `estado_vuelo`.
- **Avisos al viajero por Telegram**, solo cuando algo cambia y lo afecta: retraso nuevo de 15 minutos o más (o que crece 15 minutos más), cancelación, cambio de terminal o de puerta. Nunca un mensaje por cada consulta. Si el viajero no tiene Telegram vinculado, el aviso queda solo en el tablero.
- **Fuera de alcance para el viernes:** un proceso que consulte solo, sin nadie mirando. Necesita una tarea programada en la nube y queda anotado para después.

## Trazabilidad: todo dato queda registrado desde que se carga

Pedido de la dueña durante la construcción. Toda información que entra a la plataforma deja registro de quién, cuándo, de dónde y qué:

- Las cargas de datos de referencia (aeropuertos, lugares, países) quedan en una tabla `cargas_datos` con fuente, archivo, URL, huella del archivo, filas, momento y quién la hizo, incluso cuando una carga repetida no cambia nada.
- Cada cambio de permiso o de cargo, cada lugar elegido al cotizar, cada consulta al buscador (incluido el estado del vuelo), cada traslado calculado (con las reglas y valores usados), cada tramo registrado, cada aviso enviado y cada intento de autoaprobación impedido deja su evento en la bitácora (`eventos`) o en `consultas_buscador`.
- Cada una de estas trazas tiene una prueba que la verifica.

## La opción elegida se carga completa (pedido de la dueña)

Toda búsqueda queda guardada; la opción elegida, además, se carga completa en dos momentos. Referencia: `docs/referencias/serpapi-google-flights/`.

- **Al decidir (2 búsquedas):**
  - regreso con el `departure_token` de la opción, enviando los mismos códigos que la búsqueda original (para aprovechar la caché del proveedor); de los regresos, se toman los que salen del aeropuerto real de llegada y se elige el más barato;
  - opciones de reserva con el `booking_token` de ese regreso: `booking_options` y `baggage_prices` reales. El presupuesto usa la tarifa real cuando existe; si no, la estimada, marcada como tal.
- **Al aprobar (1 búsqueda):** se consulta de nuevo el itinerario fijo con `selected_flights_json` y se registra «precio confirmado» o «precio cambió: antes X, ahora Y». Si sube más que la regla `tolerancia_precio_aprobacion` (5 % por defecto), administración ve la diferencia y la confirma antes de aprobar. Sin clave o si la consulta falla, se aprueba con el aviso «precio no reconfirmado».
- **Seguridad:** antes de guardar una respuesta se elimina `booking_request` (URL y `post_data`). La plataforma nunca ejecuta una reserva; se limpia también la respuesta de tarifas ya versionada.
- **Sin costo de búsquedas,** con lo que ya traen las respuestas: las `extensions` del itinerario corrigen el costo estimado (cambio gratis, cambio con cargo, maleta incluida, reembolso); `often_delayed_by_over_30_min` avisa si el retraso habitual compromete la hora límite; `layovers` avisa de escalas de menos de 60 minutos o nocturnas.

## Proveedor de lugares intercambiable

El autocompletado del buscador usa datos locales en el MVP. El autocompletado de Google queda como proveedor alternativo, apagado por defecto (`PROVEEDOR_LUGARES=local`), para cuando la empresa contrate un plan que lo cubra (`PROVEEDOR_LUGARES=serpapi`). Con ese proveedor cada respuesta también se guarda y se registra.

## Para después de la entrega

- Calendario de precios: botón «¿mover la ida ±3 días ahorra?» y recolector de precios más barato.
- Alerta de ofertas para las rutas frecuentes de la empresa: una consulta semanal por aeropuerto base, cruzada con los destinos más frecuentes.
- Tarifas: rango de precio de la maleta, cargo por cambio y tiquetes separados.

## Decisiones tomadas al revisar el diseño

Decididas por quien diseña (no por la dueña), para que se puedan revisar:

| Tema | Decisión |
|---|---|
| Traslado y carro de alquiler | Sin carro de alquiler, el traslado es taxi o transfer: 0,35 USD/km, ida y vuelta, en un grupo de presupuesto nuevo, `traslados`, que en la comparación con el gasto real corresponde a la categoría transporte. Con carro de alquiler (`carro_dia` > 0), el carro ya cubre el viaje y el traslado solo suma combustible y peajes: 0,12 USD/km, ida y vuelta, en el grupo `combustible`. Las dos tarifas son reglas editables. Así nada se cuenta dos veces |
| Web Next.js | Primero se une la rama `worktree-web-next` a `dev` (ya era el primer paso del viernes); después, este cambio toca API y web juntas en `dev` |
| Elegir un país | Es un atajo para marcar sus aeropuertos principales, no una selección final. Si la persona solo marca aeropuertos, sin un lugar, no hay traslado y el hotel se busca en la ciudad del primer aeropuerto marcado |
| Qué guarda la solicitud | `solicitudes.origen` y `solicitudes.destino` siguen guardando un código de aeropuerto (el más cercano de los marcados), para no romper la API v1, los KPIs ni el modelo de precios. Columnas nuevas: el lugar elegido (nombre, región, país, coordenadas) y la lista de aeropuertos marcados. Al guardar la decisión, origen y destino pasan a los aeropuertos reales del vuelo elegido. Las observaciones del modelo de precios se registran con los aeropuertos reales de cada vuelo |

## Lo que queda a criterio de quien construye

- Estructura exacta de las tablas de geografía y sus índices, mientras la búsqueda cumpla el tiempo objetivo en SQLite y PostgreSQL.
- Cómo se dibujan las sugerencias en la pantalla actual (sin dependencias nuevas de JavaScript).
- El subconjunto de datos para las pruebas.
- Los textos exactos, siguiendo el tono de la plataforma.

## Criterios de aceptación

- Escribir «moab» sugiere Moab, Utah, Estados Unidos, con CNY, GJT y SLC y sus distancias; también Moab, Jordania.
- «Lisboa», «lisboa», «LIS» y «Portugal» llevan a Lisboa o a los aeropuertos de Portugal; «Villa de Leyva» propone Bogotá.
- Una cotización de Miami a Moab con tres aeropuertos marcados gasta **una** búsqueda y deja una fila en `consultas_buscador`.
- El desglose de cada opción muestra el traslado; una opción que con el traslado no llega a la hora límite queda descartada con su motivo.
- Una cuenta con cargo «Edición de video» cotiza, decide, recibe su viaje y reporta gastos igual que un piloto.
- Las cuentas «piloto» existentes siguen entrando y viendo lo mismo, ahora como colaborador con su cargo.
- Una cuenta de gestor cotiza, recibe su viaje y reporta gastos; una de administración también, y no puede aprobar su propio presupuesto ni sus propios gastos.
- Al guardar una decisión quedan registrados sus tramos con número de vuelo; el día del vuelo, el tablero de administración muestra su estado con la respuesta guardada de ejemplo, y un retraso de 15 minutos o más envía un solo aviso por Telegram (probado con el bot simulado).
- El monitoreo nunca pasa de 6 consultas por tramo ni consulta fuera del día del vuelo.
- Linter y todas las pruebas en verde, sin internet.
