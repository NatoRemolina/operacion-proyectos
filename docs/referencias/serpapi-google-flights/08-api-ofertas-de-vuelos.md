# API de ofertas de vuelos de Google (Google Flights Deals API)

> Fuente: <https://serpapi.com/google-flights-deals-api> — consultada el 12 de noviembre de 2026.
> Nombres de parámetros y campos en inglés (así los espera y devuelve la API); explicaciones en español.

## Qué es

Esta API extrae las ofertas de vuelos de Google Flight Deals: destinos con descuento a partir de un aeropuerto o ciudad de salida, sin tener que fijar un destino.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights_deals` |
| Motor (`engine`) | `google_flights_deals` |
| Campos que produce | `departure_informations`, `deals` |
| Disponibilidad publicada (uptime) | 100,000 % |
| Playground | <https://serpapi.com/playground?engine=google_flights_deals> |
| Notas de versión | <https://serpapi.com/google-flights-deals-api/release-notes> |
| Métricas | <https://serpapi.com/google-flights-deals-api/api-metrics> |

Diferencia con el motor principal: en `google_flights` se sabe a dónde se va; aquí se pregunta "¿a dónde puedo ir barato desde aquí?". No existe `arrival_id`.

---

## Parámetros

### Resumen

| Parámetro | Obligatorio | Por defecto | Para qué sirve |
| --- | --- | --- | --- |
| `engine` | Sí | — | Debe ser `google_flights_deals` |
| `api_key` | Sí | — | Clave privada de SerpApi |
| `departure_id` | No | — | Aeropuerto(s) o ubicación de salida |
| `gl` | No | — | País de la búsqueda |
| `hl` | No | — | Idioma de la búsqueda |
| `currency` | No | `USD` | Moneda de los precios |
| `query` | No | — | Consulta en lenguaje natural |
| `type` | No | `1` (ida y vuelta) | Tipo de vuelo |
| `travel_class` | No | `1` (Economy) | Clase de viaje |
| `outbound_date` | No | — | Fecha o ventana de salida |
| `return_date` | No | — | Fecha o ventana de regreso |
| `travel_duration` | No | `1` (1 semana) | Duración preestablecida del viaje |
| `trip_length` | No | — | Duración personalizada en días |
| `adults` | No | `1` | Número de adultos |
| `children` | No | `0` | Número de niños |
| `infants_in_seat` | No | `0` | Bebés con asiento |
| `infants_on_lap` | No | `0` | Bebés en regazo |
| `stops` | No | `0` (cualquiera) | Número de escalas |
| `exclude_airlines` | No | — | Aerolíneas a excluir |
| `include_airlines` | No | — | Aerolíneas a incluir |
| `max_price` | No | sin límite | Precio máximo |
| `max_duration` | No | — | Duración máxima del vuelo (min) |
| `no_cache` | No | `false` | Forzar búsqueda sin caché |
| `async` | No | `false` | Envío asíncrono |
| `zero_trace` | No | `false` | Modo ZeroTrace (solo Enterprise) |
| `output` | No | `json` | Formato de salida |
| `json_restrictor` | No | — | Limitar los campos devueltos |

### Consulta de búsqueda

#### `departure_id` — Opcional

Define el código del aeropuerto de salida o el kgmid de la ubicación.

- Un código de aeropuerto es un código de 3 letras mayúsculas. Se puede buscar con la [API de autocompletado de Google Flights](https://serpapi.com/google-flights-autocomplete-api) o en [IATA](https://www.iata.org/en/publications/directories/code-search). Por ejemplo, `CDG` es el Aeropuerto Charles de Gaulle de París y `AUS` es el Aeropuerto Internacional Austin-Bergstrom.
- Un kgmid de ubicación es una cadena que empieza por `/m/` o `/g/`. Se busca la ubicación en [Wikidata](https://www.wikidata.org/) y se usa su "Freebase ID". Por ejemplo, `/m/0vzm` es el kgmid de Austin, TX.
- Se pueden indicar varios aeropuertos de salida separados por coma. Por ejemplo: `CDG,ORY,/m/04jpl`.

### Localización

#### `gl` — Opcional

País de la búsqueda; código de dos letras (`us`, `uk`, `fr`). Lista: [Google countries](https://serpapi.com/google-countries).

#### `hl` — Opcional

Idioma de la búsqueda; código de dos o tres letras (`en`, `es`, `fr`), opcionalmente con código de región (`en-gb`, `es-419`). Lista: [Google languages](https://serpapi.com/google-languages).

#### `currency` — Opcional

Moneda de los precios devueltos. Por defecto `USD`. Lista: [Google Travel Currencies](https://serpapi.com/google-travel-currencies).

### Parámetros avanzados

#### `query` — Opcional

Define la consulta en lenguaje natural para Google Flights Deals. Por ejemplo: `High rises`, `beach vacation next month`.

No se puede combinar con `travel_duration` ni con `trip_length`: la duración del viaje se describe dentro del propio `query`.

#### `type` — Opcional

| Valor | Significado |
| --- | --- |
| `1` | Ida y vuelta (por defecto) |
| `2` | Solo ida |

#### `travel_class` — Opcional

| Valor | Significado |
| --- | --- |
| `1` | Economy (por defecto) |
| `2` | Premium economy |
| `3` | Business |
| `4` | First |

### Parámetros de fecha

#### `outbound_date` — Opcional

Define cuándo se quiere salir. Admite dos formas:

- **Una sola fecha** `YYYY-MM-DD` para una fecha de salida exacta: `2026-11-13`.
- **Dos fechas separadas por coma** para una ventana flexible de salida: `2026-11-13,2026-12-12`.

Reglas:

- Con **una sola fecha**: `return_date` (fecha única) es obligatorio para vuelos de ida y vuelta.
- Con **un rango**: opcionalmente se combina con uno de `return_date` (como rango), `travel_duration` o `trip_length` para controlar la duración del viaje. Si no se envía ninguno, se devuelven ofertas de cualquier duración.
- Si se omite por completo, se devuelven ofertas de cualquier fecha.

#### `return_date` — Opcional

Define cuándo se quiere regresar. Admite las mismas dos formas:

- `2026-11-19` — regresar en esa fecha exacta (se usa con un `outbound_date` único).
- `2026-11-19,2026-12-19` — regresar en cualquier momento de esa ventana (se usa con un `outbound_date` de rango).

Reglas:

- No está disponible para vuelos de solo ida (`type=2`).
- Una `return_date` única debe ir con una `outbound_date` única. Una `return_date` de rango debe ir con una `outbound_date` de rango.
- No se puede combinar con `travel_duration` ni con `trip_length` (se usa uno u otro para definir la duración del viaje).

#### `travel_duration` — Opcional

Define una duración de viaje preestablecida cuando se busca con fechas flexibles.

| Valor | Significado |
| --- | --- |
| `1` | 1 semana (por defecto) |
| `2` | Fin de semana |
| `3` | 2 semanas |

Se puede usar solo (ofertas de esa duración, cualquier fecha de salida) o con `outbound_date` como rango (por ejemplo `2026-11-13,2026-12-12`) para limitar la ventana de salida.

No se puede combinar con `return_date`, `trip_length` ni `query`. No está disponible para solo ida (`type=2`).

#### `trip_length` — Opcional

Define una duración personalizada del viaje, en días, cuando se busca con fechas flexibles. Se da un número para una duración exacta, o dos números separados por coma para un rango mínimo/máximo.

- `7` — exactamente 7 días.
- `5,10` — entre 5 y 10 días.

Se puede usar solo (ofertas de esa duración, cualquier fecha de salida) o con `outbound_date` como rango para limitar la ventana de salida.

No se puede combinar con `return_date`, `travel_duration` ni `query`. No está disponible para solo ida (`type=2`).

Cada valor debe ser al menos `1`. Cuando se dan dos valores, el primero (mínimo) debe ser menor o igual que el segundo (máximo).

### Número de pasajeros

| Parámetro | Descripción | Por defecto |
| --- | --- | --- |
| `adults` | Número de adultos | `1` |
| `children` | Número de niños | `0` |
| `infants_in_seat` | Bebés con asiento | `0` |
| `infants_on_lap` | Bebés en regazo | `0` |

### Filtros avanzados

#### `stops` — Opcional

| Valor | Significado |
| --- | --- |
| `0` | Cualquier número de escalas (por defecto) |
| `1` | Solo vuelos directos (nonstop) |
| `2` | 1 escala o menos |
| `3` | 2 escalas o menos |

#### `exclude_airlines` — Opcional

Códigos de aerolíneas a excluir, separados por coma. Cada código es un IATA de 2 caracteres (dos letras mayúsculas, o una letra mayúscula y un dígito); por ejemplo `UA` es United Airlines. También se admiten alianzas: `STAR_ALLIANCE`, `SKYTEAM`, `ONEWORLD`.

No se puede usar junto con `include_airlines`.

#### `include_airlines` — Opcional

Códigos de aerolíneas a incluir, separados por coma. Mismo formato que `exclude_airlines`, incluidas las alianzas.

No se puede usar junto con `exclude_airlines`.

#### `max_price` — Opcional

Precio máximo del tiquete. Por defecto, sin límite.

#### `max_duration` — Opcional

Duración máxima del vuelo, en minutos. Por ejemplo, `1500` para 25 horas.

Si la búsqueda no devuelve resultados, conviene aumentar `max_duration` hasta en `200` minutos para compensar las variaciones de programación propias de cada ruta.

### Parámetros de SerpApi

#### `engine` — Obligatorio

Debe valer `google_flights_deals`.

#### `api_key` — Obligatorio

Clave privada de SerpApi.

#### `no_cache` — Opcional

Fuerza a traer los resultados aunque exista versión en caché. La caché solo se sirve si la consulta y todos los parámetros son exactamente iguales, y expira después de 1 hora. Las búsquedas desde caché son gratis y no cuentan en el límite mensual. Valores: `false` (por defecto) o `true`. No usar junto con `async`.

#### `async` — Opcional

`false` (por defecto) mantiene la conexión HTTP abierta; `true` solo envía la búsqueda y los resultados se recuperan con la [Searches Archive API](https://serpapi.com/search-archive-api). No usar junto con `no_cache`, ni en cuentas con [Ludicrous Speed](https://serpapi.com/plan).

#### `zero_trace` — Opcional

Solo Enterprise. Activa el [modo ZeroTrace](https://serpapi.com/zero-trace-mode). Valores: `false` (por defecto) o `true`.

#### `output` — Opcional

`json` (por defecto), `html` o `md`.

#### `json_restrictor` — Opcional

Limita los campos de la salida. Ver [JSON Restrictor](https://serpapi.com/json-restrictor).

### Tabla de incompatibilidades

| Parámetro | No se puede combinar con | Otras restricciones |
| --- | --- | --- |
| `query` | `travel_duration`, `trip_length` | La duración se describe dentro del texto |
| `return_date` | `travel_duration`, `trip_length` | No disponible en `type=2`; el formato debe coincidir con el de `outbound_date` (única con única, rango con rango) |
| `travel_duration` | `return_date`, `trip_length`, `query` | No disponible en `type=2` |
| `trip_length` | `return_date`, `travel_duration`, `query` | No disponible en `type=2`; cada valor ≥ 1 y mínimo ≤ máximo |
| `include_airlines` | `exclude_airlines` | — |

---

## Resultados

### Resultados JSON

La salida JSON incluye datos estructurados de [Flight Results](https://serpapi.com/google-flights-results) y [Price Insights](https://serpapi.com/google-flights-price-insights). El estado está en `search_metadata.status` y fluye así: `Processing` → `Success` || `Error`. Si falla, `error` contiene el mensaje. `search_metadata.id` es el ID de la búsqueda dentro de SerpApi.

En `search_metadata` aparece `google_flights_deals_url`, el equivalente de la búsqueda en Google (`https://www.google.com/travel/flights/deals?...`).

