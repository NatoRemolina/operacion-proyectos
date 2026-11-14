import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import ErrorDeLaPagina from "./error";
import ErrorGlobal from "./global-error";

describe("fallo inesperado al mostrar una página (B7)", () => {
  it("un error de la API muestra su mensaje claro y la referencia de la petición", async () => {
    const retry = vi.fn();
    render(<ErrorDeLaPagina error={new ErrorDeAplicacion("servidor", { idPeticion: "req-123" })} retry={retry} />);
    expect(screen.getByRole("heading", { name: "Algo falló al mostrar esta página" })).toBeInTheDocument();
    expect(screen.getByText("Algo falló en el servidor. Ya quedó registrado.")).toBeInTheDocument();
    expect(screen.getByText(/req-123/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("un error del servidor de la web muestra su identificador, no el texto interno", () => {
    const interno = Object.assign(new Error("TypeError: lectura de undefined en /srv/app"), { digest: "3291048" });
    render(<ErrorDeLaPagina error={interno} retry={() => {}} />);
    expect(screen.getByText(/3291048/)).toBeInTheDocument();
    expect(screen.queryByText(/lectura de undefined/)).toBeNull();
  });

  it("lo que no es un Error también se muestra sin romper la página", () => {
    render(<ErrorDeLaPagina error="texto suelto" retry={() => {}} />);
    expect(screen.getByRole("heading", { name: "Algo falló al mostrar esta página" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a mis viajes" })).toHaveAttribute("href", "/viajes");
  });

  it("el fallo de la plantilla raíz trae su propio documento, con el mensaje y la referencia", () => {
    const html = renderToStaticMarkup(
      <ErrorGlobal error={new ErrorDeAplicacion("red", { idPeticion: "req-9" })} retry={() => {}} />,
    );
    expect(html).toMatch(/^<html lang="es"/);
    expect(html).toContain("No hubo conexión con el servidor.");
    expect(html).toContain("req-9");
  });
});
