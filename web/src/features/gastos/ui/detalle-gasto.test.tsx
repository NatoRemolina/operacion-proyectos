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

  it("si es suyo, ofrece cargar el recibo de nuevo en el mismo viaje", () => {
    render(
      <DetalleGasto
        gasto={gastoDePrueba({ estado: "rechazado", estado_texto: "Rechazado", motivo_rechazo: "Ilegible", puede_justificar: true })}
        urlOriginal={null}
      />,
    );
    expect(screen.getByRole("link", { name: "Cargar el recibo de nuevo" })).toHaveAttribute("href", "/gastos/nuevo?viaje=7");
  });

  it("si no es suyo, no lo ofrece", () => {
    render(
      <DetalleGasto
        gasto={gastoDePrueba({ estado: "rechazado", estado_texto: "Rechazado", motivo_rechazo: "Ilegible", puede_justificar: false })}
        urlOriginal={null}
      />,
    );
    expect(screen.queryByRole("link", { name: "Cargar el recibo de nuevo" })).not.toBeInTheDocument();
  });
});


describe("Detalle de un gasto que llegó por correo", () => {
  it("muestra de quién llegó y con qué asunto", () => {
    render(
      <DetalleGasto
        gasto={gastoDePrueba({
          canal: "correo",
          correo: { remitente: "Casa do Tejo <reservas@casadotejo.test>", asunto: "Fatura da sua estadia" },
        })}
        urlOriginal={null}
      />,
    );
    expect(screen.getByText("Correo")).toBeInTheDocument();
    expect(screen.getByText("Casa do Tejo <reservas@casadotejo.test>")).toBeInTheDocument();
    expect(screen.getByText("Fatura da sua estadia")).toBeInTheDocument();
  });

  it("sin correo no muestra esas filas", () => {
    render(<DetalleGasto gasto={gastoDePrueba({ correo: null })} urlOriginal={null} />);
    expect(screen.queryByText("Remitente")).not.toBeInTheDocument();
  });
});

describe("Categoría en el detalle", () => {
  it("muestra el nombre de la categoría y no su clave", () => {
    render(<DetalleGasto gasto={gastoDePrueba({ categoria: "transporte_terrestre" })} urlOriginal={null} />);
    expect(screen.getByText("Transporte terrestre: taxi, bus, tren, aplicación")).toBeInTheDocument();
  });
});

describe("Datos opcionales del recibo", () => {
  it("un impuesto o un subtotal vacío se muestra como «—»; solo el total sin leer está por confirmar", () => {
    const { rerender } = render(
      <DetalleGasto
        gasto={gastoDePrueba({ estado: "aprobado_auto", subtotal: null, impuesto: null, propina: null, total: "32.50" })}
        urlOriginal={null}
      />,
    );
    const valor = (termino: string) => screen.getByText(termino, { selector: "dt" }).nextElementSibling;
    expect(valor("Impuesto")).toHaveTextContent(/^—$/);
    expect(valor("Subtotal")).toHaveTextContent(/^—$/);
    expect(screen.queryByText("Importe por confirmar")).not.toBeInTheDocument();
    rerender(<DetalleGasto gasto={gastoDePrueba({ estado: "revision", total: null })} urlOriginal={null} />);
    expect(valor("Total")).toHaveTextContent("Importe por confirmar");
  });
});
