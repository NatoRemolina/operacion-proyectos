# Despliegue en AWS

Orden completo para publicar o actualizar la plataforma: respaldo, migración, secreto, revisión del cambio, despliegue, Telegram, comprobaciones y vuelta atrás. **Cada paso que escribe en AWS o en la base publicada lo aprueba la responsable del proyecto antes de correrlo**, y el `cdk diff` del paso 4 se le muestra completo.

**Solo se publica desde la punta de `dev`.** Todo se une antes en `dev`, y el despliegue sale de una carpeta limpia en su último commit. El guion `make desplegar` (abajo) lo exige: cualquier otro commit o rama se rechaza. Antes de pedir la aprobación, se muestra una página con el recorrido de lo que entra.

Las tres pilas de `infra/`:

| Pila | Qué tiene | Salidas |
|---|---|---|
| `OperacionBase` | El secreto con la configuración y el tema de avisos con la suscripción por correo | `SecretoArn` |
| `OperacionApp` | La API (FastAPI y pantallas Jinja) en una función con su dirección y 20 de concurrencia reservada; el analizador de Google Flights; el trabajador Tareas con su regla de EventBridge; y sus alarmas | `Url`, `Funcion`, `ConcurrenciaReservada`, `FuncionAnalizador`, `FuncionTareas` |
| `OperacionWeb` | La web nueva y administración detrás de CloudFront (con WAF si se pide), el bucket de estáticos, el certificado, los registros de los dos subdominios (ADR 0002) y las alarmas de la web y de CloudFront | `UrlWeb`, `UrlAdmin`, `FuncionWeb`, `BucketEstaticos` |

### Qué hay en cada pila

- **API** (`OperacionApp`, función `Web`): la imagen de la raíz del repositorio, arm64, 2 GB y 180 s. Reserva **20 de concurrencia** de las 400 de la cuenta: un pico o un ataque no se lleva la del resto. El guion de despliegue la pausa con 0 y la devuelve con el valor de la salida `ConcurrenciaReservada`.
- **Analizador** (`OperacionApp`, función `Analizador`): lee la página del vuelo en Google Flights con Playwright. Imagen propia (`analizador/Dockerfile`, etapa `produccion`), arm64, 2 GB y 60 s, sin secretos ni base y sin dirección: solo lo invocan la API y Tareas. «Una lectura a la vez» la garantiza la API con un cerrojo en la base. `ANALIZADOR=apagado` en su función o en la de la API lo desactiva sin desplegar.
- **Tareas** (`OperacionApp`, función `Tareas`): la imagen de la API con otro punto de entrada (`app.tareas`). Una regla de EventBridge la llama cada 15 minutos, sin reintentos, y toma de a una las capturas de evidencia pendientes. Lee el secreto e invoca al analizador; nada más. 15 minutos como máximo.
- **El borde** (`OperacionWeb`):
  - **Cabecera secreta.** CloudFront añade `X-Origen-CloudFront` a todo lo que manda a la API (web y administración), con el valor de `ORIGEN_SECRETO` del secreto, resuelto al desplegar (no queda en la plantilla). Con ella la API rechaza lo que llega directo a su dirección. `poblar_secreto` la genera si falta; cambiarla exige volver a desplegar `OperacionWeb`.
  - **WAF**, solo con `-c waf=1` (`make desplegar ARGS=--waf`): cuesta unos 7 USD al mes (5 por la lista de reglas y 1 por regla) y el presupuesto de la cuenta es de 5, así que viene apagado. Una sola lista para las dos distribuciones: 20 intentos de ingreso cada 5 minutos por dirección IP (POST a `/api/v1/auth/login` y a `/entrar`) y 2000 peticiones en general. Al pasarlas responde 429 con el JSON de error del contrato (`RATE_LIMITED`), que la web muestra como «ocupado». El plan gratuito de tarifa plana de CloudFront no sirve: cubre una sola distribución y no admite el grupo de orígenes ni políticas de cabeceras propias.
  - **Cabeceras**: HSTS de un año con subdominios en todo; la web y sus estáticos además con nosniff, marco propio y Referrer-Policy. La CSP de la web la pone Next (`web/src/config/cabeceras.ts`); la API y administración traen las suyas (`app/web.py`).

### Alarmas

