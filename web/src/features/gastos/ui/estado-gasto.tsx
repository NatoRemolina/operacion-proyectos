import { InsigniaEstado, type Tono } from "@/shared/ui/estado";
import type { EstadoGasto } from "../domain/gastos";

const TONO: Record<EstadoGasto, Tono> = {
  procesando: "neutro",
  revision: "aviso",
  aprobado_auto: "exito",
  aprobado: "exito",
  rechazado: "error",
};

export function InsigniaGasto({ estado, texto }: { estado: EstadoGasto; texto: string }) {
  return <InsigniaEstado tono={TONO[estado]}>{texto}</InsigniaEstado>;
}
