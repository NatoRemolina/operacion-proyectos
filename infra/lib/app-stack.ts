import { CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from "aws-cdk-lib";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as acciones from "aws-cdk-lib/aws-cloudwatch-actions";
import * as events from "aws-cdk-lib/aws-events";
import * as destinos from "aws-cdk-lib/aws-events-targets";
import { Platform } from "aws-cdk-lib/aws-ecr-assets";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sns from "aws-cdk-lib/aws-sns";
import { Construct } from "constructs";
import { spawnSync } from "node:child_process";
import * as path from "node:path";
import { dominioDesdeContexto } from "./dominio";

/**
 * Lo que entraría en la imagen de la API sin estar en el commit: archivos nuevos de app/ y datos/ que git no ignora
 * (por ejemplo, una respuesta del buscador pagada y sin revisar) y cambios sin guardar, preparados o no, en lo que
 * copia el Dockerfile. Fuera de git, nada que comparar.
 */
export function sinVersionar(raiz: string): string[] {
  const git = (...args: string[]) => {
    const r = spawnSync("git", args, { cwd: raiz, encoding: "utf-8" });
    return r.error || r.status !== 0 ? [] : r.stdout.split("\n").filter(Boolean);
  };
  const nuevos = git("ls-files", "--others", "--exclude-standard", "--", "app", "datos");
  const cambiados = git("diff", "--name-only", "HEAD", "--", "app", "datos", "requirements.txt", "requirements.lock", "Dockerfile");
  return [...new Set([...nuevos, ...cambiados])];
}

/**
 * Concurrencia reservada de la API: un pico o un ataque no se lleva la de toda la cuenta (400), y deja libre la del
 * analizador, Tareas y la web. El guion de despliegue la lee de la salida `ConcurrenciaReservada` para quitar la pausa.
 */
export const CONCURRENCIA_API = 20;

/**
 * Rechazos (Throttles) de una función y una duración máxima que pasa del 85 % de su plazo; con `errores`, también sus
 * fallos. Todas avisan al tema de OperacionBase. La usan la API (analizador y Tareas) y la web.
 */
export function vigilarFuncion(pila: Construct, nombre: string, funcion: lambda.IFunction, plazo: Duration,
  aviso: cloudwatch.IAlarmAction, { errores }: { errores: boolean }) {
  const periodo = Duration.minutes(5);
  const alarma = (id: string, metrica: cloudwatch.IMetric, umbral: number) =>
    new cloudwatch.Alarm(pila, `${id}${nombre}`, {
      metric: metrica, threshold: umbral, evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(aviso);
  if (errores) alarma("Fallos", funcion.metricErrors({ period: periodo }), 1);
  alarma("Rechazos", funcion.metricThrottles({ period: periodo }), 1);
  alarma("CercaDelPlazo", funcion.metricDuration({ period: periodo, statistic: "Maximum" }), Math.round(plazo.toMilliseconds() * 0.85));
}

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
    // Con dominio, la web es la única interfaz: las pantallas anteriores llevan a su equivalente en la web
    const origenesWeb: Record<string, string> = dominio
      ? { ORIGENES_WEB: `https://${dominio.web}`, INTERFAZ_ANTIGUA: "redirige" }
      : {};

    const registro = new logs.LogGroup(this, "Registro", {
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Al empaquetar para desplegar, se despliega desde una carpeta limpia: nada sin versionar viaja a la imagen
    const raiz = path.join(__dirname, "..", "..");
    const sobran = this.bundlingRequired ? sinVersionar(raiz) : [];
    if (sobran.length) {
      throw new Error(`Hay archivos sin versionar o con cambios sin guardar que entrarían en la imagen de la API: ${sobran.join(", ")}. `
        + "Despliega desde una carpeta de trabajo limpia (git worktree) o decide si se versionan (docs/despliegue.md).");
    }

    const web = new lambda.DockerImageFunction(this, "Web", {
      code: lambda.DockerImageCode.fromImageAsset(raiz, { platform: Platform.LINUX_ARM64 }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 2048,
      timeout: Duration.seconds(180),
      reservedConcurrentExecutions: CONCURRENCIA_API,
      logGroup: registro,
      // Solo el ARN: el valor del secreto se lee al arrancar, nunca queda en la plantilla.
      environment: { SECRETO_ARN: props.secreto.secretArn, ENTORNO: "nube", ...origenesWeb },
    });
    props.secreto.grantRead(web);

    // Analizador de la página del vuelo en Google Flights: su propia imagen (Playwright), sin secretos ni base. Solo la
    // API lo invoca, una lectura a la vez y con un minuto como máximo. «Una a la vez» lo garantiza la API con un cerrojo
    // en la base: sin concurrencia reservada, que haría fallar el despliegue en una cuenta con límite bajo.
    // `ANALIZADOR=apagado` lo desactiva sin desplegar código nuevo (variable de la función de la API o del analizador).
    const analizador = new lambda.DockerImageFunction(this, "Analizador", {
      code: lambda.DockerImageCode.fromImageAsset(path.join(raiz, "analizador"), {
        platform: Platform.LINUX_ARM64,
        target: "produccion",   // sin herramientas de prueba
        entrypoint: ["python", "-m", "awslambdaric"],
        cmd: ["analizador.lambda_handler.handler"],
      }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 2048,   // Chromium con una página pesada; menos memoria también es menos CPU en Lambda
      timeout: Duration.seconds(60),
      logGroup: new logs.LogGroup(this, "RegistroAnalizador", {
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      environment: { ANALIZADOR: "encendido", HOME: "/tmp" },
    });
    analizador.grantInvoke(web);
    web.addEnvironment("ANALIZADOR_FUNCION", analizador.functionName);

    // Trabajador de capturas (pieza 5): la imagen de la API con otro punto de entrada. El adaptador web de Lambda
    // reenvía el evento programado (no HTTP) a `POST /events` de `app/tareas.py`, que toma de a una las capturas
    // pendientes con el turno del analizador. Su propio rol: leer el secreto e invocar al analizador. Sin dirección.
    const tareas = new lambda.DockerImageFunction(this, "Tareas", {
      code: lambda.DockerImageCode.fromImageAsset(raiz, {
        platform: Platform.LINUX_ARM64,
        cmd: ["sh", "-c", "exec uvicorn app.tareas:aplicacion --host 0.0.0.0 --port ${PORT}"],
      }),
      architecture: lambda.Architecture.ARM_64,
      memorySize: 1024,
      timeout: Duration.minutes(15),   // hasta 10 capturas por corrida; app/tareas.py no empieza una sin margen
      logGroup: new logs.LogGroup(this, "RegistroTareas", {
        retention: logs.RetentionDays.ONE_MONTH,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      environment: {
        SECRETO_ARN: props.secreto.secretArn, ENTORNO: "nube", TAREAS: "capturas",
        ANALIZADOR_FUNCION: analizador.functionName,
      },
    });
    props.secreto.grantRead(tareas);
    analizador.grantInvoke(tareas);
    new events.Rule(this, "CapturasCadaQuinceMinutos", {
      schedule: events.Schedule.rate(Duration.minutes(15)),
      targets: [new destinos.LambdaFunction(tareas, { retryAttempts: 0 })],   // la cola reintenta; EventBridge no
    });

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
    alarma("FallosDelTrabajador", tareas.metricErrors({ period: Duration.minutes(15) }), 1);
    // Analizador y Tareas: rechazos (sin turno) y una duración que roza el plazo (al pasarlo, Lambda corta sin aviso)
    vigilarFuncion(this, "Analizador", analizador, Duration.seconds(60), aviso, { errores: true });
    vigilarFuncion(this, "Tareas", tareas, Duration.minutes(15), aviso, { errores: false });   // los fallos ya los ve FallosDelTrabajador

    // Con el adaptador web, un 500 de la aplicación es una invocación correcta para Lambda: FallosDeLaFuncion no lo
    // ve. Se cuentan los errores que la propia aplicación escribe (app/web.py) y las respuestas 5xx de la dirección.
    const errores = new logs.MetricFilter(this, "ErroresEnElRegistro", {
      logGroup: registro,
      filterPattern: logs.FilterPattern.literal('"ERROR peticion="'),
      metricNamespace: "Operacion",
      metricName: "ErroresDeLaAplicacion",
      metricValue: "1",
    });
    alarma("ErroresDeLaAplicacion", errores.metric({ period: Duration.minutes(5), statistic: "Sum" }), 1);

    // Cuando el asesor del asistente cae, la página responde bien con otra vía: ni los 5xx ni los errores lo ven.
    // app/servicios/asesor.py escribe una línea por cada pregunta que no respondió (configuración mal escrita incluida).
    const caidas = new logs.MetricFilter(this, "CaidasDelAsesorEnElRegistro", {
      logGroup: registro,
      filterPattern: logs.FilterPattern.literal('"AVISO asesor_caida"'),
      metricNamespace: "Operacion",
      metricName: "CaidasDelAsesor",
      metricValue: "1",
    });
    // Con poco tráfico (unas preguntas por hora) una ventana corta no junta caídas: 2 en una hora ya no es casualidad
    alarma("CaidasDelAsesor", caidas.metric({ period: Duration.hours(1), statistic: "Sum" }), 2);
    alarma("Respuestas5xx", vivo.metric("Url5xxCount", { period: Duration.minutes(5), statistic: "Sum" }), 1);

    new CfnOutput(this, "Url", { value: url.url });
    new CfnOutput(this, "Funcion", { value: web.functionName });
    new CfnOutput(this, "ConcurrenciaReservada", { value: String(CONCURRENCIA_API) });
    new CfnOutput(this, "FuncionAnalizador", { value: analizador.functionName });
    new CfnOutput(this, "FuncionTareas", { value: tareas.functionName });
  }
}
