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
    expect(screen.getAllByText("Cargando la cotización…").length).toBeGreaterThan(0);
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
    // el presupuesto que aprueba administración: sin riesgo de cambio ni millas
    const presupuesto = (Number(OTRA.desglose.precio_usd) + Number(OTRA.desglose.equipaje_usd) +
      Number(OTRA.desglose.traslado_usd) + Number(COTIZACION_MOAB.carro_usd)).toFixed(2);
    expect(screen.getByText("Presupuesto para aprobar:").nextElementSibling).toHaveTextContent(dinero(presupuesto));
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
        siguio_recomendacion: true, creado: "2026-11-12T20:00:00Z", aviso: null },
      viaje: { id: 31, codigo: "V-2026-0031", estado: "aprobado", estado_texto: "Aprobado", presupuesto_usd: "1240.58" },
    };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(aprobada) });
    expect(await screen.findByText(/administración debe reabrirlo/)).toBeInTheDocument();
    expect(screen.getByText("V-2026-0031")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar decisión/ })).not.toBeInTheDocument();
  });

  it("si todos los vuelos quedan descartados, se elige uno con su razón y el porqué, o se cotiza con otros datos", async () => {
    const descartados: Cotizacion = { ...COTIZACION_MOAB, vuelos: [], recomendada_id: null, mas_barata_id: null, aviso: null };
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(descartados) });
    expect(await screen.findByText("Ningún vuelo cumple")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Cotizar con otros datos" })[0]).toHaveAttribute("href", "/cotizar");
    const opciones = screen.getAllByRole("radio", { name: /costo total esperado/ });
    expect(opciones).toHaveLength(COTIZACION_MOAB.descartados.length);
    // la razón se ve sin abrir nada
    expect(screen.getByText("Con el traslado llega a las 20:10, después de la hora límite.")).toBeVisible();
    await usuario.click(opciones[1]!);
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    expect(await screen.findByText(/cuenta por qué/)).toBeInTheDocument();
    await usuario.type(screen.getByLabelText(/Por qué eliges este vuelo/), "La grabación puede empezar más tarde");
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    expect(await screen.findByRole("heading", { name: /^Viaje V-2026-\d{4} creado, pendiente de aprobación$/ })).toBeInTheDocument();
  });

  it("lo escrito en la decisión se conserva si hay que volver a entrar y se borra al decidir", async () => {
    window.sessionStorage.clear();
    const usuario = userEvent.setup();
    const repo = repositorio(COTIZACION_MOAB);
    const primera = renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repo });
    await screen.findByRole("heading", { level: 1, name: "MIA → Moab" });
    await usuario.click(screen.getByRole("radio", { name: /F9 1279/ }));
    await usuario.type(screen.getByLabelText(/Por qué eliges este vuelo/), "Sale más temprano");
    await usuario.click(screen.getByRole("checkbox", { name: "Mejor horario" }));
    primera.unmount();

    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repo });
    await screen.findByRole("heading", { level: 1, name: "MIA → Moab" });
    expect(screen.getByRole("radio", { name: /F9 1279/ })).toBeChecked();
    expect(screen.getByLabelText(/Por qué eliges este vuelo/)).toHaveValue("Sale más temprano");
    expect(await screen.findByRole("checkbox", { name: "Mejor horario" })).toBeChecked();
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    await screen.findByRole("heading", { name: /creado, pendiente de aprobación$/ });
    expect(Object.keys(window.sessionStorage).filter((k) => k.startsWith("cotizar-decision-"))).toEqual([]);
  });

  it("si la decisión se tomó sin consultar en vivo por el tope del día, lo dice", async () => {
    const decidida: Cotizacion = {
      ...COTIZACION_MOAB,
      estado: "decidido",
      decision: { id: 3, vuelo_id: RECOMENDADA.id, hotel_id: null, motivo: null, razones: [], total_usd: "980.00",
        siguio_recomendacion: true, creado: "2026-11-12T20:00:00Z",
        aviso: "Se alcanzó el tope de decisiones con consulta en vivo de hoy: el regreso y la tarifa salen de lo guardado o quedan supuestos." },
      viaje: { id: 31, codigo: "V-2026-0031", estado: "pendiente_aprobacion", estado_texto: "Pendiente de aprobación", presupuesto_usd: "1240.58" },
    };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(decidida) });
    expect(await screen.findByText(/Se alcanzó el tope de decisiones con consulta en vivo/)).toBeInTheDocument();
  });

  it("lo que se mueve anima solo escala, giro u opacidad y respeta el movimiento reducido", async () => {
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB) });
    await screen.findByRole("heading", { level: 1, name: "MIA → Moab" });
    const guardar = screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" });
    expect(guardar.className).toMatch(/se-mueve/);
    expect(guardar.className).toMatch(/motion-safe:active:scale-\[0\.97\]/);
    expect(guardar.className).toMatch(/active:transition-\[[^\]]*scale\]/);
    expect(guardar.className).toMatch(/active:duration-100/);
    const flecha = screen.getAllByRole("button", { name: /Ver desglose/ })[0]!.querySelector("[aria-hidden]")!;
    expect(flecha.className).toMatch(/se-mueve/);
    expect(flecha.className).toMatch(/transition-\[rotate\]/);
    expect(flecha.className).toMatch(/motion-reduce:transition-none/);
  });

  it("sin vuelo recomendado, los textos no hablan de «la recomendada»", async () => {
    const descartados: Cotizacion = { ...COTIZACION_MOAB, vuelos: [], recomendada_id: null, mas_barata_id: null, aviso: null };
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(descartados) });
    const opciones = await screen.findAllByRole("radio", { name: /costo total esperado/ });
    await usuario.click(opciones[0]!);
    const decision = screen.getByRole("region", { name: "Tu decisión" });
    expect(decision.textContent).not.toMatch(/recomendad/);
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    expect(await screen.findByText(/Ningún vuelo cumple las condiciones: cuenta por qué/)).toBeInTheDocument();
    expect(screen.queryByText(/distinto al recomendado/)).not.toBeInTheDocument();
  });

  it("mientras guarda la decisión dice qué está haciendo", async () => {
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizacion id={12} />, {
      cotizar: repositorio(COTIZACION_MOAB, { decidir: () => new Promise(() => {}) }),
    });
    const opciones = await screen.findAllByRole("radio", { name: /costo total esperado/ });
    await usuario.click(opciones[0]!);
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    expect(await screen.findByRole("button", { name: "Consultando el regreso y la tarifa del vuelo…" })).toBeDisabled();
    expect(screen.getByText(/Puede tardar unos 20 segundos/)).toBeInTheDocument();
  });

  it("después de decidir, «Ningún vuelo cumple» ya no invita a elegir un vuelo", async () => {
    const decidida: Cotizacion = {
      ...COTIZACION_MOAB,
      vuelos: [],
      recomendada_id: null,
      mas_barata_id: null,
      aviso: null,
      decision: {
        id: 3,
        vuelo_id: COTIZACION_MOAB.descartados[0]!.id,
        hotel_id: null,
        motivo: "La grabación puede empezar más tarde",
        razones: [],
        total_usd: "900.00",
        siguio_recomendacion: false,
        creado: "2026-11-12T10:00:00Z",
        aviso: null,
      },
      viaje: { id: 4, codigo: "V-2026-0004", estado: "pendiente_aprobacion", estado_texto: "Pendiente de aprobación", presupuesto_usd: "1200.00" },
    };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(decidida) });
    expect(await screen.findByText("Ningún vuelo cumple")).toBeInTheDocument();
    expect(screen.queryByText(/Puedes elegir uno abajo/)).not.toBeInTheDocument();
    expect(screen.getByText(/Ya decidiste con un vuelo descartado/)).toBeInTheDocument();
  });
});

