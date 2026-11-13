import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { GastoDetalle, GastosRepository } from "@/features/gastos/domain/gastos";
import { crearGastosMemoria } from "@/features/gastos/infrastructure/gastos-memoria";
import { PantallaDetalleGasto } from "@/features/gastos/ui/pantalla-detalle-gasto";
import { PlataformaProvider } from "@/shared/application/plataforma";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { gastoDePrueba, resumenDePrueba } from "@/test/fabricas";
import type { AdministracionRepository } from "../domain/administracion";
import type { DatosRevision } from "../domain/revision";
import { crearAdministracionMemoria } from "../infrastructure/administracion-memoria";

const navegacion = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navegacion, usePathname: () => "/gastos/123" }));

const EN_REVISION = gastoDePrueba({
  id: 123,
  comercio: "Café del centro",
  categoria: "comida",
  version: 3,
  alertas: ["El total no cuadra con el subtotal y el impuesto."],
  documento_id: 55,
});

function datosDe(datos: Partial<DatosRevision> = {}): DatosRevision {
  return {
    gasto_id: 123,
    version: 3,
    metodo_pago: "Tarjeta de la empresa",
    canal_reserva: null,
    lectura_original: {
      comercio: "Cafe del centr0",
      fecha: "2026-12-09",
      categoria: "comida",
      subtotal: "50.00",
      impuesto: "4.00",
      propina: null,
      total: "54.00",
      moneda: "USD",
      metodo_pago: null,
      canal_reserva: null,
      confianza: 0.62,
      dudas: ["comercio"],
    },
    soporte: { documento_id: 55, nombre: "recibo.png", forma: "imagen" },
    categorias: [
      { clave: "comida", nombre: "Comida" },
      { clave: "transporte_terrestre", nombre: "Transporte terrestre: taxi, bus, tren, aplicación" },
      { clave: "otros", nombre: "Otros" },
    ],
    viajes: [
      { id: 7, codigo: "V-2026-0007", estado: "aprobado", estado_texto: "Aprobado", titular: "Alex Rivera", origen: "MIA", destino: "SLC", ida: "2026-12-08", regreso: "2026-12-11" },
      { id: 9, codigo: "V-2026-0009", estado: "aprobado", estado_texto: "Aprobado", titular: "Sam Ortiz", origen: "MIA", destino: "LAS", ida: "2026-12-14", regreso: "2026-12-16" },
    ],
    propio: false,
    aviso_propio: null,
    ...datos,
  };
}

function montar({
  gastos = [EN_REVISION, gastoDePrueba({ id: 124, comercio: "Taxi aeropuerto", creado: "2026-11-11T04:00:00Z" })],
  revisar,
  permiso = "admin",
  datos = datosDe(),
}: {
  gastos?: GastoDetalle[];
  revisar?: AdministracionRepository["revisarGasto"];
  permiso?: "admin" | "colaborador";
  datos?: DatosRevision;
} = {}) {
  navegacion.push.mockClear();
  const repoGastos: GastosRepository = { ...crearGastosMemoria({ gastos }), urlOriginal: (id) => `/api/v1/documentos/${id}/contenido` };
  const obtener = vi.spyOn(repoGastos, "obtener");
  const memoria = crearAdministracionMemoria({ resumen: resumenDePrueba(), gastos, datosRevision: { 123: datos } });
  const administracion = {
    ...memoria,
    urlAudioJustificacion: (gid: number, jid: number) => `/api/v1/gastos/${gid}/justificaciones/${jid}/audio`,
    revisarGasto: vi.fn<AdministracionRepository["revisarGasto"]>(
      revisar ??
        (async (_id, r) => ({
          ...EN_REVISION,
          estado: r.accion === "rechazar" ? "rechazado" : r.accion === "guardar" ? "revision" : "aprobado",
          estado_texto: "Hecho",
          version: 4,
        })),
    ),
  };
  renderizarConFuente(
    <PlataformaProvider origen="http://plataforma.local">
      <PantallaDetalleGasto id={123} />
    </PlataformaProvider>,
    { gastos: repoGastos, administracion, permiso },
  );
  return { revisar: administracion.revisarGasto, obtener };
}

