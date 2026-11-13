import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { gastoDePrueba } from "@/test/fabricas";
import type { BuzonSimulado } from "../domain/buzon";
import { crearAdministracionMemoria } from "../infrastructure/administracion-memoria";
import { PantallaBuzon } from "./pantalla-buzon";

const BUZON: BuzonSimulado = {
  simulado: true,
  aviso: "Buzón simulado: lee los correos de ejemplo de la plataforma. No está conectado a ningún correo real.",
  mensajes: [
    { nombre: "reserva_hotel.eml", formato: "correo", remitente: "Casa do Tejo <reservas@casadotejo.test>", asunto: "Su reserva" },
    { nombre: "confirmacion_hotel.html", formato: "html", remitente: null, asunto: null },
  ],
  viajes: [
    { id: 7, codigo: "V-2026-0007", estado: "aprobado", estado_texto: "Aprobado", titular: "Andrés Molina", origen: "MIA", destino: "LAS", ida: "2026-12-08", regreso: "2026-12-11" },
  ],
};

function montar({ buzon = BUZON, leer }: { buzon?: BuzonSimulado | null; leer?: ReturnType<typeof crearAdministracionMemoria>["leerBuzon"] } = {}) {
  const memoria = crearAdministracionMemoria({ buzon });
  const administracion = {
    ...memoria,
    leerBuzon: vi.fn(
      leer ??
        (async () => ({
          leidos: [gastoDePrueba({ id: 41, comercio: "Casa do Tejo", estado: "revision", estado_texto: "En revisión" })],
          errores: [],
        })),
    ),
  };
  renderizarConFuente(<PantallaBuzon />, { administracion, permiso: "admin" });
  return { leer: administracion.leerBuzon };
}

describe("Buzón de correo (simulado)", () => {
  it("dice claramente que es simulado", async () => {
    montar();
    expect(await screen.findByRole("heading", { level: 1, name: /Buzón de correo/ })).toHaveTextContent("simulado");
    expect(await screen.findByText(/No está conectado a ningún correo real/)).toBeInTheDocument();
  });

  it("lista los correos con remitente y asunto, todos marcados", async () => {
    montar();
    const correo = await screen.findByRole("checkbox", { name: /reserva_hotel\.eml/ });
    expect(correo).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /confirmacion_hotel\.html/ })).toBeChecked();
    expect(screen.getByText(/Casa do Tejo <reservas@casadotejo.test>/)).toBeInTheDocument();
    expect(screen.getByText(/Su reserva/)).toBeInTheDocument();
  });

  it("lee los elegidos al viaje elegido y muestra los gastos creados con su estado", async () => {
    const usuario = userEvent.setup();
    const { leer } = montar();
    await usuario.click(await screen.findByRole("checkbox", { name: /confirmacion_hotel\.html/ }));
    await usuario.selectOptions(screen.getByLabelText("Viaje al que se cargan"), "7");
    await usuario.click(screen.getByRole("button", { name: "Leer el buzón (simulado)" }));
    expect(leer).toHaveBeenCalledWith({ nombres: ["reserva_hotel.eml"], viajeId: 7 });
    const resultado = await screen.findByRole("region", { name: "Resultado de la lectura" });
    expect(within(resultado).getByRole("link", { name: /Casa do Tejo/ })).toHaveAttribute("href", "/gastos/41");
    expect(within(resultado).getByText("En revisión")).toBeInTheDocument();
  });

  it("sin correos elegidos no lee y lo dice", async () => {
    const usuario = userEvent.setup();
    const { leer } = montar();
    await usuario.click(await screen.findByRole("checkbox", { name: /reserva_hotel\.eml/ }));
    await usuario.click(screen.getByRole("checkbox", { name: /confirmacion_hotel\.html/ }));
    await usuario.click(screen.getByRole("button", { name: "Leer el buzón (simulado)" }));
    expect(leer).not.toHaveBeenCalled();
    expect(screen.getByText("Elige al menos un correo.")).toBeInTheDocument();
  });

  it("los correos que no se pudieron leer se muestran con su motivo", async () => {
    const usuario = userEvent.setup();
    montar({ leer: async () => ({ leidos: [], errores: [{ nombre: "reserva_hotel.eml", mensaje: "El archivo está vacío." }] }) });
    await usuario.click(await screen.findByRole("button", { name: "Leer el buzón (simulado)" }));
    const resultado = await screen.findByRole("region", { name: "Resultado de la lectura" });
    expect(within(resultado).getByText(/El archivo está vacío/)).toBeInTheDocument();
  });

  it("si falla la lectura, lo dice", async () => {
    const usuario = userEvent.setup();
    montar({
      leer: async () => {
        throw new ErrorDeAplicacion("validacion", { mensaje: "Hay datos que no son válidos.", campos: { viaje_id: "Ese viaje no existe." } });
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Leer el buzón (simulado)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ese viaje no existe.");
  });

  it("quien no es de administración no lo ve", async () => {
    montar({ buzon: null });
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
  });

  it("las migas lo cuelgan de Gastos", async () => {
    montar();
    const migas = within(await screen.findByRole("navigation", { name: "Migas de pan" }));
    expect(migas.getByRole("link", { name: "Gastos" })).toHaveAttribute("href", "/gastos");
  });
});
