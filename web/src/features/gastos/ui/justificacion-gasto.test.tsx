import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { gastoDePrueba } from "@/test/fabricas";
import { renderizarConFuente } from "@/test/renderizar";
import type { GastosRepository } from "../domain/gastos";
import { crearGastosMemoria } from "../infrastructure/gastos-memoria";
import { PantallaDetalleGasto } from "./pantalla-detalle-gasto";

const conAudio = gastoDePrueba({
  id: 5,
  justificaciones: [
    {
      id: 1,
      tipo: "audio",
      canal: "telegram",
      texto: "Hotel cerca del set para salir a las cinco",
      transcripcion: "hecha",
      creado: "2026-11-10T03:20:00Z",
    },
  ],
});

describe("Para qué fue el gasto", () => {
  it("muestra lo que la persona contó, también lo transcrito de una nota de voz", async () => {
    renderizarConFuente(<PantallaDetalleGasto id={5} />, { gastos: crearGastosMemoria({ gastos: [conAudio] }) });
    const seccion = await screen.findByRole("region", { name: "Para qué fue" });
    expect(within(seccion).getByText("Hotel cerca del set para salir a las cinco")).toBeInTheDocument();
    expect(within(seccion).getByText(/Nota de voz · desde Telegram/)).toBeInTheDocument();
    expect(screen.getByText("En revisión: administración lo revisa con lo que contaste.")).toBeInTheDocument();
  });

  it("una justificación corta se corrige en la pantalla; una válida se añade a la lista", async () => {
    const usuario = userEvent.setup();
    const repositorio = crearGastosMemoria({ gastos: [gastoDePrueba({ id: 6 })] });
    const justificar = vi.spyOn(repositorio, "justificar");
    renderizarConFuente(<PantallaDetalleGasto id={6} />, { gastos: repositorio });

    expect(await screen.findByText("Aún no has contado para qué fue. Hacerlo ayuda a resolver la revisión.")).toBeInTheDocument();
    const campo = screen.getByLabelText("¿Para qué fue este gasto?");
    await usuario.type(campo, "ok");
    await usuario.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Escribe para qué fue el gasto, aunque sea en pocas palabras.")).toBeInTheDocument();
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(justificar).not.toHaveBeenCalled();

    await usuario.clear(campo);
    await usuario.type(campo, "Cena del equipo después de grabar");
    await usuario.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Cena del equipo después de grabar")).toBeInTheDocument();
    expect(screen.getByLabelText("Añadir algo más")).toHaveValue("");
    expect(justificar).toHaveBeenCalledWith(6, "Cena del equipo después de grabar");
  });

  it("si no es su gasto, explica que solo justifica quien lo hizo", async () => {
    const usuario = userEvent.setup();
    const repositorio: GastosRepository = {
      listar: async () => ({ items: [], siguiente: null }),
      obtener: async () => gastoDePrueba({ id: 7 }),
      enviar: async () => gastoDePrueba(),
      urlOriginal: () => null,
      justificar: () => Promise.reject(new ErrorDeAplicacion("prohibido")),
    };
    renderizarConFuente(<PantallaDetalleGasto id={7} />, { gastos: repositorio });

    await usuario.type(await screen.findByLabelText("¿Para qué fue este gasto?"), "Lo justifico por otra persona");
    await usuario.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Solo quien hizo el gasto o quien viaja puede justificarlo.");
  });

  it("quien no puede justificarlo (gestor, administración en lo ajeno) lo ve en lectura, sin formulario", async () => {
    const gastos = crearGastosMemoria({ gastos: [{ ...conAudio, puede_justificar: false }] });
    renderizarConFuente(<PantallaDetalleGasto id={5} />, { gastos, permiso: "gestor" });
    expect(await screen.findByText("Hotel cerca del set para salir a las cinco")).toBeInTheDocument();
    expect(screen.queryByLabelText("Añadir algo más")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Guardar" })).not.toBeInTheDocument();
  });

  it("sin justificación y sin permiso para darla, lo dice en tercera persona", async () => {
    const gastos = crearGastosMemoria({ gastos: [gastoDePrueba({ id: 6, puede_justificar: false })] });
    renderizarConFuente(<PantallaDetalleGasto id={6} />, { gastos, permiso: "gestor" });
    expect(await screen.findByText("La persona aún no contó para qué fue.")).toBeInTheDocument();
  });
});

