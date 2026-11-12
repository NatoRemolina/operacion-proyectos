import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { formatearDinero } from "@/shared/ui/formato";
import { renderizarConFuente } from "@/test/renderizar";
import type { Cotizacion, CotizarRepository } from "../domain/cotizar";
import { crearCotizarMemoria } from "../infrastructure/cotizar-memoria";
import { COTIZACION_MOAB, FORMULARIO_EJEMPLO } from "../infrastructure/ejemplo-moab";
import { PantallaCotizacion } from "./pantalla-cotizacion";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/cotizar/12",
}));

/** El detalle y la decisión responden como la API, en memoria. */
function repositorio(c: Cotizacion, cambios: Partial<CotizarRepository> = {}): CotizarRepository {
  return { ...crearCotizarMemoria({ formulario: FORMULARIO_EJEMPLO, existentes: [c] }), ...cambios };
}

/** El formato compartido puede usar espacios no separables; Testing Library los normaliza en el texto del nodo. */
function dinero(valor: string | null): string {
  return formatearDinero(valor).replace(/\s+/g, " ");
}

const RECOMENDADA = COTIZACION_MOAB.vuelos[0]!;
const OTRA = COTIZACION_MOAB.vuelos[1]!;

describe("Comparación de una cotización", () => {
  it("mientras carga muestra un esqueleto", () => {
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { obtener: () => new Promise(() => {}) }) });
    expect(screen.getByRole("status")).toHaveTextContent("Cargando la cotización…");
  });

  it("si falla, lo dice con su referencia y deja reintentar", async () => {
    const obtener = vi
      .fn<CotizarRepository["obtener"]>()
      .mockRejectedValueOnce(new ErrorDeAplicacion("servidor", { idPeticion: "abc123" }))
      .mockResolvedValueOnce(COTIZACION_MOAB);
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { obtener }) });
    expect(await screen.findByText("Referencia: abc123")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("heading", { level: 1, name: "MIA → Moab" })).toBeInTheDocument();
  });

  it("una cotización ajena o inexistente lleva a cotizar de nuevo", async () => {
    const obtener = vi.fn<CotizarRepository["obtener"]>().mockRejectedValue(new ErrorDeAplicacion("no_encontrado"));
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { obtener }) });
    expect(await screen.findByText("No encontramos esta cotización")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cotizar un viaje" })).toHaveAttribute("href", "/cotizar");
  });

  it("sin datos para esa combinación lo explica y sugiere el caso guardado", async () => {
    const vacia: Cotizacion = { ...COTIZACION_MOAB, vuelos: [], descartados: [], hoteles: [], recomendada_id: null,
      mas_barata_id: null, origen_dato: "fallida", aviso: null, puede_decidir: false };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(vacia) });
    expect(await screen.findByText("Sin datos para esa combinación")).toBeInTheDocument();
    expect(screen.getByText(/Miami → Moab del 8 al 11 de diciembre de 2026/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cotizar con otros datos" })).toHaveAttribute("href", "/cotizar");
    expect(screen.queryByRole("button", { name: /Guardar decisión/ })).not.toBeInTheDocument();
  });

  it("compara por costo total esperado: recomendada primero, la más barata marcada, origen del dato y descartes", async () => {
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB) });
    expect(await screen.findByRole("heading", { level: 1, name: "MIA → Moab" })).toBeInTheDocument();
    expect(screen.getAllByText("Precios guardados").length).toBeGreaterThan(0);

    const opciones = screen.getAllByRole("radio", { name: /costo total esperado/ });
    expect(opciones).toHaveLength(COTIZACION_MOAB.vuelos.length);
    expect(opciones[0]).toHaveAccessibleName(expect.stringContaining("UA 1047"));
    expect(opciones.every((o) => !(o as HTMLInputElement).checked)).toBe(true);   // nada llega preseleccionado

    const recomendada = screen.getByRole("group", { name: /UA 1047 \+ UA 6077/ });
    expect(within(recomendada).getByText("Recomendada")).toBeInTheDocument();
    expect(within(recomendada).getByText(dinero(RECOMENDADA.costo_total_usd))).toBeInTheDocument();
    const barata = screen.getByRole("group", { name: /F9 1279/ });
    expect(within(barata).getByText("La más barata")).toBeInTheDocument();
    expect(within(barata).getByText(dinero(OTRA.precio_usd))).toBeInTheDocument();

    await usuario.click(within(barata).getByText("Ver desglose"));
    expect(within(barata).getByText(/Combustible y peajes desde SLC/)).toBeInTheDocument();
    expect(within(barata).getByText(dinero("-24.90"))).toBeInTheDocument();

    const descartes = screen.getByText(`Vuelos descartados (${COTIZACION_MOAB.descartados.length})`);
    await usuario.click(descartes);
    expect(screen.getByText("Con el traslado llega a las 20:10, después de la hora límite.")).toBeInTheDocument();
    expect(screen.getByText(/lo más barato no es lo mejor/i)).toBeInTheDocument();
  });

  it("apartarse de la recomendada exige el porqué; con él nace el viaje y se enlaza", async () => {
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB) });
    await screen.findByRole("heading", { level: 1, name: "MIA → Moab" });

    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    expect(await screen.findByText("Elige uno de los vuelos para guardar la decisión.")).toBeInTheDocument();

    await usuario.click(screen.getByRole("radio", { name: /F9 1279/ }));
    expect(screen.getByLabelText(/Por qué eliges este vuelo/)).toBeRequired();
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    expect(await screen.findByText(/cuenta por qué/)).toBeInTheDocument();

    await usuario.type(screen.getByLabelText(/Por qué eliges este vuelo/), "Sale más temprano y llega con luz");
    await usuario.click(screen.getByRole("checkbox", { name: "Mejor horario" }));
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));

    const confirmacion = await screen.findByRole("heading", { name: /^Viaje V-2026-\d{4} creado, pendiente de aprobación$/ });
    expect(confirmacion).toHaveFocus();
    expect(screen.getByRole("link", { name: "Ver mis viajes" })).toHaveAttribute("href", "/viajes");
    expect(screen.getByRole("link", { name: "Cotizar otro viaje" })).toHaveAttribute("href", "/cotizar");
    expect(screen.queryByRole("button", { name: "Guardar decisión y enviar a aprobación" })).not.toBeInTheDocument();
  });

  it("quien solo puede ver la cotización no recibe botones que no puede usar", async () => {
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio({ ...COTIZACION_MOAB, puede_decidir: false }) });
    expect(await screen.findByText(/Solo lectura/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar decisión/ })).not.toBeInTheDocument();
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
  });

  it("con el viaje aprobado explica por qué la decisión ya no cambia", async () => {
    const aprobada: Cotizacion = {
      ...COTIZACION_MOAB,
      estado: "decidido",
      puede_decidir: false,
      bloqueo: "El viaje V-2026-0031 ya está aprobado: para cambiar la decisión, administración debe reabrirlo.",
      decision: { id: 3, vuelo_id: RECOMENDADA.id, hotel_id: null, motivo: null, razones: [], total_usd: "980.00",
        siguio_recomendacion: true, creado: "2026-11-12T20:00:00Z" },
      viaje: { id: 31, codigo: "V-2026-0031", estado: "aprobado", estado_texto: "Aprobado" },
    };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(aprobada) });
    expect(await screen.findByText(/administración debe reabrirlo/)).toBeInTheDocument();
    expect(screen.getByText("V-2026-0031")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar decisión/ })).not.toBeInTheDocument();
  });
});
