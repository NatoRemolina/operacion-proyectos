import { ZonaPrivada } from "@/features/auth/ui/zona-privada";
import { leerBaseApi } from "@/config/configuracion";
import { origenPantallasActuales } from "@/shared/domain/navegacion";

export default function LayoutPrivado({ children }: { children: React.ReactNode }) {
  // Se fija al compilar, como NEXT_PUBLIC_API_BASE: dónde viven las pantallas que aún no tiene esta web.
  const plataforma = origenPantallasActuales(
    process.env.NEXT_PUBLIC_PLATAFORMA_URL,
    leerBaseApi(process.env.NEXT_PUBLIC_API_BASE),
  );
  return <ZonaPrivada plataforma={plataforma}>{children}</ZonaPrivada>;
}
