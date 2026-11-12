# Información sobre precios (Google Flights Price Insights API)

> Fuente: <https://serpapi.com/google-flights-price-insights> — consultada el 12 de noviembre de 2026.
> Nombres de campos en inglés (así los devuelve la API); explicaciones en español.

## Qué es

SerpApi extrae la información de precios de Google Flights ("Price Insights") y la agrega a la salida JSON como el objeto `price_insights`.

| Dato | Valor |
| --- | --- |
| Endpoint | `https://serpapi.com/search?engine=google_flights` |
| Motor (`engine`) | `google_flights` |
| Campo que produce | `price_insights` |
| Playground | <https://serpapi.com/playground?engine=google_flights> |

No es un motor aparte: `price_insights` viene en la misma respuesta de una búsqueda normal de vuelos, junto a `best_flights` / `other_flights`. También aparece en las respuestas de opciones de reserva.

---

## Campos

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `lowest_price` | Integer | Precio más bajo entre los vuelos devueltos |
| `price_level` | String | Nivel de precio del `lowest_price` |
| `typical_price_range` | Array | Arreglo de dos enteros: límite inferior y superior del precio "típico" de este vuelo |
| `price_history` | Array | Arreglo de pares `[timestamp, precio]` |

### `price_level`

Es la etiqueta que Google asigna al precio más bajo encontrado, comparándolo con el rango típico de la ruta. Valores observados en la documentación: `low`, `typical`, `high`.

Interpretación práctica: si `lowest_price` queda por debajo del límite inferior de `typical_price_range`, el nivel tiende a ser `low`; si queda por encima del límite superior, tiende a ser `high`.

### `typical_price_range`

Dos enteros, en el orden `[mínimo, máximo]`, en la moneda de la búsqueda. Por ejemplo `[570, 1050]` significa que lo normal para esa ruta es pagar entre 570 y 1050.

### `price_history`

Arreglo de arreglos. Cada elemento tiene dos enteros:

1. el **timestamp** (Unix, en segundos),
2. el **precio** en la moneda seleccionada.

Los puntos suelen ser diarios. Por ejemplo `[1691013600, 575]` corresponde a un precio de 575 en la fecha de ese timestamp. Para convertirlo:

```python
from datetime import datetime, timezone
datetime.fromtimestamp(1691013600, tz=timezone.utc).date()
```

```javascript
new Date(1691013600 * 1000).toISOString().slice(0, 10)
```

---

## Ejemplo con moneda Euro

```
GET https://serpapi.com/search.json?engine=google_flights&departure_id=CDG&arrival_id=AUS&outbound_date=2026-11-13&return_date=2026-11-19&currency=EUR&hl=en&api_key=TU_API_KEY
```

```json
{
...
"price_insights": {
    "lowest_price": 1339,
    "price_level": "high",
    "typical_price_range": [
      570,
      1050
    ],
    "price_history": [
      [ 1691013600, 575 ],
      [ 1691100000, 575 ],
      ...
      [ 1696111200, 1199 ],
      [ 1696197600, 1339 ]
    ]
},
...
}
```

Aquí `lowest_price` (1339) está muy por encima del tope del rango típico (1050), por eso `price_level` es `high`.

### Otro ejemplo real (búsqueda CDG → AUS en USD, solo ida)

```json
"price_insights": {
  "lowest_price": 520,
  "price_level": "low",
  "typical_price_range": [690, 1350],
  "price_history": [[1762210800, 499], [1762297200, 499], ...]
}
```

### Ejemplo dentro de opciones de reserva

```json
"price_insights": {
  "lowest_price": 188,
  "price_level": "typical",
  "typical_price_range": [165, 500]
}
```

Nota: en ese caso `price_history` no viene incluido. El objeto puede traer solo algunos de sus campos.

---

## Resumen de la estructura (tal como la documenta SerpApi)

```json
{
...
"price_insights": {
    "lowest_price": "Integer - The lowest price among the returned flights",
    "price_level": "String - Price level of the lowest_price",
    "typical_price_range": "Array - A two-integer array, indicating the low bound and high bound of 'typical' price of this flight",
    "price_history": "Array - A two-integer array, where the first element is the timestamp, and the second one is the price"
},
...
}
```

## Para seguir precios por fecha

`price_insights` da el histórico de una búsqueda concreta. Si lo que se necesita es el precio por cada fecha de salida dentro de un rango, el motor adecuado es `google_flights_calendar`: ver [07-api-google-flights-calendar.md](07-api-google-flights-calendar.md).

## Relacionado

- Parámetros de la búsqueda: [01-api-google-flights.md](01-api-google-flights.md)
- Resultados de vuelos: [02-resultados-de-los-vuelos.md](02-resultados-de-los-vuelos.md)
- Opciones de reserva: [05-opciones-de-reserva.md](05-opciones-de-reserva.md)
