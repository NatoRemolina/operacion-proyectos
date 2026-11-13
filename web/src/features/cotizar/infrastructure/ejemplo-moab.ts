import type { Cotizacion, FormularioCotizacion, ListaLugares, LugarSugerido } from "../domain/cotizar";

/**
 * Respuestas reales de la API v1 (12 nov 2026) para el caso con precios guardados Miami (MIA) → Moab
 * (CNY, GJT, SLC) del 8 al 11 de diciembre de 2026. Sirven a las pruebas y al modo demostración.
 * `SOLO_GOOGLE` es ilustrativo: muestra cómo llega un lugar que solo conoce el autocompletado de Google.
 */

export const COTIZACION_MOAB: Cotizacion = {
  "id": 12,
  "estado": "comparando",
  "creado": "2026-11-12T19:44:48Z",
  "solicitado_por": "Andrés Molina",
  "proyecto": {
    "id": 1,
    "nombre": "Residencial Summerlin (aéreo)"
  },
  "viajero": {
    "id": 1,
    "nombre": "Andrés Molina"
  },
  "origen": {
    "codigo": "MIA",
    "aeropuertos": [
      "MIA"
    ],
    "lugar": null
  },
  "destino": {
    "codigo": "CNY",
    "aeropuertos": [
      "CNY",
      "GJT",
      "SLC"
    ],
    "lugar": {
      "nombre": "Moab",
      "region": "Utah",
      "pais": "Estados Unidos",
      "lat": 38.57332,
      "lon": -109.54984
    }
  },
  "ciudad_hotel": "Moab",
  "ida": "2026-12-08",
  "regreso": "2026-12-11",
  "noches": 3,
  "hora_limite": "18:00",
  "baterias_n": 4,
  "baterias_wh": 77.0,
  "maleta": true,
  "prob_cambio_pct": 25,
  "carro_usd": "195.00",
  "equipo": {
    "nivel": "ok",
    "texto": "4 baterías de 77 Wh: permitidas en cabina sin trámite. Nunca en bodega."
  },
  "origen_dato": "guardado",
  "aviso": "La opción más barata del buscador es Frontier por 415 USD, pero con el equipo, el riesgo de cambio y las millas su costo esperado es 824 USD. La mejor es United UA 1047 (Tarifa más baja (supuesta)): 785 USD.",
  "fallos": [],
  "recomendacion": "Recomiendo United UA 1047 + UA 6077 con la tarifa más baja (supuesta): costo total esperado de 785 USD (precio en el buscador: 508 USD).\nEl más barato del buscador es Frontier por 415 USD, pero su costo esperado sube a 824 USD. Esta tarifa no incluye equipaje de mano y las baterías deben ir en cabina. No admite cambios: si la grabación se mueve, se pierde el tiquete.\nLa segunda opción es Frontier F9 1279, a 39 USD de diferencia.\nSegún el modelo de precios, este vuelo está 32% por encima de lo esperado para la ruta.\nSe descartaron 3 vuelos por llegar después de la hora límite.\nQué la cambiaría: desde 0 % de probabilidad de cambio gana United UA 1047 (Tarifa más baja (supuesta)); desde 70 % de probabilidad de cambio gana Frontier F9 1279 (Tarifa más baja (supuesta)).\nAtención: las tarifas de este vuelo son supuestas; conviene traer las reales antes de decidir.",
  "vuelos": [
    {
      "id": 6,
      "aerolinea": "United",
      "numeros": [
        "UA 1047",
        "UA 6077"
      ],
      "desde": "MIA",
      "hasta": "CNY",
      "sale": "2026-12-08 07:35",
      "llega": "2026-12-08 13:42",
      "escalas": 1,
      "duracion_min": 487,
      "precio_usd": "508.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "785.00",
      "desglose": {
        "precio_usd": "508.00",
        "equipaje_usd": "150.00",
        "riesgo_cambio_usd": "127.00",
        "millas_usd": "0.00",
        "traslado_usd": "0.00"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "508.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Equipaje de mano (el equipo va en cabina)",
          "valor_usd": "70.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Maleta facturada",
          "valor_usd": "80.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "127.00",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        }
      ],
      "avisos": [
        "Esta tarifa no incluye equipaje de mano y las baterías deben ir en cabina.",
        "No admite cambios: si la grabación se mueve, se pierde el tiquete.",
        "La tarifa básica de esta aerolínea no acumula millas."
      ],
      "descartada": null,
      "recomendada": true,
      "mas_barata": false,
      "origen_dato": "guardado",
      "esperado_usd": "386.05",
      "frente_esperado_pct": 32,
      "total_con_hotel_usd": null
    },
    {
      "id": 1,
      "aerolinea": "Frontier",
      "numeros": [
        "F9 1279",
        "F9 3981"
      ],
      "desde": "MIA",
      "hasta": "SLC",
      "sale": "2026-12-08 05:01",
      "llega": "2026-12-08 10:08",
      "escalas": 1,
      "duracion_min": 427,
      "precio_usd": "415.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "824.43",
      "desglose": {
        "precio_usd": "415.00",
        "equipaje_usd": "230.00",
        "riesgo_cambio_usd": "103.75",
        "millas_usd": "-24.90",
        "traslado_usd": "100.58"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "415.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Equipaje de mano (el equipo va en cabina)",
          "valor_usd": "120.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Maleta facturada",
          "valor_usd": "110.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "103.75",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        },
        {
          "concepto": "Millas del viajero (5 por USD a 0.012 USD)",
          "valor_usd": "-24.90",
          "origen": "supuesto",
          "tipo": "millas"
        },
        {
          "concepto": "Combustible y peajes desde SLC (419 km, unas 6 h)",
          "valor_usd": "100.58",
          "origen": "supuesto",
          "tipo": "traslado"
        }
      ],
      "avisos": [
        "Esta tarifa no incluye equipaje de mano y las baterías deben ir en cabina.",
        "No admite cambios: si la grabación se mueve, se pierde el tiquete.",
        "Escala corta en DEN (55 min): riesgo de perder la conexión o el equipaje."
      ],
      "descartada": null,
      "recomendada": false,
      "mas_barata": true,
      "origen_dato": "guardado",
      "esperado_usd": "287.61",
      "frente_esperado_pct": 44,
      "total_con_hotel_usd": null
    },
    {
      "id": 2,
      "aerolinea": "United",
      "numeros": [
        "UA 1047",
        "UA 1714"
      ],
      "desde": "MIA",
      "hasta": "GJT",
      "sale": "2026-12-08 07:35",
      "llega": "2026-12-08 12:27",
      "escalas": 1,
      "duracion_min": 412,
      "precio_usd": "523.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "837.35",
      "desglose": {
        "precio_usd": "523.00",
        "equipaje_usd": "150.00",
        "riesgo_cambio_usd": "130.75",
        "millas_usd": "0.00",
        "traslado_usd": "33.60"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "523.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Equipaje de mano (el equipo va en cabina)",
          "valor_usd": "70.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Maleta facturada",
          "valor_usd": "80.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "130.75",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        },
        {
          "concepto": "Combustible y peajes desde GJT (140 km, unas 2 h)",
          "valor_usd": "33.60",
          "origen": "supuesto",
          "tipo": "traslado"
        }
      ],
      "avisos": [
        "Esta tarifa no incluye equipaje de mano y las baterías deben ir en cabina.",
        "No admite cambios: si la grabación se mueve, se pierde el tiquete.",
        "La tarifa básica de esta aerolínea no acumula millas."
      ],
      "descartada": null,
      "recomendada": false,
      "mas_barata": false,
      "origen_dato": "guardado",
      "esperado_usd": "397.82",
      "frente_esperado_pct": 31,
      "total_con_hotel_usd": null
    },
    {
      "id": 3,
      "aerolinea": "Delta",
      "numeros": [
        "DL 976"
      ],
      "desde": "MIA",
      "hasta": "SLC",
      "sale": "2026-12-08 06:50",
      "llega": "2026-12-08 10:15",
      "escalas": 0,
      "duracion_min": 325,
      "precio_usd": "617.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "951.83",
      "desglose": {
        "precio_usd": "617.00",
        "equipaje_usd": "80.00",
        "riesgo_cambio_usd": "154.25",
        "millas_usd": "0.00",
        "traslado_usd": "100.58"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "617.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Maleta facturada",
          "valor_usd": "80.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "154.25",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        },
        {
          "concepto": "Combustible y peajes desde SLC (419 km, unas 6 h)",
          "valor_usd": "100.58",
          "origen": "supuesto",
          "tipo": "traslado"
        }
      ],
      "avisos": [
        "No admite cambios: si la grabación se mueve, se pierde el tiquete.",
        "La tarifa básica de esta aerolínea no acumula millas."
      ],
      "descartada": null,
      "recomendada": false,
      "mas_barata": false,
      "origen_dato": "guardado",
      "esperado_usd": "442.68",
      "frente_esperado_pct": 39,
      "total_con_hotel_usd": null
    },
    {
      "id": 8,
      "aerolinea": "American",
      "numeros": [
        "AA 941",
        "AA 3385"
      ],
      "desde": "MIA",
      "hasta": "GJT",
      "sale": "2026-12-08 08:00",
      "llega": "2026-12-08 12:53",
      "escalas": 1,
      "duracion_min": 413,
      "precio_usd": "807.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "1042.35",
      "desglose": {
        "precio_usd": "807.00",
        "equipaje_usd": "0.00",
        "riesgo_cambio_usd": "201.75",
        "millas_usd": "0.00",
        "traslado_usd": "33.60"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "807.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Maleta facturada (gratis por estatus Gold)",
          "valor_usd": "0.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "201.75",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        },
        {
          "concepto": "Combustible y peajes desde GJT (140 km, unas 2 h)",
          "valor_usd": "33.60",
          "origen": "supuesto",
          "tipo": "traslado"
        }
      ],
      "avisos": [
        "No admite cambios: si la grabación se mueve, se pierde el tiquete.",
        "La tarifa básica de esta aerolínea no acumula millas.",
        "Escala corta en DFW (50 min): riesgo de perder la conexión o el equipaje."
      ],
      "descartada": null,
      "recomendada": false,
      "mas_barata": false,
      "origen_dato": "guardado",
      "esperado_usd": "382.78",
      "frente_esperado_pct": 111,
      "total_con_hotel_usd": null
    }
  ],
  "descartados": [
    {
      "id": 4,
      "aerolinea": "Frontier",
      "numeros": [
        "F9 2135",
        "F9 3277"
      ],
      "desde": "MIA",
      "hasta": "SLC",
      "sale": "2026-12-08 10:54",
      "llega": "2026-12-08 19:24",
      "escalas": 1,
      "duracion_min": 630,
      "precio_usd": "470.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "889.88",
      "desglose": {
        "precio_usd": "470.00",
        "equipaje_usd": "230.00",
        "riesgo_cambio_usd": "117.50",
        "millas_usd": "-28.20",
        "traslado_usd": "100.58"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "470.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Equipaje de mano (el equipo va en cabina)",
          "valor_usd": "120.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Maleta facturada",
          "valor_usd": "110.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "117.50",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        },
        {
          "concepto": "Millas del viajero (5 por USD a 0.012 USD)",
          "valor_usd": "-28.20",
          "origen": "supuesto",
          "tipo": "millas"
        },
        {
          "concepto": "Combustible y peajes desde SLC (419 km, unas 6 h)",
          "valor_usd": "100.58",
          "origen": "supuesto",
          "tipo": "traslado"
        }
      ],
      "avisos": [
        "Esta tarifa no incluye equipaje de mano y las baterías deben ir en cabina.",
        "No admite cambios: si la grabación se mueve, se pierde el tiquete."
      ],
      "descartada": "Llega a las 19:24, después de la hora límite.",
      "recomendada": false,
      "mas_barata": false,
      "origen_dato": "guardado",
      "esperado_usd": "314.69",
      "frente_esperado_pct": 49,
      "total_con_hotel_usd": null
    },
    {
      "id": 5,
      "aerolinea": "Southwest",
      "numeros": [
        "WN 1425",
        "WN 2775"
      ],
      "desde": "MIA",
      "hasta": "SLC",
      "sale": "2026-12-08 06:25",
      "llega": "2026-12-08 14:10",
      "escalas": 1,
      "duracion_min": 585,
      "precio_usd": "504.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "780.34",
      "desglose": {
        "precio_usd": "504.00",
        "equipaje_usd": "80.00",
        "riesgo_cambio_usd": "126.00",
        "millas_usd": "-30.24",
        "traslado_usd": "100.58"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "504.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Maleta facturada",
          "valor_usd": "80.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "126.00",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        },
        {
          "concepto": "Millas del viajero (5 por USD a 0.012 USD)",
          "valor_usd": "-30.24",
          "origen": "supuesto",
          "tipo": "millas"
        },
        {
          "concepto": "Combustible y peajes desde SLC (419 km, unas 6 h)",
          "valor_usd": "100.58",
          "origen": "supuesto",
          "tipo": "traslado"
        }
      ],
      "avisos": [
        "No admite cambios: si la grabación se mueve, se pierde el tiquete."
      ],
      "descartada": "Con el traslado llega a las 20:10, después de la hora límite.",
      "recomendada": false,
      "mas_barata": false,
      "origen_dato": "guardado",
      "esperado_usd": "386.94",
      "frente_esperado_pct": 30,
      "total_con_hotel_usd": null
    },
    {
      "id": 7,
      "aerolinea": "United",
      "numeros": [
        "UA 211",
        "UA 1110"
      ],
      "desde": "MIA",
      "hasta": "GJT",
      "sale": "2026-12-08 15:38",
      "llega": "2026-12-08 21:02",
      "escalas": 1,
      "duracion_min": 444,
      "precio_usd": "523.00",
      "tarifa": {
        "nombre": "Tarifa más baja (supuesta)",
        "permite_cambio": false,
        "reales": false
      },
      "costo_total_usd": "837.35",
      "desglose": {
        "precio_usd": "523.00",
        "equipaje_usd": "150.00",
        "riesgo_cambio_usd": "130.75",
        "millas_usd": "0.00",
        "traslado_usd": "33.60"
      },
      "lineas": [
        {
          "concepto": "Precio (Tarifa más baja (supuesta))",
          "valor_usd": "523.00",
          "origen": "buscador",
          "tipo": "precio"
        },
        {
          "concepto": "Equipaje de mano (el equipo va en cabina)",
          "valor_usd": "70.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Maleta facturada",
          "valor_usd": "80.00",
          "origen": "regla",
          "tipo": "equipaje"
        },
        {
          "concepto": "Riesgo de cambio (25% x perder el tiquete)",
          "valor_usd": "130.75",
          "origen": "supuesto",
          "tipo": "riesgo_cambio"
        },
        {
          "concepto": "Combustible y peajes desde GJT (140 km, unas 2 h)",
          "valor_usd": "33.60",
          "origen": "supuesto",
          "tipo": "traslado"
        }
      ],
      "avisos": [
        "Esta tarifa no incluye equipaje de mano y las baterías deben ir en cabina.",
        "No admite cambios: si la grabación se mueve, se pierde el tiquete.",
        "La tarifa básica de esta aerolínea no acumula millas."
      ],
      "descartada": "Llega a las 21:02, después de la hora límite.",
      "recomendada": false,
      "mas_barata": false,
      "origen_dato": "guardado",
      "esperado_usd": "405.64",
      "frente_esperado_pct": 29,
      "total_con_hotel_usd": null
    }
  ],
  "hoteles": [],
  "hoteles_descartados": [],
  "hotel_recomendado_id": null,
  "recomendada_id": 6,
  "mas_barata_id": 1,
  "decision": null,
  "viaje": null,
  "fuente_url": "https://www.google.com/travel/flights?hl=en&gl=us&curr=USD&tfs=CBwQAhowEgoyMDI2LTEyLTA4agcIARIDTUlBcgcIARIDQ05ZcgcIARIDR0pUcgcIARIDU0xDGjASCjIwMjYtMTItMTFqBwgBEgNDTllqBwgBEgNHSlRqBwgBEgNTTENyBwgBEgNNSUFAAUgBcAGYAQE&tfu=EgIIAQ",
  "fuente_hoteles_url": "https://www.google.com/travel/search?q=Moab%20hotels%20from%202026-12-08%20to%202026-12-11&hl=en&gl=us",
  "puede_decidir": true,
  "bloqueo": null
};

