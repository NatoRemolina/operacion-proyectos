# Opciones de reserva (Google Flights Booking Options API)

> Fuente: <https://serpapi.com/google-flights-booking-options> — consultada el 12 de noviembre de 2026.
> Nombres de campos en inglés (así los devuelve la API); explicaciones en español.

## Qué es

SerpApi extrae las opciones de reserva de Google Flights y las agrega a la salida JSON como el arreglo `booking_options`. Como información de apoyo también agrega `selected_flights` y `baggage_prices`.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights` |
| Motor (`engine`) | `google_flights` |
| Campos que produce | `booking_options`, `selected_flights`, `baggage_prices` (y también `price_insights`) |
| Playground | <https://serpapi.com/playground?engine=google_flights> |

## Cómo se piden

Las opciones de reserva se devuelven cuando se hace **una de estas dos cosas**:

1. Enviar un `booking_token` en los parámetros de búsqueda (token que viene en los resultados de vuelos), **o**
2. Fijar un itinerario concreto con el parámetro `selected_flights_json`.

Importante: al usar `booking_token`, los parámetros relacionados con fechas y los de la sección "Filtros avanzados" no afectan el resultado.

Nota de formato: las opciones que en el HTML de Google aparecen agrupadas por vendedor, en el JSON llegan **aplanadas** (una entrada por opción).

---

## Estructura de la respuesta

### `selected_flights`

Tiene la misma estructura que `best_flights` / `other_flights`. Describe el itinerario que se está reservando. Ver [02-resultados-de-los-vuelos.md](02-resultados-de-los-vuelos.md).

### `baggage_prices`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `together` | Array | Política de precios de equipaje del tiquete completo |
| `departing` | Array | Política de equipaje solo del vuelo de ida |
| `returning` | Array | Política de equipaje solo del vuelo de regreso |

Son cadenas de texto legibles, por ejemplo `"1 free carry-on"`, `"1st checked bag: 99-187"`, `"1st checked bag up to 23 kg free"`.

### `booking_options[]`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `separate_tickets` | Boolean | `true` si los tiquetes se reservan por separado |
| `together` | Object | Datos de la opción cuando se reserva todo junto |
| `departing` | Object | Misma estructura que `together`; aparece cuando `separate_tickets` es `true` |
| `returning` | Object | Misma estructura que `together`; aparece cuando `separate_tickets` es `true` |

### Campos de `together` / `departing` / `returning`

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `book_with` | String | Nombre del vendedor o vendedores |
| `airline` | Boolean | `true` si el vendedor es la aerolínea operadora |
| `airline_logos` | Array | URLs de los logos de los vendedores |
| `marketed_as` | Array | Números de vuelo |
| `price` | Float | Precio del tiquete |
| `local_prices` | Array | Precio en otras monedas: objetos con `currency` y `price` |
| `option_title` | String | Título de la opción (por ejemplo `"Basic Economy"`, `"Economy Plus"`) |
| `extensions` | Array | Características de la tarifa |
| `baggage_prices` | Array | Política de precios de equipaje de esa opción |
| `booking_request` | Object | Cómo ejecutar la reserva (ver abajo) |
| `booking_phone` | String | Teléfono para reservar |
| `estimated_phone_service_fee` | Float | Cargo estimado por el servicio telefónico |

Valores típicos de `extensions` en una opción: `"No refunds"`, `"Ticket changes for a fee"`, `"Seat selection for a fee"`, `"Standard seat"`.

### `booking_request` — cómo completar la reserva

| Campo | Descripción |
| --- | --- |
| `url` | Endpoint de Google que resuelve la acción de reserva. Cuando hay `post_data`, se llama con **HTTP POST** |
| `post_data` | Carga útil en formato form-encoded, que se envía **tal cual** como cuerpo del POST |

Reglas que indica la documentación:

- Cuando `post_data` está presente, se debe usar siempre **HTTP POST** hacia `booking_request.url` y enviar `post_data` como cuerpo de la petición **sin modificarlo** (no decodificar, no recodificar, no alterar).
- Solo se usa **HTTP GET** cuando se entrega un deeplink directo y `post_data` no está presente.

El `url` observado en los ejemplos es `https://www.google.com/travel/clk/f`.

Cuando una opción solo se puede reservar por teléfono, en lugar de `booking_request` aparece `booking_phone` (y, si aplica, `estimated_phone_service_fee`).

---

## Ejemplos