Todas avisan al tema de `OperacionBase` (la suscripción por correo hay que confirmarla).

| Qué | Alarmas | Avisa con |
|---|---|---|
| API | `FallosDeLaFuncion`, `PeticionesRechazadas`, `Lentitud` (p95), `ErroresDeLaAplicacion` (líneas `ERROR peticion=`), `Respuestas5xx`, `CaidasDelAsesor` | 1 en 5 minutos (p95 de 20 s dos veces; 2 caídas del asesor en una hora) |
| Analizador | `FallosAnalizador`, `RechazosAnalizador`, `CercaDelPlazoAnalizador` | 1 en 5 minutos; duración máxima de 51 s (85 % de 60) |
| Tareas | `FallosDelTrabajador`, `RechazosTareas`, `CercaDelPlazoTareas` | 1 por corrida; duración máxima de 12,75 minutos (85 % de 15) |
| Función de la web | `FallosWeb`, `RechazosWeb`, `CercaDelPlazoWeb`, `Respuestas5xxWeb` | 1 en 5 minutos; duración máxima de 25,5 s (85 % de 30) |
| CloudFront | `Tasa5xxWeb`, `Tasa5xxAdmin` | 10 % de respuestas 5xx sostenido 10 minutos (con poco tráfico, un 504 suelto es mucho porcentaje) |

Mientras dura la pausa del despliegue, cada petición a la API o a Tareas es un rechazo: el guion silencia esas alarmas y las vuelve a activar al quitar la pausa.

**Lo que es de la cuenta y CDK no crea ni borra:** la zona de Route 53 de `nataliaremolinarodriguez.com` (`Z0731422246SUYEGG2Z5R`), con el dominio raíz y `www` reservados para otro sitio, y el presupuesto de la cuenta «cuenta-mensual» (5 USD al mes, avisos al 50, 80 y 100 % y al pronóstico, por correo). Las pilas no crean otro presupuesto, para no repetir avisos.

## Antes de empezar

**Dos carpetas.** Todo el código que corre (respaldo, migración, secreto y CDK) es el **del commit que se publica**, en una carpeta limpia. El entorno de Python y los archivos `.env.*` (fuera de git) están solo en la carpeta principal y se usan con su ruta completa:

```
PRINCIPAL=/Users/nato/Documents/GitHub/inflight-prueba-tecnica      # .venv y archivos .env.* (fuera de git)
PUBLICAR=/Users/nato/Documents/GitHub/inflight-publicar             # carpeta limpia del commit que se publica
PY="$PRINCIPAL/.venv/bin/python"
DOTENV="$PRINCIPAL/.venv/bin/dotenv"
COMMIT=$(git -C "$PRINCIPAL" rev-parse dev)                         # el commit que se publica (dev ya avanzado)
git -C "$PRINCIPAL" worktree add --detach "$PUBLICAR" "$COMMIT"
cd "$PUBLICAR"
```

Cada paso dice dónde corre, y todos van en la misma terminal (usan estas variables). En `$PUBLICAR` no hay `.env`: la configuración de desarrollo no puede completar nada de lo que falte en los archivos indicados.

- **Por qué una carpeta limpia:** a la imagen de la API solo entran `requirements.txt`, `app/` y `datos/` (`.dockerignore`), y la web sale de `web/`. Si en `app/` o `datos/` hay algo sin versionar (por ejemplo, una respuesta del buscador pagada y sin revisar), o un cambio sin guardar en un commit en `app/`, `datos/`, `requirements.txt` o `Dockerfile`, la síntesis de `OperacionApp` se detiene y lo nombra.
- **Docker en marcha:** CDK construye en este equipo las dos imágenes y los estáticos de la web.
- **Credenciales de AWS de la cuenta**, región `us-east-1`: `export AWS_PROFILE=operacion AWS_REGION=us-east-1` (sin la región, las órdenes de `aws` fallan si el perfil no la trae) y `aws sts get-caller-identity` para ver la cuenta. La cuenta ya tiene el *bootstrap* de CDK de despliegues anteriores; en una cuenta nueva se hace una vez, con `(cd infra && npx cdk bootstrap aws://<cuenta>/us-east-1)`.
- **Archivos locales, fuera de git, en `$PRINCIPAL`:**
  - `.env.supabase-publicada`: la base publicada por el agrupador de **sesión (puerto 5432)**, para el respaldo y la migración (`docs/respaldo.md`).
  - `.env.produccion`: lo que va al secreto. La misma base, el almacenamiento, el buscador, el modelo, el asesor, Pinecone y Telegram. `ORIGENES_WEB` solo hace falta si se publica sin dominio (paso 5).
