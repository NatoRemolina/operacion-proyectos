import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import type { Permiso } from "@/shared/domain/navegacion";
import { renderizarConFuente } from "@/test/renderizar";
import type { AsistenteRepository, RespuestaAsistente } from "../domain/asistente";
import { crearAsistenteMemoria } from "../infrastructure/asistente-memoria";
import { AsistenteFlotante } from "./asistente-flotante";

function respuesta(extra: Partial<RespuestaAsistente> = {}): RespuestaAsistente {
  return {
    texto: "Hay **2 gastos** en revisión.\n- gasto #4: sin recibo\n- gasto #9: duplicado",
    modo: "asesor",
    modo_texto: "Asesor con herramientas",
    fuentes: [
      { tipo: "gasto", codigo: "gasto #4", destino: { tipo: "gasto", id: 4 } },
      { tipo: "persona", codigo: "P-0002", destino: null },
    ],
    herramientas: ["kpi", "gastos_de"],
    duracion_ms: 7842,
    usadas: 3,
    tope: 40,
    ...extra,
  };
}

function montar(asistente: AsistenteRepository = crearAsistenteMemoria({ responder: () => respuesta() }), permiso: Permiso = "admin") {
  return renderizarConFuente(<AsistenteFlotante />, { asistente, permiso, personaId: 7 });
}

afterEach(() => window.sessionStorage.clear());

