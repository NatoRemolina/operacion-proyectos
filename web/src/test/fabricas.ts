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