- **El contexto de CDK, igual en todas las órdenes** (el correo es obligatorio: sin él la síntesis se detiene). Va en un arreglo, que se expande igual en zsh y en bash; reemplazar `CORREO_DE_AVISOS`:
  ```
  CDK_CTX=(-c correo=CORREO_DE_AVISOS -c dominio=nataliaremolinarodriguez.com -c zonaId=Z0731422246SUYEGG2Z5R)
  ```
  y en cada orden `"${CDK_CTX[@]}"`. Una sola cadena (`CDK_CTX="-c …"` usada como `$CDK_CTX`) no se parte en zsh, la terminal de macOS: CDK recibiría una clave rara y la pila se detiene avisándolo. El subdominio es `software` por omisión (`-c subdominio=` lo cambia; nunca puede ser `www`). Sin `-c dominio` ni `-c zonaId`, la web queda en las direcciones gratuitas `https://<id>.cloudfront.net`.

## Con el guion: `make desplegar`

En la carpeta de publicación (la punta de `dev`, limpia), con Docker en marcha y la sesión de AWS abierta:

```
CORREO_AVISOS=<correo de avisos> make desplegar ARGS=--ensayo     # comprueba y muestra el plan; no cambia nada
CORREO_AVISOS=<correo de avisos> make desplegar                   # despliega
```

Opciones en `ARGS`: `--ensayo`, `--sin-telegram`, `--waf` y `--sin-dominio`. El guion (`scripts/desplegar.zsh`):

1. **Comprueba** que el commit sea la punta de `dev` y la carpeta esté limpia (si no, se detiene y dice por qué), que Docker esté en marcha, la sesión de AWS (y exporta sus credenciales para boto3, sin escribirlas en ningún archivo ni en el registro), el entorno de Python y los archivos `.env.*` de `$PRINCIPAL`.
2. **Pausa la API y Tareas** (concurrencia 0) y silencia sus alarmas de rechazos, antes del respaldo y la migración.
3. **Respaldo, migración y comprobación** de la base publicada (pasos 1 y 2: la migración pide escribir el identificador del proyecto), y la **configuración del secreto** (paso 3).
4. **Muestra el `cdk diff`** de las tres pilas y espera que se escriba «si».
5. **Despliega** `OperacionBase`, `OperacionApp` y `OperacionWeb`, **quita la pausa** (la API vuelve a su concurrencia reservada) y **comprueba** la salud de administración, la web y la API por CloudFront, que la web obligue HTTPS, las redirecciones de las pantallas anteriores y que la dirección directa de la API ya no atienda sin CloudFront.
6. **Registra todo** en `~/Respaldos/operacion-proyectos/despliegue_<fecha>.log`.

Antes de cada paso que escribe pide escribir «si». Si algo falla con la API en pausa, la deja en pausa (la base puede estar a medio migrar) y dice cómo quitarla cuando se decida. El webhook de Telegram (paso 6) sigue siendo a mano: el guion muestra la orden al final.

Los pasos de abajo son lo que hace el guion, con lo que hay que mirar en cada uno; sirven de referencia o para hacerlo a mano.

## 1. Respaldo

**En `$PUBLICAR`.** Con la aplicación en reposo, copiar la base publicada y ensayar su restauración (`docs/respaldo.md`, pasos 1 a 4):

```
"$PY" -m datos.respaldar respaldar --env "$PRINCIPAL/.env.supabase-publicada"
"$PY" -m datos.respaldar verificar --respaldo ~/Respaldos/operacion-proyectos/AAAA-MM-DD_HHMM \
  --env "$PRINCIPAL/.env.supabase-pruebas" --base restauracion_AAAAMMDD
```

La migración del paso 2 exige un respaldo **de esa misma base y de las últimas 6 horas**, con sus huellas intactas.

## 2. Migración (puerto 5432)

**En `$PUBLICAR`**, con el código del commit que se publica:

