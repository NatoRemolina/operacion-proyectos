# Resultados de los vuelos (Google Flights Results API)

> Fuente: <https://serpapi.com/google-flights-results> — consultada el 12 de noviembre de 2026.
> Nombres de campos en inglés (así los devuelve la API); explicaciones en español.

## Qué es

SerpApi extrae los resultados de vuelos de Google Flights y los agrega a la salida JSON como los arreglos `best_flights` y `other_flights`.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights` |
| Motor (`engine`) | `google_flights` |
| Campos que produce | `best_flights`, `other_flights` |
| Playground | <https://serpapi.com/playground?engine=google_flights> |

Reglas generales:

- `best_flights` **no siempre se devuelve**. Google lo muestra solo cuando separa los resultados en "mejores vuelos" y "otros vuelos".
- Cuando los resultados **no** vienen separados, todos llegan dentro de `other_flights`.
- `other_flights` tiene exactamente la misma estructura que `best_flights`.

---

## Estructura de un itinerario

Cada elemento de `best_flights` / `other_flights` es un itinerario completo:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `flights` | Array | Segmentos de vuelo que componen el itinerario |
| `layovers` | Array | Escalas entre segmentos |
| `total_duration` | Integer | Minutos totales de todos los vuelos y escalas |
| `carbon_emissions` | Object | Emisiones de carbono del itinerario |
| `price` | Integer | Precio del tiquete en la moneda seleccionada (por defecto USD) |
| `type` | String | Tipo de vuelo; refleja el parámetro `type` de la petición |
| `airline_logo` | String | URL del logo; si hay varias aerolíneas, es el logo mixto (`multi.png`) |
| `extensions` | Array | Características del itinerario completo |
| `departure_token` | String | Token para obtener los vuelos de regreso cuando el tipo es "Round trip" |
| `booking_token` | String | Token para obtener las opciones de reserva de los vuelos seleccionados |

### `flights[]` — cada segmento

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `departure_airport.name` | String | Nombre del aeropuerto de salida |
| `departure_airport.id` | String | Código del aeropuerto de salida |
| `departure_airport.time` | String | Hora de salida |
| `arrival_airport.name` | String | Nombre del aeropuerto de llegada |
| `arrival_airport.id` | String | Código del aeropuerto de llegada |
| `arrival_airport.time` | String | Hora de llegada |
| `duration` | Integer | Duración del vuelo, en minutos |
| `airplane` | String | Modelo del avión |
| `airline` | String | Nombre de la aerolínea |
| `airline_logo` | String | URL del logo de la aerolínea |
| `travel_class` | String | Clase de viaje |
| `flight_number` | String | Número de vuelo |
| `extensions` | Array | Características del vuelo |
| `ticket_also_sold_by` | Array | Otros vendedores del tiquete |
| `legroom` | String | Espacio para las piernas, con unidad |
| `overnight` | Boolean | `true` si el vuelo es nocturno |
| `often_delayed_by_over_30_min` | Boolean | `true` si el vuelo suele retrasarse más de 30 minutos |
| `plane_and_crew_by` | String | Aerolínea operadora que pone el avión y la tripulación |

Valores típicos de `extensions` en un segmento: `"Average legroom (31 in)"`, `"Below average legroom (29 in)"`, `"Above average legroom (33 in)"`, `"Wi-Fi for a fee"`, `"Free Wi-Fi"`, `"In-seat power & USB outlets"`, `"In-seat USB outlet"`, `"On-demand video"`, `"Stream media to your device"`, `"Live TV"`, `"Lie flat seat"`, `"Individual suite"`, `"Carbon emissions estimate: 133 kg"`.

### `layovers[]` — cada escala

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `duration` | Integer | Duración de la escala, en minutos |
| `name` | String | Nombre del aeropuerto de la escala |
| `id` | String | Código del aeropuerto de la escala |
| `overnight` | Boolean | `true` si la escala es nocturna |

### `carbon_emissions`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `this_flight` | Integer | Emisiones de carbono del vuelo, en gramos |
| `typical_for_this_route` | Integer | Emisiones típicas de la ruta, en gramos |
| `difference_percent` | Integer | Diferencia porcentual entre el vuelo y el valor típico |

Ojo con la unidad: `this_flight: 1106000` son 1 106 000 gramos, es decir 1 106 kg.

### `extensions` a nivel de itinerario

Valores observados: `"Checked baggage for a fee"`, `"Full refund for cancellations"`, `"Free change, possible fare difference"`, `"Bag and fare conditions depend on the return flight"`.

---

## Tokens: `departure_token` vs `booking_token`

| Token | Cuándo aparece | Para qué sirve |
| --- | --- | --- |
| `departure_token` | En la primera petición de un viaje de ida y vuelta (`type=1`) o multiciudad (`type=3`) | Pedir los vuelos de regreso o el siguiente tramo |
| `booking_token` | En resultados de solo ida, y en los resultados de regreso ya seleccionados | Pedir las opciones de reserva |

En una búsqueda de ida y vuelta, los itinerarios de la **primera** petición traen `departure_token`; los de la **segunda** petición (hecha con ese token) traen `booking_token`.

---

## Ejemplos

### 1. Con `best_flights` y `other_flights`

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=PEK&arrival_id=AUS&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&hl=en&api_key=TU_API_KEY
```

