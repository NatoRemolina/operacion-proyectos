import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { crearPilas } from "../lib/pilas";

export const DOMINIO = "nataliaremolinarodriguez.com";
export const ZONA = "Z0731422246SUYEGG2Z5R";
export const CON_DOMINIO = { dominio: DOMINIO, zonaId: ZONA };

// Identificadores de las políticas administradas de CloudFront
export const SIN_CACHE = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad";          // CachingDisabled
export const CACHE_LARGA = "658327ea-f89d-4fab-a63d-7e88639e58f6";        // CachingOptimized
export const TODO_EL_VISITANTE = "b689b0a8-53d0-40ab-baf2-68738e2966ac";  // AllViewerExceptHostHeader

/**
 * Sintetiza las tres pilas como lo haría `cdk synth`, sin construir imágenes ni compilar la web
 * (sin empaquetado y sin copiar los activos a cdk.out).
 */
export function sintetizar(contexto: Record<string, string> = {}) {
  const app = new App({
    context: {
      "aws:cdk:bundling-stacks": [],
      "aws:cdk:disable-asset-staging": true,
      correo: "avisos@example.com",
      ...contexto,
    },
  });
  const pilas = crearPilas(app, { account: "000000000000", region: "us-east-1" });
  return {
    pilas,
    base: Template.fromStack(pilas.base),
    api: Template.fromStack(pilas.api),
    web: Template.fromStack(pilas.web),
  };
}

/** Recursos de un tipo como lista de propiedades. */
export function propiedades(plantilla: Template, tipo: string): any[] {
  return Object.values(plantilla.findResources(tipo)).map((r: any) => r.Properties ?? {});
}
