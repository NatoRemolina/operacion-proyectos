import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearProyectosHttp } from "./proyectos-http";

probarRepositorioHttp("proyectos", crearProyectosHttp, {
  listar: { llamar: (r) => r.listar({ limite: 20, cursor: null } as never), plazoMs: PLAZO_MS },
  obtener: { llamar: (r) => r.obtener(1), plazoMs: PLAZO_MS },
  crear: { llamar: (r) => r.crear({} as never), plazoMs: PLAZO_MS },
  editar: { llamar: (r) => r.editar(1, {} as never), plazoMs: PLAZO_MS },
}, "listar");
