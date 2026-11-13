import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { CACHE_LARGA, CON_DOMINIO, DOMINIO, SIN_CACHE, ZONA, propiedades, sintetizar } from "./ayuda";

const WEB = `software.${DOMINIO}`;
const ADMIN = `admin.software.${DOMINIO}`;

function distribuciones(contexto: Record<string, string> = {}) {
  const { web } = sintetizar(contexto);
  return propiedades(web, "AWS::CloudFront::Distribution").map((p) => p.DistributionConfig);
}

function comportamiento(config: any, patron: string) {
  return (config.CacheBehaviors ?? []).find((c: any) => c.PathPattern === patron);
}

describe("pila de la web con dominio", () => {
  const { web } = sintetizar(CON_DOMINIO);

  test("no crea ni borra la zona del dominio: la importa", () => {
    web.resourceCountIs("AWS::Route53::HostedZone", 0);
  });

  test("solo escribe registros de los dos subdominios, nunca del raíz ni de www", () => {
    const registros = propiedades(web, "AWS::Route53::RecordSet");
    const nombres = new Set(registros.map((r) => r.Name));
    assert.deepEqual([...nombres].sort(), [`${ADMIN}.`, `${WEB}.`]);
    assert.ok(registros.every((r) => r.HostedZoneId === ZONA));
    assert.deepEqual(registros.map((r) => `${r.Name} ${r.Type}`).sort(),
      [`${ADMIN}. A`, `${ADMIN}. AAAA`, `${WEB}. A`, `${WEB}. AAAA`]);
    for (const prohibido of [`${DOMINIO}.`, `www.${DOMINIO}.`]) {
      assert.ok(!nombres.has(prohibido), `no debe haber registro ${prohibido}`);
    }
  });

  test("un certificado validado por DNS en la zona, solo para los dos nombres", () => {
    const [cert, ...otros] = propiedades(web, "AWS::CertificateManager::Certificate");
    assert.equal(otros.length, 0);
    assert.equal(cert.DomainName, WEB);
    assert.deepEqual(cert.SubjectAlternativeNames, [ADMIN]);
    assert.equal(cert.ValidationMethod, "DNS");
    assert.ok(cert.DomainValidationOptions.every((o: any) => o.HostedZoneId === ZONA));
  });

  test("una distribución para la web y otra para administración, cada una con su nombre", () => {
    const alias = distribuciones(CON_DOMINIO).map((d) => d.Aliases).sort();
    assert.deepEqual(alias, [[ADMIN], [WEB]]);
  });
});

describe("pila de la web sin dominio", () => {
  const { web } = sintetizar();

  test("usa las direcciones gratuitas de CloudFront: sin certificado, zona ni registros", () => {
    web.resourceCountIs("AWS::CertificateManager::Certificate", 0);
    web.resourceCountIs("AWS::Route53::RecordSet", 0);
    web.resourceCountIs("AWS::Route53::HostedZone", 0);
    assert.ok(distribuciones().every((d) => d.Aliases === undefined));
  });
});

