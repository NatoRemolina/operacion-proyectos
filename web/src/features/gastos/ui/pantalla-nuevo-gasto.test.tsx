import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { crearViajesMemoria } from "@/features/viajes/infrastructure/viajes-memoria";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { gastoDePrueba, viajeDePrueba } from "@/test/fabricas";
import { renderizarConFuente } from "@/test/renderizar";
import type { EnvioRecibo, GastoDetalle, GastosRepository } from "../domain/gastos";
import { PantallaNuevoGasto } from "./pantalla-nuevo-gasto";

function repositorioQueResponde(...respuestas: Array<GastoDetalle | ErrorDeAplicacion>) {
  const enviar = vi.fn<(envio: EnvioRecibo) => Promise<GastoDetalle>>();
  for (const r of respuestas) {
    if (r instanceof ErrorDeAplicacion) enviar.mockRejectedValueOnce(r);
    else enviar.mockResolvedValueOnce(r);
  }
  const repositorio: GastosRepository = {
    listar: async () => ({ items: [], siguiente: null }),
    obtener: async () => gastoDePrueba(),
    enviar,
    urlOriginal: () => null,
    justificar: () => Promise.resolve(gastoDePrueba()),
  };
  return { repositorio, enviar };
}

const viajes = crearViajesMemoria({
  viajes: [
    viajeDePrueba(),
    viajeDePrueba({ id: 8, codigo: "V-2026-0008", en_curso: false, origen: "MAD", destino: "LIS" }),
  ],
});

function foto(nombre = "recibo.jpg") {
  return new File(["contenido de la foto"], nombre, { type: "image/jpeg" });
}

/** La región viva de la pantalla (la de avisos emergentes lleva el nombre «Avisos»). */
function progreso(): HTMLElement {
  return screen.getAllByRole("status").find((e) => e.getAttribute("aria-label") !== "Avisos")!;
}

