import type { Evidencia } from "../domain/cotizar";

const BASE = "/api/v1/cotizaciones/12/evidencia";

/** La evidencia guardada de una decisión de ejemplo (Miami → Las Vegas, AA 1851 Main Cabin y el Flamingo), con la forma de la API v1. */
export const EVIDENCIA_EJEMPLO: Evidencia = {
  estado: "guardada",
  guardada: "2026-11-13T21:12:00Z",
  capturas: [
    {
      id: 51, tipo: "vuelo", motivo: "decision", estado: "lista", fallo: null, intentos: 1,
      creado: "2026-11-13T21:00:00Z", terminado: "2026-11-13T21:11:00Z",
      datos: {
        google: { precio_total: 619, precios: { nivel: "typical", rango: [410, 870] } },
        aerolinea: { total: 748.8, tarifa_base: 669.5, impuestos: 79.3, cabinas: ["Main"], numeros: ["AA 1851", "AA 1597"],
          pagina: "https://www.aa.com/airfare-sales/ui/passenger-ui/" },
      },
      imagenes: [`${BASE}/51/imagen/0`, `${BASE}/51/imagen/1`],
      texto_url: `${BASE}/51/texto`,
    },
    {
      id: 52, tipo: "hotel", motivo: "decision", estado: "lista", fallo: null, intentos: 1,
      creado: "2026-11-13T21:00:00Z", terminado: "2026-11-13T21:12:00Z",
      datos: { hotel: { nombre: "Flamingo Las Vegas Hotel & Casino", calificacion: 4.1, resenas: 52318,
        vendedores: [{ vendedor: "Booking.com", por_noche: 204, total: 612, incluye: ["Free cancellation until Dec 6"], oficial: false }] } },
      imagenes: [`${BASE}/52/imagen/0`],
      texto_url: `${BASE}/52/texto`,
    },
  ],
  seguimiento: [
    { momento: "2026-11-13T21:11:00Z", motivo: "decision", precio_google_usd: "619.00", total_aerolinea_usd: "748.80" },
    { momento: "2026-11-14T13:05:00Z", motivo: "seguimiento", precio_google_usd: "642.00", total_aerolinea_usd: "771.80" },
  ],
};

export const SIN_EVIDENCIA: Evidencia = { estado: "sin_evidencia", guardada: null, capturas: [], seguimiento: [] };
