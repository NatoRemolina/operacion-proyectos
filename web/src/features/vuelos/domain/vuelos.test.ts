import { describe, expect, it } from "vitest";
import { hora, leerFecha, textoActualizado, textoAviso, tonoDeVuelo } from "./vuelos";

describe("Vuelos: dominio", () => {
  it("lee la fecha de la dirección solo si es AAAA-MM-DD", () => {
    expect(leerFecha("2026-12-13")).toBe("2026-12-13");
    expect(leerFecha("13/12/2026")).toBeNull();
    expect(leerFecha(["2026-12-13"])).toBeNull();
  });

  it("muestra la hora local y el tono de cada estado", () => {
    expect(hora("2026-12-13 09:05")).toBe("09:05");
    expect(hora(null)).toBe("—");
    expect(tonoDeVuelo("cancelado")).toBe("error");
    expect(tonoDeVuelo("retrasado")).toBe("aviso");
    expect(tonoDeVuelo("a tiempo")).toBe("exito");
    expect(tonoDeVuelo("programado")).toBe("neutro");
  });

  it("dice hace cuánto se consultó y por dónde salió el aviso", () => {
    expect(textoActualizado({ hace_min: null, consultas: 0 })).toBe("Sin consultar · 0 consultas");
    expect(textoActualizado({ hace_min: 3, consultas: 1 })).toBe("Hace 3 min · 1 consulta");
    expect(textoAviso(null)).toBeNull();
    expect(textoAviso({ momento: "06:00", texto: "Retraso", enviado: true })).toContain("enviado por Telegram");
    expect(textoAviso({ momento: "06:00", texto: "Retraso", enviado: false, error: "bloqueado" })).toContain("no se pudo enviar por Telegram: bloqueado");
  });
});
