# API de Google Flights Calendar (Google Flights Calendar API)

> Fuente: <https://serpapi.com/google-flights-calendar-api> — consultada el 12 de noviembre de 2026.
> Nombres de parámetros y campos en inglés (así los espera y devuelve la API); explicaciones en español.

## Qué es

Esta API extrae los precios del calendario de Google Flights: el precio más bajo para cada fecha dentro de un rango, que es lo que se ve en la cuadrícula de meses de Google Flights.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights_calendar` |
| Motor (`engine`) | `google_flights_calendar` |
| Campo que produce | `prices` |
| Disponibilidad publicada (uptime) | 100,000 % |
| Playground | <https://serpapi.com/playground?engine=google_flights_calendar> |
| Notas de versión | <https://serpapi.com/google-flights-calendar-api/release-notes> |
| Métricas | <https://serpapi.com/google-flights-calendar-api/api-metrics> |

Diferencia con el motor principal: `google_flights` devuelve itinerarios concretos para una fecha; `google_flights_calendar` devuelve un precio por fecha en todo un rango, sin detalle de vuelos.

---

## Parámetros

### Resumen

| Parámetro | Obligatorio | Por defecto | Para qué sirve |
| --- | --- | --- | --- |
| `engine` | Sí | — | Debe ser `google_flights_calendar` |
| `api_key` | Sí | — | Clave privada de SerpApi |
| `departure_id` | **Sí** | — | Aeropuerto o ubicación de salida |
| `arrival_id` | **Sí** | — | Aeropuerto o ubicación de llegada |
| `gl` | No | — | País de la búsqueda |
| `hl` | No | — | Idioma de la búsqueda |
| `currency` | No | `USD` | Moneda de los precios |
| `type` | No | `1` (ida y vuelta) | Tipo de vuelo |
| `date_range_start` | No | hoy | Inicio del rango de fechas |
| `date_range_end` | No | fin del mes siguiente | Fin del rango de fechas |
| `round_trip_days` | No | `7` | Días de duración del viaje de ida y vuelta |
| `fixed_outbound_date` | No | `false` | Fijar la fecha de ida |
| `travel_class` | No | `1` (Economy) | Clase de viaje |
| `adults` | No | `1` | Número de adultos |
| `children` | No | `0` | Número de niños |
| `infants_in_seat` | No | `0` | Bebés con asiento |
| `infants_on_lap` | No | `0` | Bebés en regazo |
| `no_cache` | No | `false` | Forzar búsqueda sin caché |
| `async` | No | `false` | Envío asíncrono |
| `zero_trace` | No | `false` | Modo ZeroTrace (solo Enterprise) |
| `output` | No | `json` | Formato de salida |
| `json_restrictor` | No | — | Limitar los campos devueltos |

Ojo: a diferencia del motor principal, aquí `departure_id` y `arrival_id` son **obligatorios**.

### Consulta de búsqueda

#### `departure_id` — Obligatorio

Define el código del aeropuerto de salida o el kgmid de la ubicación.

- Un código de aeropuerto es un código de 3 letras mayúsculas. Se puede buscar en [Google Flights](https://www.google.com/travel/flights) o en [IATA](https://www.iata.org/en/publications/directories/code-search). Por ejemplo, `CDG` es el Aeropuerto Charles de Gaulle de París y `AUS` es el Aeropuerto Internacional Austin-Bergstrom.
- Un kgmid de ubicación es una cadena que empieza por `/m/`. Se busca la ubicación en [Wikidata](https://www.wikidata.org/) y se usa su "Freebase ID". Por ejemplo, `/m/0vzm` es el kgmid de Austin, TX.

Nota: en este motor la documentación solo menciona el prefijo `/m/` (en el motor principal menciona `/m/` o `/g/`), y no indica que se puedan combinar varios aeropuertos con coma.

#### `arrival_id` — Obligatorio

Define el código del aeropuerto de llegada o el kgmid de la ubicación, con el mismo formato que `departure_id`.

### Localización

#### `gl` — Opcional

País de la búsqueda; código de dos letras (`us`, `uk`, `fr`). Lista: [Google countries](https://serpapi.com/google-countries).

#### `hl` — Opcional

Idioma de la búsqueda; código de **dos letras** (`en`, `es`, `fr`). Lista: [Google languages](https://serpapi.com/google-languages).

#### `currency` — Opcional

Moneda de los precios devueltos. Por defecto `USD`. Lista: [Google Travel Currencies](https://serpapi.com/google-travel-currencies).

### Parámetros avanzados

#### `type` — Opcional

Tipo de vuelo.

| Valor | Significado |
| --- | --- |
| `1` | Ida y vuelta (por defecto) |
| `2` | Solo ida |

Este motor **no** admite multiciudad.

#### `date_range_start` — Opcional

Fecha de inicio del rango. Formato `YYYY-MM-DD`, por ejemplo `2026-11-11`. Por defecto, la fecha de hoy.

Cuando `fixed_outbound_date` está en `true`, esta fecha se usa además como fecha de ida.

#### `date_range_end` — Opcional

Fecha final del rango. Formato `YYYY-MM-DD`, por ejemplo `2026-12-31`. Por defecto, el fin del mes siguiente.

#### `round_trip_days` — Opcional

Número de días del viaje de ida y vuelta. Por defecto `7`. Solo se puede usar con `type=1` (ida y vuelta).

No se puede usar junto con `fixed_outbound_date`.

#### `fixed_outbound_date` — Opcional

Define si la fecha de ida es fija.

- `true`: se sale en `date_range_start` y se obtiene un precio para **cada fecha de regreso** dentro del rango.
- `false` (por defecto): se obtiene un precio para **cada fecha de ida** dentro del rango, con una duración de viaje de `round_trip_days`.

Solo se puede usar con `type=1` (ida y vuelta). No se puede usar junto con `round_trip_days`.

#### `travel_class` — Opcional

| Valor | Significado |
| --- | --- |
| `1` | Economy (por defecto) |
| `2` | Premium economy |
| `3` | Business |
| `4` | First |

### Número de pasajeros

| Parámetro | Descripción | Por defecto |
| --- | --- | --- |
| `adults` | Número de adultos | `1` |
| `children` | Número de niños | `0` |
| `infants_in_seat` | Bebés con asiento | `0` |
| `infants_on_lap` | Bebés en regazo | `0` |

### Parámetros de SerpApi

#### `engine` — Obligatorio

Debe valer `google_flights_calendar`.

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

### Combinaciones válidas

| Lo que se quiere | Parámetros |
| --- | --- |
| Precio por cada fecha de salida, viajes de 7 días | `type=1` (y opcionalmente `round_trip_days`) |
| Precio por cada fecha de salida, viajes de N días | `type=1` + `round_trip_days=N` |
| Salida fija, precio por cada fecha de regreso | `type=1` + `fixed_outbound_date=true` + `date_range_start` |
| Precio por cada fecha, solo ida | `type=2` |

`round_trip_days` y `fixed_outbound_date` son mutuamente excluyentes, y ambos requieren `type=1`.

---

## Resultados

### Resultados JSON

La salida JSON incluye datos estructurados en `prices`. El estado está en `search_metadata.status` y fluye así: `Processing` → `Success` || `Error`. Si falla, `error` contiene el mensaje. `search_metadata.id` es el ID de la búsqueda dentro de SerpApi.

En `search_metadata` aparece además `google_flights_calendar_url`, el equivalente de la búsqueda en Google Flights.

### Resultados HTML

Esta API no tiene respuesta HTML completa, solo texto. `search_metadata.prettify_html_file` contiene el enlace a la versión formateada que se ve en el playground.

### Resultados Markdown

Markdown optimizado para LLM y agentes de IA, con tablas, enlaces y metadatos YAML. Se accede con `output=md`, el endpoint `/search.md` o la cabecera `Accept: text/markdown`.

### Campos de `prices[]`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `outbound_date` | String | Fecha de ida |
| `return_date` | String | Fecha de regreso, si el tipo de vuelo es "Round trip" |
| `price` | Integer | Precio en la moneda seleccionada (por defecto USD) |
| `low_price` | Boolean | Indica si el precio está dentro del 5 % del precio mínimo del rango de fechas solicitado |

Detalles observados:

- `low_price` solo aparece cuando es `true`; en los demás elementos el campo simplemente no está.
- En solo ida (`type=2`) los elementos no traen `return_date`.
- `price` es un entero en la moneda pedida (en PKR, por ejemplo, salen valores como 59163).

---

## Ejemplos

### 1. Ida y vuelta de 7 días, CDG → AUS

```
GET https://serpapi.com/search.json?engine=google_flights_calendar&departure_id=CDG&arrival_id=AUS&type=1&currency=USD&api_key=TU_API_KEY
```

```json
{
"search_metadata": {
    "id": "6968ee37fc8a2ba83a6be0c7",
    "status": "Success",
    "json_endpoint": "https://serpapi.com/searches/.../6968ee37fc8a2ba83a6be0c7.json",
    "created_at": "2026-01-15 13:40:07 UTC",
    "processed_at": "2026-01-15 13:40:07 UTC",
    "google_flights_calendar_url": "https://www.google.com/travel/flights?hl=en&gl=us",
    "prettify_html_file": "https://serpapi.com/searches/.../6968ee37fc8a2ba83a6be0c7.prettify",
    "total_time_taken": 1.12
},
"search_parameters": {
    "engine": "google_flights_calendar",
    "type": "1",
    "departure_id": "CDG",
    "arrival_id": "AUS"
},
"prices": [
    { "outbound_date": "2026-01-15", "return_date": "2026-01-22", "price": 1893 },
    { "outbound_date": "2026-01-16", "return_date": "2026-01-23", "price": 1288 },
    { "outbound_date": "2026-01-17", "return_date": "2026-01-24", "price": 1312 },
    { "outbound_date": "2026-01-18", "return_date": "2026-01-25", "price": 1351 },
    { "outbound_date": "2026-01-19", "return_date": "2026-01-26", "price": 1214 },
    { "outbound_date": "2026-01-20", "return_date": "2026-01-27", "price": 1214 },
    { "outbound_date": "2026-01-21", "return_date": "2026-01-28", "price": 1214 },
    { "outbound_date": "2026-01-22", "return_date": "2026-01-29", "price": 1214, "low_price": true },
    ...
]
}
```

Nótese cómo `return_date` es siempre `outbound_date + 7 días`: ese es el efecto de `round_trip_days` con su valor por defecto.

### 2. Solo ida, KHI → ISB, en rupias paquistaníes

```
GET https://serpapi.com/search.json?engine=google_flights_calendar&departure_id=KHI&arrival_id=ISB&type=2&currency=PKR&api_key=TU_API_KEY
```

```json
{
"search_metadata": {
    "id": "6968feddfc8a2ba837a46a50",
    "status": "Success",
    "created_at": "2026-01-15 14:51:09 UTC",
    "processed_at": "2026-01-15 14:51:09 UTC",
    "google_flights_calendar_url": "https://www.google.com/travel/flights?hl=en&gl=us",
    "total_time_taken": 1.55
},
"search_parameters": {
    "engine": "google_flights_calendar",
    "type": "2",
    "departure_id": "KHI",
    "arrival_id": "ISB",
    "currency": "PKR"
},
"prices": [
    { "outbound_date": "2026-01-15", "price": 59163 },
    { "outbound_date": "2026-01-16", "price": 27009 },
    { "outbound_date": "2026-01-17", "price": 25061 },
    { "outbound_date": "2026-01-18", "price": 27009 },
    { "outbound_date": "2026-01-19", "price": 24950 },
    ...
]
}
```

Sin `return_date`, porque es solo ida.

### 3. Ejemplo del playground (CDG → AUS en USD)

```
GET https://serpapi.com/search.json?engine=google_flights_calendar&departure_id=CDG&arrival_id=AUS&currency=USD&type=1&api_key=TU_API_KEY
```

Fragmento de la respuesta, donde se ve el uso de `low_price`:

```json
"prices": [
  { "outbound_date": "2026-08-10", "return_date": "2026-08-17", "price": 2171 },
  { "outbound_date": "2026-08-11", "return_date": "2026-08-18", "price": 1979 },
  ...
  { "outbound_date": "2026-09-05", "return_date": "2026-09-12", "price": 927 },
  { "outbound_date": "2026-09-06", "return_date": "2026-09-13", "price": 776, "low_price": true },
  { "outbound_date": "2026-09-07", "return_date": "2026-09-14", "price": 959 },
  { "outbound_date": "2026-09-08", "return_date": "2026-09-15", "price": 776, "low_price": true },
  ...
]
```

El mínimo del rango es 776; todas las fechas con ese precio quedan marcadas con `low_price: true`, y las de 927 o 959 no.

---

## Resumen de la estructura (tal como la documenta SerpApi)

```json
{
...
"prices": [
    {
      "outbound_date": "String - Outbound date",
      "return_date": "String - Return date if the flight type is 'Round trip'",
      "price": "Integer - Price in the selected currency, the default currency is USD",
      "low_price": "Boolean - Indicates if the price is within 5% of the minimum price in the requested date range"
    }
],
...
}
```

## Uso típico

1. Se llama al calendario para una ruta y un rango amplio de fechas.
2. Se eligen las fechas con `low_price: true` o con el precio más bajo.
3. Se lanza una búsqueda normal con `engine=google_flights` usando esas `outbound_date` y `return_date` para obtener los itinerarios concretos.

## Relacionado

- Motor principal: [01-api-google-flights.md](01-api-google-flights.md)
- Histórico de precios de una búsqueda concreta: [03-informacion-de-precios.md](03-informacion-de-precios.md)
- Ofertas por destino: [08-api-ofertas-de-vuelos.md](08-api-ofertas-de-vuelos.md)
