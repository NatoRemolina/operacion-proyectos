# API de autocompletado de Google Flights (Google Flights Autocomplete API)

> Fuente: <https://serpapi.com/google-flights-autocomplete-api> — consultada el 12 de noviembre de 2026.
> Nombres de parámetros y campos en inglés (así los espera y devuelve la API); explicaciones en español.

## Qué es

Esta API devuelve sugerencias de ubicaciones a partir de una palabra clave: es el autocompletado de la caja "¿Desde dónde?" / "¿A dónde?" de Google Flights.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights_autocomplete` |
| Motor (`engine`) | `google_flights_autocomplete` |
| Campo que produce | `suggestions` |
| Disponibilidad publicada (uptime) | 100,000 % |
| Playground | <https://serpapi.com/playground?engine=google_flights_autocomplete> |
| Notas de versión | <https://serpapi.com/google-flights-autocomplete-api/release-notes> |
| Métricas | <https://serpapi.com/google-flights-autocomplete-api/api-metrics> |

Uso principal: convertir lo que escribe el usuario ("New", "Korea", "Medellín") en códigos IATA o en kgmid de ciudad, que es justo lo que piden `departure_id` y `arrival_id` del motor principal.

---

## Parámetros

### Resumen

| Parámetro | Obligatorio | Por defecto | Para qué sirve |
| --- | --- | --- | --- |
| `engine` | Sí | — | Debe ser `google_flights_autocomplete` |
| `api_key` | Sí | — | Clave privada de SerpApi |
| `q` | Sí | — | Texto de búsqueda |
| `gl` | No | — | País de la búsqueda |
| `hl` | No | — | Idioma de la búsqueda |
| `exclude_regions` | No | `false` | Excluir regiones de las sugerencias |
| `no_cache` | No | `false` | Forzar búsqueda sin caché |
| `async` | No | `false` | Envío asíncrono |
| `zero_trace` | No | `false` | Modo ZeroTrace (solo Enterprise) |
| `output` | No | `json` | Formato de salida |
| `json_restrictor` | No | — | Limitar los campos devueltos |

### Consulta de búsqueda

#### `q` — Obligatorio

Define la consulta de búsqueda: el texto que se usará para ofrecer opciones de autocompletado.

### Localización

#### `gl` — Opcional

Define el país que se usará para la búsqueda. Es un código de país de dos letras (por ejemplo `us` para Estados Unidos, `uk` para Reino Unido o `fr` para Francia). Lista completa: [Google countries](https://serpapi.com/google-countries).

#### `hl` — Opcional

Define el idioma de la búsqueda. Es un código de idioma de dos o tres letras (por ejemplo `en`, `es`, `fr`), seguido opcionalmente de un código de región de dos letras o tres dígitos (por ejemplo `en-gb` o `es-419`). Lista completa: [Google languages](https://serpapi.com/google-languages).

### Parámetros avanzados

#### `exclude_regions` — Opcional

Se pone en `true` para excluir de las sugerencias las ubicaciones de nivel región. Las regiones incluyen países, regiones subnacionales y áreas de varios países (por ejemplo South Korea, South East England, South East Asia). Por defecto `false`.

En la práctica: con `exclude_regions=true` solo quedan sugerencias de tipo `city`.

### Parámetros de SerpApi

#### `engine` — Obligatorio

Debe valer `google_flights_autocomplete`.

#### `api_key` — Obligatorio

Clave privada de SerpApi.

#### `no_cache` — Opcional

Obliga a SerpApi a traer los resultados aunque exista una versión en caché. La caché solo se sirve si la consulta y todos los parámetros son exactamente iguales, y expira después de 1 hora. Las búsquedas servidas desde caché son gratis y no cuentan en el límite mensual. Valores: `false` (por defecto) o `true`. No debe usarse junto con `async`.

#### `async` — Opcional

`false` (por defecto) mantiene abierta la conexión HTTP hasta recibir los resultados; `true` solo envía la búsqueda y los resultados se recuperan después con la [Searches Archive API](https://serpapi.com/search-archive-api). No debe usarse junto con `no_cache`, ni en cuentas con [Ludicrous Speed](https://serpapi.com/plan) activado.

#### `zero_trace` — Opcional

Solo Enterprise. Activa el [modo ZeroTrace](https://serpapi.com/zero-trace-mode): SerpApi no almacena parámetros, archivos ni metadatos de la búsqueda. Valores: `false` (por defecto) o `true`.

#### `output` — Opcional

Formato del resultado: `json` (por defecto), `html` (HTML crudo) o `md` (Markdown optimizado para LLM y agentes de IA).

#### `json_restrictor` — Opcional

Define los campos a incluir en la salida para reducir el tamaño de la respuesta. Ver [JSON Restrictor](https://serpapi.com/json-restrictor).

---

## Resultados

### Resultados JSON

La salida JSON incluye datos estructurados de las sugerencias. El estado está en `search_metadata.status` y fluye así: `Processing` → `Success` || `Error`. Si falla, el campo `error` contiene el mensaje. `search_metadata.id` es el ID de la búsqueda dentro de SerpApi.

### Resultados HTML

Esta API no tiene respuesta HTML completa, solo texto. `search_metadata.prettify_html_file` contiene el enlace a la versión formateada, que es la que se muestra en el playground.

### Resultados Markdown

Markdown optimizado para LLM y agentes de IA: vista curada del JSON en formato eficiente en tokens, con tablas, enlaces Markdown y metadatos YAML. Se accede con `output=md`, el endpoint `/search.md` o la cabecera `Accept: text/markdown`.

### Campos de `suggestions[]`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `position` | Integer | Posición de la sugerencia en la lista |
| `name` | String | Nombre de la ubicación sugerida |
| `type` | String | Tipo de ubicación. Valores posibles: `city` y `region` |
| `description` | String | Descripción de la ubicación sugerida |
| `id` | String | Google Knowledge Graph ID (`kgmid`) de la ubicación |
| `airports` | Array | Aeropuertos asociados (solo en ciudades) |

### Campos de `suggestions[].airports[]`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `name` | String | Nombre del aeropuerto |
| `id` | String | Código del aeropuerto (IATA) |
| `city` | String | Ciudad donde está el aeropuerto |
| `city_id` | String | `kgmid` de la ciudad donde está el aeropuerto |
| `distance` | String | Distancia de la ciudad al aeropuerto |

Detalles observados en los ejemplos:

- Las sugerencias de tipo `region` **no traen** el arreglo `airports`.
- El `city_id` de un aeropuerto puede diferir del `id` de la sugerencia: en "New York" el aeropuerto EWR tiene `city: "Newark"` y `city_id: "/m/0hptm"`.
- `distance` puede faltar en algún aeropuerto (por ejemplo el de Jeju en el ejemplo con `exclude_regions`).
- El `id` puede empezar por `/m/` o por `/g/` (por ejemplo `/g/121z6l6y` para Jeju Island).

---

## Ejemplos

### 1. `q=New` (ejemplo del playground)

```
GET https://serpapi.com/search.json?engine=google_flights_autocomplete&q=New&api_key=TU_API_KEY
```

```json
{
  "search_metadata": {
    "id": "695927a38c24bd247f1be7e8",
    "status": "Success",
    "json_endpoint": "https://serpapi.com/searches/.../695927a38c24bd247f1be7e8.json",
    "created_at": "2026-01-03 14:28:51 UTC",
    "processed_at": "2026-01-03 14:28:51 UTC",
    "google_flights_autocomplete_url": "https://www.google.com/travel/flights?hl=en&gl=us",
    "raw_html_file": "https://serpapi.com/searches/.../695927a38c24bd247f1be7e8.html",
    "prettify_html_file": "https://serpapi.com/searches/.../695927a38c24bd247f1be7e8.prettify",
    "total_time_taken": 0.93
  },
  "search_parameters": {
    "engine": "google_flights_autocomplete",
    "q": "New",
    "hl": "en",
    "gl": "us"
  },
  "suggestions": [
    {
      "position": 1,
      "name": "New York",
      "type": "city",
      "description": "City in New York State",
      "id": "/m/02_286",
      "airports": [
        { "name": "John F. Kennedy International Airport", "id": "JFK", "city": "New York", "city_id": "/m/02_286", "distance": "12 mi" },
        { "name": "LaGuardia Airport", "id": "LGA", "city": "New York", "city_id": "/m/02_286", "distance": "8 mi" },
        { "name": "Newark Liberty International Airport", "id": "EWR", "city": "Newark", "city_id": "/m/0hptm", "distance": "8 mi" }
      ]
    },
    {
      "position": 2,
      "name": "New Zealand",
      "type": "region",
      "description": "Country in Oceania",
      "id": "/m/0ctw_b"
    },
    {
      "position": 3,
      "name": "New Orleans, Louisiana",
      "type": "city",
      "description": "City in Louisiana",
      "id": "/m/0f2tj",
      "airports": [
        { "name": "Louis Armstrong New Orleans International Airport", "id": "MSY", "city": "New Orleans", "city_id": "/m/0f2tj", "distance": "11 mi" }
      ]
    },
    {
      "position": 4,
      "name": "New Jersey",
      "type": "region",
      "description": "US state",
      "id": "/m/05fjf"
    },
    {
      "position": 5,
      "name": "New Delhi, India",
      "type": "city",
      "description": "Capital of India",
      "id": "/m/0dlv0",
      "airports": [
        { "name": "Indira Gandhi International Airport", "id": "DEL", "city": "New Delhi", "city_id": "/m/0dlv0", "distance": "6 mi" }
      ]
    }
  ]
}
```

### 2. `q=Korea`

```
GET https://serpapi.com/search.json?engine=google_flights_autocomplete&q=Korea&api_key=TU_API_KEY
```

```json
{
...
"suggestions": [
    { "position": 1, "name": "South Korea", "type": "region", "description": "Country in East Asia", "id": "/m/06qd3" },
    {
      "position": 2,
      "name": "Seoul, South Korea",
      "type": "city",
      "description": "Capital of South Korea",
      "id": "/m/0hsqf",
      "airports": [
        { "name": "Gimpo International Airport", "id": "GMP", "city": "Seoul", "city_id": "/m/0hsqf", "distance": "11 mi" },
        { "name": "Incheon International Airport", "id": "ICN", "city": "Seoul", "city_id": "/m/0hsqf", "distance": "31 mi" }
      ]
    },
    {
      "position": 3,
      "name": "Busan, South Korea",
      "type": "city",
      "description": "City in South Korea",
      "id": "/m/0hv7l",
      "airports": [
        { "name": "Gimhae International Airport", "id": "PUS", "city": "Busan", "city_id": "/m/0hv7l", "distance": "7 mi" }
      ]
    },
    ...
],
...
}
```

### 3. `q=Korea` con `exclude_regions=true`

El parámetro `exclude_regions` permite filtrar las sugerencias de región, devolviendo solo sugerencias de ciudad.

```
GET https://serpapi.com/search.json?engine=google_flights_autocomplete&q=Korea&exclude_regions=true&api_key=TU_API_KEY
```

```json
{
...
"suggestions": [
    {
      "position": 1,
      "name": "Seoul, South Korea",
      "type": "city",
      "description": "Capital of South Korea",
      "id": "/m/0hsqf",
      "airports": [
        { "name": "Gimpo International Airport", "id": "GMP", "city": "Seoul", "city_id": "/m/0hsqf", "distance": "11 mi" },
        { "name": "Incheon International Airport", "id": "ICN", "city": "Seoul", "city_id": "/m/0hsqf", "distance": "31 mi" }
      ]
    },
    {
      "position": 2,
      "name": "Busan, South Korea",
      "type": "city",
      "description": "City in South Korea",
      "id": "/m/0hv7l",
      "airports": [
        { "name": "Gimhae International Airport", "id": "PUS", "city": "Busan", "city_id": "/m/0hv7l", "distance": "7 mi" }
      ]
    },
    {
      "position": 3,
      "name": "Jeju Island, South Korea",
      "type": "city",
      "description": "Island in South Korea",
      "id": "/g/121z6l6y",
      "airports": [
        { "name": "Jeju International Airport", "id": "CJU", "city": "Jeju-si", "city_id": "/m/03m9sv" }
      ]
    },
    ...
],
...
}
```

Compárese con el ejemplo 2: desapareció "South Korea" (región), y "South Korea" ya no ocupa la posición 1; las posiciones se renumeran.

---

## Resumen de la estructura (tal como la documenta SerpApi)

```json
{
...
"suggestions": [
    {
      "position": "Integer - Position of the suggestion in the list",
      "name": "String - Name of the suggested location",
      "type": "String - Type of the suggested location. Possible values are: city and region",
      "description": "String - Description of the suggested location",
      "id": "String - Google Knowledge Graph ID (kgmid) of the suggested location",
      "airports": [
        {
          "name": "String - Name of the airport",
          "id": "String - Airport code (IATA code)",
          "city": "String - City where the airport is located",
          "city_id": "String - Google Knowledge Graph ID (kgmid) of the city where the airport is located",
          "distance": "String - Distance from the city to the airport"
        },
        ...
      ]
    },
    ...
],
...
}
```

## Cómo encaja con el motor principal

El `id` de una sugerencia (`/m/02_286`) y el `id` de un aeropuerto (`JFK`) son valores válidos para `departure_id` y `arrival_id` en `engine=google_flights`. Flujo típico de una interfaz:

1. El usuario escribe texto → se llama `google_flights_autocomplete` con `q`.
2. El usuario elige una sugerencia → se guarda su `id` (ciudad) o el `id` de un aeropuerto concreto.
3. Se lanza la búsqueda de vuelos con ese valor en `departure_id` / `arrival_id`.

Usar el `id` de ciudad hace que Google considere todos los aeropuertos de esa ciudad.

## Relacionado

- Motor principal: [01-api-google-flights.md](01-api-google-flights.md)
- Aeropuertos devueltos por una búsqueda: [04-resultados-de-aeropuertos.md](04-resultados-de-aeropuertos.md)
