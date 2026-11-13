import type { PestanaMonitoreo } from "../domain/monitoreo";

const PESTANAS: PestanaMonitoreo["pestanas"] = [
  { clave: "viajes", titulo: "Viajes" },
  { clave: "gastos", titulo: "Gastos" },
  { clave: "busquedas", titulo: "Búsquedas" },
  { clave: "modelo", titulo: "Modelo de lenguaje" },
  { clave: "cupos", titulo: "Cupos" },
  { clave: "auditoria", titulo: "Auditoría" },
  { clave: "calidad", titulo: "Calidad" },
];

/** Datos de ejemplo con la forma de la API, para pruebas. */
export const GASTOS_EJEMPLO: PestanaMonitoreo = {
  pestana: "gastos",
  titulo: "Gastos",
  nota: "Cada cifra sale del catálogo de métricas.",
  pestanas: PESTANAS,
  filtros: { proyecto_id: null, desde: null, hasta: null },
  proyectos: [{ id: 1, nombre: "Casa en Moab" }],
  cifras: [
    { etiqueta: "Esperando revisión", valor: 3, unidad: null, pie: "carga actual de quien revisa" },
    { etiqueta: "Gasto real aprobado", valor: 1770.5, unidad: "USD", pie: "convertido a USD" },
    { etiqueta: "Aprobados sin intervención", valor: null, unidad: "%", pie: "de 0 recibidos" },
  ],
  tablas: [
    {
      titulo: "Embudo",
      columnas: [
        { texto: "Etapa", unidad: null, fin: false },
        { texto: "Gastos", unidad: null, fin: true },
      ],
      filas: [
        ["Recibidos", 10],
        ["Aprobados", 5],
      ],
      vacio: "Sin datos todavía.",
      nota: null,
      barras: true,
    },
    {
      titulo: "Presupuesto frente a gasto, por viaje",
      columnas: [
        { texto: "Viaje", unidad: null, fin: false },
        { texto: "Aprobado", unidad: "USD", fin: true },
      ],
      filas: [[{ texto: "V-2026-0007", href: "/viajes/7" }, 1770]],
      vacio: "Sin viajes en el periodo.",
      nota: null,
      barras: false,
    },
    {
      titulo: "Por qué van a revisión",
      columnas: [
        { texto: "Motivo", unidad: null, fin: false },
        { texto: "Gastos", unidad: null, fin: true },
      ],
      filas: [],
      vacio: "Ningún gasto ha ido a revisión.",
      nota: null,
      barras: false,
    },
  ],
  exportar: [{ vista: "v_h_gasto", texto: "Gastos" }],
};

export const MODELO_EJEMPLO: PestanaMonitoreo = {
  ...GASTOS_EJEMPLO,
  pestana: "modelo",
  titulo: "Modelo de lenguaje",
  cifras: [{ etiqueta: "Costo del asesor", valor: 0.25, unidad: "USD", pie: "1 sesiones en el periodo · tope de 2 USD por día" }],
  tablas: [],
  exportar: [],
};