describe("Revisar un gasto", () => {
  it("muestra el recibo junto a lo leído y por qué va a revisión", async () => {
    montar();
    expect(await screen.findByRole("heading", { level: 1, name: "Revisar: Café del centro" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Recibo original de Café del centro" })).toHaveAttribute(
      "src",
      "/api/v1/documentos/55/contenido",
    );
    const motivos = screen.getByRole("region", { name: "Por qué va a revisión" });
    expect(within(motivos).getByText("El total no cuadra con el subtotal y el impuesto.")).toBeInTheDocument();
    const leido = screen.getByRole("region", { name: "Lo que leímos del recibo" });
    expect(leido).toHaveTextContent("USD 54,00");
    expect(leido).toHaveTextContent("Cafe del centr0");
    expect(leido).toHaveTextContent("62 %");
  });

  it("aprobar manda la versión vista y pasa al siguiente gasto en revisión", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "aprobar" });
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/Gasto aprobado/)).toBeInTheDocument();
    expect(navegacion.push).toHaveBeenCalledWith("/gastos/124");
  });

  it("si no quedan pendientes lo dice y se queda en el gasto", async () => {
    const usuario = userEvent.setup();
    montar({ gastos: [EN_REVISION] });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/No quedan gastos en revisión/)).toBeInTheDocument();
    expect(navegacion.push).not.toHaveBeenCalled();
  });

  it("rechazar exige un motivo de 5 o más caracteres", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    await usuario.click(await screen.findByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog", { name: "Rechazar el gasto de Café del centro" });
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar gasto" }));
    expect(within(dialogo).getByText(/al menos 5 caracteres/)).toBeInTheDocument();
    expect(revisar).not.toHaveBeenCalled();
    await usuario.type(within(dialogo).getByLabelText("Motivo del rechazo"), "Es un gasto personal");
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar gasto" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "rechazar", motivo: "Es un gasto personal" });
  });

  it("si otra persona lo cambió, avisa, recarga lo último y conserva lo escrito", async () => {
    const usuario = userEvent.setup();
    const { obtener } = montar({
      revisar: async () => {
        throw new ErrorDeAplicacion("cambio_ajeno");
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog");
    await usuario.type(within(dialogo).getByLabelText("Motivo del rechazo"), "Es un gasto personal");
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar gasto" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Otra persona lo cambió");
    expect(obtener.mock.calls.length).toBeGreaterThan(1);
    await usuario.click(screen.getByRole("button", { name: "Rechazar" }));
    expect(screen.getByLabelText("Motivo del rechazo")).toHaveValue("Es un gasto personal");
  });

  it("si el gasto es suyo, explica que lo revisa otra persona", async () => {
    const usuario = userEvent.setup();
    montar({
      revisar: async () => {
        throw new ErrorDeAplicacion("prohibido");
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("lo revisa otra persona de administración");
  });

  it("quien no es de administración ve su gasto sin botones de revisión", async () => {
    montar({ permiso: "colaborador" });
    expect(await screen.findByRole("heading", { level: 1, name: "Café del centro" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprobar gasto" })).not.toBeInTheDocument();
  });

  it("si las reglas no dejan aprobarlo, lo dice, no salta al siguiente y deja corregir aquí, sin mandar a otra pantalla", async () => {
    const usuario = userEvent.setup();
    montar({
      revisar: async () => ({ ...EN_REVISION, estado: "revision", estado_texto: "En revisión", version: 4, alertas: ["Sin viaje asignado."] }),
    });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se aprobó");
    expect(navegacion.push).not.toHaveBeenCalled();
    expect(within(screen.getByRole("status", { name: "Avisos" })).queryByText(/Gasto aprobado/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /revisión completa/ })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Aprobar con excepción");
    expect(screen.getByText("Sin viaje asignado.")).toBeInTheDocument();
  });

  it("sin comercio leído, el diálogo no repite «gasto»", async () => {
    const usuario = userEvent.setup();
    montar({ gastos: [{ ...EN_REVISION, comercio: null }] });
    await usuario.click(await screen.findByRole("button", { name: "Rechazar" }));
    expect(screen.getByRole("dialog", { name: "Rechazar este gasto" })).toBeInTheDocument();
  });

  it("si el gasto es de quien revisa, no ofrece revisarlo y explica quién lo hace", async () => {
    montar({ gastos: [{ ...EN_REVISION, propio: true }] });
    expect(await screen.findByText("Es tu gasto: lo revisa otra persona de administración.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprobar gasto" })).not.toBeInTheDocument();
  });

  it("el siguiente en revisión salta los gastos propios", async () => {
    const usuario = userEvent.setup();
    montar({
      gastos: [
        EN_REVISION,
        gastoDePrueba({ id: 124, comercio: "Mío", propio: true, creado: "2026-11-11T05:00:00Z" }),
        gastoDePrueba({ id: 125, comercio: "De otra persona", creado: "2026-11-11T04:00:00Z" }),
      ],
    });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    await within(screen.getByRole("status", { name: "Avisos" })).findByText(/Gasto aprobado/);
    expect(navegacion.push).toHaveBeenCalledWith("/gastos/125");
  });

  it("el siguiente ajeno se encuentra aunque los primeros pendientes sean propios", async () => {
    const usuario = userEvent.setup();
    const propios = Array.from({ length: 6 }, (_, i) =>
      gastoDePrueba({ id: 200 + i, propio: true, creado: `2026-11-11T1${i}:00:00Z` }),
    );
    montar({
      gastos: [EN_REVISION, ...propios, gastoDePrueba({ id: 300, comercio: "Ajeno", creado: "2026-11-10T00:00:00Z" })],
    });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    await within(screen.getByRole("status", { name: "Avisos" })).findByText(/Gasto aprobado/);
    expect(navegacion.push).toHaveBeenCalledWith("/gastos/300");
  });

  it("si otra persona ya lo decidió, el aviso queda aunque la pantalla cambie a la vista normal", async () => {
    const usuario = userEvent.setup();
    const { obtener } = montar({
      revisar: async () => {
        throw new ErrorDeAplicacion("cambio_ajeno");
      },
    });
    obtener.mockResolvedValue({ ...EN_REVISION, estado: "aprobado", estado_texto: "Aprobado", version: 4 });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(
      await within(screen.getByRole("status", { name: "Avisos" })).findByText(/Otra persona cambió este gasto/),
    ).toBeInTheDocument();
  });

  it("si la imagen del recibo no se puede mostrar, lo dice sin suponer que es un PDF", async () => {
    montar();
    const imagen = await screen.findByRole("img", { name: "Recibo original de Café del centro" });
    fireEvent.error(imagen);
    expect(await screen.findByText(/No se puede mostrar aquí/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir el recibo original en otra pestaña" })).toBeInTheDocument();
  });

  it("la decisión está arriba, junto al título, y lo que contó la persona va antes que lo leído", async () => {
    montar();
    const encabezado = (await screen.findByRole("heading", { level: 1, name: "Revisar: Café del centro" })).closest("header")!;
    expect(within(encabezado).getByRole("button", { name: "Aprobar gasto" })).toBeInTheDocument();
    expect(within(encabezado).getByRole("button", { name: "Rechazar" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Tu decisión" })).not.toBeInTheDocument();
    const contado = screen.getByRole("region", { name: "Lo que contó la persona" });
    const leido = screen.getByRole("region", { name: "Lo que leímos del recibo" });
    expect(contado.compareDocumentPosition(leido) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("la categoría se lee por su nombre, no por su clave", async () => {
    const base = datosDe();
    montar({ datos: { ...base, lectura_original: { ...base.lectura_original!, categoria: "transporte_terrestre" } } });
    const leido = await screen.findByRole("region", { name: "Lo que leímos del recibo" });
    expect(leido).toHaveTextContent("Transporte terrestre");
    expect(leido).not.toHaveTextContent("transporte_terrestre");
  });

  it("si las reglas no dejan aprobarlo, el aviso ofrece aprobar con excepción ahí mismo (motivo de 8 o más)", async () => {
    const usuario = userEvent.setup();
    let llamadas = 0;
    const { revisar } = montar({
      revisar: async (_id, r) => {
        llamadas += 1;
        return llamadas === 1
          ? { ...EN_REVISION, estado: "revision", estado_texto: "En revisión", version: 3, alertas: ["Posible duplicado del gasto #9."] }
          : { ...EN_REVISION, estado: r.accion === "excepcion" ? "aprobado" : "revision", estado_texto: "Aprobado", version: 4 };
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    const aviso = await screen.findByRole("alert");
    await usuario.click(within(aviso).getByRole("button", { name: "Aprobar con excepción" }));
    const dialogo = screen.getByRole("dialog", { name: "Aprobar con excepción" });
    await usuario.type(within(dialogo).getByLabelText("Motivo de la excepción"), "Dos peajes iguales en el mismo día");
    await usuario.click(within(dialogo).getByRole("button", { name: "Aprobar con excepción" }));
    expect(revisar).toHaveBeenLastCalledWith(123, { version: 3, accion: "excepcion", motivo: "Dos peajes iguales en el mismo día" });
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/aprobado con excepción/)).toBeInTheDocument();
  });

  it("si llegó por correo, muestra el remitente y el asunto junto al recibo, como la ficha", async () => {
    montar({
      gastos: [
        {
          ...EN_REVISION,
          canal: "correo",
          correo: { remitente: "Casa do Tejo <reservas@casadotejo.test>", asunto: "FICTICIO · Factura de su estadía" },
        },
      ],
    });
    const recibo = await screen.findByRole("region", { name: "Recibo original" });
    expect(within(recibo).getByText("Remitente").nextElementSibling).toHaveTextContent("Casa do Tejo <reservas@casadotejo.test>");
    expect(within(recibo).getByText("Asunto").nextElementSibling).toHaveTextContent("FICTICIO · Factura de su estadía");
  });

  it("sin correo no muestra remitente ni asunto", async () => {
    montar();
    const recibo = await screen.findByRole("region", { name: "Recibo original" });
    expect(within(recibo).queryByText("Remitente")).not.toBeInTheDocument();
    expect(within(recibo).queryByText("Asunto")).not.toBeInTheDocument();
  });

  // ---------- revisión completa ----------
  it("los datos se corrigen aquí, con lo que se leyó al lado de cada campo", async () => {
    montar();
    const correccion = await screen.findByRole("region", { name: "Corregir los datos" });
    expect(within(correccion).getByLabelText("Comercio")).toHaveValue("Café del centro");
    expect(within(correccion).getByText("Se leyó: Cafe del centr0")).toBeInTheDocument();
    expect(within(correccion).getByLabelText("Total")).toHaveValue("54.00");
    expect(within(correccion).getByLabelText("Método de pago")).toHaveValue("Tarjeta de la empresa");
    expect(within(correccion).getByLabelText("Categoría")).toHaveDisplayValue("Comida");
    expect(within(correccion).getByLabelText("Viaje")).toHaveDisplayValue(/V-2026-0007/);
  });

  it("guardar manda solo lo corregido con la versión vista y se queda en el gasto", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    const correccion = await screen.findByRole("region", { name: "Corregir los datos" });
    await usuario.clear(within(correccion).getByLabelText("Total"));
    await usuario.type(within(correccion).getByLabelText("Total"), "60,5");
    await usuario.clear(within(correccion).getByLabelText("Impuesto"));
    await usuario.click(within(correccion).getByRole("button", { name: "Guardar correcciones" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "guardar", campos: { total: "60.50", impuesto: null } });
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/Correcciones guardadas/)).toBeInTheDocument();
    expect(navegacion.push).not.toHaveBeenCalled();
  });

  it("un importe que no es un número se marca y no se envía", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    const correccion = await screen.findByRole("region", { name: "Corregir los datos" });
    await usuario.clear(within(correccion).getByLabelText("Total"));
    await usuario.type(within(correccion).getByLabelText("Total"), "mucho");
    await usuario.click(within(correccion).getByRole("button", { name: "Guardar correcciones" }));
    expect(within(correccion).getByLabelText("Total")).toHaveAttribute("aria-invalid", "true");
    expect(within(correccion).getByText("Escribe un importe como 54.00.")).toBeInTheDocument();
    expect(revisar).not.toHaveBeenCalled();
  });

  it("sin correcciones, guardar lo dice y no envía nada", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    await usuario.click(await screen.findByRole("button", { name: "Guardar correcciones" }));
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/No hay correcciones/)).toBeInTheDocument();
    expect(revisar).not.toHaveBeenCalled();
  });

  it("aprobar incluye las correcciones y el viaje reasignado", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    const correccion = await screen.findByRole("region", { name: "Corregir los datos" });
    await usuario.selectOptions(within(correccion).getByLabelText("Viaje"), "9");
    await usuario.selectOptions(within(correccion).getByLabelText("Categoría"), "otros");
    await usuario.click(screen.getByRole("button", { name: "Aprobar gasto" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "aprobar", campos: { categoria: "otros" }, viajeId: 9 });
  });

  it("quitar el viaje manda 0", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    const correccion = await screen.findByRole("region", { name: "Corregir los datos" });
    await usuario.selectOptions(within(correccion).getByLabelText("Viaje"), "");
    await usuario.click(within(correccion).getByRole("button", { name: "Guardar correcciones" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "guardar", viajeId: 0 });
  });

  it("aprobar con excepción exige un motivo de 8 o más caracteres", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    await usuario.click(await screen.findByRole("button", { name: "Aprobar con excepción" }));
    const dialogo = screen.getByRole("dialog", { name: "Aprobar con excepción" });
    await usuario.type(within(dialogo).getByLabelText("Motivo de la excepción"), "corto");
    await usuario.click(within(dialogo).getByRole("button", { name: "Aprobar con excepción" }));
    expect(within(dialogo).getByText(/al menos 8 caracteres/)).toBeInTheDocument();
    expect(revisar).not.toHaveBeenCalled();
    await usuario.type(within(dialogo).getByLabelText("Motivo de la excepción"), ": dos peajes iguales el mismo día");
    await usuario.click(within(dialogo).getByRole("button", { name: "Aprobar con excepción" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "excepcion", motivo: "corto: dos peajes iguales el mismo día" });
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/aprobado con excepción/)).toBeInTheDocument();
  });

  it("si el servidor no deja aprobar con excepción, muestra su explicación", async () => {
    const usuario = userEvent.setup();
    montar({
      revisar: async () => {
        throw new ErrorDeAplicacion("validacion", { mensaje: "Ni con excepción se aprueba un gasto sin total." });
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar con excepción" }));
    const dialogo = screen.getByRole("dialog");
    await usuario.type(within(dialogo).getByLabelText("Motivo de la excepción"), "Gasto legítimo del rodaje");
    await usuario.click(within(dialogo).getByRole("button", { name: "Aprobar con excepción" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ni con excepción se aprueba un gasto sin total.");
  });

  it("si el servidor rechaza la categoría, el error queda junto a su selector", async () => {
    const usuario = userEvent.setup();
    montar({
      revisar: async () => {
        throw new ErrorDeAplicacion("validacion", { mensaje: "Hay datos que no son válidos.", campos: { categoria: "Esa categoría no existe." } });
      },
    });
    const correccion = await screen.findByRole("region", { name: "Corregir los datos" });
    await usuario.selectOptions(within(correccion).getByLabelText("Categoría"), "otros");
    await usuario.click(within(correccion).getByRole("button", { name: "Guardar correcciones" }));
    expect(await within(correccion).findByText("Esa categoría no existe.")).toBeInTheDocument();
    expect(within(correccion).getByLabelText("Categoría")).toHaveAttribute("aria-invalid", "true");
  });

  it("las justificaciones muestran el texto y la nota de voz se escucha aquí", async () => {
    montar({
      gastos: [
        {
          ...EN_REVISION,
          justificaciones: [
            { id: 1, tipo: "texto", canal: "web", texto: "Cena con el equipo de grabación", transcripcion: "no_aplica", creado: "2026-11-12T04:00:00Z" },
            { id: 2, tipo: "audio", canal: "telegram", texto: null, transcripcion: "pendiente", creado: "2026-11-12T05:00:00Z" },
          ],
        },
      ],
    });
    const contado = await screen.findByRole("region", { name: "Lo que contó la persona" });
    expect(within(contado).getByText("Cena con el equipo de grabación")).toBeInTheDocument();
    const audio = contado.querySelector("audio");
    expect(audio).toHaveAttribute("src", "/api/v1/gastos/123/justificaciones/2/audio");
    expect(within(contado).getByText(/Transcripción pendiente/)).toBeInTheDocument();
  });

  it("un PDF se ve al lado y un correo o una confirmación HTML se descargan", async () => {
    montar({ datos: datosDe({ soporte: { documento_id: 55, nombre: "factura.pdf", forma: "pdf" } }) });
    expect(await screen.findByTitle("Recibo original de Café del centro (PDF)")).toHaveAttribute("src", "/api/v1/documentos/55/contenido");
  });

  it("un correo o una confirmación HTML se ofrece para descargar", async () => {
    montar({ datos: datosDe({ soporte: { documento_id: 55, nombre: "reserva.eml", forma: "descarga" } }) });
    expect(await screen.findByRole("link", { name: "Descargar el recibo original (reserva.eml)" })).toHaveAttribute(
      "href",
      "/api/v1/documentos/55/contenido",
    );
  });
});
