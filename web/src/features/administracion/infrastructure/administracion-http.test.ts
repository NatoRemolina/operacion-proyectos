import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { gastoDePrueba, resumenDePrueba } from "@/test/fabricas";
import { crearAdministracionHttp } from "./administracion-http";

function respuestaJson(cuerpo: unknown, estado = 200) {
  return new Response(JSON.stringify(cuerpo), {
    status: estado,
    headers: { "Content-Type": "application/json", "X-Peticion": "peticion-1" },
  });
}

function preparar(...respuestas: Response[]) {
  const fetchFalso = vi.fn<typeof fetch>();
  for (const r of respuestas) fetchFalso.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fetchFalso);
  return { fetchFalso, administracion: crearAdministracionHttp(crearClienteHttp("/api/v1")) };
}

async function errorDe(promesa: Promise<unknown>): Promise<ErrorDeAplicacion> {
  try {
    await promesa;
  } catch (error) {
    expect(error).toBeInstanceOf(ErrorDeAplicacion);
    return error as ErrorDeAplicacion;
  }
  throw new Error("Se esperaba un error");
}

afterEach(() => vi.unstubAllGlobals());

describe("adaptador HTTP de administración", () => {
  it("lee el resumen con la forma del contrato", async () => {
    const { fetchFalso, administracion } = preparar(respuestaJson(resumenDePrueba()));
    const resumen = await administracion.resumen();
    expect(resumen.presupuesto_aprobado_usd).toBe("15000.00");
    expect(resumen.actividad[0]?.persona?.nombre).toBe("Alex Rivera");
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/resumen");
  });

  it("403 es «sin permiso»", async () => {
    const { administracion } = preparar(
      respuestaJson({ error: { code: "FORBIDDEN", message: "x" }, request_id: "r1" }, 403),
    );
    expect((await errorDe(administracion.resumen())).tipo).toBe("prohibido");
  });

  it("una respuesta con otra forma es un error de contrato", async () => {
    const { administracion } = preparar(respuestaJson({ ...resumenDePrueba(), gastado_usd: 12.5 }));
    expect((await errorDe(administracion.resumen())).tipo).toBe("contrato");
  });
});

const DATOS_REVISION = {
  gasto_id: 123,
  version: 3,
  metodo_pago: "Tarjeta",
  canal_reserva: null,
  lectura_original: {
    comercio: "Café", fecha: "2026-12-09", categoria: "comida", subtotal: "50.00", impuesto: "4.00", propina: null,
    total: "54.00", moneda: "USD", metodo_pago: null, canal_reserva: null, confianza: 0.62, dudas: ["total"],
  },
  soporte: { documento_id: 55, nombre: "recibo.png", forma: "imagen" },
  categorias: [{ clave: "comida", nombre: "Comida" }],
  viajes: [{ id: 7, codigo: "V-2026-0007", estado: "aprobado", estado_texto: "Aprobado", titular: "Alex", origen: "MIA", destino: "SLC", ida: "2026-12-08", regreso: "2026-12-11" }],
  propio: false,
  aviso_propio: null,
};

describe("adaptador HTTP de la revisión completa", () => {
  it("lee los datos de revisión del gasto", async () => {
    const { fetchFalso, administracion } = preparar(respuestaJson(DATOS_REVISION));
    const datos = await administracion.datosRevision(123);
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/gastos/123/revision");
    expect(datos.lectura_original?.dudas).toEqual(["total"]);
    expect(datos.viajes[0]?.codigo).toBe("V-2026-0007");
  });

  it("manda las correcciones, el viaje nuevo y el motivo en el cuerpo de la revisión", async () => {
    const { fetchFalso, administracion } = preparar(respuestaJson({ ...gastoDePrueba(), correo: null, motivo_rechazo: null }));
    await administracion.revisarGasto(123, {
      version: 3,
      accion: "excepcion",
      motivo: " Dos peajes iguales ",
      campos: { total: "60.00", impuesto: null },
      viajeId: 0,
    });
    const [ruta, init] = fetchFalso.mock.calls[0]!;
    expect(ruta).toBe("/api/v1/gastos/123/revision");
    expect(JSON.parse(String(init?.body))).toEqual({
      version: 3, accion: "excepcion", motivo: "Dos peajes iguales", total: "60.00", impuesto: null, viaje_id: 0,
    });
  });

  it("sin viaje nuevo no manda viaje_id: el servidor conserva el que tiene", async () => {
    const { fetchFalso, administracion } = preparar(respuestaJson({ ...gastoDePrueba(), correo: null, motivo_rechazo: null }));
    await administracion.revisarGasto(123, { version: 3, accion: "aprobar" });
    expect(JSON.parse(String(fetchFalso.mock.calls[0]![1]?.body))).toEqual({ version: 3, accion: "aprobar", motivo: "" });
  });

  it("la nota de voz se oye desde la API", () => {
    const { administracion } = preparar();
    expect(administracion.urlAudioJustificacion(123, 9)).toBe("/api/v1/gastos/123/justificaciones/9/audio");
  });
});
