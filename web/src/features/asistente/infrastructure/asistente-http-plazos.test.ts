import { PLAZO_LARGO_MS } from "@/shared/infrastructure/cliente-http";
import { probarRepositorioHttp } from "@/test/repositorio-http";
import { crearAsistenteHttp } from "./asistente-http";

// El servidor se da 55 s por pregunta (modelo y asesor); la transcripción también usa el modelo
probarRepositorioHttp("asistente", crearAsistenteHttp, {
  preguntar: { llamar: (r) => r.preguntar("¿Cuánto llevamos gastado?"), plazoMs: PLAZO_LARGO_MS },
  transcribir: { llamar: (r) => r.transcribir(new Blob(["x"], { type: "audio/wav" })), plazoMs: PLAZO_LARGO_MS },
}, "preguntar");
