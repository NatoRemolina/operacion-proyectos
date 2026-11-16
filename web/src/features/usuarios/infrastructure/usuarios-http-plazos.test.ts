import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearUsuariosHttp } from "./usuarios-http";

probarRepositorioHttp("usuarios", crearUsuariosHttp, {
  listar: { llamar: (r) => r.listar({ limite: 20, cursor: null } as never), plazoMs: PLAZO_MS },
  crear: { llamar: (r) => r.crear({} as never), plazoMs: PLAZO_MS },
  cambiarRol: { llamar: (r) => r.cambiarRol(2, "gestor"), plazoMs: PLAZO_MS },
  cambiarEstado: { llamar: (r) => r.cambiarEstado(2, false), plazoMs: PLAZO_MS },
  cambiarCargo: { llamar: (r) => r.cambiarCargo(2, 1), plazoMs: PLAZO_MS },
  asignarProyectos: { llamar: (r) => r.asignarProyectos(2, [1]), plazoMs: PLAZO_MS },
  restablecerClave: { llamar: (r) => r.restablecerClave(2, "clave-nueva-456789"), plazoMs: PLAZO_MS },
  listarCargos: { llamar: (r) => r.listarCargos(), plazoMs: PLAZO_MS },
  crearCargo: { llamar: (r) => r.crearCargo("Pilotaje"), plazoMs: PLAZO_MS },
  cambiarCargoCatalogo: { llamar: (r) => r.cambiarCargoCatalogo(1, {} as never), plazoMs: PLAZO_MS },
}, "listar");