describe("orígenes de la web", () => {
  const { web } = sintetizar(CON_DOMINIO);
  const [config] = distribuciones(CON_DOMINIO).filter((d) => d.Aliases[0] === WEB);

  test("la web es una función con imagen de contenedor y dirección propia", () => {
    const imagenes = propiedades(web, "AWS::Lambda::Function").filter((f) => f.PackageType === "Image");
    assert.equal(imagenes.length, 1);
    assert.deepEqual(imagenes[0].Architectures, ["arm64"]);
    web.resourceCountIs("AWS::Lambda::Url", 1);
  });

  test("los estáticos salen de un bucket privado por OAC, con caché larga", () => {
    const [bucket] = propiedades(web, "AWS::S3::Bucket");
    assert.deepEqual(bucket.PublicAccessBlockConfiguration, {
      BlockPublicAcls: true, BlockPublicPolicy: true, IgnorePublicAcls: true, RestrictPublicBuckets: true,
    });
    const [oac] = propiedades(web, "AWS::CloudFront::OriginAccessControl");
    assert.equal(oac.OriginAccessControlConfig.OriginAccessControlOriginType, "s3");
    const estaticos = comportamiento(config, "/_next/static/*");
    assert.equal(estaticos.CachePolicyId, CACHE_LARGA);
    assert.deepEqual(estaticos.AllowedMethods, ["GET", "HEAD"]);
  });

  test("si un estático no está en el bucket, lo sirve la función de la web", () => {
    const [grupo] = config.OriginGroups.Items;
    assert.deepEqual(grupo.FailoverCriteria.StatusCodes.Items.sort(), [403, 404]);
    assert.equal(comportamiento(config, "/_next/static/*").TargetOriginId, grupo.Id);
  });

  test("/api/v1/* va a la API sin caché y admite escrituras", () => {
    const api = comportamiento(config, "/api/v1/*");
    assert.equal(api.CachePolicyId, SIN_CACHE);
    assert.ok(api.AllowedMethods.includes("POST") && api.AllowedMethods.includes("DELETE"));
    assert.equal(api.ViewerProtocolPolicy, "redirect-to-https");
  });

  test("lo demás va a la función de la web, sin caché", () => {
    assert.equal(config.DefaultCacheBehavior.CachePolicyId, SIN_CACHE);
    assert.notEqual(config.DefaultCacheBehavior.TargetOriginId, comportamiento(config, "/api/v1/*").TargetOriginId);
  });
});

describe("administración", () => {
  const configs = distribuciones(CON_DOMINIO);
  const admin = configs.find((d) => d.Aliases[0] === ADMIN);
  const web = configs.find((d) => d.Aliases[0] === WEB);

  test("las pantallas actuales van a la misma API, sin caché", () => {
    assert.equal(admin.DefaultCacheBehavior.CachePolicyId, SIN_CACHE);
    assert.ok(admin.DefaultCacheBehavior.AllowedMethods.includes("POST"));
    const dominioApi = (d: any, id: string) => JSON.stringify(d.Origins.find((o: any) => o.Id === id).DomainName);
    assert.equal(dominioApi(admin, admin.DefaultCacheBehavior.TargetOriginId),
      dominioApi(web, comportamiento(web, "/api/v1/*").TargetOriginId));
  });
});

describe("contexto del dominio", () => {
  test("dominio y zonaId van juntos", () => {
    assert.throws(() => sintetizar({ dominio: DOMINIO }), /zonaId/);
    assert.throws(() => sintetizar({ zonaId: ZONA }), /dominio/);
  });

  test("un contexto mal partido se detiene en vez de publicar sin dominio", () => {
    // Lo que llega cuando la terminal no parte "$CTX" en palabras (zsh): una sola clave con espacios
    assert.throws(() => sintetizar({ "-c dominio": `${DOMINIO} -c zonaId=${ZONA}` }), /contexto/);
    assert.throws(() => sintetizar({ "dominio ": DOMINIO }), /contexto/);
  });

  test("el subdominio sale de -c subdominio y por omisión es software", () => {
    const { web } = sintetizar({ ...CON_DOMINIO, subdominio: "pruebas" });
    const nombres = new Set(propiedades(web, "AWS::Route53::RecordSet").map((r) => r.Name));
    assert.deepEqual([...nombres].sort(), [`admin.pruebas.${DOMINIO}.`, `pruebas.${DOMINIO}.`]);
  });

  test("el subdominio nunca es www, ni vacío, ni otra cosa que una etiqueta", () => {
    for (const malo of ["www", "WWW", "", " ", "a.b", "-x", "con espacio"]) {
      assert.throws(() => sintetizar({ ...CON_DOMINIO, subdominio: malo }), /subdominio/, `debe rechazar «${malo}»`);
    }
  });
});
