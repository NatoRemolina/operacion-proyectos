import { PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearCuentaHttp } from "./cuenta-http";

probarRepositorioHttp("mi cuenta", crearCuentaHttp, {
  obtener: { llamar: (r) => r.obtener(), plazoMs: PLAZO_MS },
  cambiarClave: { llamar: (r) => r.cambiarClave("clave-actual-123", "clave-nueva-456789"), plazoMs: PLAZO_MS },
  vincularTelegram: { llamar: (r) => r.vincularTelegram(), plazoMs: PLAZO_MS },
  desvincularTelegram: { llamar: (r) => r.desvincularTelegram(), plazoMs: PLAZO_MS },
}, "obtener");
