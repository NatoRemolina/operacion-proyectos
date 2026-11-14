import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { PLAZO_LARGO_MS, PLAZO_MS, crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { PLAZO_ANALISIS_MS, crearCotizarHttp } from "./cotizar-http";

probarRepositorioHttp("cotizar", crearCotizarHttp, {
  formulario: { llamar: (r) => r.formulario(), plazoMs: PLAZO_MS },
  buscarLugares: { llamar: (r) => r.buscarLugares("Moab", true), plazoMs: PLAZO_MS },
  // buscan vuelos y hoteles en el buscador, en vivo
  cotizar: { llamar: (r) => r.cotizar({} as never, "clave-1"), plazoMs: PLAZO_LARGO_MS },
  decidir: { llamar: (r) => r.decidir(12, {} as never, "clave-2"), plazoMs: PLAZO_LARGO_MS },
  obtener: { llamar: (r) => r.obtener(12), plazoMs: PLAZO_MS },
  registrarFuente: { llamar: (r) => r.registrarFuente(12, "vuelos"), plazoMs: PLAZO_MS },
  // 58 s: antes de los 60 s de CloudFront, para pasar a consultar la lectura en curso (B9)
  analizarVuelo: { llamar: (r) => r.analizarVuelo(12, 3), plazoMs: PLAZO_ANALISIS_MS },
  verAnalisis: { llamar: (r) => r.verAnalisis(12, 3), plazoMs: PLAZO_MS },
  opcionesBuscador: { llamar: (r) => r.opcionesBuscador(12, 3), plazoMs: PLAZO_MS },
  evidencia: { llamar: (r) => r.evidencia(12), plazoMs: PLAZO_MS },
}, "obtener");

describe("leer la página del vuelo: plazo propio (B9)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("el plazo es de 58 s, antes de que CloudFront corte a los 60", () => {
    expect(PLAZO_ANALISIS_MS).toBe(58_000);
  });

  it("un 504 de CloudFront llega como plazo agotado, para pasar a consultar el estado", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(new Response("Gateway Timeout", { status: 504 })));
    const error = await crearCotizarHttp(crearClienteHttp("/api/v1")).analizarVuelo(12, 3).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ErrorDeAplicacion);
    expect((error as ErrorDeAplicacion).tipo).toBe("tiempo_agotado");
  });
});