### Resultados HTML

Esta API no tiene respuesta HTML completa, solo texto. `search_metadata.prettify_html_file` contiene el enlace a la versión formateada que se ve en el playground.

### Resultados Markdown

Markdown optimizado para LLM y agentes de IA, con tablas, enlaces y metadatos YAML. Se accede con `output=md`, el endpoint `/search.md` o la cabecera `Accept: text/markdown`.

### `departure_informations`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `airport_name` | String | Nombre del aeropuerto de salida. **No aparece** cuando `departure_id` es un ID de ciudad |
| `airport_code` | String | Código IATA del aeropuerto de salida. **No aparece** cuando `departure_id` es un ID de ciudad |
| `city` | String | Nombre de la ciudad de salida |
| `city_id` | String | ID del Knowledge Graph de la ciudad de salida (por ejemplo `/m/05qtj`) |
| `country` | String | Nombre del país de salida. **No aparece** cuando `departure_id` es un ID de ciudad |
| `gps_coordinates.latitude` | Float | Latitud del aeropuerto de salida |
| `gps_coordinates.longitude` | Float | Longitud del aeropuerto de salida |

### `deals[]`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `destination_id` | String | ID del Knowledge Graph del destino (por ejemplo `/m/0k02q`) |
| `name` | String | Nombre de la ciudad de destino |
| `country` | String | Nombre del país de destino |
| `price` | Number | Precio de la oferta en la moneda seleccionada |
| `average_price` | Number | Precio promedio de esa ruta. No siempre está presente |
| `discount_percentage` | Number | Porcentaje de descuento frente al precio promedio. No siempre está presente |
| `flight_link` | String | Enlace directo al vuelo en Google Flights |
| `serpapi_flight_link` | String | Enlace de SerpApi para obtener la información detallada del vuelo |
| `thumbnail` | String | URL de la imagen del destino |
| `start_date` | String | Fecha del vuelo de ida (`YYYY-MM-DD`) |
| `end_date` | String | Fecha del vuelo de regreso (`YYYY-MM-DD`). No aparece en solo ida |
| `departure_airport_code` | String | Código IATA del aeropuerto de salida |
| `arrival_airport_code` | String | Código IATA del aeropuerto de llegada |
| `flight_duration` | Integer | Duración total del vuelo, en minutos |
| `stops` | Integer | Número de escalas (`0` en vuelos directos) |
| `airline` | String | Nombre de la aerolínea. No siempre está presente |
| `airline_code` | String | Código IATA de la aerolínea. No siempre está presente |
| `description` | String | Descripción corta del destino. No siempre está presente |
| `highlights` | String | Puntos destacados del destino |

