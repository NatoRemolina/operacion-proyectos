import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { ErrorConsulta } from "./error-consulta";

describe("ErrorConsulta", () => {
  it("sin permiso explica que la página es de otro permiso, sin parecer un error", () => {
    render(<ErrorConsulta error={new ErrorDeAplicacion("prohibido")} volverA={{ href: "/viajes", texto: "Ir a mis viajes" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Esta página no está disponible con tu permiso");
    expect(screen.getByRole("link", { name: "Ir a mis viajes" })).toHaveAttribute("href", "/viajes");
  });

  it("con la sesión vencida, entrar de nuevo regresa a la misma página", () => {
    window.history.pushState({}, "", "/gastos/5?x=1");
    render(<ErrorConsulta error={new ErrorDeAplicacion("sesion_vencida")} />);
    expect(screen.getByRole("link", { name: "Entra de nuevo" })).toHaveAttribute(
      "href",
      `/entrar?volver=${encodeURIComponent("/gastos/5?x=1")}`,
    );
  });

  it("un error del servidor dice qué pasó, ofrece reintentar y muestra la referencia en pequeño", () => {
    render(
      <ErrorConsulta error={new ErrorDeAplicacion("servidor", { idPeticion: "abc123" })} onReintentar={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.getByText("Referencia: abc123")).toBeInTheDocument();
  });
});
