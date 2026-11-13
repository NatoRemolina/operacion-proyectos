# Despliegue en AWS

Orden completo para publicar o actualizar la plataforma: respaldo, migración, secreto, revisión del cambio, despliegue, Telegram, comprobaciones y vuelta atrás. **Cada paso que escribe en AWS o en la base publicada lo aprueba la dueña antes de correrlo**, y el `cdk diff` del paso 4 se le muestra completo.

Las tres pilas de `infra/`:

| Pila | Qué tiene | Salidas |
|---|---|---|
| `OperacionBase` | El secreto con la configuración y el tema de avisos con la suscripción por correo | `SecretoArn` |
| `OperacionApp` | La API (FastAPI y pantallas Jinja) en una función con su dirección, y sus alarmas | `Url`, `Funcion` |
| `OperacionWeb` | La web nueva y administración detrás de CloudFront, el bucket de estáticos, el certificado y los registros de los dos subdominios (ADR 0002) | `UrlWeb`, `UrlAdmin`, `FuncionWeb`, `BucketEstaticos` |

**Lo que es de la dueña y CDK no crea ni borra:** la zona de Route 53 de `nataliaremolinarodriguez.com` (`Z0731422246SUYEGG2Z5R`), con el dominio raíz y `www` reservados para su página personal, y el presupuesto de la cuenta «cuenta-mensual» (5 USD al mes, avisos al 50, 80 y 100 % y al pronóstico, por correo). Las pilas no crean otro presupuesto, para no repetir avisos.

## Antes de empezar

- **Carpeta de trabajo limpia** en el commit que se publica (`git status` sin cambios; lo más seguro es un `git worktree` nuevo). A la imagen de la API solo entran `requirements.txt`, `app/` y `datos/` (`.dockerignore`), y la web sale de `web/`. Si en `app/` o `datos/` hay algo sin versionar (por ejemplo, una respuesta del buscador pagada y sin revisar), la síntesis de `OperacionApp` se detiene y lo nombra: o se versiona, o se despliega desde otra carpeta.
- **Docker en marcha:** CDK construye en este equipo las dos imágenes y los estáticos de la web.
- **Credenciales de AWS de la dueña**, región `us-east-1`: `export AWS_PROFILE=operacion` y `aws sts get-caller-identity` para ver la cuenta. La cuenta ya tiene el *bootstrap* de CDK de despliegues anteriores; en una cuenta nueva se hace una vez, con `npx cdk bootstrap aws://<cuenta>/us-east-1`.
- **Archivos locales, fuera de git:**
  - `.env.supabase-publicada`: la base publicada por el agrupador de **sesión (puerto 5432)**, para el respaldo y la migración (`docs/respaldo.md`).
  - `.env.produccion`: lo que va al secreto. La misma base, el almacenamiento, el buscador, el modelo, el asesor, Pinecone y Telegram. `ORIGENES_WEB` solo hace falta si se publica sin dominio (paso 5).
- **El contexto de CDK, igual en todas las órdenes** (el correo es obligatorio: sin él la síntesis se detiene):
  ```
  CDK_CTX="-c correo=<correo de avisos> -c dominio=nataliaremolinarodriguez.com -c zonaId=Z0731422246SUYEGG2Z5R"
  ```
  El subdominio es `software` por omisión (`-c subdominio=` lo cambia; nunca puede ser `www`). Sin `-c dominio` ni `-c zonaId`, la web queda en las direcciones gratuitas `https://<id>.cloudfront.net`.

## 1. Respaldo

Con la aplicación en reposo, copiar la base publicada y ensayar su restauración (`docs/respaldo.md`, pasos 1 a 4):

```
make respaldar
make verificar-respaldo RESPALDO=~/Respaldos/operacion-proyectos/AAAA-MM-DD_HHMM BASE=restauracion_AAAAMMDD
```

La migración del paso 2 exige un respaldo **de esa misma base y de las últimas 6 horas**, con sus huellas intactas.

## 2. Migración (puerto 5432)

```
.venv/bin/dotenv -f .env.supabase-publicada run -- .venv/bin/python -m datos.semilla
.venv/bin/dotenv -f .env.supabase-publicada run -- .venv/bin/python -m datos.comprobar_supabase
```

`dotenv run` carga el archivo indicado por encima del entorno; el `.env` de desarrollo solo completa lo que el archivo no trae. Sobre una base que no es local, la semilla:

1. dice el destino (proyecto, servidor y base, sin la contraseña) y avisa si es la base publicada;
2. se detiene si la conexión va por el puerto 6543: el agrupador de transacción es para la función, no para migrar;
3. busca en `~/Respaldos/operacion-proyectos/` el respaldo reciente de esa base y comprueba sus huellas;
4. pide escribir el identificador del proyecto (o `--confirmar <proyecto>` en la orden). Con cualquier otra respuesta no migra nada.

`comprobar_supabase` debe terminar con código 0. La migración se puede repetir: lo que ya hizo no lo vuelve a hacer (`docs/datos.md`, «Migración»).

## 3. Secreto

```
.venv/bin/python infra/poblar_secreto.py --env .env.produccion --ensayo
.venv/bin/python infra/poblar_secreto.py --env .env.produccion
```

El ensayo muestra las claves que subiría, sin valores y sin contactar AWS. La carga de verdad lee el secreto de `OperacionBase`, reemplaza las claves que el archivo trae con valor, conserva las demás y retira `APP_CLAVE`. Se niega a subir el proyecto de pruebas de Supabase. La base va al agrupador de transacción (6543). Si `OperacionBase` no existiera aún (cuenta nueva), se despliega primero (paso 5) y se vuelve aquí.

## 4. Revisión del cambio, aprobada por la dueña

