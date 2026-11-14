import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearReglasHttp } from "./reglas-http";

probarRepositorioHttp("reglas", crearReglasHttp, {
  catalogoReglas: { llamar: (r) => r.catalogoReglas(), plazoMs: PLAZO_MS },
  editarRegla: { llamar: (r) => r.editarRegla(1, "10"), plazoMs: PLAZO_MS },
}, "catalogoReglas");
