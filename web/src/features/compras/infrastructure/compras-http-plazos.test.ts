import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { PLAZO_ANALISIS_MS } from "@/features/cotizar/infrastructure/cotizar-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearComprasHttp } from "./compras-http";

probarRepositorioHttp("compras", crearComprasHttp, {
  lista: { llamar: (r) => r.lista(), plazoMs: PLAZO_MS },
  detalle: { llamar: (r) => r.detalle(4), plazoMs: PLAZO_MS },
  cambiarEstado: { llamar: (r) => r.cambiarEstado(4, "se_comprara" as never, 2, null as never), plazoMs: PLAZO_MS },
  registrar: { llamar: (r) => r.registrar(4, 2, {} as never), plazoMs: PLAZO_MS },
  // lee la página del vuelo con el analizador
  analizar: { llamar: (r) => r.analizar(4), plazoMs: PLAZO_ANALISIS_MS },
}, "lista");