```
cd infra && npm ci
npx cdk diff OperacionBase OperacionApp OperacionWeb $CDK_CTX
```

Qué debe mostrar:

- **OperacionBase:** solo se añade la suscripción por correo al tema de avisos. Hoy la pila no tiene suscripción (se desplegó sin `-c correo`) y no tendrá presupuesto. El secreto no se reemplaza.
- **OperacionApp:** la imagen nueva, `ORIGENES_WEB` en la función (`https://software.nataliaremolinarodriguez.com`), el filtro de métrica de las líneas `ERROR peticion=` y las alarmas `ErroresDeLaAplicacion` y `Respuestas5xx`. La función y su dirección se **actualizan**: si el diff dice que alguna se reemplaza, no se despliega.
- **OperacionWeb:** todo nuevo. Un certificado, dos distribuciones, el bucket, la función de la web y cuatro registros: A y AAAA de `software.` y de `admin.software.`. **No debe aparecer** ningún `AWS::Route53::HostedZone` ni ningún registro de `nataliaremolinarodriguez.com` ni de `www`.

Sin la aprobación de la dueña sobre este diff, no se sigue.

## 5. Despliegue, una pila a la vez

```
npx cdk deploy OperacionBase $CDK_CTX
npx cdk deploy OperacionApp $CDK_CTX
FUNCION=$(aws cloudformation describe-stacks --stack-name OperacionApp --query "Stacks[0].Outputs[?OutputKey=='Funcion'].OutputValue" --output text)
URL_API=$(aws cloudformation describe-stacks --stack-name OperacionApp --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text)
aws lambda delete-function-concurrency --function-name "$FUNCION"
curl -s -o /dev/null -w "%{http_code}\n" "${URL_API}salud"        # 200
npx cdk deploy OperacionWeb $CDK_CTX
```

- **La suscripción por correo** llega como un mensaje de AWS con un enlace: hay que confirmarla, o las alarmas no avisan.
- **La reserva de concurrencia.** La función de la API quedó pausada con concurrencia reservada 0, y por eso su dirección responde 429. La plantilla no define esa reserva, así que `cdk deploy` no la quita: lo hace `delete-function-concurrency`, y `/salud` debe pasar a 200. Para desplegar con `-c caliente=1` (una instancia siempre lista, día de demostración), la reserva se quita antes del `cdk deploy OperacionApp`.
- **La primera vez de OperacionWeb** tarda: el certificado se valida por DNS en la zona en unos minutos, y cada distribución de CloudFront tarda de 5 a 15 minutos en quedar lista.
- **Sin dominio**, `ORIGENES_WEB` no la fija la pila: se copia la salida `UrlWeb` en `.env.produccion` como `ORIGENES_WEB`, se repite el paso 3 y se vuelve a desplegar `OperacionApp`, para que la función arranque con el valor nuevo. Con dominio no hace falta.

## 6. Webhook de Telegram

```
.venv/bin/dotenv -f .env.produccion run -- .venv/bin/python -m datos.telegram_webhook "$URL_API"
.venv/bin/dotenv -f .env.produccion run -- .venv/bin/python -m datos.telegram_webhook --estado
```

El bot apunta a la dirección de la función de la API (`<Url>/telegram/webhook`), no a CloudFront: no depende del DNS ni del plazo de 60 s de las distribuciones (ADR 0002).

## 7. Comprobaciones

| Qué | Cómo | Esperado |
|---|---|---|
| API | `curl -s -o /dev/null -w "%{http_code}" "${URL_API}salud"` | 200 |
| Administración | `https://admin.software.nataliaremolinarodriguez.com/salud`, y luego entrar con una cuenta de administración y abrir la bandeja de viajes | 200; la sesión se abre |
| Web | Entrar en `https://software.nataliaremolinarodriguez.com/entrar` con una cuenta real y hacer una escritura (cotizar o cerrar la sesión) | Sin 403: CloudFront reenvía la cookie, `Origin`, `Sec-Fetch-Site` y `X-CSRF-Token` |
| Estáticos | Abrir un archivo de `/_next/static/` de la página | 200, servido desde S3 (cabecera `server: AmazonS3`) |
| Alarma de prueba | `aws cloudwatch set-alarm-state --alarm-name <nombre de ErroresDeLaAplicacion> --state-value ALARM --state-reason "Prueba del despliegue"` (el nombre sale de `aws cloudwatch describe-alarms`) | Llega el correo de aviso. La alarma vuelve sola a OK en el periodo siguiente |
| Telegram | Mandar la foto de un recibo al bot desde un celular | El gasto aparece en la plataforma |
| Concurrencia | `aws lambda get-function-concurrency --function-name "$FUNCION"` | Sin reserva |

## 8. Vuelta atrás, decidida de antemano

| Qué falla | Qué se hace |
|---|---|
| La API | Volver al commit anterior en una carpeta limpia y `npx cdk deploy OperacionApp $CDK_CTX`. La migración no se deshace con esto |
| La web | Las pantallas de administración siguen en `admin.software.`. Si hace falta retirar la web: `npx cdk destroy OperacionWeb $CDK_CTX`, que borra solo lo que creó la pila (distribuciones, certificado, los registros de `software.` y `admin.software.`, el bucket y la función). La zona, el raíz y `www` no se tocan |
| La base | `docs/respaldo.md`, «Vuelta atrás»: guardar el estado fallido, borrar lo que la copia no trae (`python -m datos.respaldar vuelta-atras`) y restaurar en una sola transacción, con la aplicación detenida |
| El secreto | Secrets Manager guarda la versión anterior (`AWSPREVIOUS`). Lo más simple es volver a cargar el archivo anterior con el paso 3 |
