import { App } from "aws-cdk-lib";
import { crearPilas } from "../lib/pilas";

// OperacionBase (secreto y avisos), OperacionApp (la API) y OperacionWeb (la web y administración en CloudFront).
crearPilas(new App(), { account: process.env.CDK_DEFAULT_ACCOUNT, region: "us-east-1" });
