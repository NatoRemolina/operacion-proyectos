# Resultados de aeropuertos (Google Flights Airports API)

> Fuente: <https://serpapi.com/google-flights-airports> — consultada el 12 de noviembre de 2026.
> Nombres de campos en inglés (así los devuelve la API); explicaciones en español.

## Qué es

SerpApi extrae la información de los aeropuertos de la búsqueda y la agrega a la salida JSON como el arreglo `airports`.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights` |
| Motor (`engine`) | `google_flights` |
| Campo que produce | `airports` |
| Playground | <https://serpapi.com/playground?engine=google_flights> |

No es un motor aparte: `airports` viene en la misma respuesta de una búsqueda normal de vuelos.

---

## Cómo se organiza

`airports` es un arreglo. **Cada elemento corresponde a un tramo del viaje** y tiene dos claves:

| Clave | Contenido |
| --- | --- |
| `departure` | Arreglo con los aeropuertos de salida de ese tramo |
| `arrival` | Arreglo con los aeropuertos de llegada de ese tramo |

- En un viaje de **ida y vuelta** hay dos elementos: el primero con CDG → AUS, el segundo con AUS → CDG.
- En un viaje **multiciudad** hay un elemento por cada tramo declarado en `multi_city_json`.
- En **solo ida** hay un único elemento.
- Si se piden varios aeropuertos (`departure_id=CDG,ORY`), el arreglo `departure` trae un objeto por cada aeropuerto.

### Campos de cada aeropuerto

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `airport.name` | String | Nombre del aeropuerto |
| `airport.id` | String | Código del aeropuerto (IATA) |
| `city` | String | Ciudad |
| `country` | String | País |
| `country_code` | String | Código del país (por ejemplo `FR`, `US`, `JP`) |
| `image` | String | URL de la imagen de la ciudad |
| `thumbnail` | String | URL de la miniatura de la ciudad |

Las URLs de `image` y `thumbnail` apuntan a `encrypted-tbn3.gstatic.com` y son cadenas muy largas.

---

## Ejemplos

### 1. Un aeropuerto de salida y uno de llegada (ida y vuelta)

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=CDG&arrival_id=AUS&outbound_date=2026-11-13&return_date=2026-11-19&currency=USD&hl=en&api_key=TU_API_KEY
```

```json
{
...
"airports": [
    {
      "departure": [
        {
          "airport": {
            "id": "CDG",
            "name": "Paris Charles de Gaulle Airport"
          },
          "city": "Paris",
          "country": "France",
          "country_code": "FR",
          "image": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcQGx8ii2KbSDdbdzfKye5oDN2bwBA6audqI7XUEf2iMRZezpn_ZbQe1ZIuvUSH-8XOMe958umDwSsAF1w",
          "thumbnail": "https://encrypted-tbn3.gstatic.com/images?q=tbn:ANd9GcSyQJ-woNs0iO22mPSkmRUM5gcsTbbYeypQ6BBTeFxXr90mqTxZl57Fdq2CDuLn4w7cKZ8TT9_zZhOpF57rIpA7yWKQnqKvkKIf9Y-qJDo"
        }
      ],
      "arrival": [
        {
          "airport": {
            "id": "AUS",
            "name": "Austin-Bergstrom International Airport"
          },
          "city": "Austin",
          "country": "United States",
          "country_code": "US",
          "image": "<URL de imagen>",
          "thumbnail": "<URL de miniatura>"
        }
      ]
    },
    {
      "departure": [
        {
          "airport": { "id": "AUS", "name": "Austin-Bergstrom International Airport" },
          "city": "Austin",
          "country": "United States",
          "country_code": "US",
          "image": "<URL de imagen>",
          "thumbnail": "<URL de miniatura>"
        }
      ],
      "arrival": [
        {
          "airport": { "id": "CDG", "name": "Paris Charles de Gaulle Airport" },
          "city": "Paris",
          "country": "France",
          "country_code": "FR",
          "image": "<URL de imagen>",
          "thumbnail": "<URL de miniatura>"
        }
      ]
    }
]
...
}
```

Fíjate en el segundo elemento: es el tramo de regreso, con los aeropuertos invertidos.

### 2. Viaje multiciudad

```
GET https://serpapi.com/search.json?engine=google_flights&type=3&multi_city_json=[{"departure_id":"CDG","arrival_id":"NRT","date":"2026-11-13"},{"departure_id":"NRT","arrival_id":"LAX,SEA","date":"2026-11-19"},{"departure_id":"LAX,SEA","arrival_id":"AUS","date":"2026-11-27","times":"8,18,9,23"}]&currency=USD&hl=en&api_key=TU_API_KEY
```

(El valor de `multi_city_json` debe ir codificado para URL.)

```json
{
...
"airports": [
    {
      "departure": [
        {
          "airport": { "id": "CDG", "name": "Paris Charles de Gaulle Airport" },
          "city": "Paris",
          "country": "France",
          "country_code": "FR",
          "image": "<URL de imagen>",
          "thumbnail": "<URL de miniatura>"
        }
      ],
      "arrival": [
        {
          "airport": { "id": "NRT", "name": "Narita International Airport" },
          "city": "Tokyo",
          "country": "Japan",
          "country_code": "JP",
          "image": "<URL de imagen>",
          "thumbnail": "<URL de miniatura>"
        }
      ]
    },
    {
      "departure": [
        { "airport": { "id": "NRT", "name": "Narita International Airport" }, "city": "Tokyo", "country": "Japan", "country_code": "JP", "...": "..." }
      ],
      "arrival": [
        { "airport": { "id": "LAX", "name": "Los Angeles International Airport" }, "city": "Los Angeles", "...": "..." },
        { "airport": { "id": "SEA", "name": "Seattle-Tacoma International Airport" }, "city": "Seattle", "...": "..." }
      ]
    },
    ...
]
...
}
```

Cuando un tramo acepta varios aeropuertos (`LAX,SEA`), el arreglo `arrival` de ese tramo trae un objeto por cada uno.

---

## Resumen de la estructura (tal como la documenta SerpApi)

```json
{
...
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
        }
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
        }
      ]
    }
]
...
}
```

## Cuándo usar esto

Este bloque es útil para mostrar en la interfaz el nombre completo y la foto de la ciudad de origen y destino sin tener que mantener un catálogo propio de aeropuertos. Para **buscar** aeropuertos a partir de texto escrito por el usuario, el motor adecuado es `google_flights_autocomplete`: ver [06-api-autocompletado.md](06-api-autocompletado.md).

## Relacionado

- Parámetros de la búsqueda: [01-api-google-flights.md](01-api-google-flights.md)
- Resultados de vuelos: [02-resultados-de-los-vuelos.md](02-resultados-de-los-vuelos.md)
- Autocompletado: [06-api-autocompletado.md](06-api-autocompletado.md)
