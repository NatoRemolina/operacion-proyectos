import { viajeDePrueba } from "@/test/fabricas";
import type { ProyectoResumen, TableroProyecto } from "../domain/proyectos";

/** Datos de prueba con la forma exacta del contrato (contracts/api-v1.md, sección «Proyectos»). */

export function proyectoDePrueba(datos: Partial<ProyectoResumen> = {}): ProyectoResumen {
  return {
    id: 1,
    nombre: "Residencial Summerlin (aéreo)",
    cliente: "Inmobiliaria Ejemplo Oeste",
    ciudad: "Las Vegas",
    fecha_inicio: "2026-12-08",
    fecha_fin: "2026-12-11",
    moneda: "USD",
    viajes: 2,
    gastos: 3,
    previsto_usd: "1500.00",
    real_usd: "1620.50",
    diferencia_usd: "120.50",
    ...datos,
  };
}

export function tableroDePrueba(datos: Partial<TableroProyecto> = {}): TableroProyecto {
  const proyecto = datos.proyecto ?? proyectoDePrueba();
  return {
    proyecto,
    categorias: [
      { clave: "vuelo", nombre: "Vuelo", previsto_usd: "900.00", real_usd: "1000.00", diferencia_usd: "100.00" },
      { clave: "hotel", nombre: "Hotel", previsto_usd: "400.00", real_usd: "0.00", diferencia_usd: "-400.00" },
      { clave: "viaticos", nombre: "Viáticos y gastos en destino", previsto_usd: "200.00", real_usd: "620.50", diferencia_usd: "420.50" },
    ],
    previsto_usd: proyecto.previsto_usd,
    real_usd: proyecto.real_usd,
    diferencia_usd: proyecto.diferencia_usd,
    en_revision: 1,
    faltantes: ["Hotel"],
    viajes: [viajeDePrueba({ id: 7, codigo: "V-2026-0007", proyecto: { id: proyecto.id, nombre: proyecto.nombre } })],
    gastos: [
      {
        id: 41,
        viaje: { id: 7, codigo: "V-2026-0007" },
        comercio: "Delta Air Lines",
        fecha: "2026-12-08",
        categoria: "vuelo",
        total: "1000.00",
        moneda: "USD",
        total_usd: "1000.00",
        estado: "aprobado",
        estado_texto: "Aprobado",
        creado: "2026-12-08T10:00:00Z",
        propio: false,
        viajero: "Alex Rivera",
      },
      {
        id: 42,
        viaje: { id: 7, codigo: "V-2026-0007" },
        comercio: "Café del Strip",
        fecha: "2026-12-09",
        categoria: "comida",
        total: "18.00",
        moneda: "USD",
        total_usd: "18.00",
        estado: "revision",
        estado_texto: "En revisión",
        creado: "2026-12-09T10:00:00Z",
        propio: false,
        viajero: "Alex Rivera",
      },
    ],
    periodo_contable: { desde: "2026-11-01", hasta: "2026-11-30" },
    ...datos,
  };
}
