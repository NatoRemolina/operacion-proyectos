import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderizarConFuente } from "@/test/renderizar";
import { VuelosRepositoryProvider } from "../application/vuelos";
import type { VuelosRepository } from "../domain/vuelos";
import { TRAMO_EJEMPLO } from "../infrastructure/ejemplo-vuelos";
import { crearVuelosMemoria } from "../infrastructure/vuelos-memoria";
import { PantallaVuelos } from "./pantalla-vuelos";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }), usePathname: () => "/vuelos" }));

function montar(repo: VuelosRepository, fecha: string | null = null) {
  return renderizarConFuente(
    <VuelosRepositoryProvider repositorio={repo}>
      <PantallaVuelos fecha={fecha} />
    </VuelosRepositoryProvider>,
    { permiso: "admin" },
  );
}

describe("Estado de los vuelos", () => {
  it("muestra estado, retraso, terminal y puerta, el origen «Estado de ejemplo» y si no llega a la grabación", async () => {
    montar(crearVuelosMemoria({ tramos: [TRAMO_EJEMPLO] }));
    expect(await screen.findByRole("heading", { level: 1, name: "Vuelos de hoy (2026-12-13, UTC)" })).toBeInTheDocument();
    const tabla = screen.getByRole("table");
    expect(within(tabla).getByText("Retrasado")).toBeInTheDocument();
    expect(within(tabla).getByText("20 min")).toBeInTheDocument();
    expect(within(tabla).getByText("4 · J58")).toBeInTheDocument();
    expect(within(tabla).getByText("Estado de ejemplo")).toBeInTheDocument();
    expect(within(tabla).getByText("No llega a la grabación")).toBeInTheDocument();
    expect(within(tabla).getByText("09:50 (prog. 09:30)")).toBeInTheDocument();
    expect(within(tabla).getByText(/Último aviso al viajero .*no tiene Telegram vinculado/)).toBeInTheDocument();
    expect(within(tabla).getByRole("link", { name: "V-2026-0007" })).toHaveAttribute("href", "/viajes/7");
  });

  it("«Actualizar ahora» llama a la acción y dice el resultado", async () => {
    const usuario = userEvent.setup();
    const base = crearVuelosMemoria({ tramos: [TRAMO_EJEMPLO] });
    const actualizar = vi.fn(base.actualizar);
    montar({ ...base, actualizar });
    const tabla = await screen.findByRole("table");
    await usuario.click(within(tabla).getByRole("button", { name: "Actualizar ahora el vuelo IB 5634 del viaje V-2026-0007" }));
    expect(actualizar).toHaveBeenCalledWith(41);
    expect(await screen.findByText("IB 5634: no se consultó (consultado hace menos de 1 min).")).toBeInTheDocument();
  });

  it("se vuelve a pedir cada 15 s", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const base = crearVuelosMemoria({ tramos: [TRAMO_EJEMPLO] });
      const delDia = vi.fn(base.delDia);
      montar({ ...base, delDia });
      await screen.findByRole("table");
      expect(delDia).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(15_000);
      expect(delDia).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("sin vuelos lo dice y deja elegir otro día", async () => {
    const usuario = userEvent.setup();
    montar(crearVuelosMemoria({ tramos: [] }), "2026-12-20");
    expect(await screen.findByText("No hay vuelos registrados para este día")).toBeInTheDocument();
    const dia = screen.getByLabelText("Día");
    await usuario.clear(dia);
    await usuario.type(dia, "2026-12-13");
    await usuario.click(screen.getByRole("button", { name: "Ver" }));
    expect(push).toHaveBeenCalledWith("/vuelos?fecha=2026-12-13");
    expect(screen.getByRole("link", { name: "Volver a hoy" })).toHaveAttribute("href", "/vuelos");
  });

  it("sin permiso lo dice", async () => {
    montar(crearVuelosMemoria({ tramos: null }));
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
  });
});
