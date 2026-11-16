import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearViajesHttp } from "./viajes-http";

probarRepositorioHttp("viajes", crearViajesHttp, {
  listar: { llamar: (r) => r.listar({ estado: null, limite: 20, cursor: null } as never), plazoMs: PLAZO_MS },
  obtener: { llamar: (r) => r.obtener(9), plazoMs: PLAZO_MS },
}, "listar");
