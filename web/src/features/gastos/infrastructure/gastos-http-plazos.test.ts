import { PLAZO_LARGO_MS, PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearGastosHttp } from "./gastos-http";

const archivo = new File(["recibo"], "recibo.jpg", { type: "image/jpeg" });

probarRepositorioHttp("gastos", crearGastosHttp, {
  listar: { llamar: (r) => r.listar({ viajeId: null, estado: null, limite: 20, cursor: null } as never), plazoMs: PLAZO_MS },
  obtener: { llamar: (r) => r.obtener(5), plazoMs: PLAZO_MS },
  // el servidor lee el recibo con el modelo antes de responder
  enviar: { llamar: (r) => r.enviar({ archivo, viajeId: null, claveIdempotencia: "clave-1" } as never), plazoMs: PLAZO_LARGO_MS },
  justificar: { llamar: (r) => r.justificar(5, "Cambio de vuelo por clima"), plazoMs: PLAZO_MS },
}, "listar");
