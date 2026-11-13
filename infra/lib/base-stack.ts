import { CfnOutput, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subs from "aws-cdk-lib/aws-sns-subscriptions";
import { Construct } from "constructs";

/**
 * Recursos con estado. Se despliegan una vez y casi nunca cambian.
 * Uso: npx cdk deploy OperacionBase -c correo=persona@ejemplo.com (el correo es obligatorio en toda orden de cdk)
 */
export class BaseStack extends Stack {
  public readonly secreto: secretsmanager.Secret;
  public readonly avisos: sns.Topic;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Un solo secreto JSON con toda la configuración sensible. CDK crea el contenedor;
    // los valores se cargan después desde un archivo (infra/poblar_secreto.py), nunca desde el código.
    this.secreto = new secretsmanager.Secret(this, "Configuracion", {
      description: "Configuracion de la aplicacion. Se puebla tras el despliegue.",
      removalPolicy: RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
    });

    this.avisos = new sns.Topic(this, "Avisos", { displayName: "Avisos de la aplicacion" });

    // Sin correo no se sigue: cualquier `cdk deploy` (también el de OperacionApp, que despliega antes esta pila)
    // dejaría la plantilla sin la suscripción, y CloudFormation la borraría.
    const correo = String(this.node.tryGetContext("correo") ?? "").trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) {
      throw new Error("Falta el correo de avisos: agrega -c correo=persona@empresa.com a cdk synth, diff o deploy. "
        + "Sin él, CloudFormation borraría la suscripción de las alarmas.");
    }
    this.avisos.addSubscription(new subs.EmailSubscription(correo));
    // El presupuesto no va aquí: es el de la cuenta («cuenta-mensual», 5 USD al mes con avisos al 50, 80 y 100 % y al
    // pronóstico), creado por la dueña fuera de CDK, como la zona del dominio. Uno solo evita avisos repetidos.

    new CfnOutput(this, "SecretoArn", { value: this.secreto.secretArn });
  }
}