### 1. Resultado típico

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=CDG&arrival_id=LHR&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&hl=en&booking_token=WyJDalJJYjJkRGNubFBWekpGVkhkQlFUazJTa0ZDUnkwdExTMHRMUzB0TFhCbVltWnhOa0ZCUVVGQlIxWm5UWE5SUlY5RU4wRkJFZ2RDUVRNeU9DTXhHZ3NJMTVJQkVBSWFBMVZUUkRnY2NOZVNBUT09...&api_key=TU_API_KEY
```

```json
{
...
"selected_flights": [
    {
      "flights": [
        {
          "departure_airport": { "name": "Paris Charles de Gaulle", "id": "CDG", "time": "2023-12-05 07:15" },
          "arrival_airport":   { "name": "Heathrow Airport", "id": "LHR", "time": "2023-12-05 07:40" },
          "duration": 85,
          "airplane": "Airbus A320",
          "airline": "British Airways",
          "travel_class": "Economy",
          "flight_number": "BA 303",
          "legroom": "29 in",
          "extensions": ["Below average legroom (29 in)", "Wi-Fi for a fee", "In-seat USB outlet", "Carbon emissions estimate: 42 kg"]
        }
      ],
      "total_duration": 85,
      "carbon_emissions": { "this_flight": 43000, "typical_for_this_route": 40000, "difference_percent": 8 },
      "type": "Round trip",
      "departure_token": "W251bGwsW1siQ0RHIiwiMjAyMy0xMi0wNSIsIkxIUiIsbnVsbCwiQkEiLCIzMDMiXV1d"
    },
    {
      "flights": [
        {
          "departure_airport": { "name": "Heathrow Airport", "id": "LHR", "time": "2023-12-28 06:55" },
          "arrival_airport":   { "name": "Paris Charles de Gaulle", "id": "CDG", "time": "2023-12-28 09:10" },
          "duration": 75,
          "airplane": "Airbus A320",
          "airline": "British Airways",
          "travel_class": "Economy",
          "flight_number": "BA 328",
          "legroom": "29 in",
          "extensions": ["Below average legroom (29 in)", "Wi-Fi for a fee", "In-seat USB outlet", "Carbon emissions estimate: 44 kg"]
        }
      ],
      "total_duration": 75,
      "carbon_emissions": { "this_flight": 44000, "typical_for_this_route": 40000, "difference_percent": 10 },
      "type": "Round trip",
      "departure_token": "W251bGwsW1siTEhSIiwiMjAyMy0xMi0yOCIsIkNERyIsbnVsbCwiQkEiLCIzMjgiXV1d"
    }
],
"baggage_prices": {
    "together": [
      "1 free carry-on",
      "1st checked bag: 99-187"
    ]
},
"booking_options": [
    {
      "together": {
        "book_with": "British Airways",
        "airline": true,
        "airline_logos": ["<URL logo>"],
        "marketed_as": ["BA 303", "BA 328"],
        "price": 188,
        "local_prices": [ { "currency": "EUR", "price": 173 } ],
        "option_title": "Basic Economy",
        "extensions": ["No refunds", "Ticket changes for a fee", "Seat selection for a fee", "Standard seat"],
        "baggage_prices": ["1 free carry-on", "1st checked bag: 99"],
        "booking_request": {
          "url": "https://www.google.com/travel/clk/f",
          "post_data": "<cadena form-encoded larga>"
        }
      }
    },
    {
      "together": {
        "book_with": "British Airways",
        "airline": true,
        "marketed_as": ["BA 303", "BA 328"],
        "price": 224,
        "local_prices": [ { "currency": "EUR", "price": 206 } ],
        "option_title": "Economy Plus",
        "extensions": ["No refunds", "Ticket changes for a fee", "Seat selection for a fee", "Standard seat"],
        "baggage_prices": ["1 free carry-on", "1st checked bag up to 23 kg free"],
        "booking_request": { "url": "https://www.google.com/travel/clk/f", "post_data": "<cadena larga>" }
      }
    },
    ...,
    {
      "together": {
        "book_with": "BudgetAir",
        "airline_logos": ["https://www.gstatic.com/flights/partner_logos/70px/TRAVIX_BUDGETAIR.png"],
        "marketed_as": ["BA 303", "BA 328"],
        "price": 232,
        "local_prices": [ { "currency": "EUR", "price": 213 } ],
        "baggage_prices": ["1 free carry-on", "1st checked bag: 187"],
        "booking_request": { "url": "https://www.google.com/travel/clk/f", "post_data": "<cadena larga>" }
      }
    },
    ...
],
"price_insights": {
    "lowest_price": 188,
    "price_level": "typical",
    "typical_price_range": [165, 500]
}
...
}
```

Observaciones útiles:

- Las opciones de agencias (BudgetAir, Gotogate, etc.) **no traen** el campo `airline: true`, y su logo viene de `partner_logos` en lugar de `airline_logos` de aerolínea.
- `option_title` solo aparece cuando la tarifa tiene nombre comercial.

### 2. Tiquetes separados (`separate_tickets: true`)

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=LAX&arrival_id=AUS&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&hl=en&booking_token=WyJDalJJUkRZMFZ6aFRablZtUmxWQlNUZHlhbWRDUnkwdExTMHRMUzB0TFMxd1ptMWlNVUZCUVVGQlIxWm5SMnAzUmt0blEyVkJFZ2RFVERRME1DTXhHZ3NJbVBrQ0VBSWFBMVZUUkRnY2NKajVBZz09...&api_key=TU_API_KEY
```

