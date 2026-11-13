import type { AnalisisVuelo } from "../domain/cotizar";

/**
 * Lectura de la página real de Google Flights del 13 nov 2026 (Miami → Las Vegas, AA 1851, 8 al 11 de diciembre de
 * 2026), con la forma de la API v1. Sirve a las pruebas y al modo demostración: la web nunca abre Google por su cuenta.
 */
export const ANALISIS_EJEMPLO: AnalisisVuelo = {
  "id": 1,
  "opcion_id": 6,
  "estado": "listo",
  "motivo": null,
  "url": "https://www.google.com/travel/flights?hl=en&gl=us&curr=USD&tfs=CBwQAhpAEgoyMDI2LTEyLTA4IiAKA01JQRIKMjAyNi0xMi0wOBoDTEFTKgJBQTIEMTg1MWoHCAESA01JQXIHCAESA0xBUxpAEgoyMDI2LTEyLTExIiAKA0xBUxIKMjAyNi0xMi0xMRoDTUlBKgJBQTIEMTg1MWoHCAESA0xBU3IHCAESA01JQUABSAFwAZgBAQ&tfu=EgIIAQ",
  "leido": "2026-11-13T15:10:00Z",
  "duracion_ms": 6800,
  "reutilizado": false,
  "precio_buscador_usd": "458.00",
  "aviso_precio": "Google Flights muestra 619 USD y el buscador dio 458 USD. La comparación sigue usando el precio del buscador.",
  "datos": {
    "precio_total": 619.0,
    "tramos": [
      {
        "fecha": "Tue, Dec 8",
        "sale": "9:48 AM",
        "llega": "12:24 PM",
        "aerolinea": "American",
        "duracion": "5 hr 36 min",
        "ruta": "MIA–LAS",
        "escalas": "Nonstop",
        "detalle_escalas": [],
        "emisiones": "269 kg CO2e"
      },
      {
        "fecha": "Fri, Dec 11",
        "sale": "1:43 PM",
        "llega": "9:29 PM",
        "aerolinea": "American",
        "duracion": "4 hr 46 min",
        "ruta": "LAS–MIA",
        "escalas": "Nonstop",
        "detalle_escalas": [],
        "emisiones": "262 kg CO2e"
      }
    ],
    "vendedores": [
      {
        "vendedor": "American",
        "aerolinea": true,
        "precio_desde": 619.0
      }
    ],
    "tarifas": [
      {
        "nombre": "Basic Economy",
        "precio": 619.0,
        "equipaje": [
          "1 free carry-on",
          "1st checked bag: $110"
        ],
        "cambios": [
          "No ticket changes"
        ],
        "reembolso": [
          "No refunds"
        ],
        "otras": [
          "Seat selection for a fee",
          "Standard seat",
          "Priority boarding for a fee"
        ],
        "vendedor": "American"
      },
      {
        "nombre": "Main Cabin",
        "precio": 1014.0,
        "equipaje": [
          "1 free carry-on",
          "1st checked bag: $100"
        ],
        "cambios": [
          "Free change, possible fare difference"
        ],
        "reembolso": [
          "No refunds"
        ],
        "otras": [
          "Free seat selection",
          "Extra legroom available for a fee",
          "Priority boarding for a fee"
        ],
        "vendedor": "American"
      },
      {
        "nombre": "Main Plus",
        "precio": 1226.0,
        "equipaje": [
          "1 free carry-on",
          "1st checked bag free"
        ],
        "cambios": [
          "Free change, possible fare difference"
        ],
        "reembolso": [
          "No refunds"
        ],
        "otras": [
          "Free seat selection",
          "Extra legroom",
          "Priority boarding for a fee"
        ],
        "vendedor": "American"
      },
      {
        "nombre": "Main Select",
        "precio": 1284.0,
        "equipaje": [
          "1 free carry-on",
          "1st checked bag: $100"
        ],
        "cambios": [
          "Free change, possible fare difference"
        ],
        "reembolso": [
          "Full refunds"
        ],
        "otras": [
          "Free seat selection",
          "Extra legroom",
          "Priority boarding"
        ],
        "vendedor": "American"
      }
    ],
    "equipaje": [
      "1 free carry-on",
      "1st checked bag free",
      "1st checked bag: $100",
      "1st checked bag: $110"
    ],
    "cambios": [
      "Free change, possible fare difference",
      "No ticket changes"
    ],
    "reembolso": [
      "Full refunds",
      "No refunds"
    ],
    "notas": [
      "Fare and baggage fees apply to your entire trip. American bag policy For non-refundable fare options, taxes may be refundable.",
      "Prices include required taxes + fees for 1 adult. Optional charges and bag fees may apply."
    ],
    "avisos": [],
    "regreso_elegido": null
  },
  "captura_url": null
};
