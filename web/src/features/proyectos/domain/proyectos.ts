import type { GastoResumen, PeriodoContable } from "@/features/gastos/domain/gastos";
import type { ViajeResumen } from "@/features/viajes/domain/viajes";
import type { Dinero, FechaISO, OpcionesListado, Pagina } from "@/shared/domain/tipos";

export interface ProyectoResumen {
  readonly id: number;
  readonly nombre: string;
  readonly cliente: string | null;
  readonly ciudad: string | null;
  readonly fecha_inicio: FechaISO;
  readonly fecha_fin: FechaISO;
  readonly moneda: string;
  /** Viajes y gastos del proyecto, en cualquier estado. */
  readonly viajes: number;
  readonly gastos: number;
  /** Presupuesto de los viajes del proyecto que no se rechazaron. */
  readonly previsto_usd: Dinero;
  /** Gastos aprobados. */
  readonly real_usd: Dinero;
  /** Real menos previsto: positivo es sobrecosto. */
  readonly diferencia_usd: Dinero;
}

export interface CategoriaProyecto {
  readonly clave: string;
  readonly nombre: string;
  readonly previsto_usd: Dinero;
  readonly real_usd: Dinero;
  readonly diferencia_usd: Dinero;
}

export interface GastoDelProyecto extends GastoResumen {
  readonly viajero: string | null;
}

export interface TableroProyecto {
  readonly proyecto: ProyectoResumen;
  readonly categorias: readonly CategoriaProyecto[];
  readonly previsto_usd: Dinero;
  readonly real_usd: Dinero;
  readonly diferencia_usd: Dinero;
  readonly en_revision: number;
  /** Categorías con previsto y sin ningún gasto aprobado todavía. */
  readonly faltantes: readonly string[];
  readonly viajes: readonly ViajeResumen[];
  readonly gastos: readonly GastoDelProyecto[];
  /** El año en curso (1 de enero a 31 de diciembre) que propone el Excel contable. */
  readonly periodo_contable: PeriodoContable;
}

/** Lo que se escribe al crear o editar un proyecto. */
export interface DatosProyecto {
  readonly nombre: string;
  readonly cliente: string;
  readonly ciudad: string;
  readonly fecha_inicio: string;
  readonly fecha_fin: string;
  readonly moneda: string;
}

export type CampoProyecto = keyof DatosProyecto;

export interface ProyectosRepository {
  /** Administración, todos; quien gestiona, los suyos. El más reciente primero. */
  listar(opciones: OpcionesListado, signal?: AbortSignal): Promise<Pagina<ProyectoResumen>>;
  obtener(id: number, signal?: AbortSignal): Promise<TableroProyecto>;
  crear(datos: DatosProyecto): Promise<ProyectoResumen>;
  editar(id: number, datos: DatosProyecto): Promise<ProyectoResumen>;
  /** Dirección de descarga; `null` si no hay plataforma conectada (modo demostración). */
  urlCsv(id: number): string | null;
  urlLibroContable(id: number, periodo: PeriodoContable): string | null;
}

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

function fechaValida(texto: string): boolean {
  if (!FECHA.test(texto)) return false;
  const fecha = new Date(`${texto}T00:00:00Z`);
  return !Number.isNaN(fecha.getTime()) && fecha.toISOString().slice(0, 10) === texto;
}

/** Qué corregir antes de enviar, campo por campo. Las mismas reglas que `app/servicios/proyectos.py`. */
export function problemasDeProyecto(datos: DatosProyecto): Partial<Record<CampoProyecto, string>> {
  const problemas: Partial<Record<CampoProyecto, string>> = {};
  if (datos.nombre.trim().length < 3) problemas.nombre = "El proyecto necesita un nombre.";
  const inicio = fechaValida(datos.fecha_inicio);
  const fin = fechaValida(datos.fecha_fin);
  if (!inicio) problemas.fecha_inicio = "Elige la fecha de inicio.";
  if (!fin) problemas.fecha_fin = "Elige la fecha final.";
  if (inicio && fin && datos.fecha_fin < datos.fecha_inicio) {
    problemas.fecha_fin = "La fecha final no puede ser anterior a la inicial.";
  }
  if (!/^[A-Za-z]{3}$/.test(datos.moneda.trim())) problemas.moneda = "La moneda es un código de tres letras, como USD o EUR.";
  return problemas;
}

export function datosDeProyecto(proyecto?: ProyectoResumen): DatosProyecto {
  return {
    nombre: proyecto?.nombre ?? "",
    cliente: proyecto?.cliente ?? "",
    ciudad: proyecto?.ciudad ?? "",
    fecha_inicio: proyecto?.fecha_inicio ?? "",
    fecha_fin: proyecto?.fecha_fin ?? "",
    moneda: proyecto?.moneda ?? "USD",
  };
}

export type SentidoDiferencia = "sobrecosto" | "por_debajo" | "igual";

/** Real − previsto: positivo es gastar más de lo previsto. */
export function sentidoDiferencia(diferencia: Dinero): SentidoDiferencia {
  const valor = Number(diferencia ?? "0");
  if (valor > 0) return "sobrecosto";
  if (valor < 0) return "por_debajo";
  return "igual";
}

/** Ancho de una barra: el valor frente al mayor de la comparación, de 0 a 100. */
export function proporcion(valor: Dinero, maximo: number): number {
  const numero = Number(valor ?? "0");
  if (!(maximo > 0) || !(numero > 0)) return 0;
  return Math.min(100, Math.round((numero / maximo) * 100));
}
