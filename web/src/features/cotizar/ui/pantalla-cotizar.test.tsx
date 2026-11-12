import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import type { CotizarRepository, PedidoCotizacion } from "../domain/cotizar";
import { crearCotizarMemoria } from "../infrastructure/cotizar-memoria";
import { COTIZACION_MOAB, FORMULARIO_EJEMPLO, LUGARES_EJEMPLO, SOLO_GOOGLE } from "../infrastructure/ejemplo-moab";
import { PantallaCotizar } from "./pantalla-cotizar";

const navegar = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: navegar, replace: navegar }),
  usePathname: () => "/cotizar",
}));

const LUGARES = [
  ...LUGARES_EJEMPLO.moab!.resultados,
  ...LUGARES_EJEMPLO.miami!.resultados,
  ...LUGARES_EJEMPLO.slc!.resultados,
  ...LUGARES_EJEMPLO["grand junction"]!.resultados,
];

function memoria(cambios: Partial<CotizarRepository> = {}): CotizarRepository {
  return {
    ...crearCotizarMemoria({
      formulario: FORMULARIO_EJEMPLO,
      lugares: LUGARES,
      lugaresGoogle: [SOLO_GOOGLE],
      guardadas: [COTIZACION_MOAB],
    }),
    ...cambios,
  };
}

beforeEach(() => {
  navegar.mockReset();
  window.sessionStorage.clear();
});

async function elegirLugar(usuario: ReturnType<typeof userEvent.setup>, campo: string, texto: string) {
  const entrada = screen.getByRole("combobox", { name: campo });
  await usuario.clear(entrada);
  await usuario.type(entrada, texto);
  await screen.findByRole("listbox", { name: `Sugerencias para ${campo.toLowerCase()}` }, { timeout: 2000 });
  await usuario.keyboard("{ArrowDown}{Enter}");
}

