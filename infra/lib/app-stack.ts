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

export interface AppStackProps extends StackProps {
  secreto: secretsmanager.Secret;
  avisos: sns.Topic;
}

/**
 * La aplicación completa en una función con imagen de contenedor y dirección HTTPS propia.
 * Sin cómputo encendido en reposo. `-c caliente=1` mantiene una instancia lista (día de demostración).
 */
export class AppStack extends Stack {
  constructor(scope: Construct, id: string, props: AppStackProps) {
    super(scope, id, props);

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
      environment: { SECRETO_ARN: props.secreto.secretArn, ENTORNO: "nube" },
    });
    props.secreto.grantRead(web);

    const caliente = this.node.tryGetContext("caliente") === "1";
    const vivo = web.addAlias("vivo", { provisionedConcurrentExecutions: caliente ? 1 : undefined });

    // El acceso lo controla la propia aplicación (sesión y roles); la dirección es pública.
    const url = vivo.addFunctionUrl({ authType: lambda.FunctionUrlAuthType.NONE });

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
