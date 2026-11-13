import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as acm from "aws-cdk-lib/aws-certificatemanager";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as targets from "aws-cdk-lib/aws-route53-targets";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { Construct } from "constructs";
import * as path from "node:path";
import { Dominio, dominioDesdeContexto } from "./dominio";
import { EstaticosDeLaWeb, IMAGEN_DE_RESERVA } from "./estaticos";

export interface WebStackProps extends StackProps {
  /** La dirección de función de la API (OperacionApp): atiende `/api/v1/*` y las pantallas de administración. */
  urlApi: lambda.IFunctionUrl;
}

/**
 * La web nueva detrás de un solo origen (ADR 0002), con el mismo patrón del backend.
 *
 * - `<subdominio>.<dominio>` (por omisión `software.`): la web (función con la imagen de `web/`), `/_next/static/*` desde un bucket privado
 *   y `/api/v1/*` hacia la API, sin caché.
 * - `admin.<subdominio>.<dominio>`: las pantallas actuales (Jinja), en la misma API. Comparten rutas con la web
 *   (`/viajes`, `/gastos`), por eso van en otra distribución.
 *
 * Sin `-c dominio`, cada distribución queda en su dirección gratuita `https://<id>.cloudfront.net`.
 */
export class WebStack extends Stack {
  constructor(scope: Construct, id: string, props: WebStackProps) {
    super(scope, id, props);

    const dominio = dominioDesdeContexto(this.node);
    const dirWeb = path.join(__dirname, "..", "..", "web");
    // Se incrustan al compilar la web: la dirección de las pantallas actuales que la web enlaza.
    // Sin dominio no se conoce antes de desplegar, y la web simplemente no ofrece esos enlaces.
    const argumentos = { NEXT_PUBLIC_API_BASE: "/api/v1", NEXT_PUBLIC_PLATAFORMA_URL: dominio ? `https://${dominio.admin}` : "" };

    // ---------- función de la web ----------
    const registro = new logs.LogGroup(this, "Registro", {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const funcion = new lambda.DockerImageFunction(this, "Web", {
      code: lambda.DockerImageCode.fromImageAsset(dirWeb, { platform: Platform.LINUX_ARM64, buildArgs: argumentos }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 1024,
      timeout: Duration.seconds(30),
      logGroup: registro,
    });
    const caliente = this.node.tryGetContext("caliente") === "1";
    const vivo = funcion.addAlias("vivo", { provisionedConcurrentExecutions: caliente ? 1 : undefined });
    // La web no guarda secretos ni datos: lo que muestra lo pide el navegador a /api/v1 con su sesión.
    const urlWeb = vivo.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE });

    // ---------- estáticos ----------
    const estaticos = new s3.Bucket(this, "Estaticos", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      // Se regeneran en cada compilación: borrar la pila no pierde nada
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });
    new s3deploy.BucketDeployment(this, "SubirEstaticos", {
      destinationBucket: estaticos,
      destinationKeyPrefix: "_next/static",
      sources: [s3deploy.Source.asset(dirWeb, {
        exclude: ["node_modules", ".next", "coverage"],
        bundling: { image: IMAGEN_DE_RESERVA, local: new EstaticosDeLaWeb(dirWeb, argumentos) },
      })],
      // Las páginas ya abiertas siguen pidiendo los archivos de la versión anterior: no se borran al desplegar
      prune: false,
      // Llevan la huella del contenido en el nombre: nunca cambian
      cacheControl: [s3deploy.CacheControl.fromString("public, max-age=31536000, immutable")],
      memoryLimit: 512,
    });

    // ---------- distribuciones ----------
    const certificado = dominio ? this.certificado(dominio) : undefined;
    const origenWeb = new origins.FunctionUrlOrigin(urlWeb);
    const origenApi = new origins.FunctionUrlOrigin(props.urlApi);
    // Si un archivo no está en el bucket (403 por OAC) lo sirve la función, que trae los suyos en la imagen
    const origenEstaticos = new origins.OriginGroup({
      primaryOrigin: origins.S3BucketOrigin.withOriginAccessControl(estaticos),
      fallbackOrigin: origenWeb,
      fallbackStatusCodes: [403, 404],
    });
    // Lo dinámico recibe todo lo del navegador salvo Host (la dirección de función exige el suyo): la cookie de
    // sesión, Origin, Sec-Fetch-Site, X-CSRF-Token e Idempotency-Key para la API y los formularios de
    // administración (app/servicios/acceso.py), y la consulta y las cabeceras de navegación de Next para la web.
    // Los estáticos no llevan política: no reciben cookies ni cabeceras.
    const dinamico = (origen: cloudfront.IOrigin): cloudfront.BehaviorOptions => ({
      origin: origen,
      viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
      cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
    });
    const comunes = {
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,   // Norteamérica y Europa, donde opera la empresa
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
      certificate: certificado,
    };

    const web = new cloudfront.Distribution(this, "DistribucionWeb", {
      ...comunes,
      comment: "Web de operacion",
      domainNames: dominio ? [dominio.web] : undefined,
      defaultBehavior: dinamico(origenWeb),
      additionalBehaviors: {
        "/_next/static/*": {
          origin: origenEstaticos,
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        },
        "/api/v1/*": dinamico(origenApi),
      },
    });
    const admin = new cloudfront.Distribution(this, "DistribucionAdmin", {
      ...comunes,
      comment: "Pantallas de administracion",
      domainNames: dominio ? [dominio.admin] : undefined,
      defaultBehavior: dinamico(origenApi),
    });

    if (dominio && certificado) {
      this.registros(dominio, web, admin);
    }

    const direccion = (d: cloudfront.Distribution, nombre?: string) => `https://${nombre ?? d.distributionDomainName}`;
    new CfnOutput(this, "UrlWeb", { value: direccion(web, dominio?.web) });
    new CfnOutput(this, "UrlAdmin", { value: direccion(admin, dominio?.admin) });
    new CfnOutput(this, "FuncionWeb", { value: funcion.functionName });
    new CfnOutput(this, "BucketEstaticos", { value: estaticos.bucketName });
  }