describe("Cargar un gasto", () => {
  it("con un archivo elegido muestra el estado real «Aprobado» que devuelve la API", async () => {
    const usuario = userEvent.setup();
    const { repositorio, enviar } = repositorioQueResponde(
      gastoDePrueba({ id: 77, estado: "aprobado_auto", estado_texto: "Aprobado" }),
    );
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    // El viaje en curso se muestra como destino automático.
    expect(await screen.findByText("BOG → MIA")).toBeInTheDocument();
    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    expect(screen.getByText("recibo.jpg")).toBeInTheDocument();
    expect(progreso()).toHaveTextContent("Archivo elegido: recibo.jpg");

    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));

    expect(await screen.findByText("Aprobado", { selector: "span" })).toBeInTheDocument();
    expect(progreso()).toHaveTextContent("Recibo enviado. Estado: Aprobado.");
    expect(screen.getByRole("link", { name: "Ver el detalle" })).toHaveAttribute("href", "/gastos/77");
    expect(enviar).toHaveBeenCalledTimes(1);
    expect(enviar.mock.calls[0]![0]).toMatchObject({ viajeId: null });
  });

  it("si queda en revisión lo dice y sugiere contar para qué fue", async () => {
    const usuario = userEvent.setup();
    const { repositorio } = repositorioQueResponde(
      gastoDePrueba({ alertas: ["No se pudo leer la fecha."] }),
    );
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));

    expect(
      await screen.findByText(
        "En revisión: administración lo revisa. Si cuentas en el detalle para qué fue, se resuelve antes.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("No se pudo leer la fecha.")).toBeInTheDocument();
    expect(screen.queryByText("Aprobado")).not.toBeInTheDocument();
  });

  it("permite elegir un viaje concreto", async () => {
    const usuario = userEvent.setup();
    const { repositorio, enviar } = repositorioQueResponde(gastoDePrueba());
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    await usuario.click(await screen.findByRole("button", { name: "Cambiar viaje" }));
    await usuario.selectOptions(screen.getByLabelText("Viaje"), "8");
    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));

    await waitFor(() => expect(enviar).toHaveBeenCalledTimes(1));
    expect(enviar.mock.calls[0]![0].viajeId).toBe(8);
  });

  it("413: explica el límite y conserva la pantalla para elegir otro archivo", async () => {
    const usuario = userEvent.setup();
    const { repositorio } = repositorioQueResponde(new ErrorDeAplicacion("demasiado_grande"));
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El archivo pesa más de 4,5 MB");
    expect(screen.getByText("recibo.jpg")).toBeInTheDocument();
  });

  it("un archivo de más de 4,5 MB se detecta antes de enviarlo", async () => {
    const usuario = userEvent.setup();
    const { repositorio, enviar } = repositorioQueResponde();
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    const grande = new File([new Uint8Array(5 * 1024 * 1024)], "grande.jpg", { type: "image/jpeg" });
    await usuario.upload(screen.getByLabelText("Elegir archivo"), grande);

    expect(await screen.findByRole("alert")).toHaveTextContent("El archivo pesa más de 4,5 MB");
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));
    expect(enviar).not.toHaveBeenCalled();
  });

  it("reintentar tras un corte usa la misma Idempotency-Key; otro archivo usa una nueva", async () => {
    const usuario = userEvent.setup();
    const { repositorio, enviar } = repositorioQueResponde(
      new ErrorDeAplicacion("red"),
      gastoDePrueba({ estado: "aprobado_auto", estado_texto: "Aprobado" }),
      gastoDePrueba({ id: 124 }),
    );
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo enviar el recibo");

    await usuario.click(screen.getByRole("button", { name: "Reintentar envío" }));
    expect(await screen.findByText("Aprobado", { selector: "span" })).toBeInTheDocument();

    const primera = enviar.mock.calls[0]![0].claveIdempotencia;
    const segunda = enviar.mock.calls[1]![0].claveIdempotencia;
    expect(primera).toMatch(/^[0-9a-f-]{36}$/);
    expect(segunda).toBe(primera);

    await usuario.click(screen.getByRole("button", { name: "Cargar otro gasto" }));
    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto("otro.jpg"));
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));
    await waitFor(() => expect(enviar).toHaveBeenCalledTimes(3));
    expect(enviar.mock.calls[2]![0].claveIdempotencia).not.toBe(primera);
  });

  it("sesión vencida: mensaje claro y enlace para entrar", async () => {
    const usuario = userEvent.setup();
    const { repositorio } = repositorioQueResponde(new ErrorDeAplicacion("sesion_vencida"));
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Tu sesión venció");
    expect(screen.getByRole("link", { name: "Entrar de nuevo" })).toHaveAttribute(
      "href",
      "/entrar?volver=%2Fgastos%2Fnuevo",
    );
  });

  it("la justificación escrita viaja con el recibo, sin espacios sobrantes en el adaptador", async () => {
    const usuario = userEvent.setup();
    const { repositorio, enviar } = repositorioQueResponde(gastoDePrueba());
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });

    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.type(screen.getByLabelText("¿Para qué fue este gasto?"), "Taxi del hotel al set");
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));

    await waitFor(() => expect(enviar).toHaveBeenCalledTimes(1));
    expect(enviar.mock.calls[0]![0].justificacion).toBe("Taxi del hotel al set");
  });

  it("si el envío anterior todavía se procesa, reintenta solo con la misma clave", async () => {
    const usuario = userEvent.setup();
    const { repositorio, enviar } = repositorioQueResponde(
      new ErrorDeAplicacion("en_curso"),
      gastoDePrueba({ id: 78, estado: "aprobado_auto", estado_texto: "Aprobado" }),
    );
    renderizarConFuente(<PantallaNuevoGasto />, { gastos: repositorio, viajes });
    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));
    await waitFor(() => expect(progreso()).toHaveTextContent("Recibo enviado. Estado: Aprobado."), { timeout: 4000 });
    expect(enviar).toHaveBeenCalledTimes(2);
    expect(enviar.mock.calls[1]![0].claveIdempotencia).toBe(enviar.mock.calls[0]![0].claveIdempotencia);
  });

  it("llega con el viaje elegido desde su detalle", async () => {
    const usuario = userEvent.setup();
    const { repositorio, enviar } = repositorioQueResponde(gastoDePrueba({ estado: "aprobado_auto", estado_texto: "Aprobado" }));
    renderizarConFuente(<PantallaNuevoGasto viajeInicial={8} />, { gastos: repositorio, viajes });
    expect(await screen.findByText("V-2026-0008", { exact: false })).toBeInTheDocument();
    await usuario.upload(screen.getByLabelText("Elegir archivo"), foto());
    await usuario.click(screen.getByRole("button", { name: "Enviar recibo" }));
    await waitFor(() => expect(enviar).toHaveBeenCalled());
    expect(enviar.mock.calls[0]![0].viajeId).toBe(8);
  });
});