```
"$DOTENV" -f "$PRINCIPAL/.env.supabase-publicada" run -- "$PY" -m datos.semilla
"$DOTENV" -f "$PRINCIPAL/.env.supabase-publicada" run -- "$PY" -m datos.comprobar_supabase
```

`dotenv run` carga el archivo indicado por encima del entorno, y en `$PUBLICAR` no hay `.env` que complete nada. Sobre una base que no es local, la semilla:

1. dice el destino (proyecto, servidor y base, sin la contraseña) y avisa si es la base publicada;
2. se detiene si la conexión va por el puerto 6543: el agrupador de transacción es para la función, no para migrar;
3. busca en `~/Respaldos/operacion-proyectos/` el respaldo reciente de esa base y comprueba sus huellas;
4. pide escribir el identificador del proyecto (o `--confirmar <proyecto>` en la orden). Con cualquier otra respuesta no migra nada.

`comprobar_supabase` debe terminar con código 0. La migración se puede repetir: lo que ya hizo no lo vuelve a hacer (`docs/datos.md`, «Migración»). En PostgreSQL corre en una sola transacción: si falla, no queda nada a medias y se repite. Las tablas, columnas y reglas que añade cada versión están en esa misma sección.

## 3. Secreto

**En `$PUBLICAR`**, con el código del commit que se publica:

```
"$PY" infra/poblar_secreto.py --env "$PRINCIPAL/.env.produccion" --ensayo
"$PY" infra/poblar_secreto.py --env "$PRINCIPAL/.env.produccion"
```

Sin Telegram, las dos órdenes llevan `--sin-telegram`:

```
"$PY" infra/poblar_secreto.py --env "$PRINCIPAL/.env.produccion" --sin-telegram --ensayo
"$PY" infra/poblar_secreto.py --env "$PRINCIPAL/.env.produccion" --sin-telegram
```

En la salida, mirar la línea de las claves que se conservan del secreto: si trae `TELEGRAM_*` de antes, Telegram seguiría activo con esas claves.

Si ni el archivo ni el secreto traen `ORIGEN_SECRETO` (la cabecera de CloudFront hacia la API), la carga la genera; una que ya está no se cambia. El ensayo muestra las claves que subiría, sin valores y sin contactar AWS. **Exige `TELEGRAM_BOT_TOKEN` y `TELEGRAM_WEBHOOK_SECRETO` en el archivo** (los del bot de producción) y se detiene si falta alguno: el paso 6 registra el webhook con ese mismo archivo, así el secreto de la función y el del webhook son iguales. Si Telegram no se publica ahora, se agrega `--sin-telegram` a las dos órdenes: no exige esas claves, no toca las que ya tenga el secreto, y el paso 6 se salta. La carga de verdad lee el secreto de `OperacionBase`, reemplaza las claves que el archivo trae con valor, conserva las demás y retira `APP_CLAVE`. Revisa la forma de lo escrito a mano y no sube nada si algo está mal: la versión del agente es un entero, las cabeceras son JSON, las direcciones van por HTTPS y el secreto del webhook es largo. Lo revisa en el archivo y en lo que queda tras la fusión, porque un valor viejo mal escrito que el archivo no reemplaza también detiene la carga. Avisa si `ASESOR_AGENTE_VERSION`, en el archivo o en lo que queda del secreto, fuerza otra versión que la del candado `app/asesor_agente.json`. Una clave vacía en el archivo no borra la del secreto: para retirar una opcional se agrega `--quitar CLAVE` a la orden (por ejemplo `--quitar ASESOR_AGENTE_VERSION`, para que las sesiones usen la versión del candado). Se niega a subir el proyecto de pruebas de Supabase, que reconoce por `$PRINCIPAL/.env.supabase-pruebas` (sin ese archivo no sigue). La base va al agrupador de transacción (6543). Si `OperacionBase` no existiera aún (cuenta nueva), se despliega primero (paso 5) y se vuelve aquí.

## 4. Revisión del cambio, aprobada por la responsable del proyecto

**En `$PUBLICAR`.** CDK corre dentro de `infra/`, en una subcapa para no cambiar de carpeta:

```
(cd infra && npm ci)
(cd infra && npx cdk diff OperacionBase OperacionApp OperacionWeb "${CDK_CTX[@]}")
```

Qué debe mostrar en el despliegue de la estabilización (además de las imágenes nuevas):

