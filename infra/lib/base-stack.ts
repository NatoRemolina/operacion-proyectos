import { CfnOutput, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as budgets from "aws-cdk-lib/aws-budgets";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subs from "aws-cdk-lib/aws-sns-subscriptions";
import { Construct } from "constructs";

/**
 * Recursos con estado. Se despliegan una vez y casi nunca cambian.
 * Uso: npx cdk deploy OperacionBase -c correo=persona@ejemplo.com
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

    const correo = this.node.tryGetContext("correo") as string | undefined;
    if (correo) {
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
    }

    new CfnOutput(this, "SecretoArn", { value: this.secreto.secretArn });
  }
}
