import { describe, expect, it } from "vitest";
import { formatearInstante } from "./formato";

describe("formatearInstante", () => {
  it("una hora de la base sin zona se toma como UTC, igual que una con Z", () => {
    // la base guarda «AAAA-MM-DD HH:MM:SS» en UTC; si se leyera como hora local cambiaría con la zona del navegador
    expect(formatearInstante("2026-11-13 14:02:00")).toBe(formatearInstante("2026-11-13T14:02:00Z"));
    expect(formatearInstante("2026-11-13T14:02:00")).toBe(formatearInstante("2026-11-13T14:02:00Z"));
  });

  it("respeta la zona cuando la trae", () => {
    expect(formatearInstante("2026-11-13T09:02:00-05:00")).toBe(formatearInstante("2026-11-13T14:02:00Z"));
  });

  it("devuelve el texto tal cual si no es una fecha", () => {
    expect(formatearInstante("sin fecha")).toBe("sin fecha");
  });
});