- **OperacionBase:** las exportaciones del ARN del secreto y del tema de avisos, que ahora importa `OperacionWeb`. Nada se reemplaza.
- **OperacionApp:** `ReservedConcurrentExecutions: 20` en la función de la API, la salida `ConcurrenciaReservada` y las alarmas del analizador y de Tareas (`Fallos…`, `Rechazos…`, `CercaDelPlazo…`). La función y su dirección se **actualizan**; si alguna se reemplaza, no se despliega.
- **OperacionWeb:** dos políticas de cabeceras (`CabecerasWeb` y `SoloHsts`) en lugar de la administrada, la cabecera `X-Origen-CloudFront` en el origen de la API de las dos distribuciones (con `{{resolve:secretsmanager:…}}`, nunca el valor), las alarmas de la web y de CloudFront y, solo con `--waf`, la lista de reglas `Cortafuegos` asociada a las dos distribuciones. Ninguna distribución se reemplaza.

Lo que mostraba el primer despliegue, como referencia:

- **OperacionBase:** solo se añade la suscripción por correo al tema de avisos. Hoy la pila no tiene suscripción ni presupuesto (se desplegó sin `-c correo`), así que esta noche no debe aparecer nada más. El secreto no se reemplaza. Si alguna vez se hubiera desplegado OperacionBase con correo desde un commit anterior a `75236e3`, el diff mostraría además que se **borra** `Presupuesto`: sería lo esperado, porque el único presupuesto es «cuenta-mensual».
- **OperacionApp:** la imagen nueva, `ORIGENES_WEB` en la función (`https://software.nataliaremolinarodriguez.com`), los filtros de métrica de las líneas `ERROR peticion=` y `AVISO asesor_caida`, y las alarmas `ErroresDeLaAplicacion`, `Respuestas5xx` y `CaidasDelAsesor`. Se añade también la exportación de la dirección de la API, que importa OperacionWeb, y pueden cambiar los permisos de invocación de la dirección. La función y su dirección se **actualizan**: si el diff dice que alguna se reemplaza, no se despliega.
- **OperacionWeb:** todo nuevo. Un certificado, dos distribuciones, el bucket, la función de la web y cuatro registros: A y AAAA de `software.` y de `admin.software.`. **No debe aparecer** ningún `AWS::Route53::HostedZone` ni ningún registro de `nataliaremolinarodriguez.com` ni de `www`.

Sin la aprobación de la responsable del proyecto sobre este diff, no se sigue.

## 5. Despliegue, una pila a la vez

**En `$PUBLICAR`** (las órdenes de `aws` sirven desde cualquier carpeta):

**Una orden a la vez**, sin pegar el bloque entero: `cdk deploy` pide confirmar los cambios de permisos, y la línea siguiente se tomaría como la respuesta y cancelaría el despliegue. La pausa se quita **después de `OperacionWeb`**: CloudFront empieza a mandar `X-Origen-CloudFront` al desplegarla, y una API que ya la exige rechazaría lo que llegue antes. La reactivación va encadenada al éxito con `&&`: si un despliegue se cancela o CloudFormation vuelve a la versión anterior, la función sigue pausada y no corre contra la base ya migrada.

```
(cd infra && npx cdk deploy OperacionBase --exclusively "${CDK_CTX[@]}")
```
```
(cd infra && npx cdk deploy OperacionApp --exclusively "${CDK_CTX[@]}") && \
FUNCION=$(aws cloudformation describe-stacks --stack-name OperacionApp --query "Stacks[0].Outputs[?OutputKey=='Funcion'].OutputValue" --output text) && \
TAREAS=$(aws cloudformation describe-stacks --stack-name OperacionApp --query "Stacks[0].Outputs[?OutputKey=='FuncionTareas'].OutputValue" --output text) && \
URL_API=$(aws cloudformation describe-stacks --stack-name OperacionApp --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text) && \
aws lambda put-function-concurrency --function-name "$FUNCION" --reserved-concurrent-executions 0   # sigue en pausa
```
```
(cd infra && npx cdk deploy OperacionWeb --exclusively "${CDK_CTX[@]}") && \
aws lambda put-function-concurrency --function-name "$FUNCION" --reserved-concurrent-executions 20 && \
aws lambda delete-function-concurrency --function-name "$TAREAS" && \
curl -s -o /dev/null -w "%{http_code}\n" "https://admin.software.nataliaremolinarodriguez.com/salud"   # 200 (por CloudFront)
```

