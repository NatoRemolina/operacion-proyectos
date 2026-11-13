import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ProyectosRepositoryProvider } from "@/features/proyectos/application/proyectos";
import { crearProyectosMemoria } from "@/features/proyectos/infrastructure/proyectos-memoria";
import { proyectoDePrueba } from "@/features/proyectos/test/fabricas";
import type { Permiso } from "@/shared/domain/navegacion";
import { renderizarConFuente } from "@/test/renderizar";
import { UsuariosRepositoryProvider } from "../application/usuarios";
import type { Usuario } from "../domain/usuarios";
import { crearUsuariosMemoria } from "../infrastructure/usuarios-memoria";
import { CARGOS_DE_PRUEBA, usuarioDePrueba } from "../test/fabricas";
import { PantallaUsuarios } from "./pantalla-usuarios";

const ADMIN = usuarioDePrueba({
  id: 1,
  codigo: "P-0001",
  correo: "admin@demo.local",
  nombre: "Administración (demo)",
  rol: "admin",
  rol_texto: "administrador",
  cargo: null,
  proyectos: [],
});
const PILOTO = usuarioDePrueba({
  id: 2,
  codigo: "P-0002",
  correo: "piloto@demo.local",
  nombre: "Andrés Molina",
  rol: "colaborador",
  rol_texto: "colaborador",
  cargo: { id: 1, nombre: "Pilotaje de dron" },
  proyectos: [],
  telegram: { vinculado: true, usuario: "andres_vuela" },
});
const GESTOR = usuarioDePrueba();

function montar({ usuarios = [ADMIN, PILOTO, GESTOR], permiso = "admin" }: { usuarios?: Usuario[]; permiso?: Permiso } = {}) {
  const repo = crearUsuariosMemoria({
    usuarios,
    cargos: CARGOS_DE_PRUEBA,
    proyectos: [
      { id: 1, nombre: "Residencial Summerlin (aéreo)" },
      { id: 2, nombre: "Apartamentos Alfama (aéreo)" },
    ],
    permiso,
    yo: 1,
  });
  renderizarConFuente(
    <ProyectosRepositoryProvider
      repositorio={crearProyectosMemoria({
        permiso,
        proyectos: [proyectoDePrueba(), proyectoDePrueba({ id: 2, nombre: "Apartamentos Alfama (aéreo)" })],
      })}
    >
      <UsuariosRepositoryProvider repositorio={repo}>
        <PantallaUsuarios />
      </UsuariosRepositoryProvider>
    </ProyectosRepositoryProvider>,
    { permiso, personaId: 1 },
  );
  return repo;
}

async function fila(nombre: string) {
  const tabla = await screen.findByRole("table", { name: "Cuentas" });
  return within(tabla).getByText(nombre).closest("tr")!;
}

async function gestionar(usuario: ReturnType<typeof userEvent.setup>, nombre: string) {
  await usuario.click(within(await fila(nombre)).getByRole("button", { name: `Gestionar la cuenta de ${nombre}` }));
  return screen.getByRole("region", { name: `Cuenta de ${nombre}` });
}

