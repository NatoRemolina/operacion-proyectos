import type { CuentaMemoria } from "@/features/auth/infrastructure/auth-memoria";
import type { GastoDetalle } from "@/features/gastos/domain/gastos";
import type { ViajePropioMemoria } from "@/features/gastos/infrastructure/gastos-memoria";
import type { ViajeResumen } from "@/features/viajes/domain/viajes";

/**
 * Datos ficticios del modo demostración (FUENTE_DATOS=demo). Toda pantalla los rotula como
 * «Datos de demostración»; nunca se mezclan con la API real.
 */

export const CUENTA_DEMO: CuentaMemoria = {
  persona: {
    id: 901,
    codigo: "P-DEMO",
    nombre: "Piloto de demostración",
    rol: "colaborador",
    correo: "piloto@demo.local",
    cargo: "Pilotaje de dron",
  },
  clave: "demo1234",
};

const titular = { id: 901, codigo: "P-DEMO", nombre: "Piloto de demostración" };
const proyecto = { id: 31, nombre: "Proyecto de demostración" };

export const VIAJES_DEMO: ViajeResumen[] = [
  {
    id: 12,
    codigo: "V-2026-0012",
    estado: "aprobado",
    estado_texto: "Aprobado",
    en_curso: true,
    origen: "BOG",
    destino: "MIA",
    ida: "2026-11-09",
    regreso: "2026-11-16",
    proyecto,
    titular,
    presupuesto_usd: "1200.00",
    gastado_usd: "540.25",
    en_revision_usd: "86.10",
    ejecucion_pct: 45,
    gastos: 3,
  },
  {
    id: 15,
    codigo: "V-2026-0015",
    estado: "pendiente_aprobacion",
    estado_texto: "Pendiente de aprobación",
    en_curso: false,
    origen: "BOG",
    destino: "JFK",
    ida: "2026-12-02",
    regreso: "2026-12-06",
    proyecto,
    titular,
    presupuesto_usd: "1800.00",
    gastado_usd: "0.00",
    en_revision_usd: "0.00",
    ejecucion_pct: 0,
    gastos: 0,
  },
  {
    id: 9,
    codigo: "V-2026-0009",
    estado: "cerrado",
    estado_texto: "Cerrado",
    en_curso: false,
    origen: "MAD",
    destino: "LIS",
    ida: "2026-09-14",
    regreso: "2026-09-18",
    proyecto,
    titular,
    presupuesto_usd: "800.00",
    gastado_usd: "896.40",
    en_revision_usd: "0.00",
    ejecucion_pct: 112,
    gastos: 2,
  },
];

export const VIAJES_PROPIOS_DEMO: ViajePropioMemoria[] = VIAJES_DEMO.filter(
  (v) => v.estado === "aprobado",
).map((v) => ({ id: v.id, codigo: v.codigo, enCurso: v.en_curso }));

function gasto(datos: Partial<GastoDetalle> & Pick<GastoDetalle, "id" | "estado" | "estado_texto">): GastoDetalle {
  return {
    viaje: { id: 12, codigo: "V-2026-0012" },
    comercio: null,
    fecha: null,
    categoria: null,
    total: null,
    moneda: null,
    total_usd: null,
    creado: "2026-11-10T15:00:00Z",
    subtotal: null,
    impuesto: null,
    propina: null,
    motivos: [],
    alertas: [],
    canal: "web",
    documento_id: null,
    lectura: { origen: "demostracion", confianza: null },
    justificaciones: [],
    ...datos,
  };
}

export const GASTOS_DEMO: GastoDetalle[] = [
  gasto({
    id: 104,
    estado: "revision",
    estado_texto: "En revisión",
    comercio: "Taxi Aeropuerto MIA",
    fecha: "2026-11-10",
    categoria: "Transporte",
    total: "86.10",
    moneda: "USD",
    total_usd: "86.10",
    subtotal: "86.10",
    creado: "2026-11-10T22:41:00Z",
    motivos: ["total_alto"],
    alertas: ["El total supera el tope habitual para transporte en esta ciudad."],
    canal: "celular",
    lectura: { origen: "demostracion", confianza: 0.88 },
  }),
  gasto({
    id: 103,
    estado: "aprobado_auto",
    estado_texto: "Aprobado",
    comercio: "Hotel de demostración Brickell",
    fecha: "2026-11-09",
    categoria: "Alojamiento",
    total: "412.00",
    moneda: "USD",
    total_usd: "412.00",
    subtotal: "372.40",
    impuesto: "39.60",
    creado: "2026-11-10T03:12:00Z",
    lectura: { origen: "demostracion", confianza: 0.96 },
    justificaciones: [
      {
        id: 1,
        tipo: "audio",
        canal: "telegram",
        texto: "Dos noches en el hotel más cercano al set para salir a las cinco con el dron cargado.",
        transcripcion: "hecha",
        creado: "2026-11-10T03:20:00Z",
      },
    ],
  }),
  gasto({
    id: 102,
    estado: "aprobado_auto",
    estado_texto: "Aprobado",
    comercio: "Café de demostración",
    fecha: "2026-11-09",
    categoria: "Alimentación",
    total: "128.25",
    moneda: "USD",
    total_usd: "128.25",
    subtotal: "106.25",
    impuesto: "7.00",
    propina: "15.00",
    creado: "2026-11-09T19:05:00Z",
    lectura: { origen: "demostracion", confianza: 0.94 },
  }),
  gasto({
    id: 98,
    estado: "rechazado",
    estado_texto: "Rechazado",
    viaje: { id: 9, codigo: "V-2026-0009" },
    comercio: "Restaurante de demostración Lisboa",
    fecha: "2026-09-16",
    categoria: "Alimentación",
    total: "96.00",
    moneda: "EUR",
    total_usd: "104.30",
    creado: "2026-09-17T09:30:00Z",
    alertas: ["Gasto duplicado: ya se había registrado el mismo recibo."],
  }),
];
