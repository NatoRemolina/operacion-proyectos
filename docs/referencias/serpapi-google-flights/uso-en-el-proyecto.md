# Uso de las APIs de Google Flights en este proyecto

Análisis del 12 de noviembre de 2026: cada documento de esta carpeta comparado con el código y con el diseño `docs/diseno/2026-11-12-buscador-mundial-y-cargos.md`. Plan del proveedor: 250 búsquedas al mes. Una consulta idéntica dentro de la misma hora se sirve de su caché y no se cobra; por eso la plataforma nunca envía `no_cache` y arma los parámetros siempre igual.

## Regla de la plataforma

Toda respuesta que se paga queda guardada (tabla `busquedas` y archivo en `datos/respaldo/`) y deja su fila en `consultas_buscador`. La opción elegida se carga completa al decidir y se reconfirma al aprobar.

| Momento | Consultas | Qué se guarda |
|---|---|---|
| Cotizar | 1 (`google_flights`, varios aeropuertos separados por coma) | Itinerarios de ida, `price_insights`, `airports` |
| Decidir | 2: regreso con `departure_token` y opciones de reserva con `booking_token` | Regreso real, `booking_options`, `baggage_prices`; el presupuesto usa la tarifa real |
| Aprobar | 1: el itinerario fijo con `selected_flights_json` | Precio vigente; si subió más que la tolerancia, administración lo confirma antes de aprobar |
| Día del vuelo | Hasta 6 por tramo, dentro de los topes por viaje y por día | Estado del vuelo (otro motor, ver el diseño) |

`booking_request` (URL y `post_data`) se elimina antes de guardar: la plataforma nunca ejecuta una reserva; la hace una persona en Google Flights.

## Por documento

| Documento | Qué usa hoy la plataforma | Qué se decidió |
|---|---|---|
| [01 Motor principal](01-api-google-flights.md) | `precios.buscar_vuelos`, `tarifas_de_vuelo` (`app/servicios/precios.py`): `departure_id`, `arrival_id`, fechas, `hl=en`, `currency=USD` | Varios aeropuertos por consulta; regreso con los mismos códigos para aprovechar la caché; `selected_flights_json` para reconfirmar al aprobar. Después: `bags=1` con baterías, `outbound_times` con la hora límite, `json_restrictor` |
| [02 Resultados de vuelos](02-resultados-de-los-vuelos.md) | `_vuelo` junta `best_flights` y `other_flights` | Leer también, sin costo: `extensions` del itinerario (cambio gratis, cambio con cargo, maleta incluida, reembolso), `often_delayed_by_over_30_min` (aviso frente a la hora límite) y `layovers` (escala corta o nocturna). Leer todos los campos con valor por defecto para no fallar en vivo |
| [03 Información de precios](03-informacion-de-precios.md) | `price_insights` se guarda con la búsqueda y alimenta el rango típico | Con varios aeropuertos describe el conjunto, no cada ruta |
| [04 Resultados de aeropuertos](04-resultados-de-aeropuertos.md) | No se lee | Validar qué códigos aceptó la búsqueda y registrar si alguno se ignoró; ciudad para el hotel cuando no hay lugar elegido. No se muestran sus imágenes (dependencia externa) |
| [05 Opciones de reserva](05-opciones-de-reserva.md) | Botón «Traer tarifas» (`app/rutas/cotizaciones.py`, `precios._tarifa`) | Se pide para la opción elegida al decidir. Después: rango de precio de maleta (hoy toma el mínimo), cargo por cambio y `separate_tickets` |
| [06 Autocompletado](06-api-autocompletado.md) | No se usa | El MVP sugiere lugares con datos locales (OurAirports y GeoNames). El autocompletado queda como proveedor alternativo, apagado por defecto, para cuando la empresa contrate un plan que lo cubra (`PROVEEDOR_LUGARES=serpapi`) |
| [07 Calendario](07-api-google-flights-calendar.md) | No se usa | Después: botón «¿mover la ida ±3 días ahorra?» (1 consulta por par de aeropuertos; no admite varios a la vez) y recolector de precios más barato (unas 10 consultas por captura en vez de 40) |
| [08 Ofertas](08-api-ofertas-de-vuelos.md) | No se usa | Después: alerta de ofertas para las rutas frecuentes de la empresa, una consulta semanal por aeropuerto base cruzada con los destinos más frecuentes (unas 4 a 8 al mes) |