describe("Usuarios y cargos", () => {
  it("lista cada cuenta con código, permiso, cargo, proyectos, estado y Telegram", async () => {
    montar();
    const gestor = await fila("Gestión de proyecto (demo)");
    expect(within(gestor).getByText("P-0004")).toBeInTheDocument();
    expect(within(gestor).getByText("gestor de proyecto")).toBeInTheDocument();
    expect(within(gestor).getByText("Producción")).toBeInTheDocument();
    expect(within(gestor).getByText("Residencial Summerlin (aéreo)")).toBeInTheDocument();
    expect(within(gestor).getByText("Activa")).toBeInTheDocument();
    expect(within(gestor).getByText("Sin vincular")).toBeInTheDocument();
    expect(within(await fila("Andrés Molina")).getByText("@andres_vuela")).toBeInTheDocument();
  });

  it("la tabla agrupa los datos en cuatro columnas para no partir palabras en escritorio", async () => {
    montar();
    const tabla = await screen.findByRole("table", { name: "Cuentas" });
    expect(within(tabla).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Persona",
      "Permiso y cargo",
      "Proyectos",
      "Estado",
      "Acción",
    ]);
  });

  it("administración crea una cuenta con su contraseña inicial", async () => {
    const usuario = userEvent.setup();
    montar();
    await screen.findByRole("table", { name: "Cuentas" });
    await usuario.click(screen.getByRole("button", { name: "Nueva cuenta" }));
    const formulario = screen.getByRole("form", { name: "Nueva cuenta" });
    await usuario.type(within(formulario).getByLabelText("Correo"), "nueva@demo.local");
    await usuario.type(within(formulario).getByLabelText("Nombre"), "Lucía Pérez");
    await usuario.selectOptions(within(formulario).getByLabelText("Permiso"), "gestor");
    await usuario.selectOptions(within(formulario).getByLabelText("Cargo"), "Edición de video");
    await usuario.type(within(formulario).getByLabelText("Contraseña inicial"), "clave-inicial-123");
    await usuario.click(within(formulario).getByRole("button", { name: "Crear cuenta" }));
    const nueva = await fila("Lucía Pérez");
    expect(within(nueva).getByText("gestor de proyecto")).toBeInTheDocument();
    expect(within(nueva).getByText("Edición de video")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Nueva cuenta" })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("clave-inicial-123")).not.toBeInTheDocument();
  });

  it("un correo repetido se señala en su campo", async () => {
    const usuario = userEvent.setup();
    montar();
    await screen.findByRole("table", { name: "Cuentas" });
    await usuario.click(screen.getByRole("button", { name: "Nueva cuenta" }));
    const formulario = screen.getByRole("form", { name: "Nueva cuenta" });
    await usuario.type(within(formulario).getByLabelText("Correo"), "piloto@demo.local");
    await usuario.type(within(formulario).getByLabelText("Nombre"), "Repetida");
    await usuario.type(within(formulario).getByLabelText("Contraseña inicial"), "clave-inicial-123");
    await usuario.click(within(formulario).getByRole("button", { name: "Crear cuenta" }));
    expect(await within(formulario).findByText("Ya existe una cuenta con ese correo.")).toBeInTheDocument();
    expect(within(formulario).getByLabelText("Correo")).toHaveAttribute("aria-invalid", "true");
  });

  it("cambia el permiso de una cuenta", async () => {
    const usuario = userEvent.setup();
    montar();
    const panel = await gestionar(usuario, "Andrés Molina");
    await usuario.selectOptions(within(panel).getByLabelText("Permiso"), "gestor");
    await usuario.click(within(panel).getByRole("button", { name: "Guardar permiso" }));
    expect(await within(await fila("Andrés Molina")).findByText("gestor de proyecto")).toBeInTheDocument();
  });

  it("cambia el cargo y los proyectos que gestiona", async () => {
    const usuario = userEvent.setup();
    montar();
    const panel = await gestionar(usuario, "Gestión de proyecto (demo)");
    await usuario.selectOptions(within(panel).getByLabelText("Cargo"), "Pilotaje de dron");
    await usuario.click(within(panel).getByRole("button", { name: "Guardar cargo" }));
    expect(await within(await fila("Gestión de proyecto (demo)")).findByText("Pilotaje de dron")).toBeInTheDocument();
    await usuario.click(within(panel).getByRole("checkbox", { name: "Apartamentos Alfama (aéreo)" }));
    await usuario.click(within(panel).getByRole("button", { name: "Guardar proyectos" }));
    expect(await within(await fila("Gestión de proyecto (demo)")).findByText("Apartamentos Alfama (aéreo)")).toBeInTheDocument();
  });

  it("solo una cuenta gestora ofrece proyectos; al dejar de serlo el bloque desaparece", async () => {
    const usuario = userEvent.setup();
    const repo = montar();
    const panel = await gestionar(usuario, "Andrés Molina");
    expect(within(panel).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(panel).getByText(/Solo una cuenta con permiso de gestor de proyecto/)).toBeInTheDocument();
    await expect(repo.asignarProyectos(2, [1])).rejects.toMatchObject({ tipo: "validacion" });
    const gestor = await gestionar(usuario, "Gestión de proyecto (demo)");
    expect(within(gestor).getAllByRole("checkbox").length).toBeGreaterThan(0);
    await usuario.selectOptions(within(gestor).getByLabelText("Permiso"), "colaborador");
    await usuario.click(within(gestor).getByRole("button", { name: "Guardar permiso" }));
    await within(await fila("Gestión de proyecto (demo)")).findByText("colaborador");
    expect(within(screen.getByRole("region", { name: "Cuenta de Gestión de proyecto (demo)" })).queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("desactiva con confirmación y luego reactiva", async () => {
    const usuario = userEvent.setup();
    montar();
    const panel = await gestionar(usuario, "Andrés Molina");
    await usuario.click(within(panel).getByRole("button", { name: "Desactivar la cuenta" }));
    const dialogo = screen.getByRole("dialog", { name: "¿Desactivar la cuenta de Andrés Molina?" });
    await usuario.click(within(dialogo).getByRole("button", { name: "Desactivar" }));
    expect(await within(await fila("Andrés Molina")).findByText("Desactivada")).toBeInTheDocument();
    await usuario.click(within(panel).getByRole("button", { name: "Reactivar la cuenta" }));
    expect(await within(await fila("Andrés Molina")).findByText("Activa")).toBeInTheDocument();
  });

  it("no deja desactivar la propia cuenta y explica por qué", async () => {
    const usuario = userEvent.setup();
    montar();
    const panel = await gestionar(usuario, "Administración (demo)");
    await usuario.click(within(panel).getByRole("button", { name: "Desactivar la cuenta" }));
    await usuario.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Desactivar" }));
    expect(await within(panel).findByText("No puedes desactivar tu propia cuenta ni al último administrador.")).toBeInTheDocument();
    expect(within(await fila("Administración (demo)")).getByText("Activa")).toBeInTheDocument();
  });

  it("restablece la contraseña y no la deja escrita", async () => {
    const usuario = userEvent.setup();
    montar();
    const panel = await gestionar(usuario, "Andrés Molina");
    const campo = within(panel).getByLabelText("Contraseña nueva");
    await usuario.type(campo, "corta");
    await usuario.click(within(panel).getByRole("button", { name: "Restablecer contraseña" }));
    expect(within(panel).getByText("La contraseña debe tener al menos 10 caracteres.")).toBeInTheDocument();
    await usuario.clear(campo);
    await usuario.type(campo, "clave-nueva-456789");
    await usuario.click(within(panel).getByRole("button", { name: "Restablecer contraseña" }));
    expect(await screen.findByText(/Contraseña de Andrés Molina restablecida/)).toBeInTheDocument();
    expect(campo).toHaveValue("");
  });

  it("crea, renombra y desactiva cargos", async () => {
    const usuario = userEvent.setup();
    montar();
    const cargos = await screen.findByRole("region", { name: "Cargos" });
    await usuario.type(within(cargos).getByLabelText("Nuevo cargo"), "Logística");
    await usuario.click(within(cargos).getByRole("button", { name: "Agregar cargo" }));
    expect(await within(cargos).findByDisplayValue("Logística")).toBeInTheDocument();
    const nombre = within(cargos).getByLabelText("Nombre del cargo Edición de video");
    await usuario.clear(nombre);
    await usuario.type(nombre, "Edición y color");
    await usuario.click(within(cargos).getByRole("button", { name: "Guardar el nombre de Edición de video" }));
    expect(await within(cargos).findByDisplayValue("Edición y color")).toBeInTheDocument();
    await usuario.click(within(cargos).getByRole("button", { name: "Desactivar el cargo Producción" }));
    expect(await within(cargos).findByRole("button", { name: "Reactivar el cargo Producción" })).toBeInTheDocument();
  });

  it("un cargo repetido se rechaza con su motivo", async () => {
    const usuario = userEvent.setup();
    montar();
    const cargos = await screen.findByRole("region", { name: "Cargos" });
    await usuario.type(within(cargos).getByLabelText("Nuevo cargo"), "producción");
    await usuario.click(within(cargos).getByRole("button", { name: "Agregar cargo" }));
    expect(await within(cargos).findByText("Ya existe el cargo «Producción».")).toBeInTheDocument();
  });

  it("quien no es de administración no ve las cuentas", async () => {
    montar({ permiso: "gestor" });
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nueva cuenta" })).not.toBeInTheDocument();
  });
});