describe("Asistente flotante", () => {
  it.each(["colaborador", "gestor"] as const)("%s también ve el botón, con su bienvenida y sus preguntas", async (permiso) => {
    const usuario = userEvent.setup();
    const preguntar = vi.fn(() => respuesta({ texto: "Te quedan 120,00 USD.", fuentes: [] }));
    montar(crearAsistenteMemoria({ responder: preguntar }), permiso);
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    const panel = screen.getByRole("dialog", { name: "Asistente IA" });
    expect(within(panel).getByText(/Solo ves lo tuyo/)).toBeInTheDocument();
    expect(within(panel).queryByText(/proyectos que gestionas/) !== null).toBe(permiso === "gestor");
    expect(within(panel).queryByRole("button", { name: "¿Cómo van los indicadores?" })).toBeNull();
    const sugerida = permiso === "gestor" ? "¿Cómo va el presupuesto de mi proyecto?" : "¿Cuánto me queda del presupuesto?";
    await usuario.click(within(panel).getByRole("button", { name: sugerida }));
    expect(preguntar).toHaveBeenCalledWith(sugerida);
    expect(await within(panel).findByText("Te quedan 120,00 USD.")).toBeInTheDocument();
  });

  it("en el modo demostración responde sin datos en vez de negarse", async () => {
    const usuario = userEvent.setup();
    montar(crearAsistenteMemoria(), "colaborador");
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    await usuario.click(screen.getByRole("button", { name: "¿Qué me falta por justificar?" }));
    expect(await screen.findByText(/modo de demostración/)).toBeInTheDocument();
  });

  it("abre el panel con el foco en la pregunta y Escape lo cierra devolviendo el foco", async () => {
    const usuario = userEvent.setup();
    montar();
    const boton = screen.getByRole("button", { name: "Asistente IA" });
    expect(boton).toHaveAttribute("aria-expanded", "false");
    await usuario.click(boton);
    expect(boton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog", { name: "Asistente IA" })).toBeVisible();
    expect(screen.getByLabelText("Tu pregunta para el asistente")).toHaveFocus();
    await usuario.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Asistente IA" })).toBeNull();
    expect(boton).toHaveFocus();
  });

  it("una pregunta sugerida se responde con formato, modo, duración y fuentes enlazadas, sin perder el foco", async () => {
    const usuario = userEvent.setup();
    const preguntar = vi.fn(() => respuesta());
    montar(crearAsistenteMemoria({ responder: preguntar }));
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    await usuario.click(screen.getByRole("button", { name: "¿Cómo van los indicadores?" }));
    expect(preguntar).toHaveBeenCalledWith("¿Cómo van los indicadores?");
    const conversacion = screen.getByRole("log", { name: "Conversación con el asistente" });
    expect(await within(conversacion).findByText("2 gastos")).toHaveProperty("tagName", "STRONG");
    expect(within(conversacion).getByText("gasto #4: sin recibo").closest("ul")).not.toBeNull();
    expect(within(conversacion).getByText("Asesor con herramientas")).toBeInTheDocument();
    expect(within(conversacion).getByText("7,8 s")).toBeInTheDocument();
    expect(within(conversacion).getByRole("link", { name: "gasto #4" })).toHaveAttribute("href", "/gastos/4");
    expect(within(conversacion).queryByRole("link", { name: "P-0002" })).toBeNull();
    expect(screen.getByText("3 de 40 preguntas hoy")).toBeInTheDocument();
    expect(screen.getByLabelText("Tu pregunta para el asistente")).toHaveFocus();
  });

  it("Enter envía lo escrito y Mayúsculas+Enter salta de línea", async () => {
    const usuario = userEvent.setup();
    const preguntar = vi.fn(() => respuesta({ texto: "Listo." }));
    montar(crearAsistenteMemoria({ responder: preguntar }));
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    const campo = screen.getByLabelText("Tu pregunta para el asistente");
    await usuario.type(campo, "Primera línea{Shift>}{Enter}{/Shift}segunda");
    expect(preguntar).not.toHaveBeenCalled();
    await usuario.keyboard("{Enter}");
    expect(preguntar).toHaveBeenCalledWith("Primera línea\nsegunda");
    expect(await screen.findByText("Listo.")).toBeInTheDocument();
    expect(campo).toHaveValue("");
  });

  it("mientras responde muestra que consulta y no deja enviar otra pregunta", async () => {
    const usuario = userEvent.setup();
    let resolver: (r: RespuestaAsistente) => void = () => {};
    const lento: AsistenteRepository = {
      preguntar: () => new Promise((r) => (resolver = r)),
      transcribir: () => Promise.resolve(""),
    };
    montar(lento);
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    await usuario.type(screen.getByLabelText("Tu pregunta para el asistente"), "¿Hola?{Enter}");
    expect(screen.getByText("Consultando los datos")).toBeInTheDocument();
    expect(screen.getByText("El asistente está consultando los datos.")).toBeInTheDocument();
    await usuario.type(screen.getByLabelText("Tu pregunta para el asistente"), "otra");
    expect(screen.getByRole("button", { name: "Enviar la pregunta" })).toBeDisabled();
    await act(async () => resolver(respuesta({ texto: "Hola." })));
    expect(await screen.findByText("Hola.")).toBeInTheDocument();
    expect(screen.queryByText("Consultando los datos")).toBeNull();
  });

  it("un fallo se explica y se puede reintentar", async () => {
    const usuario = userEvent.setup();
    const preguntar = vi
      .fn<(p: string) => RespuestaAsistente>()
      .mockImplementationOnce(() => {
        throw new ErrorDeAplicacion("red");
      })
      .mockImplementationOnce(() => respuesta({ texto: "Ahora sí." }));
    montar(crearAsistenteMemoria({ responder: preguntar }));
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    await usuario.type(screen.getByLabelText("Tu pregunta para el asistente"), "¿Hola?{Enter}");
    expect(await screen.findByText("No pude responder")).toBeInTheDocument();
    expect(screen.getByText("No hubo conexión con el servidor.")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Ahora sí.")).toBeInTheDocument();
    expect(preguntar).toHaveBeenLastCalledWith("¿Hola?");
  });

  it("con el panel cerrado avisa que llegó una respuesta", async () => {
    const usuario = userEvent.setup();
    let resolver: (r: RespuestaAsistente) => void = () => {};
    montar({ preguntar: () => new Promise((r) => (resolver = r)), transcribir: () => Promise.resolve("") });
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    await usuario.type(screen.getByLabelText("Tu pregunta para el asistente"), "¿Hola?{Enter}");
    await usuario.keyboard("{Escape}");
    await act(async () => resolver(respuesta()));
    expect(await screen.findByText("El asistente respondió. Abre el asistente para leerlo.")).toBeInTheDocument();
  });

  it("la conversación sigue en la pestaña para la misma persona y descarta lo dañado", async () => {
    window.sessionStorage.setItem(
      "asistente:v1:7",
      JSON.stringify([
        null,
        { id: "a", rol: "persona", texto: "¿Qué pasó?", porVoz: true, estado: "esperando" },
        { id: "b", rol: "desconocido" },
        { id: "c", rol: "asistente", respuesta: respuesta({ texto: "Respuesta anterior.", fuentes: [] }) },
      ]),
    );
    const usuario = userEvent.setup();
    montar();
    expect(screen.queryByText("El asistente respondió. Abre el asistente para leerlo.")).toBeNull(); // lo recuperado no es nuevo
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    expect(screen.getByText("¿Qué pasó?")).toBeInTheDocument();
    expect(screen.getByText("Dictado por voz")).toBeInTheDocument();
    expect(screen.getByText("Sin respuesta: la página se recargó antes de que terminara.")).toBeInTheDocument();
    expect(screen.getByText("Respuesta anterior.")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Empezar una conversación nueva" }));
    expect(screen.getByText("¿En qué te ayudo?")).toBeInTheDocument();
    expect(JSON.parse(window.sessionStorage.getItem("asistente:v1:7") ?? "null")).toEqual([]);
  });

  it("al entrar otra persona en la pestaña, la conversación anterior se borra del navegador", () => {
    window.sessionStorage.setItem("asistente:v1:9", JSON.stringify([{ id: "x", rol: "persona", texto: "De otra persona", porVoz: false, estado: "respondida" }]));
    window.sessionStorage.setItem("otra-cosa", "se conserva");
    montar();
    expect(window.sessionStorage.getItem("asistente:v1:9")).toBeNull();
    expect(window.sessionStorage.getItem("otra-cosa")).toBe("se conserva");
  });

  it("una respuesta guardada sin la forma completa se descarta sin romper la pantalla", async () => {
    window.sessionStorage.setItem(
      "asistente:v1:7",
      JSON.stringify([{ id: "c", rol: "asistente", respuesta: { texto: "solo texto" } }, { id: "d", rol: "persona", texto: "¿Sigue?", porVoz: false, estado: "respondida" }]),
    );
    const usuario = userEvent.setup();
    montar();
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    expect(screen.queryByText("solo texto")).toBeNull();
    expect(screen.getByText("¿Sigue?")).toBeInTheDocument();
  });

  it("sin micrófono en el navegador no ofrece dictar", async () => {
    const usuario = userEvent.setup();
    montar();
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    expect(screen.queryByRole("button", { name: "Dictar la pregunta con la voz" })).toBeNull();
  });
});