```json
{
...
"best_flights": [
    {
      "flights": [
        {
          "departure_airport": { "name": "Beijing Capital International Airport", "id": "PEK", "time": "2023-10-03 15:10" },
          "arrival_airport":   { "name": "Haneda Airport", "id": "HND", "time": "2023-10-03 19:35" },
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
          "departure_airport": { "name": "Haneda Airport", "id": "HND", "time": "2023-10-03 21:05" },
          "arrival_airport":   { "name": "Los Angeles International Airport", "id": "LAX", "time": "2023-10-03 15:10" },
          "duration": 605,
          "airplane": "Boeing 787",
          "airline": "ANA",
          "travel_class": "Economy",
          "flight_number": "NH 126",
          "ticket_also_sold_by": ["United"],
          "legroom": "32 in",
          "extensions": ["Above average legroom (32 in)", "In-seat power & USB outlets", "On-demand video", "Carbon emissions estimate: 836 kg"],
          "overnight": true
        }
      ],
      "layovers": [
        { "duration": 90,  "name": "Haneda Airport", "id": "HND" },
        { "duration": 231, "name": "Los Angeles International Airport", "id": "LAX" }
      ],
      "total_duration": 1309,
      "carbon_emissions": { "this_flight": 1106000, "typical_for_this_route": 949000, "difference_percent": 17 },
      "price": 2512,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/multi.png",
      "departure_token": "W1siUEVLIiwiMjAyMy0xMC0wMyIsIkhORCIsbnVsbCwiTkgiLCI5NjIiXSxb..."
    },
    ...
],
"other_flights": [
    // misma estructura
],
...
}
```

Este ejemplo también muestra una escala nocturna:

```json
"layovers": [
  { "duration": 425, "name": "Incheon International Airport", "id": "ICN" },
  { "duration": 970, "name": "San Francisco International Airport", "id": "SFO", "overnight": true }
]
```

### 2. Sin `best_flights` (solo `other_flights`)

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=PEK&arrival_id=IST&outbound_date=2026-11-13&return_date=2026-11-19&travel_class=4&currency=USD&hl=en&api_key=TU_API_KEY
```

Búsqueda en primera clase (`travel_class=4`) de PEK a IST. Google no separa "mejores vuelos", así que todo llega en `other_flights`:

```json
{
...
"other_flights": [
    {
      "flights": [
        {
          "departure_airport": { "name": "Beijing Capital International Airport", "id": "PEK", "time": "2023-10-26 00:40" },
          "arrival_airport":   { "name": "Dubai International Airport", "id": "DXB", "time": "2023-10-26 05:00" },
          "duration": 500,
          "airplane": "Airbus A380",
          "airline": "Emirates",
          "travel_class": "First Class",
          "flight_number": "EK 307",
          "extensions": ["Individual suite", "Wi-Fi for a fee", "In-seat power & USB outlets", "On-demand video", "Carbon emissions estimate: 2058 kg"],
          "overnight": true
        },
        {
          "departure_airport": { "name": "Dubai International Airport", "id": "DXB", "time": "2023-10-26 12:00" },
          "arrival_airport":   { "name": "Istanbul Airport", "id": "IST", "time": "2023-10-26 15:55" },
          "duration": 295,
          "airplane": "Boeing 737MAX 8 Passenger",
          "airline": "flydubai",
          "travel_class": "Business Class",
          "flight_number": "FZ 727",
          "ticket_also_sold_by": ["Emirates"],
          "extensions": ["Lie flat seat", "In-seat power & USB outlets", "On-demand video", "Carbon emissions estimate: 264 kg"]
        }
      ],
      "layovers": [{ "duration": 420, "name": "Dubai International Airport", "id": "DXB" }],
      "total_duration": 1215,
      "carbon_emissions": { "this_flight": 2324000, "typical_for_this_route": 2861000, "difference_percent": -19 },
      "price": 10474,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/multi.png",
      "departure_token": "W1siUEVLIiwiMjAyMy0xMC0yNiIsIkRYQiIsbnVsbCwiRUsiLCIzMDciXSxb..."
    },
    ...
],
...
}
```

Nota: en esta búsqueda de primera clase los segmentos no traen `legroom`, porque Google describe el asiento con `"Individual suite"` o `"Lie flat seat"` en `extensions`.

### 3. Vuelos de regreso (resultado con `booking_token`)

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=NRT&arrival_id=LAX&outbound_date=2026-11-13&return_date=2026-11-19&departure_token=WyJDalJJTVUxUmFYaGFabWR0ZEhkQlJGUXpTM2RDUnkwdExTMHRMUzB0TFhCbWEzTXhNMEZCUVVGQlIxWnNaSGt3UlVwS1dFVkJFZ1JWUVRNekdnc0k5SWNF...&currency=USD&hl=en&api_key=TU_API_KEY
```

