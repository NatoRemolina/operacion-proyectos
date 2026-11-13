import { CfnOutput, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as budgets from "aws-cdk-lib/aws-budgets";
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
    // dejaría la plantilla sin suscripción ni presupuesto, y CloudFormation los borraría.
    const correo = String(this.node.tryGetContext("correo") ?? "").trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) {
      throw new Error("Falta el correo de avisos: agrega -c correo=persona@empresa.com a cdk synth, diff o deploy. "
        + "Sin él, CloudFormation borraría la suscripción de las alarmas y el presupuesto.");
    }
    this.avisos.addSubscription(new subs.EmailSubscription(correo));
    new budgets.CfnBudget(this, "Presupuesto", {
      budget: { budgetType: "COST", timeUnit: "MONTHLY", budgetLimit: { amount: 10, unit: "USD" } },
      notificationsWithSubscribers: [
        { notification: { notificationType: "ACTUAL", comparisonOperator: "GREATER_THAN", threshold: 80, thresholdType: "PERCENTAGE" },
          subscribers: [{ subscriptionType: "EMAIL", address: correo }] },
        { notification: { notificationType: "FORECASTED", comparisonOperator: "GREATER_THAN", threshold: 100, thresholdType: "PERCENTAGE" },
          subscribers: [{ subscriptionType: "EMAIL", address: correo }] },
      ],
    });

    new CfnOutput(this, "SecretoArn", { value: this.secreto.secretArn });
  }
}
