import { PLAZO_LARGO_MS, PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearCotizarHttp } from "./cotizar-http";

probarRepositorioHttp("cotizar", crearCotizarHttp, {
  formulario: { llamar: (r) => r.formulario(), plazoMs: PLAZO_MS },
  buscarLugares: { llamar: (r) => r.buscarLugares("Moab", true), plazoMs: PLAZO_MS },
  // buscan vuelos y hoteles en el buscador, en vivo
  cotizar: { llamar: (r) => r.cotizar({} as never, "clave-1"), plazoMs: PLAZO_LARGO_MS },
  decidir: { llamar: (r) => r.decidir(12, {} as never, "clave-2"), plazoMs: PLAZO_LARGO_MS },
  obtener: { llamar: (r) => r.obtener(12), plazoMs: PLAZO_MS },
  registrarFuente: { llamar: (r) => r.registrarFuente(12, "vuelos"), plazoMs: PLAZO_MS },
  analizarVuelo: { llamar: (r) => r.analizarVuelo(12, 3), plazoMs: PLAZO_LARGO_MS },
  verAnalisis: { llamar: (r) => r.verAnalisis(12, 3), plazoMs: PLAZO_MS },
  opcionesBuscador: { llamar: (r) => r.opcionesBuscador(12, 3), plazoMs: PLAZO_MS },
  evidencia: { llamar: (r) => r.evidencia(12), plazoMs: PLAZO_MS },
}, "obtener");
