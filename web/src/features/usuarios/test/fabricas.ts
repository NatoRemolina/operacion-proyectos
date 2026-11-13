import type { Cargo, Usuario } from "../domain/usuarios";

/** Datos de prueba con la forma exacta del contrato (contracts/api-v1.md, sección «Usuarios y cargos»). */

export function usuarioDePrueba(datos: Partial<Usuario> = {}): Usuario {
  return {
    id: 4,
    codigo: "P-0004",
    correo: "gestor@demo.local",
    nombre: "Gestión de proyecto (demo)",
    rol: "gestor",
    rol_texto: "gestor de proyecto",
    cargo: { id: 3, nombre: "Producción" },
    proyectos: [{ id: 1, nombre: "Residencial Summerlin (aéreo)" }],
    activo: true,
    telegram: { vinculado: false, usuario: null },
    ultima_sesion: "2026-11-12T04:13:13Z",
    creado: "2026-11-01T10:00:00Z",
    ...datos,
  };
}

export const CARGOS_DE_PRUEBA: Cargo[] = [
  { id: 1, nombre: "Pilotaje de dron", activo: true, personas: 2 },
  { id: 2, nombre: "Edición de video", activo: true, personas: 0 },
  { id: 3, nombre: "Producción", activo: true, personas: 1 },
  { id: 4, nombre: "Fotografía aérea", activo: false, personas: 1 },
];
