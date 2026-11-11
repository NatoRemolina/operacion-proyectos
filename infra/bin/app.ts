import { App } from "aws-cdk-lib";
import { BaseStack } from "../lib/base-stack";
import { AppStack } from "../lib/app-stack";

// Dos pilas: lo que tiene estado (secreto, avisos) aparte de lo que se redespliega a menudo (la función).
const app = new App();
const entorno = { account: process.env.CDK_DEFAULT_ACCOUNT, region: "us-east-1" };
const base = new BaseStack(app, "OperacionBase", { env: entorno });
new AppStack(app, "OperacionApp", { env: entorno, secreto: base.secreto, avisos: base.avisos });