Detalle observado: en el ejemplo con `query`, los elementos de `deals` traen las fechas en los campos `outbound_date` y `return_date` en lugar de `start_date` y `end_date`. Conviene leer ambos nombres al parsear.

El campo `serpapi_flight_link` es el puente hacia el motor principal: lleva a una búsqueda de `engine=google_flights` con el itinerario concreto de esa oferta.

---

## Ejemplos

### 1. `departure_id=CDG`

```
GET https://serpapi.com/search.json?engine=google_flights_deals&departure_id=CDG&currency=USD&gl=us&hl=en&api_key=TU_API_KEY
```

```json
{
"search_metadata": {
    "id": "69df341afe1c6b0c8741b97a",
    "status": "Success",
    "json_endpoint": "https://serpapi.com/searches/.../69df341afe1c6b0c8741b97a.json",
    "created_at": "2026-04-15 06:45:46 UTC",
    "processed_at": "2026-04-15 06:45:46 UTC",
    "google_flights_deals_url": "https://www.google.com/travel/flights/deals?hl=en&gl=us&curr=USD&tfs=...",
    "raw_html_file": "https://serpapi.com/searches/.../69df341afe1c6b0c8741b97a.html",
    "prettify_html_file": "https://serpapi.com/searches/.../69df341afe1c6b0c8741b97a.prettify",
    "total_time_taken": 1.05
},
"search_parameters": {
    "engine": "google_flights_deals",
    "hl": "en",
    "gl": "us",
    "departure_id": "CDG",
    "currency": "USD"
},
"departure_informations": {
    "airport_name": "Paris Charles de Gaulle Airport",
    "airport_code": "CDG",
    "city": "Paris",
    "city_id": "/m/05qtj",
    "country": "France",
    "gps_coordinates": {
      "latitude": 49.0097222,
      "longitude": 2.54777778
    }
},
"deals": [
    {
      "destination_id": "/m/0k02q",
      "name": "São Vicente",
      "country": "Cape Verde",
      "price": 468,
      "average_price": 2023,
      "discount_percentage": 77,
      "flight_link": "<URL de Google Flights>",
      "serpapi_flight_link": "<URL de SerpApi>",
      "thumbnail": "<URL de imagen>",
      "start_date": "2026-09-21",
      "end_date": "2026-09-27",
      "departure_airport_code": "CDG",
      "arrival_airport_code": "VXE",
      "flight_duration": 350,
      "stops": 0,
      "airline": "Cabo Verde Airlines",
      "airline_code": "VR",
      "description": "Cape Verde island with beaches, colonial buildings in Mindelo city & Parque Natural Monte Verde.",
      "highlights": "Port city of Mindelo & Monte Verde park"
    },
    {
      "destination_id": "/m/04yqyw",
      "name": "Calvi",
      "country": "France",
      "price": 118,
      "average_price": 476,
      "discount_percentage": 75,
      "start_date": "2026-06-28",
      "end_date": "2026-07-04",
      "departure_airport_code": "CDG",
      "arrival_airport_code": "CLY",
      "flight_duration": 110,
      "stops": 0,
      "airline": "easyJet",
      "airline_code": "U2",
      "description": "Corsican town with a medieval citadel, the cathedral of St-Jean-Baptiste, & Quai Landry esplanade.",
      "highlights": "St-Jean-Baptiste Cathedral & Quai Landry"
    },
    {
      "destination_id": "/m/01_8b9",
      "name": "Tetouan",
      "country": "Morocco",
      "price": 175,
      "average_price": 560,
      "discount_percentage": 69,
      "start_date": "2026-06-04",
      "end_date": "2026-06-11",
      "departure_airport_code": "CDG",
      "arrival_airport_code": "TTU",
      "flight_duration": 175,
      "stops": 0,
      "airline": "Royal Air Maroc",
      "airline_code": "AT",
      "highlights": "Beach and palace"
    },
    ...
]
}
```

