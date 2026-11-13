import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderizarConFuente } from "@/test/renderizar";
import { historialDe, type Mensaje } from "../application/asistente";
import { PREGUNTA_EXPLICAR, type OpcionesPregunta, type RespuestaAsistente } from "../domain/asistente";
import { crearAsistenteMemoria } from "../infrastructure/asistente-memoria";
import { AsistenteFlotante } from "./asistente-flotante";

// La pantalla en la que está la persona: cada prueba la fija en `navegacion.ruta`
const navegacion = vi.hoisted(() => ({ ruta: "/gastos/123" as string | null }));
vi.mock("next/navigation", () => ({ usePathname: () => navegacion.ruta }));

function respuesta(texto: string): RespuestaAsistente {
  return { texto, modo: "asesor", modo_texto: "Asesor con herramientas", fuentes: [], herramientas: [], duracion_ms: 900, usadas: 1, tope: 40 };
}

function montar() {
  const responder = vi.fn((p: string, opciones: OpcionesPregunta) => respuesta(opciones && `Respuesta a: ${p}`));
  renderizarConFuente(<AsistenteFlotante />, { asistente: crearAsistenteMemoria({ responder }), permiso: "admin", personaId: 11 });
  return responder;
}

afterEach(() => {
  window.sessionStorage.clear();
  navegacion.ruta = "/gastos/123";
});

describe("El asistente sabe qué estás viendo", () => {
  it("dice la pantalla, propone sus preguntas y explica la pantalla con su contexto", async () => {
    const usuario = userEvent.setup();
    const responder = montar();
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    const panel = screen.getByRole("dialog", { name: "Asistente IA" });
    expect(within(panel).getByText("Viendo: Gasto #123")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "¿Por qué está en revisión este gasto?" })).toBeInTheDocument();
    await usuario.click(within(panel).getByRole("button", { name: /Explícame esta pantalla/ }));
    expect(responder).toHaveBeenCalledWith(PREGUNTA_EXPLICAR, { contexto: { pantalla: "gasto", id: 123 }, historial: [] });
    expect(await screen.findByText(`Respuesta a: ${PREGUNTA_EXPLICAR}`)).toBeInTheDocument();
    expect(screen.getByText("Desde Gasto #123")).toBeInTheDocument();
  });

  it("la segunda pregunta lleva la conversación reciente y hay atajos de la pantalla", async () => {
    const usuario = userEvent.setup();
    const responder = montar();
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    await usuario.type(screen.getByLabelText(/Tu pregunta/), "¿Qué gastos hay en revisión?{Enter}");
    await screen.findByText("Respuesta a: ¿Qué gastos hay en revisión?");
    const atajos = screen.getByRole("list", { name: "Atajos de esta pantalla" });
    expect(within(atajos).getByRole("button", { name: /Explícame esta pantalla/ })).toBeInTheDocument();
    await usuario.type(screen.getByLabelText(/Tu pregunta/), "¿Y el más antiguo?{Enter}");
    await screen.findByText("Respuesta a: ¿Y el más antiguo?");
    const [, opciones] = responder.mock.calls[1]!;
    expect(opciones.historial).toEqual([{ pregunta: "¿Qué gastos hay en revisión?", respuesta: "Respuesta a: ¿Qué gastos hay en revisión?" }]);
  });

  it("fuera de una pantalla conocida no ofrece explicarla", async () => {
    navegacion.ruta = "/inicio";
    const usuario = userEvent.setup();
    const responder = montar();
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    expect(screen.queryByRole("button", { name: /Explícame esta pantalla/ })).toBeNull();
    expect(screen.getByText("Con datos de la plataforma")).toBeInTheDocument();
    await usuario.type(screen.getByLabelText(/Tu pregunta/), "¿Hola?{Enter}");
    expect(responder).toHaveBeenCalledWith("¿Hola?", { contexto: null, historial: [] });
  });
});

describe("historialDe", () => {
  it("toma las tres últimas preguntas respondidas, sin errores ni preguntas sin respuesta", () => {
    const persona = (id: string, texto: string): Mensaje => ({ id, rol: "persona", texto, porVoz: false, estado: "respondida" });
    const asistente = (id: string, texto: string): Mensaje => ({ id, rol: "asistente", respuesta: respuesta(texto) });
    const mensajes: Mensaje[] = [
      persona("1", "P1"), asistente("2", "R1"), persona("3", "P2"), { id: "4", rol: "error", texto: "falló", tipo: "red", pregunta: "P2" },
      persona("5", "P3"), asistente("6", "R3"), persona("7", "P4"), asistente("8", "R4"), persona("9", "P5"), asistente("10", "R5"),
      persona("11", "P6"),
    ];
    expect(historialDe(mensajes)).toEqual([
      { pregunta: "P3", respuesta: "R3" }, { pregunta: "P4", respuesta: "R4" }, { pregunta: "P5", respuesta: "R5" },
    ]);
  });
});
