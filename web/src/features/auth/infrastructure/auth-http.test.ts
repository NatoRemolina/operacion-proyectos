import { describe, expect, it } from "vitest";
import { personaDePrueba } from "@/test/fabricas";
import { personaSchema } from "./auth-http";

describe("Persona del contrato (permiso y cargo por separado)", () => {
  it("acepta el permiso colaborador con su cargo, o sin cargo", () => {
    expect(personaSchema.parse(personaDePrueba()).cargo).toBe("Pilotaje de dron");
    expect(personaSchema.parse(personaDePrueba({ rol: "admin", cargo: null })).cargo).toBeNull();
  });

  it("rechaza el permiso anterior «piloto» y una respuesta sin cargo", () => {
    expect(personaSchema.safeParse({ ...personaDePrueba(), rol: "piloto" }).success).toBe(false);
    const sinCargo: Record<string, unknown> = { ...personaDePrueba() };
    delete sinCargo.cargo;
    expect(personaSchema.safeParse(sinCargo).success).toBe(false);
  });
});