La tercera oferta no trae `description`: es uno de los campos que "no siempre está presente".

### 2. `departure_id=/m/04jpl` (Londres, ID de ciudad)

```
GET https://serpapi.com/search.json?engine=google_flights_deals&departure_id=/m/04jpl&currency=USD&gl=us&hl=en&api_key=TU_API_KEY
```

```json
{
...
"departure_informations": {
    "city": "London",
    "city_id": "/m/04jpl"
},
"deals": [
    {
      "destination_id": "/m/016d7r",
      "name": "Santander",
      "country": "Spain",
      "price": 41,
      "average_price": 203,
      "discount_percentage": 80,
      "start_date": "2026-04-20",
      "end_date": "2026-04-28",
      "departure_airport_code": "STN",
      "arrival_airport_code": "SDR",
      "flight_duration": 120,
      "stops": 0,
      "description": "Spanish city on the Bay of Santander with the Palacio de la Magdalena & a striking cathedral.",
      "highlights": "Palacio de la Magdalena, cathedral & bay"
    },
    {
      "destination_id": "/m/09b83",
      "name": "Strasbourg",
      "country": "France",
      "price": 65,
      "average_price": 313,
      "discount_percentage": 79,
      ...
    },
    ...
]
}
```

Dos diferencias clave frente al ejemplo 1:

- `departure_informations` solo trae `city` y `city_id` (no hay `airport_name`, `airport_code`, `country` ni `gps_coordinates`), porque se buscó por ciudad.
- Cada oferta indica en `departure_airport_code` el aeropuerto concreto que usó (aquí `STN`, Stansted), que puede variar de una oferta a otra.

### 3. Solo ida (`type=2`)

```
GET https://serpapi.com/search.json?engine=google_flights_deals&departure_id=MAD&type=2&currency=USD&gl=us&hl=en&api_key=TU_API_KEY
```

```json
{
...
"search_parameters": {
    "engine": "google_flights_deals",
    "hl": "en",
    "gl": "us",
    "type": "2",
    "departure_id": "MAD",
    "currency": "USD"
},
"departure_informations": {
    "airport_name": "Adolfo Suárez Madrid-Barajas Airport",
    "airport_code": "MAD",
    "city": "Madrid",
    "city_id": "/m/056_y",
    "country": "Spain",
    "gps_coordinates": { "latitude": 40.4997222, "longitude": -3.5655556 }
},
"deals": [
    {
      "destination_id": "/m/0ccn5",
      "name": "Alghero",
      "country": "Italy",
      "price": 36,
      "average_price": 135,
      "discount_percentage": 74,
      ...
    },
    ...
]
}
```

En solo ida las ofertas no traen `end_date`.

### 4. Filtrando por aerolíneas (`include_airlines`)

También se pueden filtrar los resultados por aerolíneas específicas usando `include_airlines`. En este ejemplo se incluyen Wizz Air (`W4`) y Ryanair (`FR`).

```
GET https://serpapi.com/search.json?engine=google_flights_deals&departure_id=/m/0947l&include_airlines=W4,FR&currency=USD&gl=us&hl=en&api_key=TU_API_KEY
```

### 5. Fechas exactas (`outbound_date` + `return_date`)

