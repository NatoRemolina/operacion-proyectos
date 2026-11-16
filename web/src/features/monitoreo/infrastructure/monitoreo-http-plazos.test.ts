import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { SIN_FILTROS } from "@/features/kpis/domain/kpis";
import { crearMonitoreoHttp } from "./monitoreo-http";

probarRepositorioHttp("monitoreo", crearMonitoreoHttp, {
  pestana: { llamar: (r) => r.pestana("resumen" as never, SIN_FILTROS), plazoMs: PLAZO_MS },
}, "pestana");
