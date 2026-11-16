import { PLAZO_LARGO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearVuelosHttp } from "./vuelos-http";

// El tablero y la actualización consultan el estado del vuelo en el buscador
probarRepositorioHttp("vuelos", crearVuelosHttp, {
  delDia: { llamar: (r) => r.delDia("2026-12-13"), plazoMs: PLAZO_LARGO_MS },
  actualizar: { llamar: (r) => r.actualizar(4), plazoMs: PLAZO_LARGO_MS },
}, "delDia");
