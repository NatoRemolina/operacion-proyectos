import { describe, expect, it } from "vitest";
import { consultaDeDireccion, formatearValor, hayFiltros, leerFiltros, textoMeta, tonoDeEstado } from "./kpis";

describe("KPIs: dominio", () => {
  it("lee los filtros de la dirección e ignora lo que no es válido, como el servidor", () => {
    expect(leerFiltros({ proyecto: "3", desde: "2026-11-01", hasta: "ayer" })).toEqual({ proyecto_id: 3, desde: "2026-11-01", hasta: null });
    expect(leerFiltros({ proyecto: "0" })).toEqual({ proyecto_id: null, desde: null, hasta: null });
    expect(leerFiltros({ proyecto: ["1", "2"] }).proyecto_id).toBeNull();
    expect(hayFiltros(leerFiltros({}))).toBe(false);
  });

  it("arma la consulta solo con los parámetros que tienen valor", () => {
    expect(consultaDeDireccion({ proyecto: 1, desde: null, hasta: "" })).toBe("?proyecto=1");
    expect(consultaDeDireccion({})).toBe("");
  });

  it("muestra cada valor con su unidad y «Sin datos» sin valor", () => {
    expect(formatearValor(72, "%")).toBe("72 %");
    expect(formatearValor(1234.5, "USD")).toMatch(/^USD\s1\.234,50$/);
    expect(formatearValor(8000, "ms")).toBe("8.000 ms");
    expect(formatearValor(null, "%")).toBe("Sin datos");
  });

  it("dice la meta según hacia dónde es mejor", () => {
    expect(textoMeta({ sentido: "mayor", meta: 60, alerta: 30, unidad: "%" })).toBe("Meta ≥ 60 % · rojo si < 30 %");
    expect(textoMeta({ sentido: "menor", meta: 24, alerta: 72, unidad: "h" })).toBe("Meta ≤ 24 h · rojo si > 72 h");
  });

  it("cada estado del semáforo tiene su tono", () => {
    expect(["verde", "ambar", "rojo", "sin datos"].map((e) => tonoDeEstado(e as never))).toEqual(["exito", "aviso", "error", "neutro"]);
  });
});
