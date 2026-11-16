import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { SIN_FILTROS } from "../domain/kpis";
import { crearKpisHttp } from "./kpis-http";

probarRepositorioHttp("indicadores", crearKpisHttp, {
  tablero: { llamar: (r) => r.tablero(SIN_FILTROS), plazoMs: PLAZO_MS },
  ficha: { llamar: (r) => r.ficha(2), plazoMs: PLAZO_MS },
  rutasFrecuentes: { llamar: (r) => r.rutasFrecuentes(), plazoMs: PLAZO_MS },
}, "tablero");