Se usan `outbound_date` y `return_date` para buscar ofertas en fechas específicas. Ambos parámetros usan el formato `YYYY-MM-DD`. Para vuelos de solo ida (`type=2`) solo se necesita `outbound_date`.

```
GET https://serpapi.com/search.json?engine=google_flights_deals&departure_id=FCO&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&gl=us&hl=en&api_key=TU_API_KEY
```

### 6. Rangos de fechas flexibles (`outbound_date` como rango + `travel_duration`)

Se usa una `outbound_date` separada por coma para buscar ofertas dentro de una ventana de fechas. Se combina con `travel_duration` para fijar la duración del viaje. Como alternativa se puede usar `trip_length` para una duración personalizada (por ejemplo `5,10` para 5 a 10 días), o `return_date` como rango separado por coma para una ventana de regreso específica.

```
GET https://serpapi.com/search.json?engine=google_flights_deals&departure_id=BCN&outbound_date=2026-11-13,2026-12-12&travel_duration=3&currency=USD&gl=us&hl=en&api_key=TU_API_KEY
```

Aquí `travel_duration=3` son 2 semanas, dentro de una ventana de salida del 13 de noviembre al 12 de diciembre.

### 7. Consulta en lenguaje natural (`query`)

```
GET https://serpapi.com/search.json?engine=google_flights_deals&departure_id=CDG&query=High+rises&currency=USD&gl=us&hl=en&api_key=TU_API_KEY
```

```json
{
...
"deals": [
    {
      "destination_id": "/m/0gxj",
      "name": "Abu Dhabi",
      "country": "United Arab Emirates",
      "price": 345,
      "average_price": 590,
      "discount_percentage": 41,
      "flight_link": "<URL>",
      "serpapi_flight_link": "<URL>",
      "thumbnail": "<URL>",
      "outbound_date": "2026-10-03",
      "return_date": "2026-10-09",
      "departure_airport_code": "CDG",
      "arrival_airport_code": "AUH",
      "flight_duration": 780,
      "stops": 1,
      "airline": "Pegasus",
      "airline_code": "..."
    },
    ...
]
}
```

Aquí las fechas vienen como `outbound_date` / `return_date` en vez de `start_date` / `end_date`.

---

## Resumen de la estructura (tal como la documenta SerpApi)

```json
{
  ...
  "departure_informations": {
    "airport_name": "String - Name of the departure airport. Not present when departure_id is a city ID",
    "airport_code": "String - IATA code of the departure airport. Not present when departure_id is a city ID",
    "city": "String - Name of the departure city",
    "city_id": "String - Google knowledge graph ID of the departure city (e.g. /m/05qtj)",
    "country": "String - Name of the departure country. Not present when departure_id is a city ID",
    "gps_coordinates": {
      "latitude": "Float - Latitude of the departure airport",
      "longitude": "Float - Longitude of the departure airport"
    }
  },
  "deals": [
    {
      "destination_id": "String - Google knowledge graph ID of the destination (e.g. /m/0k02q)",
      "name": "String - Name of the destination city",
      "country": "String - Name of the destination country",
      "price": "Number - Price of the flight deal in the selected currency",
      "average_price": "Number - Average price for this route. Not always present",
      "discount_percentage": "Number - Discount percentage compared to the average price. Not always present",
      "flight_link": "String - Direct link to the flight on Google Flights",
      "serpapi_flight_link": "String - SerpApi link to retrieve detailed flight information",
      "thumbnail": "String - URL of the destination thumbnail image",
      "start_date": "String - Outbound flight date (YYYY-MM-DD)",
      "end_date": "String - Return flight date (YYYY-MM-DD). Not present for one-way flights",
      "departure_airport_code": "String - IATA code of the departure airport",
      "arrival_airport_code": "String - IATA code of the arrival airport",
      "flight_duration": "Integer - Total flight duration in minutes",
      "stops": "Integer - Number of stops (0 for non-stop flights)",
      "airline": "String - Name of the airline. Not always present",
      "airline_code": "String - IATA code of the airline. Not always present",
      "description": "String - Short description of the destination. Not always present",
      "highlights": "String - Key highlights of the destination"
    }
  ]
}
```

## Relacionado

- Motor principal: [01-api-google-flights.md](01-api-google-flights.md)
- Para resolver `departure_id` desde texto: [06-api-autocompletado.md](06-api-autocompletado.md)
- Precios por fecha de una ruta concreta: [07-api-google-flights-calendar.md](07-api-google-flights-calendar.md)