Al usar `departure_token`, los itinerarios devueltos ya no traen `departure_token` sino `booking_token`:

```json
{
...
"best_flights": [
    {
      "flights": [
        {
          "departure_airport": { "name": "Los Angeles International Airport", "id": "LAX", "time": "2023-10-07 13:05" },
          "arrival_airport":   { "name": "Narita International Airport", "id": "NRT", "time": "2023-10-08 16:40" },
          "duration": 695,
          "airplane": "Boeing 787",
          "airline": "JAL",
          "travel_class": "Economy",
          "flight_number": "JL 61",
          "ticket_also_sold_by": ["American", "Alaska"],
          "legroom": "33 in",
          "extensions": ["Above average legroom (33 in)", "Wi-Fi for a fee", "In-seat power & USB outlets", "On-demand video", "Carbon emissions estimate: 807 kg"]
        }
      ],
      "total_duration": 695,
      "carbon_emissions": { "this_flight": 808000, "typical_for_this_route": 615000, "difference_percent": 31 },
      "price": 1862,
      "type": "Round trip",
      "airline_logo": "https://www.gstatic.com/flights/airline_logos/70px/JL.png",
      "booking_token": "WyJDalJJTVUxUmFYaGFabWR0ZEhkQlJGUXpTM2RDUnkwdExTMHRMUzB0TFhCbWEzTXhNMEZCUVVGQlIxWnNaSGt3UlVwS1dFVkJFZ1JWUVRNekdnc0k5SWNFRUFJYUExVlRSRGdjY1BTSEJBPT0iLFtb..."
    },
    ...
],
...
}
```

Un itinerario sin escalas no incluye el arreglo `layovers`.

### 4. Vuelos con "Plane and crew by ..."

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=PAE&arrival_id=JFK&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&hl=en&api_key=TU_API_KEY
```

Cuando una aerolínea regional opera el vuelo en nombre de otra, aparece `plane_and_crew_by`:

```json
{
  "departure_airport": { "name": "Paine Field", "id": "PAE", "time": "2025-04-10 14:49" },
  "arrival_airport":   { "name": "San Francisco International Airport", "id": "SFO", "time": "2025-04-10 16:57" },
  "duration": 128,
  "airplane": "Embraer 175",
  "airline": "Alaska",
  "travel_class": "Economy",
  "flight_number": "AS 2334",
  "ticket_also_sold_by": ["Hawaiian"],
  "legroom": "31 in",
  "extensions": ["Average legroom (31 in)", "Wi-Fi for a fee", "Stream media to your device", "Carbon emissions estimate: 159 kg"],
  "plane_and_crew_by": "Horizon Air as Alaska Horizon"
}
```

Otro valor del mismo ejemplo: `"plane_and_crew_by": "SkyWest Airlines as Alaska SkyWest"`.

---

## Resumen de la estructura (tal como la documenta SerpApi)

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
          "plane_and_crew_by": "String - Information about operating airline that provides the plane and the crew"
        }
      ],
      "layovers": [
        {
          "duration": "Integer - Duration of the layover, in minutes",
          "name": "String - Name of the airport for the layover",
          "id": "String - The airport code for the layover",
          "overnight": "Boolean - Returns 'true' if the layover is overnight"
        }
      ],
      "total_duration": "Integer - Total minutes of all flights and layovers",
      "carbon_emissions": {
        "this_flight": "Integer - The amount of carbon emissions of the flight, in grams",
        "typical_for_this_route": "Integer - Typical amount of carbon emissions for the route, in grams",
        "difference_percent": "Integer - The carbon emissions difference between the flight and typical value, in percent"
      },
      "price": "Integer - This ticket price in the selected currency, the default currency is USD",
      "type": "String - The type of the flight. It's a reflection of the request parameter `type`",
      "airline_logo": "String - URL to the logo of mixed airlines",
      "extensions": "Array - A list of features of the entire flight",
      "departure_token": "String - The token for retrieving returning flights when the flight type is 'Round trip'",
      "booking_token": "String - The token for retrieving booking options for selected flights"
    }
  ],
  "other_flights": [
    // The same structure as best_flights
    // When the results are not separated into best_flights and other_flights, they are in other_flights
  ],
  ...
}
```

## Relacionado

- Parámetros de la búsqueda: [01-api-google-flights.md](01-api-google-flights.md)
- Precios: [03-informacion-de-precios.md](03-informacion-de-precios.md)
- Aeropuertos: [04-resultados-de-aeropuertos.md](04-resultados-de-aeropuertos.md)
- Reserva: [05-opciones-de-reserva.md](05-opciones-de-reserva.md)
