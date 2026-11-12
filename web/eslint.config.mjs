import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// Límites de capas (sección 13 del plan): el dominio no conoce React ni el transporte,
// la interfaz no conoce la infraestructura y solo `composition` elige adaptadores concretos.
const INFRAESTRUCTURA = {
  group: ["**/infrastructure", "**/infrastructure/**"],
  message: "Solo src/composition puede importar adaptadores de infraestructura.",
};
const COMPOSICION = {
  group: ["@/composition", "@/composition/**", "**/composition/**"],
  message: "La composición se monta en el layout raíz; las capas no la importan.",
};
const REACT_Y_TRANSPORTE = {
  group: ["react", "react-dom", "react/**", "next", "next/**", "@tanstack/**", "zod"],
  message: "El dominio no depende de React, Next, TanStack ni del transporte.",
};
const CAPAS_SUPERIORES = {
  group: ["**/application", "**/application/**", "**/ui", "**/ui/**"],
  message: "El dominio no depende de la aplicación ni de la interfaz.",
};
const PRUEBAS = ["**/*.test.ts", "**/*.test.tsx", "src/test/**"];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "out/**", "build/**", "coverage/**", "next-env.d.ts"]),
  {
    files: ["src/features/*/domain/**", "src/shared/domain/**"],
    ignores: PRUEBAS,
    rules: {
      "no-restricted-imports": [
        "error",
        { patterns: [REACT_Y_TRANSPORTE, CAPAS_SUPERIORES, INFRAESTRUCTURA, COMPOSICION] },
      ],
    },
  },
  {
    files: [
      "src/features/*/application/**",
      "src/features/*/ui/**",
      "src/shared/application/**",
      "src/shared/ui/**",
    ],
    ignores: PRUEBAS,
    rules: {
      "no-restricted-imports": ["error", { patterns: [INFRAESTRUCTURA, COMPOSICION] }],
    },
  },
  {
    files: ["src/app/**", "src/config/**"],
    ignores: PRUEBAS,
    rules: {
      "no-restricted-imports": ["error", { patterns: [INFRAESTRUCTURA] }],
    },
  },
  {
    // fetch vive solo en los adaptadores HTTP.
    files: ["src/**"],
    ignores: [...PRUEBAS, "src/**/infrastructure/**"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Usa un repositorio; fetch solo existe en infrastructure." },
      ],
    },
  },
]);

export default eslintConfig;
