import type { EstadoVisible } from "@/shared/domain/estados";
import { InsigniaEstado, type Tono } from "./estado";

const ESTADOS: Record<EstadoVisible, { tono: Tono; texto: string }> = {
  aprobado: { tono: "exito", texto: "Aprobado" },
  revision: { tono: "aviso", texto: "En revisión" },
  rechazado: { tono: "error", texto: "Rechazado" },
  pendiente: { tono: "neutro", texto: "Pendiente" },
  en_curso: { tono: "info", texto: "En curso" },
  cerrado: { tono: "neutro", texto: "Cerrado" },
  procesando: { tono: "info", texto: "Procesando" },
};

/** Etiqueta de estado: color, símbolo y texto siempre juntos. `texto` usa el que manda la API. */
export function EtiquetaEstado({ estado, texto }: { estado: EstadoVisible; texto?: string }) {
  const { tono, texto: porDefecto } = ESTADOS[estado];
  return <InsigniaEstado tono={tono}>{texto ?? porDefecto}</InsigniaEstado>;
}
