# Documentación — APIs de Google Flights en SerpApi

Documentación de referencia para el proyecto, armada a partir de las páginas oficiales de SerpApi consultadas el **12 de noviembre de 2026**.

Criterios de toda la carpeta:

- Los **nombres de parámetros y campos JSON se dejan en inglés**, porque así los espera y los devuelve la API. Las explicaciones están en español.
- La clave privada que aparece en los ejemplos de la web fue reemplazada por `TU_API_KEY`.
- Las URLs de imágenes, logos y tokens muy largos se abrevian en los ejemplos para que se lean; en la respuesta real vienen completos.

## Índice

| # | Archivo | Qué cubre |
| --- | --- | --- |
| 01 | [01-api-google-flights.md](01-api-google-flights.md) | **API de Google Flights**: motor principal, todos los parámetros de búsqueda, filtros, tokens, formatos de salida y ejemplos |
| 02 | [02-resultados-de-los-vuelos.md](02-resultados-de-los-vuelos.md) | **Resultados de los vuelos**: `best_flights` y `other_flights`, segmentos, escalas, emisiones, tokens |
| 03 | [03-informacion-de-precios.md](03-informacion-de-precios.md) | **Información sobre precios**: `price_insights`, nivel de precio, rango típico e histórico |
| 04 | [04-resultados-de-aeropuertos.md](04-resultados-de-aeropuertos.md) | **Resultados de aeropuertos**: `airports`, con ciudad, país e imágenes por tramo |
| 05 | [05-opciones-de-reserva.md](05-opciones-de-reserva.md) | **Opciones de reserva**: `booking_options`, `selected_flights`, `baggage_prices` y cómo ejecutar la reserva |
| 06 | [06-api-autocompletado.md](06-api-autocompletado.md) | **API de autocompletado**: sugerencias de ciudades y aeropuertos a partir de texto |
| 07 | [07-api-google-flights-calendar.md](07-api-google-flights-calendar.md) | **Google Flights Calendar API**: precio por fecha dentro de un rango |
| 08 | [08-api-ofertas-de-vuelos.md](08-api-ofertas-de-vuelos.md) | **API de ofertas de vuelos**: destinos con descuento desde un origen |

## Los cuatro motores (`engine`)

| Motor | Endpoint | Qué devuelve | Documento |
| --- | --- | --- | --- |
| `google_flights` | `https://serpapi.com/search?engine=google_flights` | Itinerarios, precios, aeropuertos, opciones de reserva | 01, 02, 03, 04, 05 |
| `google_flights_autocomplete` | `https://serpapi.com/search?engine=google_flights_autocomplete` | `suggestions` | 06 |
| `google_flights_calendar` | `https://serpapi.com/search?engine=google_flights_calendar` | `prices` | 07 |
| `google_flights_deals` | `https://serpapi.com/search?engine=google_flights_deals` | `departure_informations`, `deals` | 08 |

Los documentos 02 a 05 **no son motores aparte**: describen los bloques que devuelve el motor `google_flights` en una misma respuesta.

## Qué devuelve cada motor, de un vistazo

```
google_flights
├── best_flights[]        → doc 02
├── other_flights[]       → doc 02
├── price_insights        → doc 03
├── airports[]            → doc 04
└── con booking_token o selected_flights_json:
    ├── selected_flights[]  → doc 05
    ├── baggage_prices      → doc 05
    └── booking_options[]   → doc 05

google_flights_autocomplete
└── suggestions[]         → doc 06

google_flights_calendar
└── prices[]              → doc 07

google_flights_deals
├── departure_informations → doc 08
└── deals[]                → doc 08
```

## Parámetros comunes a los cuatro motores

Estos se comportan igual en todos: `api_key` (obligatorio), `engine` (obligatorio), `gl`, `hl`, `no_cache`, `async`, `zero_trace`, `output`, `json_restrictor`. Están explicados en detalle en el documento 01 y se repiten resumidos en cada documento.

Reglas que aplican siempre:

- La caché expira a la hora, solo aplica si la consulta y **todos** los parámetros son idénticos, y las búsquedas servidas desde caché son gratis.
- `no_cache` y `async` no deben usarse juntos.
- El estado de la búsqueda está en `search_metadata.status`: `Processing` → `Success` || `Error`.

## Flujo típico de una integración

1. **Autocompletado** (doc 06): el usuario escribe texto → se obtienen `id` de ciudad o códigos IATA.
2. **Calendario** (doc 07) u **Ofertas** (doc 08), si las fechas o el destino son flexibles.
3. **Búsqueda de vuelos** (docs 01 y 02): con `departure_id`, `arrival_id` y fechas → itinerarios.
4. Si es ida y vuelta, segunda llamada con el `departure_token` del itinerario elegido → vuelos de regreso.
5. **Opciones de reserva** (doc 05): llamada con el `booking_token` (o fijando el itinerario con `selected_flights_json`) → vendedores, precios y el `booking_request` con el que se completa la reserva.

## Enlaces oficiales

- API de Google Flights: <https://serpapi.com/google-flights-api>
- Resultados de vuelos: <https://serpapi.com/google-flights-results>
- Información de precios: <https://serpapi.com/google-flights-price-insights>
- Resultados de aeropuertos: <https://serpapi.com/google-flights-airports>
- Opciones de reserva: <https://serpapi.com/google-flights-booking-options>
- API de autocompletado: <https://serpapi.com/google-flights-autocomplete-api>
- Google Flights Calendar API: <https://serpapi.com/google-flights-calendar-api>
- API de ofertas de vuelos: <https://serpapi.com/google-flights-deals-api>
- Países (`gl`): <https://serpapi.com/google-countries>
- Idiomas (`hl`): <https://serpapi.com/google-languages>
- Monedas (`currency`): <https://serpapi.com/google-travel-currencies>
- JSON Restrictor: <https://serpapi.com/json-restrictor>
- Searches Archive API (para `async`): <https://serpapi.com/search-archive-api>
- Modo ZeroTrace: <https://serpapi.com/zero-trace-mode>
- Códigos IATA: <https://www.iata.org/en/publications/directories/code-search>

## Nota sobre las fechas de los ejemplos

Las fechas que aparecen en las URLs de ejemplo (`2026-11-13`, `2026-11-19`, etc.) son las que la web de SerpApi generaba el día de la consulta: se recalculan solas en la página. Los JSON de ejemplo conservan las fechas originales de cada caso documentado (2023, 2025, 2026), por eso no coinciden entre sí.
