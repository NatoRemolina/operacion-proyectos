import type { NextConfig } from "next";

// Sin rewrites hacia el backend: en local el gateway pone la web y /api/v1 en el mismo origen,
// y el navegador llama directamente a NEXT_PUBLIC_API_BASE (por defecto /api/v1).
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // No generar archivos de instrucciones para herramientas de terceros dentro del proyecto.
  agentRules: false,
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
