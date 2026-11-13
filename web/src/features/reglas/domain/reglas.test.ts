import { describe, expect, it } from "vitest";
import { esFuenteEnlace, problemaDeValor, valorParaEnviar, type Regla } from "./reglas";

const NUMERICA: Regla = {
  id: 26, ambito: "supuesto", entidad: "", tarifa: "", clave: "tolerancia_presupuesto", valor: "0.1", numerica: true,
  nota: "Holgura del presupuesto", fuente: "Supuesto de la empresa", confianza: "supuesto", verificado: "2026-11-11",
};
const DE_TEXTO: Regla = { ...NUMERICA, id: 3, ambito: "aerolinea", clave: "equipaje_mano", valor: "no", numerica: false };

describe("valor de una regla", () => {
  it("una regla numérica acepta la coma decimal y se envía con punto", () => {
    expect(problemaDeValor(NUMERICA, " 0,25 ")).toBeNull();
    expect(valorParaEnviar(NUMERICA, " 0,25 ")).toBe("0.25");
  });

  it.each(["80 USD", "-1", "", "nan", "Infinity"])("una regla numérica no acepta «%s»", (valor) => {
    expect(problemaDeValor(NUMERICA, valor)).toMatch(/no es un número válido para tolerancia_presupuesto/);
  });

  it("una regla de texto acepta texto y se envía sin espacios en los extremos", () => {
    expect(problemaDeValor(DE_TEXTO, "  sí, en rutas nacionales ")).toBeNull();
    expect(valorParaEnviar(DE_TEXTO, "  sí, en rutas nacionales ")).toBe("sí, en rutas nacionales");
  });

  it("más de 500 caracteres no se envía", () => {
    expect(problemaDeValor(DE_TEXTO, "x".repeat(501))).toMatch(/500 caracteres/);
  });

  it("solo una dirección http(s) es un enlace", () => {
    expect(esFuenteEnlace("https://www.faa.gov/hazmat")).toBe(true);
    expect(esFuenteEnlace("javascript:alert(1)")).toBe(false);
    expect(esFuenteEnlace("Supuesto de la empresa")).toBe(false);
    expect(esFuenteEnlace(null)).toBe(false);
  });
});
