import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { gastoDePrueba } from "@/test/fabricas";
import { DetalleGasto } from "./detalle-gasto";

describe("Detalle de un gasto rechazado", () => {
  it("la persona ve el motivo con las palabras de quien revisó", () => {
    render(
      <DetalleGasto
        gasto={gastoDePrueba({ estado: "rechazado", estado_texto: "Rechazado", motivo_rechazo: "Es un gasto personal" })}
        urlOriginal={null}
      />,
    );
    expect(screen.getByText("Por qué se rechazó")).toBeInTheDocument();
    expect(screen.getByText("Es un gasto personal")).toBeInTheDocument();
  });

  it("sin motivo guardado lo dice en vez de dejar el hueco", () => {
    render(<DetalleGasto gasto={gastoDePrueba({ estado: "rechazado", estado_texto: "Rechazado", motivo_rechazo: null })} urlOriginal={null} />);
    expect(screen.getByText("Quien revisó no dejó el motivo escrito.")).toBeInTheDocument();
  });
});