export const FORMULARIO_EJEMPLO: FormularioCotizacion = {
  "proyectos": [
    {
      "id": 1,
      "nombre": "Residencial Summerlin (aéreo)",
      "ciudad": "Las Vegas",
      "inicio": "2026-12-08",
      "fin": "2026-12-11",
      "para_otra_persona": false
    },
    {
      "id": 2,
      "nombre": "Apartamentos Alfama (aéreo)",
      "ciudad": "Lisboa",
      "inicio": "2026-12-13",
      "fin": "2026-12-16",
      "para_otra_persona": false
    }
  ],
  "viajeros": [
    {
      "id": 1,
      "nombre": "Andrés Molina",
      "base": "Miami",
      "soy_yo": true
    }
  ],
  "viajero_propio_id": 1,
  "elige_viajero": false,
  "razones": [
    {
      "clave": "costo_total",
      "texto": "Menor costo total"
    },
    {
      "clave": "horario",
      "texto": "Mejor horario"
    },
    {
      "clave": "directo",
      "texto": "Vuelo directo"
    },
    {
      "clave": "flexibilidad",
      "texto": "Permite cambios"
    },
    {
      "clave": "equipaje",
      "texto": "Equipaje del equipo"
    },
    {
      "clave": "fidelizacion",
      "texto": "Millas o estatus"
    },
    {
      "clave": "cliente",
      "texto": "Exigencia del cliente o del proyecto"
    },
    {
      "clave": "hotel",
      "texto": "Ubicación del hotel"
    },
    {
      "clave": "otra",
      "texto": "Otra"
    }
  ],
  "precios_en_vivo": false
};