- **La suscripción por correo** llega como un mensaje de AWS con un enlace: hay que confirmarla, o las alarmas no avisan.
- **La reserva de concurrencia.** La plantilla reserva 20 para la API. La pausa la pone en 0 (la dirección responde 429) y `cdk deploy` no la devuelve, porque la plantilla no cambió: se quita con `aws lambda put-function-concurrency --function-name "$FUNCION" --reserved-concurrent-executions 20` (el valor de la salida `ConcurrenciaReservada`), no con `delete-function-concurrency`, que dejaría la API sin reserva. Tareas no tiene reserva propia: su pausa sí se quita con `delete-function-concurrency`. El primer despliegue con la reserva la aplica CloudFormation y quita la pausa antes de tiempo: el guion vuelve a pausar en cuanto termina `OperacionApp`. Con `-c caliente=1` (una instancia siempre lista, día de demostración) la instancia cabe dentro de la reserva.
- **La primera vez de OperacionWeb** tarda: el certificado se valida por DNS en la zona en unos minutos, y cada distribución de CloudFront tarda de 5 a 15 minutos en quedar lista.
- **Sin dominio**, `ORIGENES_WEB` no la fija la pila: se copia la salida `UrlWeb` en `$PRINCIPAL/.env.produccion` como `ORIGENES_WEB`, se repite el paso 3 y se vuelve a desplegar `OperacionApp`, para que la función arranque con el valor nuevo. Con dominio no hace falta.

## 6. Webhook de Telegram

**En `$PUBLICAR`**, en la misma terminal del paso 5 (usa `$URL_API`):

```
"$DOTENV" -f "$PRINCIPAL/.env.produccion" run -- "$PY" -m datos.telegram_webhook "$URL_API"
"$DOTENV" -f "$PRINCIPAL/.env.produccion" run -- "$PY" -m datos.telegram_webhook --estado
```

El bot apunta a la dirección de la función de la API (`<Url>/telegram/webhook`), no a CloudFront: no depende del DNS ni del plazo de 60 s de las distribuciones (ADR 0002). Por eso, cuando la API exija `X-Origen-CloudFront`, `/telegram/webhook` tiene que quedar fuera de esa exigencia (ya trae su propio secreto); si no, Telegram recibiría 403.

- **Mismo archivo que el paso 3:** `dotenv run` toma del archivo la clave del bot y el secreto del webhook. En `$PUBLICAR` no hay `.env`, así que no pueden salir de la configuración de desarrollo; y el paso 3 ya se detuvo si faltaban.
- **`--estado` debe mostrar** `Entrada registrada: <Url>telegram/webhook` y **ninguna línea «Último error»**. Si aparece un error, no se sigue: lo más común es un secreto distinto en la función y en el webhook. Se repiten los pasos 3 y 6 con el mismo archivo, y se despliega una versión nueva de OperacionApp para que la función relea el secreto.
- **Si Telegram no se publica ahora:** se usó `--sin-telegram` en el paso 3 y este paso se salta entero. Nada del resto depende de Telegram. Si el bot ya tenía un webhook registrado, sigue como estaba.

## 7. Comprobaciones

