import { QueryClient } from "@tanstack/react-query";
import { esErrorDeAplicacion } from "@/shared/domain/errores";

/**
 * Política de caché común. Las lecturas se reintentan solo ante fallos transitorios
 * (red o servidor); las escrituras nunca se repiten solas.
 */
export function crearQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        retry: (intentos, error) =>
          intentos < 2 &&
          esErrorDeAplicacion(error) &&
          (error.tipo === "red" || error.tipo === "servidor"),
      },
      mutations: { retry: false },
    },
  });
}
