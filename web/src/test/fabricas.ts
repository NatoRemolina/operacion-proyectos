import type { ResumenAdmin } from "@/features/administracion/domain/administracion";
import type { Persona } from "@/features/auth/domain/auth";
import type { GastoDetalle } from "@/features/gastos/domain/gastos";
import type { ViajeResumen } from "@/features/viajes/domain/viajes";

/** Datos de prueba con la forma exacta del contrato (contracts/api-v1.md). */

export function personaDePrueba(datos: Partial<Persona> = {}): Persona {
  return {
    id: 1,
    codigo: "P-0001",
    nombre: "Persona de prueba",
    rol: "colaborador",
    correo: "persona@demo.local",
    cargo: "Pilotaje de dron",
    ...datos,
  };
}

export function gastoDePrueba(datos: Partial<GastoDetalle> = {}): GastoDetalle {
  return {
    id: 123,
    viaje: { id: 7, codigo: "V-2026-0007" },
    comercio: "Comercio de prueba",
    fecha: "2026-12-09",
    categoria: "Alimentación",
    total: "54.00",
    moneda: "USD",
    total_usd: "54.00",
    estado: "revision",
    estado_texto: "En revisión",
    creado: "2026-11-12T04:13:13Z",
    subtotal: "50.00",
    impuesto: "4.00",
    propina: null,
    motivos: [],
    alertas: [],
    canal: "web",
    documento_id: 55,
    lectura: { origen: "modelo", confianza: 0.9 },
    justificaciones: [],
    version: 0,
    propio: false,
    puede_justificar: true,
    ...datos,
  };
}

export function viajeDePrueba(datos: Partial<ViajeResumen> = {}): ViajeResumen {
  return {
    id: 7,
    codigo: "V-2026-0007",
    estado: "aprobado",
    estado_texto: "Aprobado",
    en_curso: true,
    origen: "BOG",
    destino: "MIA",
    ida: "2026-12-08",
    regreso: "2026-12-12",
    proyecto: { id: 1, nombre: "Proyecto de prueba" },
    titular: { id: 1, codigo: "P-0001", nombre: "Persona de prueba" },
    presupuesto_usd: "1000.00",
    gastado_usd: "450.00",
    en_revision_usd: "54.00",
    ejecucion_pct: 45,
    gastos: 2,
    ...datos,
  };
}

export function resumenDePrueba(datos: Partial<ResumenAdmin> = {}): ResumenAdmin {
  return {
    presupuesto_aprobado_usd: "15000.00",
    gastado_usd: "4200.50",
    disponible_usd: "10799.50",
    en_revision_usd: "54.00",
    ejecucion_pct: 28,
    viajes_por_aprobar: 1,
    gastos_en_revision: 1,
    pendientes: [viajeDePrueba({ id: 12, codigo: "V-2026-0012", estado: "pendiente_aprobacion", estado_texto: "Pendiente de aprobación", en_curso: false })],
    revision: [gastoDePrueba({ id: 123 })],
    actividad: [
      {
        gasto_id: 123,
        comercio: "Café del centro",
        persona: { id: 7, codigo: "P-0007", nombre: "Alex Rivera" },
        viaje: { id: 12, codigo: "V-2026-0012" },
        total: "54.00",
        moneda: "USD",
        total_usd: "54.00",
        estado: "revision",
        estado_texto: "En revisión",
        creado: "2026-11-12T04:13:13Z",
      },
      {
        gasto_id: 122,
        comercio: "Hotel de ejemplo",
        persona: { id: 7, codigo: "P-0007", nombre: "Alex Rivera" },
        viaje: { id: 12, codigo: "V-2026-0012" },
        total: "780.00",
        moneda: "USD",
        total_usd: "780.00",
        estado: "aprobado_auto",
        estado_texto: "Aprobado automático",
        creado: "2026-11-11T04:13:13Z",
      },
    ],
    nota: "Presupuesto disponible = aprobado − gastos aprobados. Las reservas de tiquetes se sumarán cuando existan.",
    datos_demostracion: false,
    ...datos,
  };
}