```json
{
...
"baggage_prices": {
    "departing": ["1 free carry-on", "1st checked bag: 30"],
    "returning": ["1 free carry-on", "1st checked bag: 30"]
},
"booking_options": [
    {
      "separate_tickets": true,
      "together": {
        "book_with": "Delta, American",
        "airline": true,
        "airline_logos": ["<URL logo Delta>", "<URL logo American>"],
        "marketed_as": ["DL 548", "AA 2869"],
        "price": 303
      },
      "departing": {
        "book_with": "Delta",
        "airline": true,
        "airline_logos": ["<URL logo>"],
        "marketed_as": ["DL 548"],
        "price": 134,
        "baggage_prices": ["1 free carry-on", "1st checked bag: 30"],
        "booking_request": { "url": "https://www.google.com/travel/clk/f", "post_data": "<cadena larga>" }
      },
      "returning": {
        "book_with": "American",
        "airline": true,
        "airline_logos": ["<URL logo>"],
        "marketed_as": ["AA 2869"],
        "price": 169,
        "baggage_prices": ["1 free carry-on", "1st checked bag: 30"],
        "booking_request": { "url": "https://www.google.com/travel/clk/f", "post_data": "<cadena larga>" }
      }
    }
],
...
}
```

Aquí `together` solo resume el precio total (303 = 134 + 169) y los vendedores; las dos reservas reales se hacen por separado con los `booking_request` de `departing` y `returning`.

### 3. Reserva por teléfono

```json
{
...
"booking_options": [
    {
      "together": {
        "book_with": "Gotogate",
        "airline_logos": ["<URL logo>"],
        "marketed_as": ["LH 723", "LH 2484", "MS 778", "MS 955"],
        "price": 6163,
        "baggage_prices": ["1 free carry-on"],
        "booking_request": { "url": "https://www.google.com/travel/clk/f", "post_data": "<cadena larga>" }
      }
    },
    {
      "together": {
        "book_with": "Lufthansa",
        "airline": true,
        "airline_logos": ["<URL logo>"],
        "marketed_as": ["LH 723", "LH 2484", "MS 778", "MS 955"],
        "price": 6130,
        "local_prices": [ { "currency": "CNY", "price": 43847 } ],
        "baggage_prices": ["1 free carry-on"],
        "booking_phone": "1 (800) 645-3880"
      }
    }
],
...
}
```

La segunda opción no tiene `booking_request`: solo se reserva llamando al número de `booking_phone`.

### 4. Fijar el itinerario por número de vuelo (ida y vuelta con escala)

En lugar de paginar por los resultados y arrastrar un `booking_token`, se pueden pedir las opciones de reserva directamente fijando los vuelos de ida y de regreso, segmento por segmento, con `selected_flights_json`. Cada segmento lleva su propio `flight_number`, `departure_id`, `arrival_id` y `date`, de modo que los aeropuertos de conexión y las escalas nocturnas se expresan de forma natural.

```
GET https://serpapi.com/search.json?engine=google_flights&currency=USD&hl=en&selected_flights_json={"outbound":[{"flight_number":"BA591","departure_id":"MXP","arrival_id":"LHR","date":"2026-11-13"},{"flight_number":"BA460","departure_id":"LHR","arrival_id":"MAD","date":"2026-11-13"}],"return":[{"flight_number":"IB675","departure_id":"MAD","arrival_id":"MXP","date":"2026-11-19"}]}&api_key=TU_API_KEY
```

(El valor de `selected_flights_json` debe ir codificado para URL.)

El itinerario fijado se devuelve en `selected_flights`:

```json
"selected_flights": [
  {
    "flights": [
      {
        "departure_airport": { "name": "...", "id": "MXP", "time": "2026-06-23 08:30" },
        "arrival_airport":   { "name": "Heathrow Airport", "id": "LHR", "time": "2026-06-23 09:35" },
        "duration": 125,
        "airplane": "Airbus A321neo",
        "airline": "British Airways",
        "travel_class": "Economy",
        "flight_number": "BA 591",
        "legroom": "29 in",
        "extensions": ["Below average legroom (29 in)", "Wi-Fi for a fee", "In-seat USB outlet", "Carbon emissions estimate: 75 kg"]
      },
      {
        "departure_airport": { "name": "Heathrow Airport", "id": "LHR", "time": "2026-06-23 12:20" },
        "arrival_airport":   { "name": "Adolfo Suárez Madrid-Barajas Airport", "id": "MAD", "time": "2026-06-23 15:50" },
        "duration": 150,
        "airplane": "Boeing 777",
        "airline": "British Airways",
        "travel_class": "Economy",
        "flight_number": "BA 460",
        "ticket_also_sold_by": ["Iberia"],
        "legroom": "31 in",
        "extensions": ["Average legroom (31 in)", "Wi-Fi for a fee", "In-seat USB outlet", "On-demand video", "Carbon emissions estimate: 126 kg"]
      }
    ],
    "layovers": [ { "duration": 165, "name": "Heathrow Airport", "id": "LHR" } ],
    "total_duration": 440,
    "carbon_emissions": { "this_flight": 202000, "...": "..." }
  }
]
```

### 5. Escala nocturna (solo ida, fechas por segmento)

Cuando una escala cruza la medianoche, el siguiente segmento sale un día después. Con `selected_flights_json` cada segmento lleva su propia `date`, así que basta con poner una fecha posterior en el segmento que sale al día siguiente. Las fechas dentro de un mismo tramo no pueden decrecer.

```
GET https://serpapi.com/search.json?engine=google_flights&type=2&currency=USD&hl=en&selected_flights_json={"outbound":[{"flight_number":"EY801","departure_id":"NRT","arrival_id":"AUH","date":"2026-11-13"},{"flight_number":"EY79","departure_id":"AUH","arrival_id":"MXP","date":"2026-11-14"}]}&api_key=TU_API_KEY
```

Nótese que en solo ida (`type=2`) no se envía la clave `return`, y que el segundo segmento sale el día 14 mientras el primero salió el 13.

---

## Resumen de la estructura (tal como la documenta SerpApi)

```json
{
...
"selected_flights": [
    // The same structure as `best_flights` or `other_flights`.
    // Visit https://serpapi.com/google-flights-results for more information
],
"baggage_prices": {
    "together": "Array - A list of baggage price policy",
    "departing": "Array - A list of baggage price policy, only for the departing flight",
    "returning": "Array - A list of baggage price policy, only for the returning flight"
},
"booking_options": [
    {
      "separate_tickets": "Boolean - True if the tickets are booked separately",
      "together": {
        "book_with": "String - name of the seller(s)",
        "airline": "Boolean - True if the seller is the operating airline",
        "airline_logos": "Array - URLs to the logos of the sellers",
        "marketed_as": "Array - Flight numbers",
        "price": "Float - Ticket price",
        "local_prices": [
          {
            "currency": "String - Currency of the price",
            "price": "Float - The ticket price in the currency"
          }
        ],
        "option_title": "String - Title of the option",
        "extensions": "Array - A list of features of the flight",
        "baggage_prices": "Array - A list of baggage price policy",
        "booking_request": {
          "url": "String - Google endpoint to resolve the booking action. When post_data is present, call this URL with HTTP POST.",
          "post_data": "String - Form-encoded payload to send as the POST body as is (do not decode, re-encode, or modify)."
          // When post_data is present, always use HTTP POST to booking_request.url
          // and send post_data as the request body without changes.
          // Only use HTTP GET when a direct deeplink is provided and post_data is absent.
        },
        "booking_phone": "String - Phone number for booking",
        "estimated_phone_service_fee": "Float - Estimated phone service fee for booking"
      },
      "departing": {
        // The same structure as together. It shows when `separate_tickets` is true
      },
      "returning": {
        // The same structure as together. It shows when `separate_tickets` is true
      }
    }
],
"price_insights": {
    "lowest_price": "Integer - The lowest price among the returned flights",
    "price_level": "String - Price level of the lowest_price",
    "typical_price_range": "Array - A two-integer array, indicating the low bound and high bound of 'typical' price of this flight",
    "price_history": "Array - A two-integer array, where the first element is the timestamp, and the second one is the price"
},
...
}
```

## Relacionado

- Parámetros `booking_token` y `selected_flights_json`: [01-api-google-flights.md](01-api-google-flights.md)
- Resultados de vuelos (de donde sale el token): [02-resultados-de-los-vuelos.md](02-resultados-de-los-vuelos.md)
- Información de precios: [03-informacion-de-precios.md](03-informacion-de-precios.md)
