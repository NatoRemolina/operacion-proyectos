import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { crearCotizarMemoria } from "@/features/cotizar/infrastructure/cotizar-memoria";
import { FORMULARIO_EJEMPLO } from "@/features/cotizar/infrastructure/ejemplo-moab";
import { PantallaCotizar } from "@/features/cotizar/ui/pantalla-cotizar";
import { PantallaGastos } from "@/features/gastos/ui/pantalla-gastos";
import { PantallaNuevoGasto } from "@/features/gastos/ui/pantalla-nuevo-gasto";
import { PantallaViajes } from "@/features/viajes/ui/pantalla-viajes";
import { renderizarConFuente } from "@/test/renderizar";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
}));

function migas() {
  return within(screen.getByRole("navigation", { name: "Migas de pan" }));
}

/** Toda pantalla dice dónde estás con las mismas migas: «Operaciones» y la sección, o la sección y la página. */
describe("Migas coherentes en todas las pantallas", () => {
  it("cotizar un viaje", () => {
    renderizarConFuente(<PantallaCotizar />, { cotizar: crearCotizarMemoria({ formulario: FORMULARIO_EJEMPLO }) });
    expect(migas().getByText("Operaciones")).toBeInTheDocument();
    expect(migas().getByText("Cotizar viaje")).toHaveAttribute("aria-current", "page");
  });

  it("viajes y gastos", () => {
    const { unmount } = renderizarConFuente(<PantallaViajes />, { permiso: "colaborador" });
    expect(migas().getByText("Mis viajes")).toHaveAttribute("aria-current", "page");
    unmount();
    renderizarConFuente(<PantallaGastos />, { permiso: "admin" });
    expect(migas().getByText("Gastos")).toHaveAttribute("aria-current", "page");
  });

  it("cargar un gasto cuelga de gastos", () => {
    renderizarConFuente(<PantallaNuevoGasto />);
    expect(migas().getByRole("link", { name: "Gastos" })).toHaveAttribute("href", "/gastos");
    expect(migas().getByText("Cargar un gasto")).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});