| Qué | Cómo | Esperado |
|---|---|---|
| API | `curl -s -o /dev/null -w "%{http_code}" "${URL_API}salud"` (directo, sin CloudFront) | 403: la API exige `X-Origen-CloudFront`; el 200 se ve por CloudFront, en la fila de administración |
| Administración | `https://admin.software.nataliaremolinarodriguez.com/salud`, y luego entrar con una cuenta de administración y abrir la bandeja de viajes | 200; la sesión se abre |
| Web | Entrar en `https://software.nataliaremolinarodriguez.com/entrar` con una cuenta real y hacer una escritura (cotizar o cerrar la sesión) | Sin 403: CloudFront reenvía la cookie, `Origin`, `Sec-Fetch-Site` y `X-CSRF-Token` |
| Estáticos | Abrir un archivo de `/_next/static/` de la página | 200, servido desde S3 (cabecera `server: AmazonS3`) |
| Alarma de prueba | `aws cloudwatch set-alarm-state --alarm-name <nombre de ErroresDeLaAplicacion> --state-value ALARM --state-reason "Prueba del despliegue"` (el nombre sale de `aws cloudwatch describe-alarms`) | Llega el correo de aviso. La alarma vuelve sola a OK en el periodo siguiente |
| Telegram (si se publicó) | `--estado` del paso 6, y mandar la foto de un recibo al bot desde un celular | Sin «Último error»; el gasto aparece en la plataforma |
| Concurrencia | `aws lambda get-function-concurrency --function-name "$FUNCION"` | `ReservedConcurrentExecutions: 20` (y Tareas sin reserva) |
| La API solo por CloudFront | `curl -s -o /dev/null -w "%{http_code}" "${URL_API}salud"`, directo a la función | 403, y el guion lo exige: con un 200 falla con «La función acepta peticiones directas: revisa ORIGEN_SECRETO en el secreto y vuelve a desplegar OperacionApp»; por CloudFront, `https://admin.software.nataliaremolinarodriguez.com/salud` sigue en 200 |
| Cabeceras | `curl -sI https://software.nataliaremolinarodriguez.com/entrar` | `strict-transport-security` con `includeSubDomains` y `content-security-policy` |
| Agente del asesor | `"$PY" -m datos.asesor --verificar`, con la configuración del asesor (el agente es el mismo en local y en producción) | Termina con ✓: el agente coincide con el código y con el candado, y su entorno no tiene salida a la red |
| Configuración al arrancar | En el registro de la función, buscar `ERROR peticion=arranque` después del despliegue | Ninguna línea. Si hay, nombra la variable mal escrita; se corrige en `.env.produccion` y se repite el paso 3 |
| Asistente con su asesor | Hacer una pregunta en el asistente de la web y abrir Monitoreo, pestaña «Modelo de lenguaje» | La cifra «Respondió el asesor» cuenta esa pregunta y dice «asesor listo». Si dice otra cosa, el motivo está ahí mismo |

## 8. Vuelta atrás, decidida de antemano

Desde `$PUBLICAR`, como el resto.

| Qué falla | Qué se hace |
|---|---|
| La API | Volver atrás **solo el código** de la API, con la infraestructura del commit nuevo (abajo). La migración no se deshace con esto |
| La web | Las pantallas de administración siguen en `admin.software.`. Si hace falta retirar la web: `(cd infra && npx cdk destroy OperacionWeb "${CDK_CTX[@]}")`, que borra solo lo que creó la pila (distribuciones, certificado, los registros de `software.` y `admin.software.`, el bucket y la función). La zona, el raíz y `www` no se tocan |
| La base | `docs/respaldo.md`, «Vuelta atrás»: guardar el estado fallido, borrar lo que la copia no trae (`"$PY" -m datos.respaldar vuelta-atras`) y restaurar en una sola transacción, con la aplicación detenida (concurrencia 0). Las variables `PG*` se cargan sin imprimirlas con `eval "$("$PY" -m datos.respaldar variables-pg --env <archivo de la publicada>)"` |
| El secreto | Secrets Manager guarda la versión anterior (`AWSPREVIOUS`). Lo más simple es volver a cargar el archivo anterior con el paso 3 |

### Vuelta atrás de la API: solo el código

**No se despliega OperacionApp desde el commit anterior.** Las pilas de ese commit no sirven:

- quitarían la exportación de la dirección de la API que OperacionWeb importa, y CloudFormation rechaza el cambio;
- antes desplegarían su propia OperacionBase, que con `-c correo` crea otro presupuesto («Presupuesto»), y quedarían dos;
- Lambda no conserva las versiones anteriores de la imagen, así que mover el alias `vivo` tampoco sirve.

Se vuelve atrás el código de la API (`app/`, `datos/`, `requirements.txt`, `requirements.lock` y `Dockerfile`) y se mantiene la infraestructura del commit nuevo. Con las variables de «Antes de empezar» (`PRINCIPAL`, `CDK_CTX`) y `URL_API` del paso 5 en la terminal, `NUEVO` el commit publicado que falla y `ANTERIOR` el que funcionaba:

