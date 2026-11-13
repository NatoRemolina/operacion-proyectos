import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderizarConFuente } from "@/test/renderizar";
import { CuentaRepositoryProvider } from "../application/cuenta";
import type { MiCuenta } from "../domain/cuenta";
import { crearCuentaMemoria } from "../infrastructure/cuenta-memoria";
import { PantallaMiCuenta } from "./pantalla-mi-cuenta";

function cuentaDePrueba(telegram: Partial<MiCuenta["telegram"]> = {}): MiCuenta {
  return {
    persona: { id: 2, codigo: "P-0002", nombre: "Andrés Molina", rol: "colaborador", correo: "piloto@demo.local", cargo: "Pilotaje de dron" },
    rol_texto: "colaborador",
    telegram: { vinculado: false, usuario: null, canal_activo: false, ...telegram },
  };
}

function montar(cuenta = cuentaDePrueba()) {
  renderizarConFuente(
    <CuentaRepositoryProvider repositorio={crearCuentaMemoria({ cuenta, clave: "clave-actual-123" })}>
      <PantallaMiCuenta />
    </CuentaRepositoryProvider>,
    { personaId: 2 },
  );
}

describe("Mi cuenta", () => {
  it("muestra mis datos: nombre, código, correo, permiso y cargo", async () => {
    montar();
    const datos = await screen.findByRole("region", { name: "Mis datos" });
    expect(within(datos).getByText("Andrés Molina")).toBeInTheDocument();
    expect(within(datos).getByText("P-0002")).toBeInTheDocument();
    expect(within(datos).getByText("piloto@demo.local")).toBeInTheDocument();
    expect(within(datos).getByText("colaborador")).toBeInTheDocument();
    expect(within(datos).getByText("Pilotaje de dron")).toBeInTheDocument();
  });

  it("con el canal de Telegram apagado lo dice y no ofrece vincular", async () => {
    montar();
    const telegram = await screen.findByRole("region", { name: "Telegram" });
    expect(within(telegram).getByText(/no está configurado en esta instalación/)).toBeInTheDocument();
    expect(within(telegram).queryByRole("button", { name: "Vincular Telegram" })).not.toBeInTheDocument();
  });

  it("con el canal activo da el enlace y el código para vincular", async () => {
    const usuario = userEvent.setup();
    montar(cuentaDePrueba({ canal_activo: true }));
    const telegram = await screen.findByRole("region", { name: "Telegram" });
    expect(within(telegram).getByText("Sin vincular")).toBeInTheDocument();
    await usuario.click(within(telegram).getByRole("button", { name: "Vincular Telegram" }));
    const enlace = await within(telegram).findByRole("link", { name: "Abrir el chat y vincular" });
    expect(enlace.getAttribute("href")).toMatch(/^https:\/\/t\.me\/bot_de_demostracion\?start=/);
    expect(within(telegram).getByText(/\/start /)).toBeInTheDocument();
    expect(within(telegram).getByText(/Vale 15 minutos/)).toBeInTheDocument();
  });

  it("un chat vinculado se puede desvincular", async () => {
    const usuario = userEvent.setup();
    montar(cuentaDePrueba({ canal_activo: true, vinculado: true, usuario: "andres_vuela" }));
    const telegram = await screen.findByRole("region", { name: "Telegram" });
    expect(within(telegram).getByText("Chat vinculado")).toBeInTheDocument();
    expect(within(telegram).getByText("@andres_vuela")).toBeInTheDocument();
    await usuario.click(within(telegram).getByRole("button", { name: "Desvincular" }));
    expect(await within(telegram).findByText("Sin vincular")).toBeInTheDocument();
  });

  it("cambiar la contraseña pide la actual y la nueva dos veces", async () => {
    const usuario = userEvent.setup();
    montar();
    const formulario = await screen.findByRole("form", { name: "Cambiar mi contraseña" });
    const actual = within(formulario).getByLabelText("Contraseña actual");
    const nueva = within(formulario).getByLabelText("Contraseña nueva");
    const repetida = within(formulario).getByLabelText("Repite la contraseña nueva");
    await usuario.type(actual, "equivocada");
    await usuario.type(nueva, "clave-nueva-456789");
    await usuario.type(repetida, "clave-nueva-456780");
    await usuario.click(within(formulario).getByRole("button", { name: "Cambiar contraseña" }));
    expect(within(formulario).getByText("Las dos contraseñas nuevas no coinciden.")).toBeInTheDocument();
    await usuario.clear(repetida);
    await usuario.type(repetida, "clave-nueva-456789");
    await usuario.click(within(formulario).getByRole("button", { name: "Cambiar contraseña" }));
    expect(await within(formulario).findByText("La contraseña actual no coincide.")).toBeInTheDocument();
    expect(actual).toHaveAttribute("aria-invalid", "true");
    await usuario.clear(actual);
    await usuario.type(actual, "clave-actual-123");
    await usuario.click(within(formulario).getByRole("button", { name: "Cambiar contraseña" }));
    expect(await screen.findByText("Contraseña cambiada. Se cerraron tus otras sesiones.")).toBeInTheDocument();
    expect(actual).toHaveValue("");
    expect(nueva).toHaveValue("");
  });

  it("la nueva debe tener 10 caracteres o más", async () => {
    const usuario = userEvent.setup();
    montar();
    const formulario = await screen.findByRole("form", { name: "Cambiar mi contraseña" });
    await usuario.type(within(formulario).getByLabelText("Contraseña actual"), "clave-actual-123");
    await usuario.type(within(formulario).getByLabelText("Contraseña nueva"), "corta");
    await usuario.type(within(formulario).getByLabelText("Repite la contraseña nueva"), "corta");
    await usuario.click(within(formulario).getByRole("button", { name: "Cambiar contraseña" }));
    expect(within(formulario).getByText("La nueva contraseña debe tener al menos 10 caracteres y ser distinta.")).toBeInTheDocument();
  });
});
