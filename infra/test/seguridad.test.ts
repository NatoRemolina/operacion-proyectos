import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { CON_DOMINIO, propiedades, sintetizar } from "./ayuda";

describe("cabeceras de seguridad de la web", () => {
  const { web } = sintetizar(CON_DOMINIO);
  const politicas = web.findResources("AWS::CloudFront::ResponseHeadersPolicy");
  const politica = (id: any) => politicas[id?.Ref]?.Properties.ResponseHeadersPolicyConfig;
  const [config] = propiedades(web, "AWS::CloudFront::Distribution")
    .map((p) => p.DistributionConfig)
    .filter((c) => (c.Aliases ?? []).some((a: string) => a.startsWith("software.")));

  test("la página y los estáticos salen con las cabeceras de seguridad (contra el enmarcado ajeno)", () => {
    const estaticos = config.CacheBehaviors.find((c: any) => c.PathPattern === "/_next/static/*");
    for (const id of [config.DefaultCacheBehavior.ResponseHeadersPolicyId, estaticos.ResponseHeadersPolicyId]) {
      const seguridad = politica(id).SecurityHeadersConfig;
      assert.equal(seguridad.FrameOptions.FrameOption, "SAMEORIGIN");
      assert.equal(seguridad.ContentTypeOptions.Override, true);
    }
  });

  test("la API conserva sus propias cabeceras: CloudFront solo le fija HSTS con subdominios", () => {
    const api = config.CacheBehaviors.find((c: any) => c.PathPattern === "/api/v1/*");
    const seguridad = politica(api.ResponseHeadersPolicyId).SecurityHeadersConfig;
    assert.deepEqual(Object.keys(seguridad), ["StrictTransportSecurity"]);
  });
});
