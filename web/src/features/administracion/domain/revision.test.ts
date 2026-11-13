import { describe, expect, it } from "vitest";
import { gastoDePrueba } from "@/test/fabricas";
import {
  cambiosDeRevision,
  formularioInicial,
  importeNormalizado,
  problemaDeMotivoExcepcion,
  type DatosRevision,
} from "./revision";

const DATOS: DatosRevision = {
  gasto_id: 123,
  version: 3,
  metodo_pago: "Tarjeta",
  canal_reserva: null,
  lectura_original: null,
  soporte: null,
  categorias: [
    { clave: "comida", nombre: "Comida" },
    { clave: "otros", nombre: "Otros" },
  ],
  viajes: [],
  propio: false,
  aviso_propio: null,
};

const GASTO = gastoDePrueba({ comercio: "Café", categoria: "comida", total: "54.00", impuesto: "4.00", viaje: { id: 7, codigo: "V-7" } });

describe("importes que escribe quien revisa", () => {
  it.each([
    ["54", "54.00"],
    ["54,5", "54.50"],
    ["1.234,56", "1234.56"],
    ["1,234.56", "1234.56"],
    ["45.000", "45000.00"],
    [" USD 12.30 ", "12.30"],
  ])("«%s» se envía como %s", (texto, valor) => {
    expect(importeNormalizado(texto)).toEqual({ valor });
  });

  it("vacío quita el importe", () => {
    expect(importeNormalizado("  ")).toEqual({ valor: null });
  });

  it("lo que no es un número se explica", () => {
    expect(importeNormalizado("cuarenta")).toEqual({ error: "Escribe un importe como 54.00." });
  });
});

describe("cambios de la revisión", () => {
  it("sin tocar nada no hay cambios", () => {
    const inicial = formularioInicial(GASTO, DATOS);
    expect(cambiosDeRevision(inicial, inicial)).toEqual({ campos: {}, errores: {} });
  });

  it("solo manda lo que cambió, ya normalizado", () => {
    const inicial = formularioInicial(GASTO, DATOS);
    const cambios = cambiosDeRevision(
      { ...inicial, comercio: "  Café del centro ", total: "60,5", moneda: "eur", impuesto: "", metodo_pago: "Efectivo" },
      inicial,
    );
    expect(cambios).toEqual({
      campos: { comercio: "Café del centro", total: "60.50", moneda: "EUR", impuesto: null, metodo_pago: "Efectivo" },
      errores: {},
    });
  });

  it("un importe o una moneda que no sirven se marcan por campo", () => {
    const inicial = formularioInicial(GASTO, DATOS);
    const { errores } = cambiosDeRevision({ ...inicial, total: "mucho", moneda: "EURO" }, inicial);
    expect(errores).toEqual({ total: "Escribe un importe como 54.00.", moneda: "La moneda son 3 letras, como USD o EUR." });
  });

  it("reasignar o quitar el viaje", () => {
    const inicial = formularioInicial(GASTO, DATOS);
    expect(inicial.viaje).toBe("7");
    expect(cambiosDeRevision({ ...inicial, viaje: "9" }, inicial)).toEqual({ campos: {}, viajeId: 9, errores: {} });
    expect(cambiosDeRevision({ ...inicial, viaje: "" }, inicial)).toEqual({ campos: {}, viajeId: 0, errores: {} });
  });

  it("los datos que la ficha no trae salen de los datos de revisión", () => {
    expect(formularioInicial(GASTO, DATOS)).toMatchObject({ metodo_pago: "Tarjeta", canal_reserva: "", total: "54.00" });
  });
});

describe("motivo de la excepción", () => {
  it("pide 8 caracteres o más", () => {
    expect(problemaDeMotivoExcepcion(" corto  ")).toMatch(/al menos 8 caracteres/);
    expect(problemaDeMotivoExcepcion("Dos peajes iguales el mismo día")).toBeNull();
  });
});
