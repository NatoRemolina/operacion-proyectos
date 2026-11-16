import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearAuthHttp } from "./auth-http";

probarRepositorioHttp("ingreso", crearAuthHttp, {
  entrar: { llamar: (r) => r.entrar("persona@empresa.com", "clave-de-prueba"), plazoMs: PLAZO_MS },
  quienSoy: { llamar: (r) => r.quienSoy(), plazoMs: PLAZO_MS },
  salir: { llamar: (r) => r.salir(), plazoMs: PLAZO_MS },
}, "entrar");
