import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { CON_DOMINIO, propiedades, sintetizar } from "./ayuda";

// Política administrada «SecurityHeadersPolicy» de CloudFront: HSTS, nosniff, X-Frame-Options SAMEORIGIN y Referrer-Policy
const CABECERAS_DE_SEGURIDAD = "67f7725c-6f97-4210-82d7-5512b31e9d03";

describe("cabeceras de seguridad de la web", () => {
  const { web } = sintetizar(CON_DOMINIO);
  const [config] = propiedades(web, "AWS::CloudFront::Distribution")
    .map((p) => p.DistributionConfig)
    .filter((c) => (c.Aliases ?? []).some((a: string) => a.startsWith("software.")));

  test("la página y los estáticos salen con las cabeceras de seguridad (contra el enmarcado ajeno)", () => {
    assert.equal(config.DefaultCacheBehavior.ResponseHeadersPolicyId, CABECERAS_DE_SEGURIDAD);
    const estaticos = config.CacheBehaviors.find((c: any) => c.PathPattern === "/_next/static/*");
    assert.equal(estaticos.ResponseHeadersPolicyId, CABECERAS_DE_SEGURIDAD);
  });

  test("la API conserva sus propias cabeceras: CloudFront no las pisa", () => {
    const api = config.CacheBehaviors.find((c: any) => c.PathPattern === "/api/v1/*");
    assert.equal(api.ResponseHeadersPolicyId, undefined);
  });
});