describe("Cotizar un viaje", () => {
  it("mientras carga muestra un esqueleto y luego el formulario con quien viaja", async () => {
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria() });
    expect(screen.getByRole("heading", { level: 1, name: "Cotizar un viaje" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Preparando el formulario…");
    expect(await screen.findByText("Andrés Molina (tú)")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Proyecto" })).toBeInTheDocument();
  });

  it("si el formulario no carga, lo dice y deja reintentar", async () => {
    const formulario = vi
      .fn<CotizarRepository["formulario"]>()
      .mockRejectedValueOnce(new ErrorDeAplicacion("servidor", { idPeticion: "abc123" }))
      .mockResolvedValueOnce(FORMULARIO_EJEMPLO);
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria({ formulario }) });
    expect(await screen.findByText("Referencia: abc123")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("button", { name: "Buscar y comparar" })).toBeInTheDocument();
  });

  it("el campo de lugar funciona con teclado: elige Moab, quita un aeropuerto y agrega otro por código", async () => {
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria() });
    await screen.findByRole("button", { name: "Buscar y comparar" });
    await elegirLugar(usuario, "Destino", "moab");

    const destino = screen.getByRole("combobox", { name: "Destino" });
    expect(destino).toHaveValue("Moab, Utah, Estados Unidos");
    expect(destino).toHaveAttribute("aria-expanded", "false");
    const lista = screen.getByRole("list", { name: "Aeropuertos que se comparan en el destino" });
    expect(within(lista).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringMatching(/^CNY.*27 km, menos de 1 h por carretera/),
      expect.stringMatching(/^GJT.*108 km, unas 2 h por carretera/),
      expect.stringMatching(/^SLC.*322 km, unas 6 h por carretera/),
    ]);
    expect(screen.getByText("Se comparan 3 aeropuertos en una sola búsqueda.")).toBeInTheDocument();

    await usuario.click(within(lista).getByRole("button", { name: "Quitar GJT" }));
    expect(within(lista).getAllByRole("listitem")).toHaveLength(2);

    const agregar = screen.getByRole("combobox", { name: "Agregar otro aeropuerto al destino" });
    await usuario.type(agregar, "grand junction");
    // Enter con la lista en camino no envía el formulario: elige en cuanto llega
    await usuario.keyboard("{Enter}");
    expect(await within(lista).findByText("GJT", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(navegar).not.toHaveBeenCalled();
  });

  it("Escape cierra la lista y lo que solo trae Google se marca como tal", async () => {
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria() });
    await screen.findByRole("button", { name: "Buscar y comparar" });
    const destino = screen.getByRole("combobox", { name: "Destino" });
    await usuario.type(destino, "bryce");
    const lista = await screen.findByRole("listbox", { name: "Sugerencias para destino" }, { timeout: 2000 });
    const opcion = await within(lista).findByRole("option", { name: /Bryce Canyon City/ }, { timeout: 2000 });
    expect(within(opcion).getByText("Google")).toBeInTheDocument();
    await usuario.keyboard("{Escape}");
    expect(destino).toHaveAttribute("aria-expanded", "false");
  });

  it("enviar sin datos marca cada campo con cómo corregirlo y no busca nada", async () => {
    const cotizar = vi.fn<CotizarRepository["cotizar"]>();
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria({ cotizar }) });
    await screen.findByRole("button", { name: "Buscar y comparar" });
    await usuario.click(screen.getByRole("button", { name: "Buscar y comparar" }));
    expect(await screen.findByText(/Escribe de dónde sale/)).toBeInTheDocument();
    expect(screen.getByText(/Escribe a dónde va/)).toBeInTheDocument();
    expect(screen.getByText("Elige la fecha de ida.")).toBeInTheDocument();
    expect(screen.getByText("Elige el proyecto del viaje.")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Proyecto" })).toHaveFocus();   // el primero que falta
    expect(cotizar).not.toHaveBeenCalled();
  });

  it("con el caso de ejemplo anuncia la búsqueda en 3 aeropuertos y abre la comparación", async () => {
    let terminar: (valor: typeof COTIZACION_MOAB) => void = () => {};
    const cotizar = vi.fn<(p: PedidoCotizacion) => Promise<typeof COTIZACION_MOAB>>(
      () => new Promise((resolver) => (terminar = resolver)),
    );
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria({ cotizar }) });
    await screen.findByRole("button", { name: "Buscar y comparar" });
    await usuario.click(screen.getByRole("button", { name: "Usar el caso de ejemplo" }));
    await usuario.click(screen.getByRole("button", { name: "Buscar y comparar" }));

    expect(await screen.findByText("Buscando vuelos en 3 aeropuertos (MIA → CNY, GJT, SLC)…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Buscando…" })).toBeDisabled();
    expect(cotizar.mock.calls[0]![0]).toMatchObject({
      proyecto_id: 1,
      viajero_id: null,
      destino: { aeropuertos: ["CNY", "GJT", "SLC"] },
      ida: "2026-12-08",
      hora_limite: "18:00",
    });
    terminar(COTIZACION_MOAB);
    await waitFor(() => expect(navegar).toHaveBeenCalledWith(`/cotizar/${COTIZACION_MOAB.id}`));
  });

  it("un dato que el servidor no reconoce queda en su campo y lo escrito se conserva", async () => {
    const cotizar = vi.fn<CotizarRepository["cotizar"]>().mockRejectedValue(
      new ErrorDeAplicacion("validacion", {
        mensaje: "Hay datos que no son válidos.",
        campos: { destino: "No reconozco \"ZZZ\". Elige una ciudad de la lista." },
        idPeticion: "r9",
      }),
    );
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria({ cotizar }) });
    await screen.findByRole("button", { name: "Buscar y comparar" });
    await usuario.click(screen.getByRole("button", { name: "Usar el caso de ejemplo" }));
    await usuario.click(screen.getByRole("button", { name: "Buscar y comparar" }));
    expect(await screen.findByText(/No reconozco "ZZZ"/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Destino" })).toHaveValue("Moab, Utah, Estados Unidos");
    expect(screen.getByLabelText("Ida")).toHaveValue("2026-12-08");
    expect(navegar).not.toHaveBeenCalled();
  });

  it("si el tope del día se alcanzó, lo explica en lenguaje claro", async () => {
    const cotizar = vi.fn<CotizarRepository["cotizar"]>().mockRejectedValue(new ErrorDeAplicacion("demasiados_intentos"));
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizar />, { cotizar: memoria({ cotizar }) });
    await screen.findByRole("button", { name: "Buscar y comparar" });
    await usuario.click(screen.getByRole("button", { name: "Usar el caso de ejemplo" }));
    await usuario.click(screen.getByRole("button", { name: "Buscar y comparar" }));
    expect(await screen.findByText(/tope de cotizaciones nuevas de hoy/)).toBeInTheDocument();
  });
});
