import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderizarConFuente } from "@/test/renderizar";
import { MonitoreoRepositoryProvider } from "../application/monitoreo";
import type { MonitoreoRepository } from "../domain/monitoreo";
import { GASTOS_EJEMPLO, MODELO_EJEMPLO } from "../infrastructure/ejemplo-monitoreo";
import { crearMonitoreoMemoria } from "../infrastructure/monitoreo-memoria";
import { PantallaMonitoreo } from "./pantalla-monitoreo";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/monitoreo" }));

const SIN = { proyecto_id: null, desde: null, hasta: null };

function montar(ui: React.ReactElement, repo: MonitoreoRepository) {
  return renderizarConFuente(<MonitoreoRepositoryProvider repositorio={repo}>{ui}</MonitoreoRepositoryProvider>, { permiso: "admin" });
}

describe("Pantalla de Monitoreo", () => {
  it("muestra las cifras con su unidad y «Sin datos» cuando no hay", async () => {
    montar(<PantallaMonitoreo pestana="gastos" filtros={SIN} />, crearMonitoreoMemoria({ pestanas: { gastos: GASTOS_EJEMPLO } }));
    const cifras = await screen.findByRole("group", { name: "Cifras de Gastos" });
    expect(within(cifras).getByText("3")).toBeInTheDocument();
    expect(within(cifras).getByText(/^USD\s1\.770,50$/)).toBeInTheDocument();
    expect(within(cifras).getByText("Sin datos")).toBeInTheDocument();
  });

  it("pinta las tablas con enlaces a la web, barras y el texto de vacío", async () => {
    montar(<PantallaMonitoreo pestana="gastos" filtros={SIN} />, crearMonitoreoMemoria({ pestanas: { gastos: GASTOS_EJEMPLO } }));
    expect(await screen.findByRole("link", { name: "V-2026-0007" })).toHaveAttribute("href", "/viajes/7");
    const embudo = screen.getByRole("region", { name: "Embudo (se desliza de lado)" });
    expect(within(embudo).getByText("Recibidos")).toBeInTheDocument();
    expect(within(embudo).getByText("Proporción")).toBeInTheDocument();
    expect(screen.getByText("Ningún gasto ha ido a revisión.")).toBeInTheDocument();
  });

  it("las pestañas son enlaces que conservan los filtros y marcan la actual", async () => {
    montar(
      <PantallaMonitoreo pestana="gastos" filtros={{ proyecto_id: 1, desde: "2026-11-01", hasta: null }} />,
      crearMonitoreoMemoria({ pestanas: { gastos: GASTOS_EJEMPLO } }),
    );
    const nav = screen.getByRole("navigation", { name: "Pestañas de Monitoreo" });
    expect(within(nav).getByRole("link", { name: "Gastos" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Modelo de lenguaje" })).toHaveAttribute(
      "href",
      "/monitoreo?pestana=modelo&proyecto=1&desde=2026-11-01",
    );
    expect(within(nav).getAllByRole("link")).toHaveLength(7);
  });

  it("la pestaña del modelo muestra el costo del asesor", async () => {
    montar(<PantallaMonitoreo pestana="modelo" filtros={SIN} />, crearMonitoreoMemoria({ pestanas: { modelo: MODELO_EJEMPLO } }));
    expect(await screen.findByText("Costo del asesor")).toBeInTheDocument();
    expect(screen.getByText(/tope de 2 USD por día/)).toBeInTheDocument();
  });

  it("ofrece la descarga de la vista con los filtros", async () => {
    const repo: MonitoreoRepository = {
      ...crearMonitoreoMemoria({ pestanas: { gastos: GASTOS_EJEMPLO } }),
      urlExportar: (vista) => `/api/v1/monitoreo/exportar.csv?vista=${vista}`,
    };
    montar(<PantallaMonitoreo pestana="gastos" filtros={SIN} />, repo);
    const descargas = await screen.findByRole("region", { name: "Descargar en CSV" });
    expect(within(descargas).getByRole("link", { name: "Gastos" })).toHaveAttribute("href", "/api/v1/monitoreo/exportar.csv?vista=v_h_gasto");
  });

  it("sin permiso lo dice", async () => {
    montar(<PantallaMonitoreo pestana="gastos" filtros={SIN} />, crearMonitoreoMemoria({ pestanas: null }));
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
  });
});