export const LUGARES_EJEMPLO: Record<string, ListaLugares> = {
  "moab": {
    "resultados": [
      {
        "tipo": "lugar",
        "id": "5543307",
        "nombre": "Moab",
        "region": "Utah",
        "pais": "Estados Unidos",
        "lat": 38.57332,
        "lon": -109.54984,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "CNY",
            "nombre": "Canyonlands Regional Airport",
            "municipio": "Moab",
            "km": 26.9,
            "horas": 0.5,
            "grande": false
          },
          {
            "iata": "GJT",
            "nombre": "Grand Junction Regional Airport",
            "municipio": "Grand Junction",
            "km": 107.7,
            "horas": 2.0,
            "grande": false
          },
          {
            "iata": "SLC",
            "nombre": "Salt Lake City International Airport",
            "municipio": "Salt Lake City",
            "km": 322.4,
            "horas": 6.0,
            "grande": true
          }
        ]
      },
      {
        "tipo": "lugar",
        "id": "250624",
        "nombre": "Qīr Moāv",
        "region": "Ma’an",
        "pais": "Jordania",
        "lat": 31.18248,
        "lon": 35.69999,
        "tambien": "kir moab",
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "AMM",
            "nombre": "Queen Alia International Airport",
            "municipio": "Amman",
            "km": 66.2,
            "horas": 1.2,
            "grande": true
          },
          {
            "iata": "AQJ",
            "nombre": "King Hussein International Airport",
            "municipio": "Aqaba",
            "km": 186.5,
            "horas": 3.5,
            "grande": true
          }
        ]
      },
      {
        "tipo": "lugar",
        "id": "250345",
        "nombre": "Ar Rabbah",
        "region": "Karak",
        "pais": "Jordania",
        "lat": 31.26923,
        "lon": 35.73829,
        "tambien": "rabbat moab",
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "AMM",
            "nombre": "Queen Alia International Airport",
            "municipio": "Amman",
            "km": 55.9,
            "horas": 1.0,
            "grande": true
          },
          {
            "iata": "AQJ",
            "nombre": "King Hussein International Airport",
            "municipio": "Aqaba",
            "km": 196.8,
            "horas": 3.7,
            "grande": true
          }
        ]
      },
      {
        "tipo": "aeropuerto",
        "id": "CNY",
        "nombre": "Canyonlands Regional Airport",
        "region": "Moab",
        "pais": "Estados Unidos",
        "lat": 38.755,
        "lon": -109.755,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "CNY",
            "nombre": "Canyonlands Regional Airport",
            "municipio": "Moab",
            "km": 0.0,
            "horas": 0.0,
            "grande": false
          }
        ]
      },
      {
        "tipo": "lugar",
        "id": "5012194",
        "nombre": "Three Rivers",
        "region": "Michigan",
        "pais": "Estados Unidos",
        "lat": 41.94394,
        "lon": -85.63249,
        "tambien": "moab",
        "aviso": "Sin aeropuertos con vuelos regulares a menos de 400 km. Busca un aeropuerto por nombre o código.",
        "origen": "local",
        "aeropuertos": []
      }
    ],
    "aviso_google": null,
    "carretera": {
      "factor": 1.3,
      "velocidad_kmh": 70.0
    }
  },
  "miami": {
    "resultados": [
      {
        "tipo": "lugar",
        "id": "4164138",
        "nombre": "Miami",
        "region": "Florida",
        "pais": "Estados Unidos",
        "lat": 25.77427,
        "lon": -80.19366,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "MIA",
            "nombre": "Miami International Airport",
            "municipio": "Miami",
            "km": 9.9,
            "horas": 0.2,
            "grande": true
          }
        ]
      },
      {
        "tipo": "aeropuerto",
        "id": "MIA",
        "nombre": "Miami International Airport",
        "region": "Miami",
        "pais": "Estados Unidos",
        "lat": 25.79601,
        "lon": -80.28975,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "MIA",
            "nombre": "Miami International Airport",
            "municipio": "Miami",
            "km": 0.0,
            "horas": 0.0,
            "grande": true
          }
        ]
      }
    ],
    "aviso_google": null,
    "carretera": {
      "factor": 1.3,
      "velocidad_kmh": 70.0
    }
  },
  "mia": {
    "resultados": [
      {
        "tipo": "aeropuerto",
        "id": "MIA",
        "nombre": "Miami International Airport",
        "region": "Miami",
        "pais": "Estados Unidos",
        "lat": 25.79601,
        "lon": -80.28975,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "MIA",
            "nombre": "Miami International Airport",
            "municipio": "Miami",
            "km": 0.0,
            "horas": 0.0,
            "grande": true
          }
        ]
      },
      {
        "tipo": "lugar",
        "id": "4164138",
        "nombre": "Miami",
        "region": "Florida",
        "pais": "Estados Unidos",
        "lat": 25.77427,
        "lon": -80.19366,
        "tambien": "mia",
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "MIA",
            "nombre": "Miami International Airport",
            "municipio": "Miami",
            "km": 9.9,
            "horas": 0.2,
            "grande": true
          }
        ]
      }
    ],
    "aviso_google": null,
    "carretera": {
      "factor": 1.3,
      "velocidad_kmh": 70.0
    }
  },
  "salt lake": {
    "resultados": [
      {
        "tipo": "aeropuerto",
        "id": "SLC",
        "nombre": "Salt Lake City International Airport",
        "region": "Salt Lake City",
        "pais": "Estados Unidos",
        "lat": 40.78886,
        "lon": -111.97987,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "SLC",
            "nombre": "Salt Lake City International Airport",
            "municipio": "Salt Lake City",
            "km": 0.0,
            "horas": 0.0,
            "grande": true
          }
        ]
      }
    ],
    "aviso_google": null,
    "carretera": {
      "factor": 1.3,
      "velocidad_kmh": 70.0
    }
  },
  "slc": {
    "resultados": [
      {
        "tipo": "aeropuerto",
        "id": "SLC",
        "nombre": "Salt Lake City International Airport",
        "region": "Salt Lake City",
        "pais": "Estados Unidos",
        "lat": 40.78886,
        "lon": -111.97987,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "SLC",
            "nombre": "Salt Lake City International Airport",
            "municipio": "Salt Lake City",
            "km": 0.0,
            "horas": 0.0,
            "grande": true
          }
        ]
      }
    ],
    "aviso_google": null,
    "carretera": {
      "factor": 1.3,
      "velocidad_kmh": 70.0
    }
  },
  "grand junction": {
    "resultados": [
      {
        "tipo": "aeropuerto",
        "id": "GJT",
        "nombre": "Grand Junction Regional Airport",
        "region": "Grand Junction",
        "pais": "Estados Unidos",
        "lat": 39.12666,
        "lon": -108.52939,
        "tambien": null,
        "aviso": null,
        "origen": "local",
        "aeropuertos": [
          {
            "iata": "GJT",
            "nombre": "Grand Junction Regional Airport",
            "municipio": "Grand Junction",
            "km": 0.0,
            "horas": 0.0,
            "grande": false
          }
        ]
      }
    ],
    "aviso_google": null,
    "carretera": {
      "factor": 1.3,
      "velocidad_kmh": 70.0
    }
  }
};

export const SOLO_GOOGLE: LugarSugerido = {
  "tipo": "lugar",
  "id": "/m/0bryce",
  "nombre": "Bryce Canyon City",
  "region": "Ciudad de Utah, Estados Unidos",
  "pais": "",
  "lat": null,
  "lon": null,
  "tambien": null,
  "aviso": null,
  "origen": "google",
  "aeropuertos": [
    {
      "iata": "BCE",
      "nombre": "Bryce Canyon Airport",
      "municipio": "Bryce Canyon",
      "km": 5,
      "horas": null,
      "grande": false
    }
  ]
};
