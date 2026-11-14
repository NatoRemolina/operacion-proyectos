import { PLAZO_LARGO_MS, PLAZO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearAdministracionHttp } from "./administracion-http";

probarRepositorioHttp("administración", crearAdministracionHttp, {
  resumen: { llamar: (r) => r.resumen(), plazoMs: PLAZO_MS },
  // aprobar consulta el precio del vuelo en el buscador antes de decidir
  cambiarEstadoViaje: { llamar: (r) => r.cambiarEstadoViaje(7, { accion: "aprobar" }), plazoMs: PLAZO_LARGO_MS },
  revisarGasto: { llamar: (r) => r.revisarGasto(3, { version: 1, accion: "aprobar" } as never), plazoMs: PLAZO_MS },
  datosRevision: { llamar: (r) => r.datosRevision(3), plazoMs: PLAZO_MS },
  buzon: { llamar: (r) => r.buzon(), plazoMs: PLAZO_MS },
  // lee con el modelo cada recibo del buzón
  leerBuzon: { llamar: (r) => r.leerBuzon({ nombres: ["a.eml"], viajeId: null }), plazoMs: PLAZO_LARGO_MS },
  catalogoReglas: { llamar: (r) => r.catalogoReglas(), plazoMs: PLAZO_MS },
  editarRegla: { llamar: (r) => r.editarRegla(1, "10"), plazoMs: PLAZO_MS },
}, "resumen");
