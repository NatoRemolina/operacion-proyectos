import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { crearViajesMemoria } from "@/features/viajes/infrastructure/viajes-memoria";
import { gastoDePrueba, viajeDePrueba } from "@/test/fabricas";
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

    const lista = await screen.findByRole("list", { name: "Gastos" });
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
    expect(screen.getByRole("link", { name: "Entra de nuevo" })).toHaveAttribute("href", `/entrar?volver=${encodeURIComponent("/")}`);
  });

  it("cada gasto dice su siguiente paso", async () => {
    renderizarConFuente(<PantallaGastos />, {
      gastos: crearGastosMemoria({
        gastos: [
          gastoDePrueba({ id: 1, comercio: "Taxi", estado: "revision", estado_texto: "En revisión" }),
          gastoDePrueba({ id: 2, comercio: "Cena", estado: "rechazado", estado_texto: "Rechazado", creado: "2026-11-10T00:00:00Z" }),
        ],
      }),
    });
    const lista = await screen.findByRole("list", { name: "Gastos" });
    expect(within(lista).getByText(/Administración lo revisa/)).toBeInTheDocument();
    expect(within(lista).getByText(/Mira el motivo en el detalle/)).toBeInTheDocument();
  });

  it("se filtra por estado y por viaje, y el filtro activo se marca", async () => {
    const usuario = userEvent.setup();
    const gastos = crearGastosMemoria({
      gastos: [
        gastoDePrueba({ id: 1, comercio: "Taxi", estado: "revision", estado_texto: "En revisión" }),
        gastoDePrueba({ id: 2, comercio: "Hotel", estado: "aprobado_auto", estado_texto: "Aprobado", viaje: { id: 9, codigo: "V-2026-0009" } }),
      ],
    });
    const viajes = crearViajesMemoria({ viajes: [viajeDePrueba(), viajeDePrueba({ id: 9, codigo: "V-2026-0009" })] });
    renderizarConFuente(<PantallaGastos estado="revision" />, { gastos, viajes });
    const filtros = screen.getByRole("group", { name: "Filtrar por estado" });
    expect(within(filtros).getByRole("button", { name: "En revisión" })).toHaveAttribute("aria-pressed", "true");
    const lista = await screen.findByRole("list", { name: "Gastos" });
    expect(within(lista).queryByText("Hotel")).not.toBeInTheDocument();

    await usuario.click(within(filtros).getByRole("button", { name: "Todos" }));
    await usuario.selectOptions(await screen.findByLabelText("Viaje"), "9");
    expect(await within(screen.getByRole("list", { name: "Gastos" })).findByText("Hotel")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Gastos" })).queryByText("Taxi")).not.toBeInTheDocument();
  });
});

