# API de Google Flights (SerpApi)

> Fuente: <https://serpapi.com/google-flights-api> — consultada el 12 de noviembre de 2026.
> Los nombres de parámetros y campos JSON se dejan en inglés, tal como los espera la API. Las explicaciones están en español.
> La clave privada (`api_key`) que aparece en la página fue reemplazada por `TU_API_KEY`.

## Contenido

1. [Descripción general](#descripción-general)
2. [Nota sobre la similitud de resultados](#nota-sobre-la-similitud-de-resultados)
3. [Parámetros de la API](#parámetros-de-la-api)
4. [Resultados de la API](#resultados-de-la-api)
5. [Flujos de uso (ida y vuelta, multiciudad, reserva)](#flujos-de-uso)
6. [Ejemplos de la API](#ejemplos-de-la-api)
7. [Estructura del JSON](#estructura-del-json)
8. [Enlaces relacionados](#enlaces-relacionados)

---

## Descripción general

La API de Google Flights de SerpApi permite extraer (scrapear) resultados de vuelos de Google Flights en forma de JSON estructurado.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights` |
| Endpoint JSON | `https://serpapi.com/search.json?engine=google_flights` |
| Endpoint Markdown | `https://serpapi.com/search.md?engine=google_flights` |
| Método | `GET` |
| Disponibilidad publicada (uptime) | 99,999 % |
| Parámetros obligatorios | `engine=google_flights` y `api_key` |
| Demo interactiva | [Playground](https://serpapi.com/playground?engine=google_flights) |
| Notas de versión | <https://serpapi.com/google-flights-api/release-notes> |
| Métricas de la API | <https://serpapi.com/google-flights-api/api-metrics> |

La página ofrece código de integración en: cURL, CLI, Ruby, Python, JavaScript, Go, PHP, Java, Rust, C++, .NET, Swift y Google Sheets.

## Nota sobre la similitud de resultados

Los resultados que se reciben por defecto pueden diferir de los que se ven en Google Flights en el navegador.

Poner `deep_search` en `true` produce resultados idénticos a los de Google Flights en el navegador, a costa de un mayor tiempo de respuesta. Conviene activarlo cuando la precisión de los resultados es esencial para el caso de uso.

---

## Parámetros de la API

### Resumen rápido

| Parámetro | Obligatorio | Valor por defecto | Para qué sirve |
| --- | --- | --- | --- |
| `engine` | Sí | — | Debe ser `google_flights` |
| `api_key` | Sí | — | Clave privada de SerpApi |
| `departure_id` | No* | — | Aeropuerto(s) o ubicación de salida |
| `arrival_id` | No* | — | Aeropuerto(s) o ubicación de llegada |
| `gl` | No | — | País de la búsqueda |
| `hl` | No | — | Idioma de la búsqueda |
| `currency` | No | `USD` | Moneda de los precios |
| `type` | No | `1` (ida y vuelta) | Tipo de vuelo |
| `outbound_date` | No* | — | Fecha de ida (`YYYY-MM-DD`) |
| `return_date` | No* | — | Fecha de regreso (`YYYY-MM-DD`) |
| `travel_class` | No | `1` (Economy) | Clase de viaje |
| `multi_city_json` | No* | — | Tramos de un viaje multiciudad |
| `show_hidden` | No | `false` | Incluir vuelos ocultos |
| `exclude_basic` | No | `false` | Excluir tarifas básicas |
| `deep_search` | No | `false` | Resultados idénticos al navegador |
| `adults` | No | `1` | Número de adultos |
| `children` | No | `0` | Número de niños |
| `infants_in_seat` | No | `0` | Bebés con asiento |
| `infants_on_lap` | No | `0` | Bebés en regazo |
| `sort_by` | No | `1` (mejores vuelos) | Orden de los resultados |
| `stops` | No | `0` (cualquiera) | Número de escalas |
| `exclude_airlines` | No | — | Aerolíneas a excluir |
| `include_airlines` | No | — | Aerolíneas a incluir |
| `bags` | No | `0` | Número de maletas de mano |
| `max_price` | No | sin límite | Precio máximo del tiquete |
| `outbound_times` | No | — | Rango horario de la ida |
| `return_times` | No | — | Rango horario del regreso |
| `emissions` | No | — | Filtro por emisiones |
| `layover_duration` | No | — | Duración de las escalas (min) |
| `exclude_conns` | No | — | Aeropuertos de conexión a excluir |
| `max_duration` | No | — | Duración máxima del vuelo (min) |
| `selected_flights_json` | No | — | Fijar el itinerario a vuelos concretos |
| `departure_token` | No | — | Obtener el regreso o el siguiente tramo |
| `booking_token` | No | — | Obtener opciones de reserva |
| `no_cache` | No | `false` | Forzar búsqueda sin caché |
| `async` | No | `false` | Envío asíncrono |
| `zero_trace` | No | `false` | Modo ZeroTrace (solo Enterprise) |
| `output` | No | `json` | Formato de salida |
| `json_restrictor` | No | — | Limitar los campos devueltos |

\* Marcados como opcionales en la documentación, pero se vuelven necesarios según el `type` elegido (ver el detalle de cada uno).

### Consulta de búsqueda (Search query)

#### `departure_id` — Opcional

Define el código del aeropuerto de salida o el kgmid de la ubicación.

- Un código de aeropuerto es un código de 3 letras mayúsculas. Se puede buscar en [Google Flights](https://www.google.com/travel/flights) o en [IATA](https://www.iata.org/en/publications/directories/code-search). Por ejemplo, `CDG` es el Aeropuerto Charles de Gaulle de París y `AUS` es el Aeropuerto Internacional Austin-Bergstrom.
- Un kgmid de ubicación es una cadena que empieza por `/m/` o `/g/`. Se puede buscar la ubicación en [Wikidata](https://www.wikidata.org/) y usar su "Freebase ID" como kgmid. Por ejemplo, `/m/0vzm` es el kgmid de Austin, TX.
- Se pueden indicar varios aeropuertos de salida separados por coma. Por ejemplo: `CDG,ORY,/m/04jpl`.

#### `arrival_id` — Opcional

Define el código del aeropuerto de llegada o el kgmid de la ubicación. Usa exactamente el mismo formato que `departure_id` (código IATA de 3 letras mayúsculas, o kgmid que empieza por `/m/` o `/g/`), y también admite varios valores separados por coma, por ejemplo `CDG,ORY,/m/04jpl`.

### Localización (Localization)

#### `gl` — Opcional

Define el país que se usará para la búsqueda en Google Flights. Es un código de país de dos letras (por ejemplo, `us` para Estados Unidos, `uk` para Reino Unido o `fr` para Francia). Lista completa: [Google countries](https://serpapi.com/google-countries).

#### `hl` — Opcional

Define el idioma de la búsqueda. Es un código de idioma de dos o tres letras (por ejemplo, `en` inglés, `es` español, `fr` francés), seguido opcionalmente de un código de región de dos letras o tres dígitos (por ejemplo, `en-gb` para inglés británico o `es-419` para español latinoamericano). Lista completa: [Google languages](https://serpapi.com/google-languages).

#### `currency` — Opcional

Define la moneda de los precios devueltos. Por defecto `USD`. Lista completa: [Google Travel Currencies](https://serpapi.com/google-travel-currencies).

### Parámetros avanzados (Advanced parameters)

#### `type` — Opcional

Define el tipo de vuelo.

| Valor | Significado |
| --- | --- |
| `1` | Ida y vuelta (por defecto) |
| `2` | Solo ida |
| `3` | Multiciudad |

Cuando vale `3`, la información de los vuelos se indica con `multi_city_json`.

Para obtener los vuelos de regreso en un viaje de ida y vuelta (`1`) hay que hacer otra petición usando un `departure_token`.

#### `outbound_date` — Opcional

Define la fecha de ida. Formato `YYYY-MM-DD`, por ejemplo `2026-11-13`.

- Es obligatorio cuando `type` es `1` (ida y vuelta) o `2` (solo ida), salvo que se use `selected_flights_json`.
- No se puede usar cuando `type` es `3` (multiciudad); en ese caso se usa `date` dentro de `multi_city_json`.

#### `return_date` — Opcional

Define la fecha de regreso. Formato `YYYY-MM-DD`, por ejemplo `2026-11-19`.

- Es obligatorio cuando `type` es `1` (ida y vuelta), salvo que se use `selected_flights_json`.
- No se puede usar cuando `type` es `2` (solo ida) o `3` (multiciudad).

#### `travel_class` — Opcional

Define la clase de viaje.

| Valor | Significado |
| --- | --- |
| `1` | Economy (por defecto) |
| `2` | Premium economy |
| `3` | Business |
| `4` | First |

#### `multi_city_json` — Opcional

Define la información de vuelo para viajes multiciudad. Es una cadena JSON con varios objetos, uno por tramo. Cada objeto debe contener:

| Campo | Descripción |
| --- | --- |
| `departure_id` | Código de aeropuerto de salida o kgmid. Mismo formato que el parámetro principal `departure_id`. |
| `arrival_id` | Código de aeropuerto de llegada o kgmid. Mismo formato que el parámetro principal `arrival_id`. |
| `date` | Fecha del vuelo. Mismo formato que `outbound_date`. |
| `times` | Rango horario del vuelo. Mismo formato que `outbound_times`. Opcional. |

Ejemplo:

```json
[{"departure_id":"CDG","arrival_id":"NRT","date":"2026-11-19"},{"departure_id":"NRT","arrival_id":"LAX,SEA","date":"2026-11-26"},{"departure_id":"LAX,SEA","arrival_id":"AUS","date":"2026-12-03","times":"8,18,9,23"}]
```

El ejemplo es un viaje multiciudad de `CDG` a `NRT` el `2026-11-19`, luego de `NRT` a `LAX` o `SEA` el `2026-11-26`, y finalmente de `LAX` o `SEA` a `AUS` el `2026-12-03`. El último vuelo tiene un rango de salida de 8:00 AM a 7:00 PM y un rango de llegada de 9:00 AM a 12:00 AM (medianoche).

#### `show_hidden` — Opcional

Poner en `true` para incluir los resultados de vuelos ocultos. Equivale a hacer clic en "View more flights" en Google Flights. Por defecto `false`.

#### `exclude_basic` — Opcional

Poner en `true` para excluir las tarifas básicas. Las tarifas resultantes incluyen selección de asiento gratuita y equipaje de mano. Por defecto `false`. Por ahora este filtro solo funciona para vuelos nacionales en EE. UU.

Solo se puede usar cuando `gl` es `us` y `travel_class` es `1`.

#### `deep_search` — Opcional

Poner en `true` para activar la búsqueda profunda, que puede dar mejores resultados pero con mayor tiempo de respuesta. Los resultados de la búsqueda profunda son idénticos a los de las páginas de Google Flights en el navegador. Por defecto `false` por razones de rendimiento.

### Número de pasajeros (Number of passengers)

| Parámetro | Obligatorio | Descripción | Por defecto |
| --- | --- | --- | --- |
| `adults` | Opcional | Número de adultos | `1` |
| `children` | Opcional | Número de niños | `0` |
| `infants_in_seat` | Opcional | Número de bebés con asiento | `0` |
| `infants_on_lap` | Opcional | Número de bebés en regazo | `0` |

### Ordenamiento (Sorting)

#### `sort_by` — Opcional

Define el orden de los resultados.

| Valor | Significado |
| --- | --- |
| `1` | Mejores vuelos / Top flights (por defecto) |
| `2` | Precio |
| `3` | Hora de salida |
| `4` | Hora de llegada |
| `5` | Duración |
| `6` | Emisiones |

### Filtros avanzados (Advanced filters)

#### `stops` — Opcional

Define el número de escalas del vuelo.

| Valor | Significado |
| --- | --- |
| `0` | Cualquier número de escalas (por defecto) |
| `1` | Solo vuelos directos (nonstop) |
| `2` | 1 escala o menos |
| `3` | 2 escalas o menos |

#### `exclude_airlines` — Opcional

Define los códigos de aerolíneas que se excluyen. Varias aerolíneas se separan con coma.

- Cada código debe ser un código IATA de 2 caracteres: dos letras mayúsculas, o una letra mayúscula y un dígito. Se pueden buscar en [IATA](https://www.iata.org/en/publications/directories/code-search). Por ejemplo, `UA` es United Airlines.
- También se pueden indicar alianzas: `STAR_ALLIANCE` (Star Alliance), `SKYTEAM` (SkyTeam) y `ONEWORLD` (Oneworld).
- No se puede usar junto con `include_airlines`.

#### `include_airlines` — Opcional

Define los códigos de aerolíneas que se incluyen. Varias aerolíneas se separan con coma. Mismo formato que `exclude_airlines` (código IATA de 2 caracteres o las alianzas `STAR_ALLIANCE`, `SKYTEAM`, `ONEWORLD`).

No se puede usar junto con `exclude_airlines`.

#### `bags` — Opcional

Define el número de maletas de mano (carry-on). Por defecto `0`.

No debe superar el número total de pasajeros con derecho a equipaje de mano (`adults`, `children` e `infants_in_seat`).

#### `max_price` — Opcional

Define el precio máximo del tiquete. Por defecto, sin límite.

#### `outbound_times` — Opcional

Define el rango horario de la ida. Es una cadena con dos números (solo salida) o cuatro números (salida y llegada) separados por coma. Cada número representa el inicio de una hora.

| Valor | Significado |
| --- | --- |
| `4,18` | Salida entre 4:00 AM y 7:00 PM |
| `0,18` | Salida entre 12:00 AM y 7:00 PM |
| `19,23` | Salida entre 7:00 PM y 12:00 AM |
| `4,18,3,19` | Salida entre 4:00 AM y 7:00 PM, llegada entre 3:00 AM y 8:00 PM |
| `0,23,3,19` | Salida sin restricción, llegada entre 3:00 AM y 8:00 PM |

#### `return_times` — Opcional

Define el rango horario del regreso. Mismo formato y mismos ejemplos que `outbound_times`.

Solo debe usarse cuando `type` es `1` (ida y vuelta).

#### `emissions` — Opcional

Define el nivel de emisiones del vuelo.

| Valor | Significado |
| --- | --- |
| `1` | Solo vuelos con menos emisiones |

#### `layover_duration` — Opcional

Define la duración de las escalas, en minutos. Es una cadena con dos números separados por coma. Por ejemplo, `90,330` significa entre 1 h 30 min y 5 h 30 min.

#### `exclude_conns` — Opcional

Define los códigos de los aeropuertos de conexión que se excluyen. Cada uno es un código de 3 letras mayúsculas (se buscan en Google Flights o IATA). Se pueden combinar varios separándolos con coma, por ejemplo `CDG,AUS`.

#### `max_duration` — Opcional

Define la duración máxima del vuelo, en minutos. Por ejemplo, `1500` para 25 horas.

Si la búsqueda no devuelve resultados, se recomienda aumentar `max_duration` hasta en `200` minutos para compensar las variaciones de programación propias de cada ruta.

### Seleccionar vuelos específicos (Select specific flights)

#### `selected_flights_json` — Opcional

Fija el itinerario a vuelos concretos, segmento por segmento. Es un objeto JSON con una clave `outbound` (obligatoria) y una clave `return` (obligatoria en ida y vuelta, prohibida en solo ida). Cada valor es un arreglo ordenado de objetos de segmento, cada uno con:

| Campo | Descripción |
| --- | --- |
| `flight_number` | Número de vuelo IATA (código de aerolínea de 2 caracteres + 1 a 4 dígitos, p. ej. `BA591`). |
| `departure_id` | Código IATA de 3 letras del aeropuerto de salida de ese segmento. |
| `arrival_id` | Código IATA de 3 letras del aeropuerto de llegada de ese segmento. |
| `date` | Fecha de salida de ese segmento, `YYYY-MM-DD`. |

Dentro de un mismo tramo, el `departure_id` de cada segmento debe ser igual al `arrival_id` del segmento anterior, y las fechas no pueden decrecer.

Ejemplo (ida y vuelta: ida `MXP → LHR → MAD`, regreso directo `MAD → MXP`):

```json
{"outbound":[{"flight_number":"BA591","departure_id":"MXP","arrival_id":"LHR","date":"2026-11-13"},{"flight_number":"BA460","departure_id":"LHR","arrival_id":"MAD","date":"2026-11-13"}],"return":[{"flight_number":"IB675","departure_id":"MAD","arrival_id":"MXP","date":"2026-11-19"}]}
```

Cuando se envía este parámetro, los parámetros de nivel superior `departure_id`, `arrival_id`, `outbound_date` y `return_date` son opcionales y se derivan del primer y último segmento de cada tramo. Si se envían, deben coincidir.

No se puede usar junto con `departure_token`, `booking_token` ni `multi_city_json` (`type` = 3).

### Obtener los siguientes vuelos (Get next flights)

#### `departure_token` — Opcional

Sirve para seleccionar un vuelo y obtener los vuelos de regreso (en ida y vuelta) o los vuelos del siguiente tramo del itinerario (en multiciudad). El token se encuentra en los resultados de los vuelos de salida.

No se puede usar junto con `booking_token`.

### Obtener opciones de reserva (Get booking options)

#### `booking_token` — Opcional

Sirve para obtener las opciones de reserva de los vuelos seleccionados. El token se encuentra en los resultados de vuelos.

- No se puede usar junto con `departure_token`.
- Al usar este token, los parámetros de fecha y los de la sección "Filtros avanzados" no afectan el resultado.

### Parámetros de SerpApi

#### `engine` — Obligatorio

Debe valer `google_flights` para usar el motor de la API de Google Flights.

#### `api_key` — Obligatorio

Define la clave privada de SerpApi que se va a usar.

#### `no_cache` — Opcional

Obliga a SerpApi a traer los resultados de Google Flights aunque ya exista una versión en caché.

- La caché solo se sirve si la consulta y todos los parámetros son exactamente iguales.
- La caché expira después de 1 hora.
- Las búsquedas servidas desde caché son gratis y no cuentan dentro de las búsquedas mensuales.
- Valores: `false` (por defecto) permite resultados de caché; `true` los impide.
- `no_cache` y `async` no deben usarse juntos.

#### `async` — Opcional

Define cómo se envía la búsqueda a SerpApi.

- `false` (por defecto): abre una conexión HTTP y la mantiene abierta hasta recibir los resultados.
- `true`: solo envía la búsqueda, y los resultados se recuperan después con la [Searches Archive API](https://serpapi.com/search-archive-api).
- `async` y `no_cache` no deben usarse juntos.
- `async` no debe usarse en cuentas con [Ludicrous Speed](https://serpapi.com/plan) activado.

#### `zero_trace` — Opcional

Solo para planes Enterprise. Activa el [modo ZeroTrace](https://serpapi.com/zero-trace-mode). Valores: `false` (por defecto) o `true`. Con este modo SerpApi no almacena en sus servidores los parámetros, los archivos ni los metadatos de la búsqueda, lo cual puede dificultar la depuración.

#### `output` — Opcional

Define el formato del resultado.

| Valor | Resultado |
| --- | --- |
| `json` | JSON estructurado de los resultados (por defecto) |
| `html` | HTML crudo obtenido |
| `md` | Versión en Markdown optimizada para LLM y agentes de IA |

#### `json_restrictor` — Opcional

Define los campos que se quieren incluir en la salida, lo que reduce el tamaño de la respuesta y la hace más rápida. Detalles en la [documentación de JSON Restrictor](https://serpapi.com/json-restrictor).

### Restricciones entre parámetros

| Regla | Detalle |
| --- | --- |
| `type=1` (ida y vuelta) | Requiere `outbound_date` y `return_date` (salvo con `selected_flights_json`) |
| `type=2` (solo ida) | Requiere `outbound_date`; no admite `return_date` |
| `type=3` (multiciudad) | Usa `multi_city_json`; no admite `outbound_date` ni `return_date` |
| `return_times` | Solo con `type=1` |
| `exclude_basic` | Solo con `gl=us` y `travel_class=1`; solo vuelos nacionales de EE. UU. |
| `include_airlines` / `exclude_airlines` | No se pueden usar juntos |
| `departure_token` / `booking_token` | No se pueden usar juntos |
| `selected_flights_json` | No se combina con `departure_token`, `booking_token` ni `multi_city_json` |
| `booking_token` | Ignora los parámetros de fecha y los filtros avanzados |
| `bags` | No puede superar `adults` + `children` + `infants_in_seat` |
| `no_cache` / `async` | No deben usarse juntos |

---

## Resultados de la API

### Resultados JSON

La salida JSON incluye datos estructurados de [Flight Results](https://serpapi.com/google-flights-results) (resultados de vuelos) y [Price Insights](https://serpapi.com/google-flights-price-insights) (información de precios).

El estado de la búsqueda está en `search_metadata.status` y sigue este flujo: `Processing` → `Success` || `Error`. Si la búsqueda falla, el campo `error` contiene el mensaje de error. `search_metadata.id` es el ID de la búsqueda dentro de SerpApi.

### Resultados HTML

Esta API no tiene una respuesta HTML completa, solo texto. `search_metadata.prettify_html_file` contiene un enlace a la versión formateada del resultado, que es la que se muestra en el playground.

### Resultados Markdown

La salida en Markdown está optimizada para LLM y agentes de IA. Ofrece una vista curada de los resultados JSON en un formato eficiente en tokens, usando tablas, enlaces Markdown y metadatos YAML (frontmatter).

Hay tres formas de pedirla: el parámetro `output=md`, el endpoint `/search.md`, o la cabecera de la petición `Accept: text/markdown`.

---

## Flujos de uso

**Solo ida (`type=2`).** Una sola petición con `departure_id`, `arrival_id` y `outbound_date`. Cada resultado trae un `booking_token`.

**Ida y vuelta (`type=1`).** La primera petición (con `outbound_date` y `return_date`) devuelve los vuelos de ida, cada uno con un `departure_token`. Una segunda petición con ese `departure_token` devuelve los vuelos de regreso. Con el `booking_token` del vuelo elegido se consultan las opciones de reserva.

**Multiciudad (`type=3`).** La primera petición lleva `multi_city_json` y devuelve los vuelos del primer tramo. Con el `departure_token` del vuelo elegido se pide el siguiente tramo, y así sucesivamente hasta el último, que entrega el `booking_token`.

**Opciones de reserva.** Una petición con `booking_token` devuelve las opciones de reserva de los vuelos seleccionados.

---

## Ejemplos de la API

### Ejemplo del playground: solo ida CDG → AUS

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=CDG&arrival_id=AUS&currency=USD&type=2&outbound_date=2026-11-13&api_key=TU_API_KEY
```

cURL:

```bash
curl --get https://serpapi.com/search.json \
  -d engine="google_flights" \
  -d departure_id="CDG" \
  -d arrival_id="AUS" \
  -d currency="USD" \
  -d type="2" \
  -d outbound_date="2026-11-13" \
  -d api_key="TU_API_KEY"
```

Ruby (tal como lo muestra la página):

```ruby
require "serpapi"

client = SerpApi::Client.new(
  engine: "google_flights",
  departure_id: "CDG",
  arrival_id: "AUS",
  currency: "USD",
  type: "2",
  outbound_date: "2026-11-13",
  api_key: "TU_API_KEY"
)

results = client.search
best_flights = results[:best_flights]
```

Python (equivalente con la librería oficial `serpapi`):

```python
import serpapi

client = serpapi.Client(api_key="TU_API_KEY")
results = client.search({
    "engine": "google_flights",
    "departure_id": "CDG",
    "arrival_id": "AUS",
    "currency": "USD",
    "type": "2",
    "outbound_date": "2026-11-13",
})
best_flights = results["best_flights"]
```

La respuesta de esta búsqueda en el playground contiene `search_metadata`, `search_parameters`, `best_flights` (5 itinerarios, desde 520 USD), `other_flights` (4 itinerarios), `price_insights` (precio más bajo 520, nivel `low`, rango típico 690–1350 e historial de precios diario) y `airports`. En solo ida, cada itinerario trae `booking_token` en vez de `departure_token`.


### Ejemplo típico: ida y vuelta PEK → AUS

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=PEK&arrival_id=AUS&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&hl=en&api_key=TU_API_KEY
```

Ejemplo de JSON (cada itinerario trae `departure_token` para pedir el regreso):

```json
{
"search_metadata": {
    "id": "651a585815afff2d53eb9a5e",
    "status": "Success",
    "json_endpoint": "https://serpapi.com/searches/e65fd34e00db9b2b/651a585815afff2d53eb9a5e.json",
    "created_at": "2023-10-02 05:42:48 UTC",
    "processed_at": "2023-10-02 05:42:48 UTC",
    "google_flights_url": "https://www.google.com/travel/flights?hl=en",
    "raw_html_file": "https://serpapi.com/searches/e65fd34e00db9b2b/651a585815afff2d53eb9a5e.html",
    "prettify_html_file": "https://serpapi.com/searches/e65fd34e00db9b2b/651a585815afff2d53eb9a5e.prettify",
    "total_time_taken": 0.71
},
"search_parameters": {
    "engine": "google_flights",
    "hl": "en",
    "departure_id": "PEK",
    "arrival_id": "AUS",
    "outbound_date": "2023-10-03",
    "return_date": "2023-10-09",
    "currency": "USD"
},
"best_flights": [
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Beijing Capital International Airport",
            "id": "PEK",
            "time": "2023-10-03 15:10"
          },
          "arrival_airport": {
            "name": "Haneda Airport",
            "id": "HND",
            "time": "2023-10-03 19:35"
          },
          "duration": 205,
          "airplane": "Boeing 787",
          "airline": "ANA",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/NH.png",
          "travel_class": "Economy",
          "flight_number": "NH 962",
          "legroom": "31 in",
          "extensions": [
            "Average legroom (31 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "On-demand video",
            "Carbon emissions estimate: 133 kg"
          ]
        },
        {
          "departure_airport": {
            "name": "Haneda Airport",
            "id": "HND",
            "time": "2023-10-03 21:05"
          },
          "arrival_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2023-10-03 15:10"
          },
          "duration": 605,
          "airplane": "Boeing 787",
          "airline": "ANA",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/NH.png",
          "travel_class": "Economy",
          "flight_number": "NH 126",
          "ticket_also_sold_by": [
            "United"
          ],
          "legroom": "32 in",
          "extensions": [
            "Above average legroom (32 in)",
            "In-seat power & USB outlets",
            "On-demand video",
            "Carbon emissions estimate: 836 kg"
          ],
          "overnight": true
        },
        {
          "departure_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2023-10-03 19:01"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2023-10-03 23:59"
          },
          "duration": 178,
          "airplane": "Boeing 737MAX 9 Passenger",
          "airline": "United",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/UA.png",
          "travel_class": "Economy",
          "flight_number": "UA 2175",
          "legroom": "30 in",
          "extensions": [
            "Average legroom (30 in)",
            "Wi-Fi for a fee",
            "In-seat power outlet",
            "Stream media to your device",
            "Carbon emissions estimate: 135 kg"
          ]
        }
      ],
      "layovers": [
        {
          "duration": 90,
          "name": "Haneda Airport",
          "id": "HND"
        },
        {
          "duration": 231,
          "name": "Los Angeles International Airport",
          "id": "LAX"
        }
      ],
      "total_duration": 1309,
      "carbon_emissions": {
        "this_flight": 1106000,
        "typical_for_this_route": 949000,
        "difference_percent": 17
      },
      "price": 2512,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/multi.png",
      "departure_token": "W1siUEVLIiwiMjAyMy0xMC0wMyIsIkhORCIsbnVsbCwiTkgiLCI5NjIiXSxbIkhORCIsIjIwMjMtMTAtMDMiLCJMQVgiLG51bGwsIk5IIiwiMTI2Il0sWyJMQVgiLCIyMDIzLTEwLTAzIiwiQVVTIixudWxsLCJVQSIsIjIxNzUiXV0="
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Beijing Capital International Airport",
            "id": "PEK",
            "time": "2023-10-03 10:40"
          },
          "arrival_airport": {
            "name": "Incheon International Airport",
            "id": "ICN",
            "time": "2023-10-03 13:50"
          },
          "duration": 130,
          "airplane": "Airbus A330",
          "airline": "Asiana",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/OZ.png",
          "travel_class": "Economy",
          "flight_number": "OZ 332",
          "legroom": "32 in",
          "extensions": [
            "Above average legroom (32 in)",
            "In-seat power outlet",
            "On-demand video",
            "Carbon emissions estimate: 84 kg"
          ]
        },
        {
          "departure_airport": {
            "name": "Incheon International Airport",
            "id": "ICN",
            "time": "2023-10-03 20:55"
          },
          "arrival_airport": {
            "name": "San Francisco International Airport",
            "id": "SFO",
            "time": "2023-10-03 15:30"
          },
          "duration": 635,
          "airplane": "Airbus A350",
          "airline": "Asiana",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/OZ.png",
          "travel_class": "Economy",
          "flight_number": "OZ 212",
          "legroom": "32 in",
          "extensions": [
            "Above average legroom (32 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "On-demand video",
            "Carbon emissions estimate: 619 kg"
          ],
          "overnight": true,
          "often_delayed_by_over_30_min": true
        },
        {
          "departure_airport": {
            "name": "San Francisco International Airport",
            "id": "SFO",
            "time": "2023-10-04 07:40"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2023-10-04 13:10"
          },
          "duration": 210,
          "airplane": "Boeing 737",
          "airline": "Alaska",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/AS.png",
          "travel_class": "Economy",
          "flight_number": "AS 512",
          "legroom": "31 in",
          "extensions": [
            "Average legroom (31 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "Stream media to your device",
            "Carbon emissions estimate: 175 kg"
          ]
        }
      ],
      "layovers": [
        {
          "duration": 425,
          "name": "Incheon International Airport",
          "id": "ICN"
        },
        {
          "duration": 970,
          "name": "San Francisco International Airport",
          "id": "SFO",
          "overnight": true
        }
      ],
      "total_duration": 2370,
      "carbon_emissions": {
        "this_flight": 880000,
        "typical_for_this_route": 949000,
        "difference_percent": -7
      },
      "price": 2513,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/multi.png",
      "departure_token": "W1siUEVLIiwiMjAyMy0xMC0wMyIsIklDTiIsbnVsbCwiT1oiLCIzMzIiXSxbIklDTiIsIjIwMjMtMTAtMDMiLCJTRk8iLG51bGwsIk9aIiwiMjEyIl0sWyJTRk8iLCIyMDIzLTEwLTA0IiwiQVVTIixudWxsLCJBUyIsIjUxMiJdXQ=="
    },
    ...
],
"other_flights": [
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Beijing Capital International Airport",
            "id": "PEK",
            "time": "2023-10-03 18:30"
          },
          "arrival_airport": {
            "name": "Incheon International Airport",
            "id": "ICN",
            "time": "2023-10-03 21:40"
          },
          "duration": 130,
          "airplane": "Boeing 737MAX 8 Passenger",
          "airline": "Korean Air",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/KE.png",
          "travel_class": "Economy",
          "flight_number": "KE 860",
          "legroom": "31 in",
          "extensions": [
            "Average legroom (31 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "Stream media to your device",
            "Carbon emissions estimate: 81 kg"
          ]
        },
        {
          "departure_airport": {
            "name": "Incheon International Airport",
            "id": "ICN",
            "time": "2023-10-04 09:20"
          },
          "arrival_airport": {
            "name": "Dallas/Fort Worth International Airport",
            "id": "DFW",
            "time": "2023-10-04 08:00"
          },
          "duration": 760,
          "airplane": "Boeing 787",
          "airline": "Korean Air",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/KE.png",
          "travel_class": "Economy",
          "flight_number": "KE 31",
          "legroom": "33 in",
          "extensions": [
            "Above average legroom (33 in)",
            "In-seat power & USB outlets",
            "On-demand video",
            "Carbon emissions estimate: 807 kg"
          ],
          "overnight": true
        },
        {
          "departure_airport": {
            "name": "Dallas/Fort Worth International Airport",
            "id": "DFW",
            "time": "2023-10-04 09:35"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2023-10-04 10:40"
          },
          "duration": 65,
          "airplane": "Embraer 175",
          "airline": "American",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/AA.png",
          "travel_class": "Economy",
          "flight_number": "AA 3489",
          "legroom": "30 in",
          "extensions": [
            "Average legroom (30 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "Stream media to your device",
            "Carbon emissions estimate: 60 kg"
          ]
        }
      ],
      "layovers": [
        {
          "duration": 700,
          "name": "Incheon International Airport",
          "id": "ICN",
          "overnight": true
        },
        {
          "duration": 95,
          "name": "Dallas/Fort Worth International Airport",
          "id": "DFW"
        }
      ],
      "total_duration": 1750,
      "carbon_emissions": {
        "this_flight": 949000,
        "typical_for_this_route": 949000,
        "difference_percent": 0
      },
      "price": 3521,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/multi.png",
      "departure_token": "W1siUEVLIiwiMjAyMy0xMC0wMyIsIklDTiIsbnVsbCwiS0UiLCI4NjAiXSxbIklDTiIsIjIwMjMtMTAtMDQiLCJERlciLG51bGwsIktFIiwiMzEiXSxbIkRGVyIsIjIwMjMtMTAtMDQiLCJBVVMiLG51bGwsIkFBIiwiMzQ4OSJdXQ=="
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Beijing Capital International Airport",
            "id": "PEK",
            "time": "2023-10-03 18:30"
          },
          "arrival_airport": {
            "name": "Incheon International Airport",
            "id": "ICN",
            "time": "2023-10-03 21:40"
          },
          "duration": 130,
          "airplane": "Boeing 737MAX 8 Passenger",
          "airline": "Korean Air",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/KE.png",
          "travel_class": "Economy",
          "flight_number": "KE 860",
          "legroom": "31 in",
          "extensions": [
            "Average legroom (31 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "Stream media to your device",
            "Carbon emissions estimate: 81 kg"
          ]
        },
        {
          "departure_airport": {
            "name": "Incheon International Airport",
            "id": "ICN",
            "time": "2023-10-04 09:20"
          },
          "arrival_airport": {
            "name": "Hartsfield-Jackson Atlanta International Airport",
            "id": "ATL",
            "time": "2023-10-04 09:50"
          },
          "duration": 810,
          "airplane": "Boeing 747",
          "airline": "Korean Air",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/KE.png",
          "travel_class": "Economy",
          "flight_number": "KE 35",
          "legroom": "33 in",
          "extensions": [
            "Above average legroom (33 in)",
            "In-seat power & USB outlets",
            "On-demand video",
            "Carbon emissions estimate: 954 kg"
          ],
          "overnight": true
        },
        {
          "departure_airport": {
            "name": "Hartsfield-Jackson Atlanta International Airport",
            "id": "ATL",
            "time": "2023-10-04 12:59"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2023-10-04 14:18"
          },
          "duration": 139,
          "airplane": "Airbus A321",
          "airline": "Delta",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/DL.png",
          "travel_class": "Economy",
          "flight_number": "DL 1384",
          "ticket_also_sold_by": [
            "Korean Air"
          ],
          "legroom": "31 in",
          "extensions": [
            "Average legroom (31 in)",
            "Free Wi-Fi",
            "In-seat power & USB outlets",
            "Live TV",
            "Carbon emissions estimate: 109 kg"
          ]
        }
      ],
      "layovers": [
        {
          "duration": 700,
          "name": "Incheon International Airport",
          "id": "ICN",
          "overnight": true
        },
        {
          "duration": 189,
          "name": "Hartsfield-Jackson Atlanta International Airport",
          "id": "ATL"
        }
      ],
      "total_duration": 1968,
      "carbon_emissions": {
        "this_flight": 1146000,
        "typical_for_this_route": 949000,
        "difference_percent": 21
      },
      "price": 3521,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/multi.png",
      "departure_token": "W1siUEVLIiwiMjAyMy0xMC0wMyIsIklDTiIsbnVsbCwiS0UiLCI4NjAiXSxbIklDTiIsIjIwMjMtMTAtMDQiLCJBVEwiLG51bGwsIktFIiwiMzUiXSxbIkFUTCIsIjIwMjMtMTAtMDQiLCJBVVMiLG51bGwsIkRMIiwiMTM4NCJdXQ=="
    },
    ...
],
"price_insights": {
    "lowest_price": 2512,
    "price_level": "high",
    "typical_price_range": [
      1500,
      1900
    ],
    "price_history": [
      [
        1691424000,
        1877
      ],
      [
        1691510400,
        1915
      ],
      ...,
      [
        1696089600,
        2309
      ],
      [
        1696176000,
        2512
      ]
    ]
},
"airports": [
    {
      "departure": [
        {
          "airport": {
            "name": "Beijing Capital International Airport",
            "id": "PEK"
          },
          "city": "Beijing",
          "country": "China",
          "country_code": "CN",
          "image": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcQ9v_tNYxaummsU2qbFn8zuYzkcG0x6qCvqB2gbBnx-2FVlZZPsnkvUXGk07vxotk-0vRQMUYCjj2d4Wg",
          "thumbnail": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcSzsj_yw6o3vb8i54_D21VgI5rTohxexQkZ0TrZKDKJwTSKw2yqnRYLoIcBWIY50BlHo-OPMm68zbUO-qnFvmQmm6jvtWPwo7WOzjNGX_A"
        }
      ],
      "arrival": [
        {
          "airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS"
          },
          "city": "Austin",
          "country": "United States",
          "country_code": "US",
          "image": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcRKdjkMcBZuGRD1MjnuLQvdGtpTk0RyjdYs0Z8JsPtfIjer-6VvmfmMLxzvBkeyUrhf_focikfda4rVHg",
          "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcSQ73FSj9E8pKaNvjWKyEDQGfLV-pky_onARvOY-zHWvQ-hOuPJSqyyXzvyg4-kGGAcZxdO6T5SYGWBzrX8x6MSPq7gBHsSLzX9MYjFJWA"
        }
      ]
    },
    {
      "departure": [
        {
          "airport": {
            "name": "John F. Kennedy International Airport",
            "id": "JFK"
          },
          "city": "New York",
          "country": "United States",
          "country_code": "US",
          "image": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcQXj9frEFT6DZoIoTn-QoPoV3oZxBBgHclLt7dHsHG6B1AGu8zJzYmj_4rFxyc",
          "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcSO9yu_buXnYWg4cXn3J8RU6YZyOG59BovV4PfIt8x5_lc5F8-9l9Yxv9oIH8"
        }
      ],
      "arrival": [
        {
          "airport": {
            "name": "London Heathrow Airport",
            "id": "LHR"
          },
          "city": "London",
          "country": "United Kingdom",
          "country_code": "GB",
          "image": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcS1nKcZksZTFlL5sKtK3HZf2wPzU-QdOcE6XQulTyP5WBGXlb1D-8FbfyCTFbU",
          "thumbnail": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcS_kdUQHgJlIUl0c3uHq6LfVRfHRyKP9dJUpge3DEx8HmxldzLZQw1xCdLfYM"
        }
      ]
    }
],
...
}
```

### Ejemplo con `departure_id`: `CDG,ORY` (varios aeropuertos de salida)

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=CDG,ORY&arrival_id=LAX&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&hl=en&api_key=TU_API_KEY
```

Ejemplo de JSON:

```json
{
...
"best_flights": [
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Paris Charles de Gaulle Airport",
            "id": "CDG",
            "time": "2024-03-20 18:50"
          },
          "arrival_airport": {
            "name": "Istanbul Airport",
            "id": "IST",
            "time": "2024-03-21 00:20"
          },
          ...
        },
        {
          "departure_airport": {
            "name": "Istanbul Airport",
            "id": "IST",
            "time": "2024-03-21 08:00"
          },
          "arrival_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2024-03-21 11:55"
          },
          ...
        }
      ],
      "layovers": [
        {
          "duration": 460,
          "name": "Istanbul Airport",
          "id": "IST",
          "overnight": true
        }
      ],
      "total_duration": 1505,
      "price": 887,
      "type": "Round trip",
      ...
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Paris-Orly Airport",
            "id": "ORY",
            "time": "2024-03-20 07:00"
          },
          "arrival_airport": {
            "name": "London Gatwick Airport",
            "id": "LGW",
            "time": "2024-03-20 07:10"
          },
          ...
        },
        {
          "departure_airport": {
            "name": "London Gatwick Airport",
            "id": "LGW",
            "time": "2024-03-20 10:35"
          },
          "arrival_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2024-03-20 15:10"
          },
          ...
        }
      ],
      "layovers": [
        {
          "duration": 205,
          "name": "London Gatwick Airport",
          "id": "LGW"
        }
      ],
      "total_duration": 970,
      "price": 890,
      "type": "Round trip",
      ...
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Paris Charles de Gaulle Airport",
            "id": "CDG",
            "time": "2024-03-20 13:15"
          },
          "arrival_airport": {
            "name": "Dublin Airport",
            "id": "DUB",
            "time": "2024-03-20 14:05"
          },
          ...
        },
        {
          "departure_airport": {
            "name": "Dublin Airport",
            "id": "DUB",
            "time": "2024-03-20 15:20"
          },
          "arrival_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2024-03-20 19:35"
          },
          ...
        }
      ],
      "layovers": [
        {
          "duration": 75,
          "name": "Dublin Airport",
          "id": "DUB"
        }
      ],
      "total_duration": 860,
      "price": 1240,
      "type": "Round trip",
      ...
    }
],
"airports": [
    {
      "departure": [
        {
          "airport": {
            "name": "Paris Charles de Gaulle Airport",
            "id": "CDG"
          },
          "city": "Paris",
          "country": "France",
          "country_code": "FR",
          "image": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcQ9v_tNYxaummsU2qbFn8zuYzkcG0x6qCvqB2gbBnx-2FVlZZPsnkvUXGk07vxotk-0vRQMUYCjj2d4Wg",
          "thumbnail": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcSzsj_yw6o3vb8i54_D21VgI5rTohxexQkZ0TrZKDKJwTSKw2yqnRYLoIcBWIY50BlHo-OPMm68zbUO-qnFvmQmm6jvtWPwo7WOzjNGX_A"
        },
        {
          "airport": {
            "name": "Paris-Orly Airport",
            "id": "ORY"
          },
          "city": "Paris",
          "country": "France",
          "country_code": "FR",
          "image": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcQGx8ii2KbSDdbdzfKye5oDN2bwBA6audqI7XUEf2iMRZezpn_ZbQe1ZIuvUSH-8XOMe958umDwSsAF1w",
          "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcSyQJ-woNs0iO22mPSkmRUM5gcsTbbYeypQ6BBTeFxXr90mqTxZl57Fdq2CDuLn4w7cKZ8TT9_zZhOpF57rIpA7yWKQnqKvkKIf9Y-qJDo"
        },
        ...
      ],
      "arrival": [
        {
          "airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX"
          },
          "city": "Los Angeles",
          "country": "United States",
          "country_code": "US",
          "image": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcRKdjkMcBZuGRD1MjnuLQvdGtpTk0RyjdYs0Z8JsPtfIjer-6VvmfmMLxzvBkeyUrhf_focikfda4rVHg",
          "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcSQ73FSj9E8pKaNvjWKyEDQGfLV-pky_onARvOY-zHWvQ-hOuPJSqyyXzvyg4-kGGAcZxdO6T5SYGWBzrX8x6MSPq7gBHsSLzX9MYjFJWA"
        },
        ...
      ]
    },
    ...
],
...
}
```

### Ejemplo multiciudad

Se usa `departure_token` para seleccionar el vuelo y obtener los vuelos del siguiente tramo del itinerario.

```
GET https://serpapi.com/search.json?engine=google_flights&currency=USD&hl=en&type=3&multi_city_json=[{"departure_id":"CDG","arrival_id":"NRT","date":"2026-11-19"},{"departure_id":"NRT","arrival_id":"LAX,SEA","date":"2026-11-26"},{"departure_id":"LAX,SEA","arrival_id":"AUS","date":"2026-12-03","times":"8,18,9,23"}]&api_key=TU_API_KEY
```

El valor de `multi_city_json` debe ir codificado para URL (URL-encoded) al enviarlo; las librerías cliente lo hacen automáticamente.

Ejemplo de JSON:

```json
{
...
"best_flights": [
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Paris Charles de Gaulle Airport",
            "id": "CDG",
            "time": "2024-07-16 09:10"
          },
          "arrival_airport": {
            "name": "Montréal-Pierre Elliott Trudeau International Airport",
            "id": "YUL",
            "time": "2024-07-16 10:45"
          },
          ...
        },
        {
          "departure_airport": {
            "name": "Montréal-Pierre Elliott Trudeau International Airport",
            "id": "YUL",
            "time": "2024-07-16 12:50"
          },
          "arrival_airport": {
            "name": "Narita International Airport",
            "id": "NRT",
            "time": "2024-07-17 15:25"
          },
          ...
        }
      ],
      "layovers": [
        {
          "duration": 125,
          "name": "Montréal-Pierre Elliott Trudeau International Airport",
          "id": "YUL"
        }
      ],
      "total_duration": 1395,
      "price": 3124,
      "type": "Multi-city",
      ...
      "departure_token": "WyJDalJJU21sa1NWOWZibGMwVGpCQlEwZGplbmRDUnkwdExTMHRMUzB0TFhWcWFHMHpNMEZCUVVGQlIyRk5lVUZqU2tKbFJXRkJFZ2xCUXpnM05YeEJRelVhQ3dqUGlCTVFBaG9EVlZORU9CeHd6NGdUIixbWyJDREciLCIyMDI0LTA3LTE2IiwiWVVMIixudWxsLCJBQyIsIjg3NSJdLFsiWVVMIiwiMjAyNC0wNy0xNiIsIk5SVCIsbnVsbCwiQUMiLCI1Il1dXQ=="
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Paris Charles de Gaulle Airport",
            "id": "CDG",
            "time": "2024-07-16 13:25"
          },
          "arrival_airport": {
            "name": "Shanghai Pudong International Airport",
            "id": "PVG",
            "time": "2024-07-17 07:00"
          },
          ...
        },
        {
          "departure_airport": {
            "name": "Shanghai Pudong International Airport",
            "id": "PVG",
            "time": "2024-07-17 09:05"
          },
          "arrival_airport": {
            "name": "Narita International Airport",
            "id": "NRT",
            "time": "2024-07-17 12:50"
          },
          ...
        }
      ],
      "layovers": [
        {
          "duration": 125,
          "name": "Shanghai Pudong International Airport",
          "id": "PVG"
        }
      ],
      "total_duration": 985,
      "price": 4174,
      "type": "Multi-city",
      ...
      "departure_token": "WyJDalJJU21sa1NWOWZibGMwVGpCQlEwZGplbmRDUnkwdExTMHRMUzB0TFhWcWFHMHpNMEZCUVVGQlIyRk5lVUZqU2tKbFJXRkJFZ3ROVlRVMU5IeE5WVFV5TXhvTENQYThHUkFDR2dOVlUwUTRISEQydkJrPSIsW1siQ0RHIiwiMjAyNC0wNy0xNiIsIlBWRyIsbnVsbCwiTVUiLCI1NTQiXSxbIlBWRyIsIjIwMjQtMDctMTciLCJOUlQiLG51bGwsIk1VIiwiNTIzIl1dXQ=="
    }
],
"other_flights": [
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Paris Charles de Gaulle Airport",
            "id": "CDG",
            "time": "2024-07-16 21:20"
          },
          "arrival_airport": {
            "name": "Shanghai Pudong International Airport",
            "id": "PVG",
            "time": "2024-07-17 14:40"
          },
          ...
        },
        {
          "departure_airport": {
            "name": "Shanghai Pudong International Airport",
            "id": "PVG",
            "time": "2024-07-17 16:55"
          },
          "arrival_airport": {
            "name": "Narita International Airport",
            "id": "NRT",
            "time": "2024-07-17 20:55"
          },
          ...
        }
      ],
      "layovers": [
        {
          "duration": 135,
          "name": "Shanghai Pudong International Airport",
          "id": "PVG"
        }
      ],
      "total_duration": 995,
      "price": 4174,
      "type": "Multi-city",
      ...
      "departure_token": "WyJDalJJU21sa1NWOWZibGMwVGpCQlEwZGplbmRDUnkwdExTMHRMUzB0TFhWcWFHMHpNMEZCUVVGQlIyRk5lVUZqU2tKbFJXRkJFZ3ROVlRVM01IeE5WVEkzTVJvTENQYThHUkFDR2dOVlUwUTRISEQydkJrPSIsW1siQ0RHIiwiMjAyNC0wNy0xNiIsIlBWRyIsbnVsbCwiTVUiLCI1NzAiXSxbIlBWRyIsIjIwMjQtMDctMTciLCJOUlQiLG51bGwsIk1VIiwiMjcxIl1dXQ=="
    },
    ...
],
"airports": [
    {
      "departure": [
        {
          "airport": {
            "name": "Paris Charles de Gaulle Airport",
            "id": "CDG"
          },
          "city": "Paris",
          "country": "France",
          "country_code": "FR",
          "image": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcQ9v_tNYxaummsU2qbFn8zuYzkcG0x6qCvqB2gbBnx-2FVlZZPsnkvUXGk07vxotk-0vRQMUYCjj2d4Wg",
          "thumbnail": "https://encrypted-tbn1.gstatic.com/images?q=tbn:ANd9GcSzsj_yw6o3vb8i54_D21VgI5rTohxexQkZ0TrZKDKJwTSKw2yqnRYLoIcBWIY50BlHo-OPMm68zbUO-qnFvmQmm6jvtWPwo7WOzjNGX_A"
        },
        {
          "airport": {
            "name": "Narita International Airport",
            "id": "NRT"
          },
          "city": "Tokyo",
          "country": "Japan",
          "country_code": "JP",
          "image": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcRLnIToEgwiM_jV3cbw5eQZoUAIg6XqdrJAiClDyyg0w-JBSRN5ZeOT-iFb3SvwkwP1uoBCmT-gKE5VcyCYf-xq4guL4NAFICSaNyOnYOA",
          "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcRLnIToEgwiM_jV3cbw5eQZoUAIg6XqdrJAiClDyyg0w-JBSRN5ZeOT-iFb3SvwkwP1uoBCmT-gKE5VcyCYf-xq4guL4NAFICSaNyOnYOA"
        },
        ...
      ],
      "arrival": [
        {
          "airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS"
          },
          "city": "Austin",
          "country": "United States",
          "country_code": "US",
          "image": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcRKdjkMcBZuGRD1MjnuLQvdGtpTk0RyjdYs0Z8JsPtfIjer-6VvmfmMLxzvBkeyUrhf_focikfda4rVHg",
          "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcSQ73FSj9E8pKaNvjWKyEDQGfLV-pky_onARvOY-zHWvQ-hOuPJSqyyXzvyg4-kGGAcZxdO6T5SYGWBzrX8x6MSPq7gBHsSLzX9MYjFJWA"
        },
        ...
      ]
    },
    ...
],
...
}
```

### Ejemplo con `exclude_basic`: `true` (Economy sin tarifas básicas)

Se usa `exclude_basic` para filtrar vuelos Economy que incluyen equipaje de mano y selección de asiento gratuita.

Ejemplo de JSON:

```json
{
  "search_metadata": {
    "id": "68d55f17fc8a2b590a866dc5",
    "status": "Success",
    "json_endpoint": "https://www.serpapi.com/searches/247809397c7209a6/68d55f17fc8a2b590a866dc5.json",
    "created_at": "2025-09-25 15:26:15 UTC",
    "processed_at": "2025-09-25 15:26:15 UTC",
    "google_flights_url": "https://www.google.com/travel/flights?hl=en&gl=us&curr=USD&tfs=CBwQAhoeEgoyMDI1LTEwLTE0agcIARIDTEFYcgcIARIDQVVTGh4SCjIwMjUtMTAtMjFqBwgBEgNBVVNyBwgBEgNMQVhCAQFIAXABmAEByAEB&tfu=EgIIAQ",
    "raw_html_file": "https://www.serpapi.com/searches/247809397c7209a6/68d55f17fc8a2b590a866dc5.html",
    "prettify_html_file": "https://www.serpapi.com/searches/247809397c7209a6/68d55f17fc8a2b590a866dc5.prettify",
    "total_time_taken": 1.37
  },
  "search_parameters": {
    "engine": "google_flights",
    "hl": "en",
    "gl": "us",
    "departure_id": "LAX",
    "arrival_id": "AUS",
    "outbound_date": "2025-10-14",
    "return_date": "2025-10-21",
    "travel_class": 1,
    "currency": "USD",
    "exclude_basic": true
  },
  "best_flights": [
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2025-10-14 11:30"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2025-10-14 16:25"
          },
          "duration": 175,
          "airplane": "Boeing 737MAX 8 Passenger",
          "airline": "Southwest",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/WN.png",
          "travel_class": "Economy",
          "flight_number": "WN 649",
          "legroom": "31 in",
          "extensions": [
            "Average legroom (31 in)",
            "Wi-Fi",
            "In-seat USB outlet",
            "Stream media to your device",
            "Carbon emissions estimate: 150 kg"
          ]
        }
      ],
      "total_duration": 175,
      "carbon_emissions": {
        "this_flight": 151000,
        "typical_for_this_route": 187000,
        "difference_percent": -19
      },
      "price": 393,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/WN.png",
      "extensions": [
        "Checked baggage for a fee",
        "Bag and fare conditions depend on the return flight"
      ],
      "departure_token": "WyJDalJJUW05cFJuUndUakJuTFZWQlJrRXdTbEZDUnkwdExTMHRMUzB0TFhkaVltWm1Na0ZCUVVGQlIycFdXSGhyUzI1TWJIbEJFZ1ZYVGpZME9Sb0xDUGF5QWhBQ0dnTlZVMFE0SEhEMnNnST0iLFtbIkxBWCIsIjIwMjUtMTAtMTQiLCJBVVMiLG51bGwsIldOIiwiNjQ5Il1dXQ=="
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2025-10-14 10:04"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2025-10-14 15:10"
          },
          "duration": 186,
          "airplane": "Boeing 737",
          "airline": "Delta",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/DL.png",
          "travel_class": "Economy",
          "flight_number": "DL 986",
          "legroom": "31 in",
          "extensions": [
            "Average legroom (31 in)",
            "Free Wi-Fi",
            "In-seat power & USB outlets",
            "Live TV",
            "Carbon emissions estimate: 175 kg"
          ]
        }
      ],
      "total_duration": 186,
      "carbon_emissions": {
        "this_flight": 176000,
        "typical_for_this_route": 187000,
        "difference_percent": -6
      },
      "price": 464,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/DL.png",
      "extensions": [
        "Checked baggage for a fee",
        "Bag and fare conditions depend on the return flight"
      ],
      "departure_token": "WyJDalJJUW05cFJuUndUakJuTFZWQlJrRXdTbEZDUnkwdExTMHRMUzB0TFhkaVltWm1Na0ZCUVVGQlIycFdXSGhyUzI1TWJIbEJFZ1ZFVERrNE5ob0xDTDdxQWhBQ0dnTlZVMFE0SEhDKzZnST0iLFtbIkxBWCIsIjIwMjUtMTAtMTQiLCJBVVMiLG51bGwsIkRMIiwiOTg2Il1dXQ=="
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2025-10-14 07:45"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2025-10-14 12:44"
          },
          "duration": 179,
          "airplane": "Boeing 737",
          "airline": "American",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/AA.png",
          "travel_class": "Economy",
          "flight_number": "AA 821",
          "ticket_also_sold_by": [
            "Alaska"
          ],
          "legroom": "30 in",
          "extensions": [
            "Average legroom (30 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "Stream media to your device",
            "Carbon emissions estimate: 185 kg"
          ]
        }
      ],
      "total_duration": 179,
      "carbon_emissions": {
        "this_flight": 186000,
        "typical_for_this_route": 187000,
        "difference_percent": -1
      },
      "price": 473,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/AA.png",
      "extensions": [
        "Checked baggage for a fee",
        "Bag and fare conditions depend on the return flight"
      ],
      "departure_token": "WyJDalJJUW05cFJuUndUakJuTFZWQlJrRXdTbEZDUnkwdExTMHRMUzB0TFhkaVltWm1Na0ZCUVVGQlIycFdXSGhyUzI1TWJIbEJFZ1ZCUVRneU1Sb0xDTUh4QWhBQ0dnTlZVMFE0SEhEQjhRST0iLFtbIkxBWCIsIjIwMjUtMTAtMTQiLCJBVVMiLG51bGwsIkFBIiwiODIxIl1dXQ=="
    },
    {
      "flights": [
        {
          "departure_airport": {
            "name": "Los Angeles International Airport",
            "id": "LAX",
            "time": "2025-10-14 10:35"
          },
          "arrival_airport": {
            "name": "Austin-Bergstrom International Airport",
            "id": "AUS",
            "time": "2025-10-14 15:38"
          },
          "duration": 183,
          "airplane": "Boeing 737MAX 8 Passenger",
          "airline": "United",
          "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/UA.png",
          "travel_class": "Economy",
          "flight_number": "UA 1990",
          "legroom": "30 in",
          "extensions": [
            "Average legroom (30 in)",
            "Wi-Fi for a fee",
            "In-seat power & USB outlets",
            "On-demand video",
            "Carbon emissions estimate: 197 kg"
          ]
        }
      ],
      "total_duration": 183,
      "carbon_emissions": {
        "this_flight": 197000,
        "typical_for_this_route": 187000,
        "difference_percent": 5
      },
      "price": 473,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/UA.png",
      "extensions": [
        "Checked baggage for a fee",
        "Bag and fare conditions depend on the return flight"
      ],
      "departure_token": "WyJDalJJUW05cFJuUndUakJuTFZWQlJrRXdTbEZDUnkwdExTMHRMUzB0TFhkaVltWm1Na0ZCUVVGQlIycFdXSGhyUzI1TWJIbEJFZ1pWUVRFNU9UQWFDd2pCOFFJUUFob0RWVk5FT0J4d3dmRUMiLFtbIkxBWCIsIjIwMjUtMTAtMTQiLCJBVVMiLG51bGwsIlVBIiwiMTk5MCJdXV0="
    }
  ],
  ...
}
```

---

## Estructura del JSON

Resumen de la estructura de la respuesta (los valores describen el tipo y el significado de cada campo, tal como aparecen en la documentación):

```json
{
  ...
  "best_flights": [
    // best_flights is not always returned
    {
      "flights": [
        {
          "departure_airport": {
            "name": "String - Departure airport name",
            "id": "String - Departure airport code",
            "time": "String - Departure time"
          },
          "arrival_airport": {
            "name": "String - Arrival airport name",
            "id": "String - Arrival airport code",
            "time": "String - Arrival time"
          },
          "duration": "Integer - Flight duration, in minutes",
          "airplane": "String - Airplane model",
          "airline": "String - Name of the airline",
          "airline_logo": "String - URL to the logo of the airline",
          "travel_class": "String - Travel class",
          "flight_number": "String - The flight number",
          "extensions": "Array - A list of flight features",
          "ticket_also_sold_by": "Array - A list of other sellers",
          "legroom": "String - The legroom, including unit",
          "overnight": "Boolean - Returns 'true' if the flight is overnight",
          "often_delayed_by_over_30_min": "Boolean - Returns 'true' if the flight is often delayed by 30+ min.",
          "plane_and_crew_by": "String - Information about operating airline that provides the plane and the crew",
        }
      ],
      "layovers": [
        {
          "duration": "Integer - Duration of the layover, in minutes",
          "name": "String - Name of the airport for the layover",
          "id": "String - The airport code for the layover",
          "overnight": "Boolean - Returns 'true' if the layover is overnight",
        }
      ],
      "total_duration": "Integer - Total minutes of all flights and layovers",
      "carbon_emissions": {
        "this_flight": "Integer - The amount of carbon emissions of the flight, in grams",
        "typical_for_this_route": "Integer - Typical amount of carbon emissions for the route, in grams",
        "difference_percent": "Integer - The carbon emissions difference between the flight and typical value, in percent",
      },
      "price": "Integer - This ticket price in the selected currency, the default currency is USD",
      "type": "String - The type of the flight. It's a reflection of the request parameter `type`",
      "airline_logo": "String - URL to the logo of mixed airlines",
      "extensions": "Array - A list of features of the entire flight",
      "departure_token": "String - The token for retrieving returning flights when the flight type is 'Round trip'",
      "booking_token": "String - The token for retrieving booking options for selected flights",
    }
  ],
  "other_flights": [
    // The same structure as best_flights
    // When the results are not separated into best_flights and other_flights, they are in other_flights
  ]
  "price_insights": {
    "lowest_price": "Integer - The lowest price among the returned flights",
    "price_level": "String - Price level of the lowest_price",
    "typical_price_range": "Array - A two-integer array, indicating the low bound and high bound of 'typical' price of this flight",
    "price_history": "Array - A two-integer array, where the first element is the timestamp, and the second one is the price",
  },
  "airports": [
    {
      "departure": [
        {
          "airport": {
            "name": "String - Departure airport name",
            "id": "String - Departure airport code"
          },
          "city": "String - Departure city",
          "country": "String - Departure country name",
          "country_code": "String - Departure country code",
          "image": "String - URL to the image of the departure city",
          "thumbnail": "String - URL to the thumbnail image of the departure city"
        },
      ],
      "arrival": [
        {
          "airport": {
            "name": "String - Arrival airport name",
            "id": "String - Arrival airport code"
          },
          "city": "String - Arrival city",
          "country": "String - Arrival country name",
          "country_code": "String - Arrival country code",
          "image": "String - URL to the image of the arrival city",
          "thumbnail": "String - URL to the thumbnail image of the arrival city"
        },
      ]
    },
  ],
  ...
}
```


### Campos explicados en español

`best_flights` no siempre se devuelve. `other_flights` tiene la misma estructura; cuando los resultados no vienen separados en "mejores" y "otros", todos llegan en `other_flights`.

Cada itinerario (elemento de `best_flights` u `other_flights`):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `flights` | Array | Segmentos de vuelo del itinerario |
| `layovers` | Array | Escalas entre segmentos |
| `total_duration` | Integer | Minutos totales de todos los vuelos y escalas |
| `carbon_emissions.this_flight` | Integer | Emisiones de carbono del vuelo, en gramos |
| `carbon_emissions.typical_for_this_route` | Integer | Emisiones típicas de la ruta, en gramos |
| `carbon_emissions.difference_percent` | Integer | Diferencia entre el vuelo y el valor típico, en porcentaje |
| `price` | Integer | Precio del tiquete en la moneda seleccionada (USD por defecto) |
| `type` | String | Tipo de vuelo; refleja el parámetro `type` de la petición |
| `airline_logo` | String | URL del logo (logo mixto si hay varias aerolíneas) |
| `extensions` | Array | Características del itinerario completo |
| `departure_token` | String | Token para obtener los vuelos de regreso cuando el tipo es ida y vuelta |
| `booking_token` | String | Token para obtener las opciones de reserva de los vuelos seleccionados |

Cada segmento dentro de `flights`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `departure_airport.name` / `.id` / `.time` | String | Nombre, código y hora del aeropuerto de salida |
| `arrival_airport.name` / `.id` / `.time` | String | Nombre, código y hora del aeropuerto de llegada |
| `duration` | Integer | Duración del vuelo, en minutos |
| `airplane` | String | Modelo del avión |
| `airline` | String | Nombre de la aerolínea |
| `airline_logo` | String | URL del logo de la aerolínea |
| `travel_class` | String | Clase de viaje |
| `flight_number` | String | Número de vuelo |
| `extensions` | Array | Lista de características del vuelo |
| `ticket_also_sold_by` | Array | Otros vendedores del tiquete |
| `legroom` | String | Espacio para las piernas, con unidad |
| `overnight` | Boolean | `true` si el vuelo es nocturno |
| `often_delayed_by_over_30_min` | Boolean | `true` si el vuelo suele retrasarse más de 30 min |
| `plane_and_crew_by` | String | Aerolínea operadora que pone el avión y la tripulación |

Cada escala dentro de `layovers`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `duration` | Integer | Duración de la escala, en minutos |
| `name` | String | Nombre del aeropuerto de la escala |
| `id` | String | Código del aeropuerto de la escala |
| `overnight` | Boolean | `true` si la escala es nocturna |

`price_insights`:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `lowest_price` | Integer | Precio más bajo entre los vuelos devueltos |
| `price_level` | String | Nivel de precio del `lowest_price` (p. ej. `low`) |
| `typical_price_range` | Array | Dos enteros: límite inferior y superior del precio "típico" del vuelo |
| `price_history` | Array | Pares de enteros: marca de tiempo (timestamp) y precio |

`airports` (cada elemento tiene `departure` y `arrival`, con la misma forma):

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `airport.name` / `airport.id` | String | Nombre y código del aeropuerto |
| `city` | String | Ciudad |
| `country` | String | País |
| `country_code` | String | Código del país |
| `image` | String | URL de la imagen de la ciudad |
| `thumbnail` | String | URL de la miniatura de la ciudad |

`search_metadata`:

| Campo | Descripción |
| --- | --- |
| `id` | ID de la búsqueda dentro de SerpApi |
| `status` | Estado: `Processing`, `Success` o `Error` |
| `json_endpoint` | URL del resultado JSON guardado |
| `created_at` / `processed_at` | Fechas de creación y procesamiento (UTC) |
| `google_flights_url` | URL equivalente en Google Flights |
| `raw_html_file` | URL del HTML crudo |
| `prettify_html_file` | URL de la versión formateada |
| `total_time_taken` | Tiempo total de la búsqueda, en segundos |

`search_parameters` repite los parámetros con los que se hizo la petición.

---

## Enlaces relacionados

- Documentación principal: <https://serpapi.com/google-flights-api>
- Playground: <https://serpapi.com/playground?engine=google_flights>
- Notas de versión: <https://serpapi.com/google-flights-api/release-notes>
- Métricas / uptime: <https://serpapi.com/google-flights-api/api-metrics>
- Flight Results: <https://serpapi.com/google-flights-results>
- Price Insights: <https://serpapi.com/google-flights-price-insights>
- Países soportados (`gl`): <https://serpapi.com/google-countries>
- Idiomas soportados (`hl`): <https://serpapi.com/google-languages>
- Monedas soportadas (`currency`): <https://serpapi.com/google-travel-currencies>
- Searches Archive API (para `async`): <https://serpapi.com/search-archive-api>
- JSON Restrictor: <https://serpapi.com/json-restrictor>
- Modo ZeroTrace: <https://serpapi.com/zero-trace-mode>
- Códigos IATA de aeropuertos y aerolíneas: <https://www.iata.org/en/publications/directories/code-search>