  /** Un certificado en us-east-1 (el que acepta CloudFront) para los dos nombres, validado por DNS en la zona. */
  private certificado(dominio: Dominio): acm.ICertificate {
    if (this.region !== "us-east-1") {
      throw new Error("CloudFront solo acepta certificados de us-east-1: despliega OperacionWeb en esa región.");
    }
    return new acm.Certificate(this, "Certificado", {
      domainName: dominio.web,
      subjectAlternativeNames: [dominio.admin],
      validation: acm.CertificateValidation.fromDns(this.zona(dominio)),
    });
  }

  private zona(dominio: Dominio): route53.IHostedZone {
    return (this.node.tryFindChild("Zona") as route53.IHostedZone | undefined)
      ?? route53.HostedZone.fromHostedZoneAttributes(this, "Zona", { hostedZoneId: dominio.zonaId, zoneName: dominio.raiz });
  }

  /** Alias A y AAAA de los dos subdominios. El raíz y `www` quedan para la página personal de la dueña. */
  private registros(dominio: Dominio, web: cloudfront.Distribution, admin: cloudfront.Distribution) {
    const zona = this.zona(dominio);
    const prohibidos = [dominio.raiz, `www.${dominio.raiz}`];
    for (const [id, nombre, distribucion] of [["Web", dominio.web, web], ["Admin", dominio.admin, admin]] as const) {
      if (prohibidos.includes(nombre)) throw new Error(`La pila no escribe registros en ${nombre}.`);
      const destino = route53.RecordTarget.fromAlias(new targets.CloudFrontTarget(distribucion));
      new route53.ARecord(this, `Registro${id}`, { zone: zona, recordName: nombre, target: destino });
      new route53.AaaaRecord(this, `Registro${id}V6`, { zone: zona, recordName: nombre, target: destino });
    }
  }
}
