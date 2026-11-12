import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { gastoDePrueba } from "@/test/fabricas";
import type { GastosRepository } from "../domain/gastos";
import { crearGastosMemoria } from "../infrastructure/gastos-memoria";
import { PantallaGastos } from "./pantalla-gastos";

/**
 * ARCH-01: la misma pantalla, sin tocar su código, funciona con otra fuente de datos.
 * Solo cambia el repositorio que se inyecta.
 */
describe("Mis gastos con fuentes intercambiables (ARCH-01)", () => {
  it("muestra los gastos del adaptador en memoria", async () => {
    const gastos = crearGastosMemoria({
      gastos: [
        gastoDePrueba({ id: 1, comercio: "Café del centro", creado: "2026-11-10T10:00:00Z" }),
        gastoDePrueba({
          id: 2,
          comercio: "Hotel Brickell",
          total: "780.00",
          estado: "aprobado_auto",
          estado_texto: "Aprobado",
          viaje: null,
          creado: "2026-11-11T10:00:00Z",
        }),
      ],
    });

    renderizarConFuente(<PantallaGastos />, { gastos });

    const lista = await screen.findByRole("list", { name: "Mis gastos" });
    const tarjetas = within(lista).getAllByRole("listitem");
    expect(tarjetas).toHaveLength(2);
    // Más reciente primero, con estado en texto y viaje legibles.
    expect(within(tarjetas[0]!).getByRole("link", { name: "Hotel Brickell" })).toHaveAttribute(
      "href",
      "/gastos/2",
    );
    expect(within(tarjetas[0]!).getByText("Aprobado")).toBeInTheDocument();
    expect(within(tarjetas[0]!).getByText(/Sin viaje asignado/)).toBeInTheDocument();
    expect(within(tarjetas[1]!).getByText("En revisión")).toBeInTheDocument();
    expect(within(tarjetas[1]!).getByText(/Viaje V-2026-0007/)).toBeInTheDocument();
  });

  it("muestra lo mismo con una implementación escrita a mano del puerto", async () => {
    const otraFuente: GastosRepository = {
      listar: async () => ({
        items: [gastoDePrueba({ comercio: "Comercio de otra fuente" })],
        siguiente: null,
      }),
      obtener: async () => gastoDePrueba(),
      enviar: async () => gastoDePrueba(),
      urlOriginal: () => null,
      justificar: () => Promise.resolve(gastoDePrueba()),
    };

    renderizarConFuente(<PantallaGastos />, { gastos: otraFuente });

    expect(await screen.findByRole("link", { name: "Comercio de otra fuente" })).toBeInTheDocument();
  });

  it("sin gastos invita a cargar el primero", async () => {
    renderizarConFuente(<PantallaGastos />, { gastos: crearGastosMemoria({}) });
    expect(await screen.findByText(/Aún no tienes gastos/)).toBeInTheDocument();
  });

  it("con la sesión vencida ofrece volver a entrar", async () => {
    const vencida: GastosRepository = {
      listar: () => Promise.reject(new ErrorDeAplicacion("sesion_vencida")),
      obtener: () => Promise.reject(new ErrorDeAplicacion("sesion_vencida")),
      enviar: () => Promise.reject(new ErrorDeAplicacion("sesion_vencida")),
      urlOriginal: () => null,
      justificar: () => Promise.resolve(gastoDePrueba()),
    };
    renderizarConFuente(<PantallaGastos />, { gastos: vencida });
    expect(await screen.findByRole("alert")).toHaveTextContent("Tu sesión venció");
    expect(screen.getByRole("link", { name: "Entra de nuevo" })).toHaveAttribute("href", "/entrar");
  });
});
