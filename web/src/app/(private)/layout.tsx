import { ZonaPrivada } from "@/features/auth/ui/zona-privada";

export default function LayoutPrivado({ children }: { children: React.ReactNode }) {
  return <ZonaPrivada>{children}</ZonaPrivada>;
}
