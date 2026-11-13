import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FormularioEntrar } from "./formulario-entrar";

function Montaje() {
  const [error, setError] = useState<string | null>(null);
  return (
    <FormularioEntrar
      enviando={false}
      error={error}
      onEntrar={() => setError("El correo o la contraseña no son correctos.")}
    />
  );
}

describe("Formulario de ingreso", () => {
  it("tiene etiquetas y, si falla, muestra un error genérico sin borrar el correo", async () => {
    const usuario = userEvent.setup();
    render(<Montaje />);

    await usuario.type(screen.getByLabelText("Correo"), "ana@empresa.com");
    await usuario.type(screen.getByLabelText("Contraseña"), "incorrecta");
    await usuario.click(screen.getByRole("button", { name: "Ingresar" }));

    expect(screen.getByRole("alert")).toHaveTextContent("El correo o la contraseña no son correctos.");
    expect(screen.getByLabelText("Correo")).toHaveValue("ana@empresa.com");
  });
});
