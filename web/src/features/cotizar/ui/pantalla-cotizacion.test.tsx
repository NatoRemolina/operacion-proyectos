import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { formatearDinero } from "@/shared/ui/formato";
import { renderizarConFuente } from "@/test/renderizar";
import type { Cotizacion, CotizarRepository, OpcionHotel } from "../domain/cotizar";
import { crearCotizarMemoria } from "../infrastructure/cotizar-memoria";
import { ANALISIS_EJEMPLO } from "../infrastructure/ejemplo-analisis";
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

  it("la decisión guardada muestra la evidencia que guardó el trabajador (pieza 5)", async () => {
    const decidida: Cotizacion = {
      ...COTIZACION_MOAB,
      estado: "decidido",
      decision: { id: 3, vuelo_id: RECOMENDADA.id, hotel_id: null, motivo: null, razones: [], total_usd: "980.00",
        siguio_recomendacion: true, creado: "2026-11-12T20:00:00Z", aviso: null },
      viaje: { id: 31, codigo: "V-2026-0031", estado: "pendiente_aprobacion", estado_texto: "Pendiente de aprobación",
        presupuesto_usd: "1240.58" },
    };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(decidida) });
    const evidencia = await screen.findByRole("region", { name: /Evidencia guardada a las \d{2}:\d{2}/ });
    expect(within(evidencia).getAllByRole("link", { name: /Captura de página completa/ }).length).toBeGreaterThan(0);
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
    // en el celular, la tabla no parte los importes ni las palabras («USD 415,0 / 0», «Supue / sto»)
    const tabla = within(barata).getByRole("table", { name: /Desglose del costo total esperado/ });
    expect(tabla).toHaveClass("[overflow-wrap:normal]");
    for (const fila of within(tabla).getAllByRole("row").slice(1)) {
      const celdas = within(fila).getAllByRole("cell");
      for (const celda of celdas.slice(-2)) expect(celda).toHaveClass("whitespace-nowrap");
    }

    const descartes = screen.getByText(`Vuelos descartados (${COTIZACION_MOAB.descartados.length})`);
    await usuario.click(descartes);
    expect(screen.getByText("Con el traslado llega a las 20:10, después de la hora límite.")).toBeInTheDocument();
    expect(screen.getByText(/lo más barato no es lo mejor/i)).toBeInTheDocument();
  });

  it("la más barata del resumen es la que sirve; si una descartada es más barata, no se la llama «del buscador»", async () => {
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB) });
    expect(await screen.findByText("La más barata del buscador")).toBeInTheDocument();

    const [descartada] = COTIZACION_MOAB.descartados;
    const conDescartadaBarata: Cotizacion = { ...COTIZACION_MOAB, id: 13, descartados: [{ ...descartada!, precio_usd: "279.00" }] };
    renderizarConFuente(<PantallaCotizacion id={13} />, { cotizar: repositorio(conDescartadaBarata) });
    expect(await screen.findByText("La más barata que sirve")).toBeInTheDocument();
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
    // la solicitud de compra nace con la decisión y la persona ve su estado
    expect(screen.getByText("Compra del tiquete:").nextElementSibling).toHaveTextContent("Solicitud de compra enviada");
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
    expect(Object.keys(window.sessionStorage).filter((k) => k.startsWith("borrador:decision:"))).toEqual([]);
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
    // La respuesta al presionar es la del sistema compartido: escala 0,97 en 100 ms, sin escala con movimiento reducido
    expect(guardar.className).toMatch(/se-mueve/);
    expect(guardar.className).toMatch(/active:scale-97/);
    expect(guardar.className).toMatch(/duration-100/);
    const flecha = screen.getAllByRole("link", { name: /Ver desglose/ })[0]!.querySelector("[aria-hidden]")!;
    // La flecha conserva el giro (indica si está abierto); con movimiento reducido cambia sin animación
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

  it("al decidir, un aviso emergente confirma el viaje creado", async () => {
    const usuario = userEvent.setup();
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB) });
    const opciones = await screen.findAllByRole("radio", { name: /costo total esperado/ });
    await usuario.click(opciones[0]!);
    await usuario.click(screen.getByRole("button", { name: "Guardar decisión y enviar a aprobación" }));
    const avisos = screen.getByRole("status", { name: "Avisos" });
    expect(await within(avisos).findByText(/^Viaje V-2026-\d{4} creado, pendiente de aprobación\.$/)).toBeInTheDocument();
  });

  it("los hoteles se ordenan por costo total con la fidelización: recomendado, el más barato, descartes y total del viaje", async () => {
    const usuario = userEvent.setup();
    const tru: OpcionHotel = {
      id: 90, nombre: "Tru by Hilton Moab", noche_usd: "81.00", total_usd: "243.00", costo_total_usd: "219.31",
      lineas: [
        { concepto: "Tarifa total (3 noches)", valor_usd: "243.00", origen: "buscador", tipo: "tarifa" },
        { concepto: "Tarifa de miembro (−5 %)", valor_usd: "-12.15", origen: "supuesto", tipo: "tarifa_miembro" },
        { concepto: "Puntos del programa (10 por USD a 0.005 USD)", valor_usd: "-11.54", origen: "supuesto", tipo: "puntos" },
      ],
      avisos: ["Acumula solo con reserva directa."], calificacion: 4.1, clase: 3, programa: "Hilton Honors", socio: true,
      membresia_de_ejemplo: true, descartado: null, origen_dato: "guardado", recomendada: true, mas_barata: false,
      fuente_url: "https://www.google.com/travel/search?q=Tru%20by%20Hilton%20Moab%2C%20Moab%20from%202026-12-08%20to%202026-12-11",
    };
    const independiente: OpcionHotel = {
      ...tru, id: 91, nombre: "Independiente Moab", noche_usd: "75.00", total_usd: "225.00", costo_total_usd: "225.00",
      lineas: [{ concepto: "Tarifa total (3 noches)", valor_usd: "225.00", origen: "buscador", tipo: "tarifa" }],
      avisos: [], programa: null, socio: false, membresia_de_ejemplo: false, recomendada: false, mas_barata: true,
    };
    const malo: OpcionHotel = {
      ...independiente, id: 92, nombre: "Motel Barato", total_usd: "150.00", costo_total_usd: "150.00", calificacion: 3.2,
      mas_barata: false, descartado: "Calificación 3.2, por debajo del mínimo de 3.5.",
    };
    const conHoteles: Cotizacion = {
      ...COTIZACION_MOAB, hoteles: [tru, independiente], hoteles_descartados: [malo], hotel_recomendado_id: 90,
      vuelos: COTIZACION_MOAB.vuelos.map((v, i) => (i === 0 ? { ...v, total_con_hotel_usd: "999.31" } : v)),
    };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(conHoteles) });
    const recomendada = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    expect(within(recomendada).getByText(/Total con el hotel recomendado/)).toHaveTextContent(dinero("999.31"));

    const hoteles = screen.getByRole("group", { name: "Hotel (opcional)" });
    const opciones = within(hoteles).getAllByRole("radio");
    expect(opciones).toHaveLength(3);   // sin hotel, Tru y el independiente; el descartado no se elige
    // el nombre accesible de la opción es solo el hotel y su costo total; distintivos y avisos quedan como descripción
    const radioTru = within(hoteles).getByRole("radio", { name: `Tru by Hilton Moab, costo total ${dinero("219.31")}` });
    expect(radioTru).toHaveAccessibleDescription(/Recomendado.*Hilton Honors · socio.*Dato de ejemplo/);   // membresía inventada
    const radioIndependiente = within(hoteles).getByRole("radio", { name: `Independiente Moab, costo total ${dinero("225.00")}` });
    expect(radioIndependiente).toHaveAccessibleDescription(/El más barato/);
    const filaTru = radioTru.closest("li")!;
    expect(within(filaTru).getByText(dinero("219.31"))).toBeInTheDocument();
    // el desglose plegable no está dentro del label: abrirlo no elige el hotel
    const resumen = within(filaTru).getByText("Ver desglose");
    expect(resumen.closest("label")).toBeNull();
    await usuario.click(resumen);
    expect(within(filaTru).getByText("Tarifa de miembro (−5 %)")).toBeVisible();
    expect(radioTru).not.toBeChecked();
    expect(screen.getByText("Motel Barato")).toBeInTheDocument();
    expect(screen.getByText("Calificación 3.2, por debajo del mínimo de 3.5.")).toBeInTheDocument();
  });

  it("enlaza a la búsqueda en Google Flights y Google Hotels y deja el rastro de cada clic", async () => {
    const usuario = userEvent.setup();
    const registrarFuente = vi.fn<CotizarRepository["registrarFuente"]>().mockResolvedValue(undefined);
    const hotel: OpcionHotel = {
      id: 90, nombre: "Tru by Hilton Moab", noche_usd: "81.00", total_usd: "243.00", costo_total_usd: "243.00",
      lineas: [{ concepto: "Tarifa total (3 noches)", valor_usd: "243.00", origen: "buscador", tipo: "tarifa" }],
      avisos: [], calificacion: 4.1, clase: 3, programa: null, socio: false, membresia_de_ejemplo: false, descartado: null,
      origen_dato: "guardado", recomendada: true, mas_barata: false,
      fuente_url: "https://www.google.com/travel/search?q=Tru%20by%20Hilton%20Moab",
    };
    const conHotel: Cotizacion = { ...COTIZACION_MOAB, hoteles: [hotel], hotel_recomendado_id: 90 };
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(conHotel, { registrarFuente }) });

    const vuelos = await screen.findByRole("link", { name: "Ver en Google Flights, se abre en otra pestaña" });
    expect(vuelos).toHaveAttribute("href", COTIZACION_MOAB.fuente_url);
    expect(vuelos).toHaveAttribute("target", "_blank");
    expect(vuelos).toHaveAttribute("rel", "noopener noreferrer");
    await usuario.click(vuelos);
    expect(registrarFuente).toHaveBeenLastCalledWith(12, "vuelos", undefined);

    const lista = screen.getByRole("link", { name: "Ver en Google Hotels, se abre en otra pestaña" });
    expect(lista).toHaveAttribute("href", COTIZACION_MOAB.fuente_hoteles_url);
    expect(lista).toHaveAttribute("rel", "noopener noreferrer");
    await usuario.click(lista);
    expect(registrarFuente).toHaveBeenLastCalledWith(12, "hoteles", undefined);

    const uno = screen.getByRole("link", { name: "Ver en Google Hotels (Tru by Hilton Moab), se abre en otra pestaña" });
    expect(uno).toHaveAttribute("href", hotel.fuente_url);
    expect(uno).toHaveAttribute("target", "_blank");
    await usuario.pointer({ keys: "[MouseMiddle]", target: uno });   // abrir en otra pestaña con el botón central
    expect(registrarFuente).toHaveBeenLastCalledWith(12, "hoteles", { hotelId: 90 });
    // el enlace no elige el hotel
    expect(screen.getByRole("radio", { name: `Tru by Hilton Moab, costo total ${dinero("243.00")}` })).not.toBeChecked();
  });

  it("al abrir el desglose abre la página oficial del vendedor y deja solo lo esencial: el costo y los botones a la aerolínea", async () => {
    const usuario = userEvent.setup();
    const registrarFuente = vi.fn<CotizarRepository["registrarFuente"]>().mockResolvedValue(undefined);
    let responder: (a: typeof ANALISIS_EJEMPLO) => void = () => {};
    const analizarVuelo = vi.fn<CotizarRepository["analizarVuelo"]>(
      () => new Promise((r) => { responder = r; }),
    );
    renderizarConFuente(<PantallaCotizacion id={12} />, {
      cotizar: repositorio(COTIZACION_MOAB, { registrarFuente, analizarVuelo }),
    });
    const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    const ver = within(tarjeta).getByRole("link", { name: /^Ver desglose/ });
    expect(ver).toHaveAttribute("href", RECOMENDADA.vendedor_url);
    expect(ver).toHaveAttribute("target", "_blank");
    expect(ver).toHaveAttribute("rel", "noopener noreferrer");
    await usuario.click(ver);
    expect(registrarFuente).not.toHaveBeenCalled();   // el rastro del clic al vendedor lo deja el servidor
    expect(analizarVuelo).toHaveBeenCalledWith(12, RECOMENDADA.id);
    // Google Flights queda como segundo enlace del vuelo, con su propio rastro
    const google = within(tarjeta).getByRole("link", { name: /^Ver en Google Flights \(United UA 1047/ });
    expect(google).toHaveAttribute("href", RECOMENDADA.fuente_url);
    expect(google).toHaveAttribute("rel", "noopener noreferrer");
    await usuario.click(google);
    expect(registrarFuente).toHaveBeenLastCalledWith(12, "vuelos", { vueloId: RECOMENDADA.id });
    // el desglose del buscador se ve enseguida; la lectura llega después
    expect(within(tarjeta).getByRole("table", { name: /Desglose del costo total esperado/ })).toBeInTheDocument();
    expect(within(within(tarjeta).getByRole("region", { name: "Ir a la aerolínea" })).getByRole("status"))
      .toHaveTextContent("Leyendo la página del vuelo…");
    // primera capa: lo del buscador aparece sin esperar a la lectura de la página
    const capa = within(tarjeta).getByRole("region", { name: "Opciones del buscador" });
    expect(await within(capa).findByText("Opciones de reserva del buscador")).toBeInTheDocument();
    const deBuscador = within(capa).getByRole("table", { name: "American (según el buscador)" });
    expect(within(deBuscador).getAllByRole("row").slice(1).map((f) => within(f).getByRole("rowheader").textContent))
      .toEqual(["Basic Economy", "Main Cabin", "Main Plus", "Main Select"]);
    expect(within(deBuscador).getByRole("link", { name: "Ir a American, Basic Economy, se abre en otra pestaña" })).toBeInTheDocument();
    // cada tarifa trae su «Ir a…» firmado por la API
    const datos = { ...ANALISIS_EJEMPLO.datos!, tarifas: ANALISIS_EJEMPLO.datos!.tarifas.map((t) => ({ ...t, ir_url: `/api/v1/ir/${t.nombre}` })) };
    responder({ ...ANALISIS_EJEMPLO, datos, opcion_id: RECOMENDADA.id, leido: "2026-11-13T15:10:00Z", captura_url: "/api/v1/captura.png" });
    const aerolinea = within(tarjeta).getByRole("region", { name: "Ir a la aerolínea" });
    expect(await within(aerolinea).findByText(/^Tarifas de la aerolínea leídas a las \d\d:\d\d$/)).toBeInTheDocument();
    expect(within(aerolinea).getByText("El precio de la página no es el del buscador")).toBeInTheDocument();
    // un botón por tarifa de la aerolínea, con el enlace firmado que da la API tal cual (en otra pestaña)
    const ir = within(aerolinea).getByRole("link", { name: /^Ir a American · Main Cabin/ });
    expect(ir).toHaveAttribute("href", "/api/v1/ir/Main Cabin");
    expect(ir).toHaveAttribute("target", "_blank");
    expect(ir).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(aerolinea).getAllByRole("link").map((a) => a.textContent)).toEqual(
      expect.arrayContaining([expect.stringMatching(/^Ir a American · Basic Economy/)]));
    // lo largo ya no se muestra: ni la tabla de lo leído, ni la captura, ni «Página leída»
    expect(within(tarjeta).queryByText("Tarifas y qué incluye cada una")).toBeNull();
    expect(within(tarjeta).queryByRole("table", { name: "American (según la página)" })).toBeNull();
    expect(within(tarjeta).queryByRole("img")).toBeNull();
    expect(within(tarjeta).queryByText("Página leída")).toBeNull();
    expect(within(tarjeta).queryByText("Precio por vendedor")).toBeNull();
    // el precio del buscador no cambia en la tarjeta
    expect(within(tarjeta).getAllByText(dinero(RECOMENDADA.precio_usd)).length).toBeGreaterThan(0);
    // cerrar no abre otra pestaña: es un botón
    expect(within(tarjeta).getByRole("button", { name: "Ocultar desglose" })).toBeInTheDocument();
  });

  it("con billetes separados hay un botón por tiquete, cada uno a su aerolínea (prueba 12)", async () => {
    const usuario = userEvent.setup();
    const tiquete = (vendedor: string, nombre: string, precio: number) => ({ vendedor, nombre, precio, equipaje: [], cambios: [],
      reembolso: [], otras: [], ir_url: `/api/v1/ir/${vendedor}/${nombre}` });
    const datos = { ...ANALISIS_EJEMPLO.datos!, tarifas: [tiquete("COPA", "ida", 334), tiquete("Avianca", "regreso", 323)],
      vendedores: [{ vendedor: "COPA", aerolinea: true, precio_desde: 334 }, { vendedor: "Avianca", aerolinea: true, precio_desde: 323 }] };
    const analizarVuelo = vi.fn<CotizarRepository["analizarVuelo"]>()
      .mockResolvedValue({ ...ANALISIS_EJEMPLO, datos, aviso_precio: null, leido: "2026-11-13T22:00:00Z" });
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { analizarVuelo }) });
    const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
    const aerolinea = within(tarjeta).getByRole("region", { name: "Ir a la aerolínea" });
    expect(await within(aerolinea).findByRole("link", { name: /^Ir a COPA · ida/ })).toHaveAttribute("href", "/api/v1/ir/COPA/ida");
    expect(within(aerolinea).getByRole("link", { name: /^Ir a Avianca · regreso/ })).toHaveAttribute("href", "/api/v1/ir/Avianca/regreso");
  });

  it("con billetes separados en el buscador hay un botón por tiquete con su vendedor y su precio (pieza 6)", async () => {
    const usuario = userEvent.setup();
    const tiquete = (vendedor: string, nombre: string, precio: number) => ({ vendedor, nombre, precio,
      equipaje: ["1 free carry-on"], cambios: [], reembolso: [], otras: [], ir_url: `/api/v1/ir/${vendedor}/${nombre}` });
    const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockResolvedValue({
      estado: "listo", consultado: "2026-11-14T15:00:00Z", tarifas: [tiquete("COPA", "ida", 334), tiquete("eDreams", "regreso", 316)],
      vendedores: [{ vendedor: "COPA", aerolinea: true, precio_desde: 334 }, { vendedor: "eDreams", aerolinea: false, precio_desde: 316 }],
    });
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { opcionesBuscador }) });
    const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
    const capa = within(tarjeta).getByRole("region", { name: "Opciones del buscador" });
    expect(await within(capa).findByText("Billetes separados: un tiquete por tramo, cada uno con su vendedor.")).toBeInTheDocument();
    const ida = within(capa).getByRole("link", { name: `Ir a COPA · ida ${dinero("334.00")}, se abre en otra pestaña` });
    expect(ida).toHaveAttribute("href", "/api/v1/ir/COPA/ida");
    expect(ida).toHaveAttribute("target", "_blank");
    expect(ida).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(capa).getByRole("link", { name: `Ir a eDreams · regreso ${dinero("316.00")}, se abre en otra pestaña` }))
      .toHaveAttribute("href", "/api/v1/ir/eDreams/regreso");
    // los tiquetes no se pintan como tarifas de una tabla por vendedor
    expect(within(capa).queryByRole("table")).toBeNull();
  });

  it("el desglose dice qué vuelos elegir en el vendedor y que una verificación la resuelve la persona (integración)", async () => {
    const usuario = userEvent.setup();
    const tarifa = (vendedor: string, nombre: string, precio: number, elige: string) => ({ vendedor, nombre, precio,
      equipaje: [], cambios: [], reembolso: [], otras: [], elige, ir_url: `/api/v1/ir/${vendedor}/${nombre}` });
    const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockResolvedValueOnce({
      estado: "listo", consultado: "2026-11-16T15:00:00Z",
      tarifas: [tarifa("American", "Basic Economy", 564, "la ida AA 1851, sale 9:48 am, y el regreso AA 3321, sale 11:06 pm"),
        tarifa("American", "Main Cabin", 694, "la ida AA 1851, sale 9:48 am, y el regreso AA 3321, sale 11:06 pm")],
      vendedores: [{ vendedor: "American", aerolinea: true, precio_desde: 564 }],
    });
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { opcionesBuscador }) });
    const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
    const capa = within(tarjeta).getByRole("region", { name: "Opciones del buscador" });
    expect(await within(capa).findByText(
      "En la página del vendedor, elige la ida AA 1851, sale 9:48 am, y el regreso AA 3321, sale 11:06 pm.")).toBeInTheDocument();
    expect(within(capa).getByText(/puede pedir una verificación/)).toBeInTheDocument();
  });

  it("con billetes separados cada tiquete dice qué vuelo elegir (integración)", async () => {
    const usuario = userEvent.setup();
    const tiquete = (vendedor: string, nombre: string, precio: number, elige: string) => ({ vendedor, nombre, precio,
      equipaje: [], cambios: [], reembolso: [], otras: [], elige, ir_url: `/api/v1/ir/${vendedor}/${nombre}` });
    const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockResolvedValueOnce({
      estado: "listo", consultado: "2026-11-16T15:00:00Z",
      tarifas: [tiquete("COPA", "ida", 334, "CM 687 · CM 240, sale 12:40 pm"), tiquete("eDreams", "regreso", 316, "el regreso AV 9, sale 1:35 am")],
      vendedores: [{ vendedor: "COPA", aerolinea: true, precio_desde: 334 }, { vendedor: "eDreams", aerolinea: false, precio_desde: 316 }],
    });
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { opcionesBuscador }) });
    const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
    const capa = within(tarjeta).getByRole("region", { name: "Opciones del buscador" });
    expect(await within(capa).findByText("En COPA, elige CM 687 · CM 240, sale 12:40 pm.")).toBeInTheDocument();
    expect(within(capa).getByText("En eDreams, elige el regreso AV 9, sale 1:35 am.")).toBeInTheDocument();
  });

  it("si la lectura falla o no está disponible, el desglose lo dice y muestra solo lo del buscador", async () => {
    const usuario = userEvent.setup();
    const analizarVuelo = vi.fn<CotizarRepository["analizarVuelo"]>()
      .mockResolvedValueOnce({ ...ANALISIS_EJEMPLO, estado: "fallido", motivo: "la página tardó demasiado en mostrar los precios",
        datos: null, extracto: "Something went wrong", captura_url: "/api/v1/captura.png" })
      .mockResolvedValueOnce({ ...ANALISIS_EJEMPLO, estado: "no_disponible", datos: null,
        motivo: "Llegaste al tope de lecturas de Google Flights de hoy: el desglose muestra solo lo del buscador." });
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { analizarVuelo }) });
    const [primera, segunda] = (await screen.findAllByRole("link", { name: /^Ver desglose/ })).map((a) => a.closest("[role=group]") as HTMLElement);
    await usuario.click(within(primera!).getByRole("link", { name: /^Ver desglose/ }));
    expect(await within(primera!).findByText("No se pudo leer la página: la página tardó demasiado en mostrar los precios.")).toBeInTheDocument();
    expect(within(primera!).queryByRole("link", { name: "Ver lo que mostró la página" })).toBeNull();   // la captura no se muestra aquí
    await usuario.click(within(segunda!).getByRole("link", { name: /^Ver desglose/ }));
    expect(await within(segunda!).findByText(/Llegaste al tope de lecturas de Google Flights de hoy/)).toBeInTheDocument();
    expect(within(segunda!).queryByText("Tarifas y qué incluye cada una")).toBeNull();
  });

  it("si el pedido de lectura agota su plazo (o llega un 504), pasa a consultar la lectura en curso (B9)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const usuario = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const enCurso = { ...ANALISIS_EJEMPLO, estado: "pendiente" as const, datos: null, leido: null, reutilizado: true };
      const analizarVuelo = vi.fn<CotizarRepository["analizarVuelo"]>().mockRejectedValue(new ErrorDeAplicacion("tiempo_agotado"));
      const verAnalisis = vi.fn<CotizarRepository["verAnalisis"]>()
        .mockResolvedValueOnce(enCurso)
        .mockResolvedValueOnce({ ...ANALISIS_EJEMPLO, leido: "2026-11-13T15:10:00Z" });
      renderizarConFuente(<PantallaCotizacion id={12} />, {
        cotizar: repositorio(COTIZACION_MOAB, { analizarVuelo, verAnalisis }),
      });
      const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
      await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
      await vi.waitFor(() => expect(verAnalisis).toHaveBeenCalledTimes(1));
      expect(within(tarjeta).getByText("Leyendo la página del vuelo…")).toBeInTheDocument();
      expect(within(tarjeta).queryByText(/No se pudo leer/)).toBeNull();
      await vi.advanceTimersByTimeAsync(3000);
      expect(await within(tarjeta).findByText(/^Tarifas de la aerolínea leídas a las/)).toBeInTheDocument();
      expect(verAnalisis).toHaveBeenCalledWith(12, RECOMENDADA.id, expect.anything());
      expect(analizarVuelo).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("si tras agotar el plazo la lectura no quedó registrada, lo dice en vez de seguir esperando (B9)", async () => {
    const usuario = userEvent.setup();
    const analizarVuelo = vi.fn<CotizarRepository["analizarVuelo"]>().mockRejectedValue(new ErrorDeAplicacion("tiempo_agotado"));
    const verAnalisis = vi.fn<CotizarRepository["verAnalisis"]>().mockRejectedValue(new ErrorDeAplicacion("no_encontrado"));
    renderizarConFuente(<PantallaCotizacion id={12} />, {
      cotizar: repositorio(COTIZACION_MOAB, { analizarVuelo, verAnalisis }),
    });
    const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
    expect(await within(tarjeta).findByText(/^No se pudo leer/)).toBeInTheDocument();
    expect(verAnalisis).toHaveBeenCalledTimes(1);
  });

  it("si la lectura está en curso la sigue cada 3 s y, si no termina, lo dice", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const usuario = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      const enCurso = { ...ANALISIS_EJEMPLO, estado: "pendiente" as const, datos: null, leido: null, reutilizado: true };
      const analizarVuelo = vi.fn<CotizarRepository["analizarVuelo"]>().mockResolvedValue(enCurso);
      const verAnalisis = vi.fn<CotizarRepository["verAnalisis"]>()
        .mockResolvedValueOnce(enCurso)
        .mockResolvedValueOnce({ ...ANALISIS_EJEMPLO, leido: "2026-11-13T15:10:00Z" });
      renderizarConFuente(<PantallaCotizacion id={12} />, {
        cotizar: repositorio(COTIZACION_MOAB, { analizarVuelo, verAnalisis }),
      });
      const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
      await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
      expect(await within(tarjeta).findByText("Leyendo la página del vuelo…")).toBeInTheDocument();
      await vi.advanceTimersByTimeAsync(3000);
      await vi.advanceTimersByTimeAsync(3000);
      expect(await within(tarjeta).findByText(/^Tarifas de la aerolínea leídas a las/)).toBeInTheDocument();
      expect(verAnalisis).toHaveBeenCalledTimes(2);
      expect(verAnalisis).toHaveBeenCalledWith(12, RECOMENDADA.id, expect.anything());

      // otra que nunca termina: tras 15 consultas deja de preguntar y lo dice
      verAnalisis.mockReset();
      verAnalisis.mockResolvedValue(enCurso);
      const otra = screen.getByRole("group", { name: new RegExp(OTRA.numeros[0]!) });
      await usuario.click(within(otra).getByRole("link", { name: /^Ver desglose/ }));
      for (let i = 0; i < 17; i++) await vi.advanceTimersByTimeAsync(3000);
      expect(verAnalisis).toHaveBeenCalledTimes(15);
      expect(await within(otra).findByText("La lectura sigue en curso; vuelve a abrir el desglose en un momento.")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  // ---------- I-8 (QA del 16 nov): la capa del buscador espera la consulta en vivo que dispara el clic ----------
  const vacio = { estado: "sin_datos" as const, consultado: null, tarifas: [], vendedores: [] };
  const conTarifa = (precio: number, consultado: string | null) => ({
    estado: "listo" as const, consultado,
    tarifas: [{ vendedor: "American", nombre: "Main Cabin", precio, equipaje: [], cambios: [], reembolso: [], otras: [],
      ir_url: `/api/v1/ir/American/Main%20Cabin/${precio}` }],
    vendedores: [{ vendedor: "American", aerolinea: true, precio_desde: precio }],
  });
  const ahora = () => new Date().toISOString();

  async function abrirCapa(opcionesBuscador: CotizarRepository["opcionesBuscador"]) {
    const usuario = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderizarConFuente(<PantallaCotizacion id={12} />, { cotizar: repositorio(COTIZACION_MOAB, { opcionesBuscador }) });
    const tarjeta = await screen.findByRole("group", { name: /UA 1047 \+ UA 6077/ });
    await usuario.click(within(tarjeta).getByRole("link", { name: /^Ver desglose/ }));
    return within(tarjeta).getByRole("region", { name: "Opciones del buscador" });
  }

  it("con el buscador encendido muestra lo guardado marcado y lo reemplaza cuando llega lo consultado tras el clic", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let pedidos = 0;
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockImplementation(async () =>
        pedidos++ < 2 ? { ...conTarifa(588, "2026-11-11T15:00:00Z"), en_vivo: true } : { ...conTarifa(694, ahora()), en_vivo: true });
      const capa = await abrirCapa(opcionesBuscador);
      expect(await within(capa).findByText(/^Precios guardados del .+: actualizando con el buscador…$/)).toBeInTheDocument();
      expect(within(capa).getAllByText(dinero("588.00")).length).toBeGreaterThan(0);
      expect(within(capa).getByRole("link", { name: /^Ir a American/ })).toBeInTheDocument();   // «Ir a…» sigue funcionando
      expect(within(capa).getByText(/el precio final es el que diga esa página/)).toBeInTheDocument();
      for (let i = 0; i < 3; i++) await vi.advanceTimersByTimeAsync(2000);
      expect(await within(capa).findByText(/^Opciones de reserva del buscador \(consultadas a las \d{2}:\d{2}\)$/)).toBeInTheDocument();
      expect(within(capa).getAllByText(dinero("694.00")).length).toBeGreaterThan(0);
      expect(within(capa).queryByText(dinero("588.00"))).toBeNull();
      expect(within(capa).queryByText(/actualizando con el buscador/)).toBeNull();
      expect(within(capa).queryByText(/el precio final es el que diga esa página/)).toBeNull();
      const llamadas = opcionesBuscador.mock.calls.length;
      await vi.advanceTimersByTimeAsync(10_000);
      expect(opcionesBuscador).toHaveBeenCalledTimes(llamadas);                // con lo nuevo deja de preguntar
    } finally {
      vi.useRealTimers();
    }
  });

  it("el respaldo sin fecha se marca «de referencia» mientras espera", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockResolvedValue({ ...conTarifa(588, null), en_vivo: true });
      const capa = await abrirCapa(opcionesBuscador);
      expect(await within(capa).findByText("Precios de referencia: actualizando con el buscador…")).toBeInTheDocument();
      for (let i = 0; i < 21; i++) await vi.advanceTimersByTimeAsync(2000);
      expect(await within(capa).findByText("El buscador no respondió a tiempo; los precios son de referencia.")).toBeInTheDocument();
      expect(within(capa).getAllByText(dinero("588.00")).length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("sin nada guardado dice «Consultando el buscador…» y nunca «no trajo opciones» antes de que lleguen", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const inicio = Date.now();
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockImplementation(async () =>
        Date.now() - inicio < 10_000 ? { ...vacio, en_vivo: true } : { ...conTarifa(336, ahora()), en_vivo: true });
      const capa = await abrirCapa(opcionesBuscador);
      expect(await within(capa).findByText("Consultando el buscador…")).toBeInTheDocument();
      for (let i = 0; i < 6; i++) {
        expect(within(capa).queryByText("El buscador no trajo opciones de reserva para este vuelo.")).toBeNull();
        await vi.advanceTimersByTimeAsync(2000);
      }
      expect(await within(capa).findByText(/^Opciones de reserva del buscador \(consultadas a las/)).toBeInTheDocument();
      expect(within(capa).getAllByText(dinero("336.00")).length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("si en 40 s no llega nada y no hay nada guardado, dice «no trajo opciones» y deja de preguntar", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockResolvedValue({ ...vacio, en_vivo: true });
      const capa = await abrirCapa(opcionesBuscador);
      for (let i = 0; i < 19; i++) await vi.advanceTimersByTimeAsync(2000);
      expect(within(capa).getByText("Consultando el buscador…")).toBeInTheDocument();      // a los 38 s todavía espera
      for (let i = 0; i < 4; i++) await vi.advanceTimersByTimeAsync(2000);
      expect(await within(capa).findByText("El buscador no trajo opciones de reserva para este vuelo.")).toBeInTheDocument();
      const llamadas = opcionesBuscador.mock.calls.length;
      expect(llamadas).toBeGreaterThanOrEqual(20);
      await vi.advanceTimersByTimeAsync(10_000);
      expect(opcionesBuscador).toHaveBeenCalledTimes(llamadas);
    } finally {
      vi.useRealTimers();
    }
  });

  it("si en 40 s no llega nada nuevo, deja lo guardado con su fecha y lo dice", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>()
        .mockResolvedValue({ ...conTarifa(588, "2026-11-11T15:00:00Z"), en_vivo: true });
      const capa = await abrirCapa(opcionesBuscador);
      for (let i = 0; i < 21; i++) await vi.advanceTimersByTimeAsync(2000);
      expect(await within(capa).findByText(/^El buscador no respondió a tiempo; los precios son del .*11.*\.$/)).toBeInTheDocument();
      expect(within(capa).getAllByText(dinero("588.00")).length).toBeGreaterThan(0);
      expect(within(capa).getByRole("link", { name: /^Ir a American/ })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("si el servidor falla mientras espera, deja de preguntar y deja lo guardado con su nota (ronda 1)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let pedidos = 0;
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockImplementation(async () => {
        if (pedidos++ === 0) return { ...conTarifa(588, "2026-11-11T15:00:00Z"), en_vivo: true };
        throw new ErrorDeAplicacion("servidor");
      });
      const capa = await abrirCapa(opcionesBuscador);
      expect(await within(capa).findByText(/^Precios guardados del .+: actualizando con el buscador…$/)).toBeInTheDocument();
      for (let i = 0; i < 20; i++) await vi.advanceTimersByTimeAsync(2000);
      const llamadas = opcionesBuscador.mock.calls.length;
      for (let i = 0; i < 40; i++) await vi.advanceTimersByTimeAsync(2000);   // hasta los 120 s, ningún pedido más
      expect(opcionesBuscador).toHaveBeenCalledTimes(llamadas);
      expect(within(capa).queryByText(/actualizando con el buscador/)).toBeNull();
      expect(within(capa).getByText(/^El buscador no respondió a tiempo; los precios son del .*11.*\.$/)).toBeInTheDocument();
      expect(within(capa).getAllByText(dinero("588.00")).length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("si el servidor falla sin nada guardado, lo dice y deja de preguntar (ronda 1)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let pedidos = 0;
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockImplementation(async () => {
        if (pedidos++ === 0) return { ...vacio, en_vivo: true };
        throw new ErrorDeAplicacion("servidor");
      });
      const capa = await abrirCapa(opcionesBuscador);
      expect(await within(capa).findByText("Consultando el buscador…")).toBeInTheDocument();
      for (let i = 0; i < 60; i++) await vi.advanceTimersByTimeAsync(2000);
      expect(opcionesBuscador.mock.calls.length).toBeLessThanOrEqual(21);
      expect(within(capa).getByText("No se pudieron traer las opciones del buscador.")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("con el buscador apagado hace un solo pedido y marca el respaldo «de referencia»", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockResolvedValue({ ...conTarifa(588, null), en_vivo: false });
      const capa = await abrirCapa(opcionesBuscador);
      expect(await within(capa).findByText("Opciones de reserva del buscador")).toBeInTheDocument();
      expect(within(capa).getByText(/^Precios de referencia\. «Ir a…» lleva a la página del vendedor/)).toBeInTheDocument();
      await vi.advanceTimersByTimeAsync(10_000);
      expect(opcionesBuscador).toHaveBeenCalledTimes(1);
      expect(within(capa).queryByText(/actualizando con el buscador/)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("con el buscador apagado y sin nada guardado lo dice enseguida, con un solo pedido", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const opcionesBuscador = vi.fn<CotizarRepository["opcionesBuscador"]>().mockResolvedValue({ ...vacio, en_vivo: false });
      const capa = await abrirCapa(opcionesBuscador);
      expect(await within(capa).findByText("El buscador no trajo opciones de reserva para este vuelo.")).toBeInTheDocument();
      await vi.advanceTimersByTimeAsync(10_000);
      expect(opcionesBuscador).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

