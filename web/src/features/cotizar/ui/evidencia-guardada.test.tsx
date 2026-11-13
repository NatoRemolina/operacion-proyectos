import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { formatearDinero } from "@/shared/ui/formato";
import { renderizarConFuente } from "@/test/renderizar";
import type { Evidencia } from "../domain/cotizar";
import { EVIDENCIA_EJEMPLO } from "../infrastructure/ejemplo-evidencia";
import { EvidenciaGuardada } from "./evidencia-guardada";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/cotizar/12" }));

describe("Evidencia guardada de la decisión (pieza 5)", () => {
  it("mientras el trabajador la guarda, lo dice", () => {
    const guardando: Evidencia = { estado: "guardando", guardada: null, seguimiento: [],
      capturas: [{ ...EVIDENCIA_EJEMPLO.capturas[0]!, estado: "pendiente", datos: null, imagenes: [], texto_url: null, terminado: null }] };
    renderizarConFuente(<EvidenciaGuardada evidencia={guardando} />);
    expect(screen.getByText("Guardando la evidencia del vuelo…")).toHaveAttribute("role", "status");
  });

  it("guardada: la hora, las capturas, el detalle completo y la línea de precios del seguimiento", () => {
    renderizarConFuente(<EvidenciaGuardada evidencia={EVIDENCIA_EJEMPLO} />);
    const region = screen.getByRole("region", { name: /Evidencia guardada a las \d{2}:\d{2}/ });
    const imagenes = within(region).getAllByRole("link", { name: /Captura de página completa/ });
    expect(imagenes.map((a) => a.getAttribute("href"))).toEqual(EVIDENCIA_EJEMPLO.capturas.flatMap((c) => c.imagenes));
    expect(within(region).getByRole("link", { name: /Texto completo del vuelo/ })).toHaveAttribute("href", EVIDENCIA_EJEMPLO.capturas[0]!.texto_url);
    // lo leído en la aerolínea, con impuestos, y del hotel
    expect(within(region).getByText(`Impuestos: ${formatearDinero("79.30")}`, { normalizer: (t) => t.replace(/\s+/g, " ").trim() })).toBeInTheDocument();
    expect(within(region).getByText("Flamingo Las Vegas Hotel & Casino", { selector: "li" })).toBeInTheDocument();
    const filas = within(within(region).getByRole("table", { name: "Precios del seguimiento" })).getAllByRole("row");
    expect(filas).toHaveLength(1 + EVIDENCIA_EJEMPLO.seguimiento.length);
  });

  it("sin evidencia no muestra nada", () => {
    const { container } = renderizarConFuente(<EvidenciaGuardada evidencia={{ estado: "sin_evidencia", guardada: null, capturas: [], seguimiento: [] }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
