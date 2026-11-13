import type { FichaPersona, Kpi, TableroKpis } from "../domain/kpis";

/** Datos de ejemplo con la forma de la API, para pruebas. */
export const KPI_EJEMPLO: Kpi = {
  nombre: "tasa_reutilizacion",
  titulo: "Búsquedas resueltas sin pagar otra consulta",
  unidad: "%",
  para_que: "Costo del buscador",
  formula: "Consultas resueltas con una respuesta guardada ÷ consultas resueltas",
  sentido: "mayor",
  meta: 60,
  alerta: 30,
  responsable: "Operaciones",
  reto: 1,
  principal: true,
  valor: 72,
  estado: "verde",
  estado_texto: "En meta",
};

export const TABLERO_EJEMPLO: TableroKpis = {
  filtros: { proyecto_id: null, desde: null, hasta: null },
  retos: [
    { reto: 1, nombre: "Cotización de viajes" },
    { reto: 2, nombre: "Gastos (mirada de Finanzas)" },
  ],
  proyectos: [{ id: 1, nombre: "Casa en Moab" }],
  kpis: [
    KPI_EJEMPLO,
    {
      ...KPI_EJEMPLO,
      nombre: "ejecucion_presupuesto",
      titulo: "Gasto aprobado sobre presupuesto aprobado",
      sentido: "menor",
      meta: 100,
      alerta: 110,
      responsable: "Finanzas",
      reto: 2,
      valor: 118,
      estado: "rojo",
      estado_texto: "Fuera de meta",
    },
    { ...KPI_EJEMPLO, nombre: "gastos_sin_viaje", titulo: "Gastos sin viaje", unidad: "gastos", reto: 2, valor: null, estado: "sin datos", estado_texto: "Sin datos" },
  ],
  resumen: { verde: 1, ambar: 0, rojo: 1, sin_datos: 1 },
  tendencia: {
    semanas: ["2026-11-02", "2026-11-09"],
    filas: [{ nombre: "tasa_reutilizacion", titulo: "Búsquedas resueltas sin pagar otra consulta", unidad: "%", puntos: [{ valor: null, estado: "sin datos" }, { valor: 72, estado: "verde" }] }],
  },
  cotizacion: {
    cotizaciones_por_persona: [{ etiqueta: "Ana Piloto", valor: 3 }],
    cotizaciones_por_ruta: [{ etiqueta: "MIA → CNY", valor: 2 }],
    consultas_por_origen: [{ etiqueta: "en vivo", valor: 4 }],
    consultas_por_tipo: [],
    consultas_por_persona: [],
    consultas_por_ruta: [],
    errores_buscador: [],
    cupo: null,
  },
  gastos: {
    por_viaje: [{ id: 7, codigo: "V-2026-0007", titular: "Ana Piloto", ruta: "MIA → CNY", ida: "2026-12-08", estado: "aprobado", presupuesto: 1500, gastado: 1770, en_revision: 0, pct: 118 }],
    por_proyecto: [],
    por_categoria: [],
    por_moneda: [],
    revision_antiguas: [],
    real_total: 1770,
  },
  personas: [
    { id: 2, codigo: "P-0002", nombre: "Ana Piloto", rol: "colaborador", rol_texto: "Colaboración", activo: true, cotizaciones: 3, viajes: 1, presupuesto: 1500, gastado: 1770, en_revision: 0, ejecucion: 118, gastos: 4, gastos_revision: 1 },
  ],
  por_cargo: [],
};

export const FICHA_EJEMPLO: FichaPersona = {
  usuario: { id: 2, codigo: "P-0002", nombre: "Ana Piloto", correo: "piloto@demo.local", rol: "colaborador", rol_texto: "Colaboración", activo: true, creado: "2026-11-01", cargo: "Piloto", viajero: "Ana Piloto", base: "Miami" },
  totales: { presupuesto: 1500, gastado: 1770, en_revision: 0 },
  indicadores: [KPI_EJEMPLO],
  cotizaciones: [],
  viajes: [{ id: 7, codigo: "V-2026-0007", origen: "Miami", destino: "Moab", ida: "2026-12-08", regreso: "2026-12-11", estado: "aprobado", estado_texto: "Aprobado", proyecto: "Casa en Moab", presupuesto_usd: 1500, gastado: 1770, en_revision: 0, pct: 118 }],
  gastos: [],
  evidencias: [],
  eventos: [
    { momento: "2026-11-10T15:00:00", entidad: "viaje", entidad_id: 7, paso: "presupuesto aprobado", detalle: "Aprobado por administración", fuente: "web", quien: "Admin" },
  ],
  gastos_por_estado: [],
  gastos_por_canal: [],
};
