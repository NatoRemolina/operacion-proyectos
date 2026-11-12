import { describe, expect, it } from "vitest";
import { crearSesionMemoria } from "@/shared/infrastructure/memoria";
import { crearGastosMemoria } from "./gastos-memoria";

const viajesPropios = [{ id: 12, codigo: "V-2026-0012", enCurso: true }];

describe("adaptador en memoria de gastos", () => {
  it("cumple la idempotencia del contrato", async () => {
    const gastos = crearGastosMemoria({ viajesPropios });
    const archivo = new File(["a"], "a.jpg", { type: "image/jpeg", lastModified: 1 });
    const otro = new File(["bb"], "b.jpg", { type: "image/jpeg", lastModified: 2 });

    const primero = await gastos.enviar({ archivo, viajeId: null, claveIdempotencia: "k1" });
    const repetido = await gastos.enviar({ archivo, viajeId: null, claveIdempotencia: "k1" });
    expect(repetido.id).toBe(primero.id);
    await expect(gastos.enviar({ archivo: otro, viajeId: null, claveIdempotencia: "k1" })).rejects.toMatchObject({
      tipo: "conflicto",
    });
    expect((await gastos.listar({})).items).toHaveLength(1);
  });

  it("imagen con viaje en curso se aprueba; PDF o sin viaje queda en revisión", async () => {
    const gastos = crearGastosMemoria({ viajesPropios });
    const imagen = new File(["a"], "a.jpg", { type: "image/jpeg" });
    const pdf = new File(["a"], "a.pdf", { type: "application/pdf" });

    expect((await gastos.enviar({ archivo: imagen, viajeId: null, claveIdempotencia: "1" })).estado).toBe("aprobado_auto");
    expect((await gastos.enviar({ archivo: pdf, viajeId: null, claveIdempotencia: "2" })).estado).toBe("revision");
    const sinViaje = await gastos.enviar({ archivo: imagen, viajeId: 999, claveIdempotencia: "3" });
    expect(sinViaje.estado).toBe("revision");
    expect(sinViaje.motivos).toContain("sin_viaje");
  });

  it("sin sesión responde como la API: sesión vencida", async () => {
    const gastos = crearGastosMemoria({ sesion: crearSesionMemoria() });
    await expect(gastos.listar({})).rejects.toMatchObject({ tipo: "sesion_vencida" });
  });
});