```
VUELTA=/Users/nato/Documents/GitHub/inflight-vuelta-atras
git -C "$PRINCIPAL" worktree add -b vuelta-atras-api "$VUELTA" "$NUEVO"
cd "$VUELTA"
git restore --source="$ANTERIOR" --staged --worktree -- app datos requirements.txt requirements.lock Dockerfile
git commit -m "Vuelta atrás del código de la API a $ANTERIOR"
(cd infra && npm ci)
(cd infra && npx cdk diff OperacionApp --exclusively "${CDK_CTX[@]}")
(cd infra && npx cdk deploy OperacionApp --exclusively "${CDK_CTX[@]}")
curl -s -o /dev/null -w "%{http_code}\n" "${URL_API}salud"        # 200
```

- **`git restore --source`** deja esas carpetas exactamente como en `ANTERIOR`, y **borra** también los archivos que se añadieron después. `git checkout ANTERIOR -- …` los dejaría, y un módulo nuevo de `app/rutas/` se cargaría solo.
- **El commit** es local (rama `vuelta-atras-api`, sin push), y hace falta porque la síntesis de OperacionApp se niega a empaquetar cambios sin versionar.
- **`--exclusively`** despliega solo OperacionApp, sin su dependencia OperacionBase. El `cdk diff` debe mostrar solo el cambio de imagen de la función: ni la exportación, ni las alarmas, ni `ORIGENES_WEB`.
- **La base** queda como la dejó la migración: la versión anterior de la API tiene que funcionar con ese esquema. Si no, primero se vuelve atrás la base (fila «La base»).
- **Comprobación:** `/salud` responde 200, y en `https://admin.software.nataliaremolinarodriguez.com` se entra y se abre la bandeja de viajes. Al terminar, `git -C "$PRINCIPAL" worktree remove "$VUELTA"`; la rama queda como registro de lo publicado.

### Ensayo de la vuelta atrás de la base (14 de noviembre, Supabase de pruebas)

Se ensayó la fila «La base» de la tabla de arriba con datos reales: la copia de la publicada del 12 de noviembre (27 tablas, 3693 filas, el esquema de entonces) restaurada en el proyecto de pruebas, respaldada, migrada con el código de `dev` 7d446d2 (quedó con 36 tablas y `comprobar_supabase` en orden) y vuelta atrás con el procedimiento de `docs/respaldo.md`:

1. `python -m datos.respaldar vuelta-atras --respaldo <respaldo previo a migrar>` generó el SQL: 7 vistas del código y 19 tablas que la copia no trae.
2. Ese SQL en una sola transacción con `psql -v ON_ERROR_STOP=1 --single-transaction`, y `pg_restore --clean --if-exists --single-transaction --exit-on-error` de `base.dump`: 56 segundos en total.
3. La base quedó con 27 tablas y 3693 filas, tabla por tabla iguales al manifiesto.

**Cuidado al repetirlo en otra base:** `datos.respaldar variables-pg` exporta siempre `PGDATABASE=postgres`, que es la base de la publicada. En el ensayo, por eso, el SQL y la restauración corrieron sobre la base principal del proyecto de pruebas y no sobre la base de ensayo, y se perdieron sus datos de demostración. Para ensayar sobre otra base, fijar `PGDATABASE` (o `-d`) a mano y comprobar `select current_database()` antes de borrar o restaurar.

## Imágenes y dependencias fijadas

- **Imágenes por digest** (`Dockerfile`, `web/Dockerfile`, `analizador/Dockerfile`, `docker-compose.yml` y la imagen de reserva de `infra/lib/estaticos.ts`): una etiqueta cambia de contenido sin aviso. Para actualizar una, se mira su digest con `docker buildx imagetools inspect <imagen>:<etiqueta>` (la línea `Digest:` del índice, que sirve para amd64 y arm64), se cambia en el archivo y se construye y prueba antes de unir.
- **Python con bloqueo**: `requirements.lock` (la imagen de la API), `requirements-dev.lock` (integración continua y `make instalar`) y los del analizador, para el Python 3.10 de su imagen. Se instalan con `pip install --require-hashes`. Tras cambiar un `requirements*.txt`, `make bloquear` los regenera partiendo de las versiones ya fijadas (necesita `uv`).
- **Node**: `npm ci` sobre el `package-lock.json` de `web/` e `infra/`.
- `infra/pruebas/test_dependencias_fijadas.py` comprueba todo lo anterior en la integración continua.
