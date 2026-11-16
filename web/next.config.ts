import type { NextConfig } from "next";
import { politicaDeContenido } from "./src/config/cabeceras";

// Sin rewrites hacia el backend: en local el gateway pone la web y /api/v1 en el mismo origen,
// y el navegador llama directamente a NEXT_PUBLIC_API_BASE (por defecto /api/v1).
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // No generar archivos de instrucciones para herramientas de terceros dentro del proyecto.
  agentRules: false,
  async headers() {
    const csp = politicaDeContenido({
      desarrollo: process.env.NODE_ENV !== "production",
      baseApi: process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1",
    });
    return [{ source: "/:path*", headers: [{ key: "Content-Security-Policy", value: csp }] }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
