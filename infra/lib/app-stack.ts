import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as acciones from "aws-cdk-lib/aws-cloudwatch-actions";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sns from "aws-cdk-lib/aws-sns";
import { Construct } from "constructs";
import * as path from "node:path";
import { dominioDesdeContexto } from "./dominio";

export interface AppStackProps extends StackProps {
  secreto: secretsmanager.Secret;
  avisos: sns.Topic;
}

/**
 * La aplicación completa en una función con imagen de contenedor y dirección HTTPS propia.
 * Sin cómputo encendido en reposo. `-c caliente=1` mantiene una instancia lista (día de demostración).
 */
export class AppStack extends Stack {
  /** La dirección pública de la función. La web (OperacionWeb) la pone detrás de CloudFront. */
  public readonly url: lambda.FunctionUrl;

  constructor(scope: Construct, id: string, props: AppStackProps) {
    super(scope, id, props);

    // Con dominio, el origen de la web nueva se conoce antes de desplegar y la API lo admite para escribir en /api/v1
    // (app/servicios/acceso.py). Sin dominio la dirección de CloudFront sale al desplegar OperacionWeb y va en el
    // secreto. Una variable de la función prevalece sobre la misma clave del secreto (app/config.py).
    const dominio = dominioDesdeContexto(this.node);
    const origenesWeb: Record<string, string> = dominio ? { ORIGENES_WEB: `https://${dominio.web}` } : {};

    const registro = new logs.LogGroup(this, "Registro", {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const web = new lambda.DockerImageFunction(this, "Web", {
      code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, "..", ".."), { platform: Platform.LINUX_ARM64 }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 2048,
      timeout: Duration.seconds(180),
      logGroup: registro,
      // Solo el ARN: el valor del secreto se lee al arrancar, nunca queda en la plantilla.
      environment: { SECRETO_ARN: props.secreto.secretArn, ENTORNO: "nube", ...origenesWeb },
    });
    props.secreto.grantRead(web);

    const caliente = this.node.tryGetContext("caliente") === "1";
    const vivo = web.addAlias("vivo", { provisionedConcurrentExecutions: caliente ? 1 : undefined });

    // El acceso lo controla la propia aplicación (sesión y roles); la dirección es pública.
    const url = vivo.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE });
    this.url = url;

    const aviso = new acciones.SnsAction(props.avisos);
    const alarma = (nombre: string, metrica: cloudwatch.Metric, umbral: number, periodos = 1) =>
      new cloudwatch.Alarm(this, nombre, {
        metric: metrica, threshold: umbral, evaluationPeriods: periodos,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      }).addAlarmAction(aviso);
    alarma("FallosDeLaFuncion", web.metricErrors({ period: Duration.minutes(5) }), 1);
    alarma("PeticionesRechazadas", web.metricThrottles({ period: Duration.minutes(5) }), 1);
    alarma("Lentitud", web.metricDuration({ period: Duration.minutes(5), statistic: "p95" }), 20000, 2);

    new CfnOutput(this, "Url", { value: url.url });
    new CfnOutput(this, "Funcion", { value: web.functionName });
  }
}
