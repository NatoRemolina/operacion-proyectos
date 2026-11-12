import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarcoPrivado } from "./marco-privado";

const ENLACES = [{ href: "/viajes", texto: "Mis viajes", corto: "Viajes" }];

function marco(cargo?: string | null) {
  return render(
    <MarcoPrivado nombre="Andrés Molina" cargo={cargo} enlaces={ENLACES} rutaActual="/viajes" onSalir={() => {}} saliendo={false}>
      <p>contenido</p>
    </MarcoPrivado>,
  );
}

describe("Marco privado", () => {
  it("muestra el cargo bajo el nombre", () => {
    marco("Pilotaje de dron");
    expect(screen.getByText("Andrés Molina")).toBeInTheDocument();
    expect(screen.getByText("Pilotaje de dron")).toBeInTheDocument();
  });

  it("sin cargo solo muestra el nombre", () => {
    const { container } = marco(null);
    expect(screen.getByText("Andrés Molina")).toBeInTheDocument();
    expect(container.textContent).not.toContain("Pilotaje");
  });
});
