import { describe, expect, it } from "vitest";
import { accionesPosibles, bloqueoSeComprara, requiereMotivo, validarRegistro } from "./compras";

describe("reglas de la bandeja de compras", () => {
  it("ofrece solo lo que se puede hacer desde cada estado", () => {
    expect(accionesPosibles({ estado: "solicitada" })).toEqual(["en_analisis", "se_comprara", "no_se_comprara"]);
    expect(accionesPosibles({ estado: "en_analisis" })).toEqual(["se_comprara", "no_se_comprara"]);
    expect(accionesPosibles({ estado: "se_comprara" })).toEqual(["cancelada"]);
    expect(accionesPosibles({ estado: "no_se_comprara" })).toEqual([]);
  });

  it("pide motivo para no comprar o cancelar, y el viaje aprobado para comprar", () => {
    expect([requiereMotivo("no_se_comprara"), requiereMotivo("cancelada"), requiereMotivo("se_comprara")]).toEqual([true, true, false]);
    const viaje = { id: 1, codigo: "V-2026-0001", presupuesto_usd: "1000.00" };
    expect(bloqueoSeComprara({ viaje: { ...viaje, estado: "pendiente_aprobacion" } })).toMatch(/no tiene el presupuesto aprobado/);
    expect(bloqueoSeComprara({ viaje: { ...viaje, estado: "aprobado" } })).toBeNull();
  });

  it("valida el registro de la compra antes de enviarlo", () => {
    expect(validarRegistro({ localizador: "x", precio_pagado: "abc", vendedor: " " })).toEqual({
      localizador: "El localizador son 5 a 8 letras o números.",
      precio_pagado: "Escribe el precio pagado en USD, como 461.30.",
      vendedor: "Escribe a quién se le compró.",
    });
    expect(validarRegistro({ localizador: "QX7Z2P", precio_pagado: "461.30", vendedor: "American" })).toEqual({});
  });
});
