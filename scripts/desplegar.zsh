#!/bin/zsh
# Despliegue único de la plataforma en AWS (docs/despliegue.md). Corre en una carpeta limpia en la punta de dev:
#
#   git -C <carpeta principal> worktree add --detach <carpeta de publicación> dev
#   cd <carpeta de publicación>
#   CORREO_AVISOS=persona@empresa.com make desplegar ARGS=--ensayo   # comprueba y muestra el plan; no cambia nada
#   CORREO_AVISOS=persona@empresa.com make desplegar                 # despliega; pide escribir «si» antes de cada escritura
#
# Pasos: 1) comprueba la carpeta (punta de dev, sin cambios), Docker, la sesión de AWS y los archivos locales;
# 2) pausa la API y Tareas (concurrencia 0); 3) respaldo, migración (la confirma quien despliega) y comprobación de la
# base, y la configuración del secreto; 4) muestra el cdk diff y espera «si»; 5) despliega Base, App y Web, quita la
# pausa y comprueba la salud y las redirecciones; 6) todo queda en ~/Respaldos/operacion-proyectos/despliegue_<fecha>.log.
#
# Opciones: --ensayo  --sin-telegram  --waf (WAF en CloudFront: unos 7 USD al mes)  --sin-dominio  --ayuda
# Variables: CORREO_AVISOS (obligatoria), AWS_PROFILE (operacion), PRINCIPAL (la carpeta con .venv y los .env.*),
# DOMINIO, ZONA_ID y SUBDOMINIO (los de docs/despliegue.md), RESPALDOS (~/Respaldos/operacion-proyectos).

emulate -L zsh
setopt errexit nounset pipefail

ENSAYO=0 SIN_TELEGRAM=0 WAF=0 SIN_DOMINIO=0
for opcion in "$@"; do
  case $opcion in
    --ensayo) ENSAYO=1 ;;
    --sin-telegram) SIN_TELEGRAM=1 ;;
    --waf) WAF=1 ;;
    --sin-dominio) SIN_DOMINIO=1 ;;
    -h|--ayuda) sed -n '2,17p' "$0" | cut -c3-; exit 0 ;;
    *) print -u2 "Opción desconocida: $opcion (ver --ayuda)."; exit 2 ;;
  esac
done

REGION=us-east-1
DOMINIO=${DOMINIO:-nataliaremolinarodriguez.com}
ZONA_ID=${ZONA_ID:-Z0731422246SUYEGG2Z5R}
SUBDOMINIO=${SUBDOMINIO:-software}
RESPALDOS=${RESPALDOS:-$HOME/Respaldos/operacion-proyectos}
PAUSADA=0 TERMINADO=0 FUNCION="" TAREAS="" CONCURRENCIA=20
typeset -a ALARMAS_RECHAZOS=()

fallar() { print -u2 "\n✗ $*"; exit 1 }
paso() { print "\n== $* ==" }
# Una orden que escribe algo: en ensayo solo se muestra
correr() {
  local orden="$*"
  orden=${orden/#en_infra /(en infra\/) }
  if (( ENSAYO )); then print "[ensayo] $orden"; else print "+ $orden"; "$@"; fi
}
en_infra() { (cd infra && "$@") }
confirmar() {
  if (( ENSAYO )); then print "[ensayo] Aquí se pide escribir «si»: $1"; return 0; fi
  local respuesta
  print -n "$1 Escribe «si» para seguir: "
  read -r respuesta
  [[ $respuesta == si ]] || fallar "No se escribió «si»: no se sigue. ${2:-}"
}
salida() {
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text 2>/dev/null || true
}

# Si algo falla con la API en pausa, se queda en pausa: la base puede estar a medio migrar. Se dice cómo quitarla.
avisar_pausa() {
  (( PAUSADA && ! TERMINADO )) || return 0
  print -u2 "\nLa API y Tareas siguen en pausa (concurrencia 0). Cuando se decida (docs/despliegue.md, «Vuelta atrás»):"
  print -u2 "  aws lambda put-function-concurrency --function-name $FUNCION --reserved-concurrent-executions $CONCURRENCIA"
  [[ -n $TAREAS ]] && print -u2 "  aws lambda delete-function-concurrency --function-name $TAREAS"
  (( ${#ALARMAS_RECHAZOS} )) && print -u2 "  aws cloudwatch enable-alarm-actions --alarm-names ${ALARMAS_RECHAZOS[*]}"
  return 0
}
trap avisar_pausa EXIT

# ---------- 0. registro ----------
RAIZ=$(git rev-parse --show-toplevel 2>/dev/null) || fallar "Esto no es una carpeta de git: se despliega desde una carpeta de publicación."
cd "$RAIZ"
PRINCIPAL=${PRINCIPAL:-$(cd "$(git rev-parse --git-common-dir)/.." && pwd)}
mkdir -p "$RESPALDOS"
REGISTRO="$RESPALDOS/despliegue_$(date +%Y-%m-%d_%H%M%S)$( (( ENSAYO )) && print -n _ensayo).log"
exec > >(tee -a "$REGISTRO") 2>&1
print "Despliegue $( (( ENSAYO )) && print -n "(ensayo, no cambia nada) ")desde $RAIZ — registro en $REGISTRO"

# ---------- 1. comprobaciones ----------
paso "1. Comprobaciones"
CABEZA=$(git rev-parse HEAD)
DEV=$(git rev-parse --verify --quiet refs/heads/dev) \
  || fallar "No existe la rama dev en este repositorio. Solo se despliega desde la punta de dev."
RAMA=$(git symbolic-ref --quiet --short HEAD || print "sin rama")
if [[ $CABEZA != $DEV ]]; then
  fallar "Solo se despliega desde la punta de dev. Esta carpeta está en ${CABEZA[1,7]} ($RAMA) y dev está en ${DEV[1,7]}.
  Une el trabajo en dev y despliega desde una carpeta en su punta: git worktree add --detach <carpeta> dev"
fi
[[ -z $(git status --porcelain) ]] \
  || fallar "Hay cambios sin guardar en $RAIZ: se despliega exactamente el commit de dev, desde una carpeta limpia."
if git rev-parse --verify --quiet refs/remotes/origin/dev >/dev/null && [[ $(git rev-parse refs/remotes/origin/dev) != $DEV ]]; then
  print "Aviso: dev (${DEV[1,7]}) no coincide con origin/dev: lo que se publica no está aún en GitHub."
fi
print "✓ ${CABEZA[1,7]} es la punta de dev y la carpeta está limpia."

[[ -n ${CORREO_AVISOS:-} ]] || fallar "Falta CORREO_AVISOS: el correo de las alarmas (sin él, CloudFormation borraría la suscripción)."
PY="$PRINCIPAL/.venv/bin/python"
DOTENV="$PRINCIPAL/.venv/bin/dotenv"
for ejecutable in $PY $DOTENV; do
  [[ -x $ejecutable ]] || fallar "Falta $ejecutable: make instalar en $PRINCIPAL."
done
for archivo in .env.supabase-publicada .env.produccion .env.supabase-pruebas; do
  [[ -f $PRINCIPAL/$archivo ]] || fallar "Falta $PRINCIPAL/$archivo (docs/despliegue.md, «Antes de empezar»)."
done
print "✓ Entorno de Python y archivos de configuración en $PRINCIPAL."

docker info >/dev/null 2>&1 || fallar "Docker no está en marcha: CDK construye en este equipo las imágenes y los estáticos de la web."
print "✓ Docker en marcha."

export AWS_PROFILE=${AWS_PROFILE:-operacion} AWS_REGION=$REGION AWS_DEFAULT_REGION=$REGION
CUENTA=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  || fallar "Sin sesión de AWS con el perfil $AWS_PROFILE: inicia sesión (aws sso login --profile $AWS_PROFILE) y repite."
# boto3 (el respaldo de los recibos, poblar_secreto) recibe las mismas credenciales, sin escribirlas en un archivo ni aquí
CREDENCIALES=$(aws configure export-credentials --format env 2>/dev/null) \
  || fallar "No se pudieron exportar las credenciales de AWS para boto3 (perfil $AWS_PROFILE)."
eval "$CREDENCIALES"
unset CREDENCIALES
print "✓ Sesión de AWS en la cuenta $CUENTA (perfil $AWS_PROFILE, $REGION); credenciales exportadas para boto3."

typeset -a CDK_CTX=(-c "correo=$CORREO_AVISOS")
(( SIN_DOMINIO )) || CDK_CTX+=(-c "dominio=$DOMINIO" -c "zonaId=$ZONA_ID" -c "subdominio=$SUBDOMINIO")
(( WAF )) && CDK_CTX+=(-c waf=1)
typeset -a TELEGRAM=()
(( SIN_TELEGRAM )) && TELEGRAM=(--sin-telegram)

# ---------- 2. pausa ----------
paso "2. Pausa de la API y de Tareas (concurrencia 0) antes del respaldo y la migración"
FUNCION=$(salida OperacionApp Funcion)
TAREAS=$(salida OperacionApp FuncionTareas)
[[ $TAREAS == None ]] && TAREAS=""
if [[ -z $FUNCION || $FUNCION == None ]]; then
  FUNCION=""
  print "OperacionApp aún no existe: no hay nada que pausar."
else
  CONCURRENCIA=$(salida OperacionApp ConcurrenciaReservada)
  [[ $CONCURRENCIA == <-> ]] || CONCURRENCIA=20
  # En pausa, cada petición es un rechazo: sus alarmas se silencian hasta quitarla
  ALARMAS_RECHAZOS=(${(z)$(aws cloudwatch describe-alarms --alarm-name-prefix OperacionApp- \
    --query "MetricAlarms[?MetricName=='Throttles'].AlarmName" --output text 2>/dev/null || true)})
  ALARMAS_RECHAZOS=(${ALARMAS_RECHAZOS:#None})
  confirmar "Se pausan $FUNCION y $TAREAS: la plataforma responde «ocupado» hasta el final del despliegue."
  (( ${#ALARMAS_RECHAZOS} )) && correr aws cloudwatch disable-alarm-actions --alarm-names $ALARMAS_RECHAZOS
  correr aws lambda put-function-concurrency --function-name "$FUNCION" --reserved-concurrent-executions 0
  [[ -n $TAREAS ]] && correr aws lambda put-function-concurrency --function-name "$TAREAS" --reserved-concurrent-executions 0
  (( ENSAYO )) || PAUSADA=1
fi

# ---------- 3. respaldo, migración, comprobación y secreto ----------
paso "3. Respaldo, migración y comprobación de la base publicada; configuración del secreto"
correr "$PY" -m datos.respaldar respaldar --env "$PRINCIPAL/.env.supabase-publicada"
print "La migración pide escribir el identificador del proyecto: la confirma quien despliega."
correr "$DOTENV" -f "$PRINCIPAL/.env.supabase-publicada" run -- "$PY" -m datos.semilla
correr "$DOTENV" -f "$PRINCIPAL/.env.supabase-publicada" run -- "$PY" -m datos.comprobar_supabase
correr "$PY" infra/poblar_secreto.py --env "$PRINCIPAL/.env.produccion" $TELEGRAM --ensayo
confirmar "Se sube al secreto la configuración de .env.produccion (sin mostrar valores; ORIGEN_SECRETO se genera si falta)."
correr "$PY" infra/poblar_secreto.py --env "$PRINCIPAL/.env.produccion" $TELEGRAM

# ---------- 4. revisión del cambio ----------
paso "4. Revisión del cambio en AWS (cdk diff)"
correr en_infra npm ci --no-audit --no-fund
correr en_infra npx cdk diff OperacionBase OperacionApp OperacionWeb $CDK_CTX
confirmar "Ese es todo el cambio en AWS." "La API sigue en pausa."

# ---------- 5. despliegue, fin de la pausa y comprobaciones ----------
paso "5. Despliegue de Base, App y Web"
for pila in OperacionBase OperacionApp OperacionWeb; do
  correr en_infra npx cdk deploy "$pila" --exclusively --require-approval never $CDK_CTX
  if [[ $pila == OperacionApp ]]; then
    # La plantilla trae la concurrencia reservada de la API: si CloudFormation la cambió, quitó la pausa antes de tiempo
    FUNCION=${FUNCION:-$(salida OperacionApp Funcion)}
    TAREAS=${TAREAS:-$(salida OperacionApp FuncionTareas)}
    if [[ -n $FUNCION && $FUNCION != None ]]; then
      correr aws lambda put-function-concurrency --function-name "$FUNCION" --reserved-concurrent-executions 0
      (( ENSAYO )) || PAUSADA=1
    fi
  fi
done

paso "Fin de la pausa"
CONCURRENCIA=$(salida OperacionApp ConcurrenciaReservada)
[[ $CONCURRENCIA == <-> ]] || CONCURRENCIA=20
if [[ -n $FUNCION && $FUNCION != None ]]; then
  correr aws lambda put-function-concurrency --function-name "$FUNCION" --reserved-concurrent-executions "$CONCURRENCIA"
fi
[[ -n $TAREAS && $TAREAS != None ]] && correr aws lambda delete-function-concurrency --function-name "$TAREAS"
(( ${#ALARMAS_RECHAZOS} )) && correr aws cloudwatch enable-alarm-actions --alarm-names $ALARMAS_RECHAZOS
TERMINADO=1

paso "Comprobaciones de salud y redirecciones"
URL_WEB=$(salida OperacionWeb UrlWeb)
URL_ADMIN=$(salida OperacionWeb UrlAdmin)
URL_API=$(salida OperacionApp Url)
FALLOS=0
comprobar() {   # descripción, dirección, códigos aceptados (expresión), destino esperado de la redirección (opcional)
  local que=$1 url=$2 esperado=$3 destino=${4:-} codigo ubicacion
  if (( ENSAYO )); then print "[ensayo] $que: $url → $esperado${destino:+ hacia $destino}"; return 0; fi
  read -r codigo ubicacion <<< "$(curl -s -o /dev/null --max-time 30 -w '%{http_code} %{redirect_url}' "$url" || print 000)"
  if [[ $codigo == ${~esperado} && ( -z $destino || $ubicacion == $destino ) ]]; then
    print "✓ $que: $codigo${ubicacion:+ → $ubicacion}"
  else
    print "✗ $que: $url respondió $codigo${ubicacion:+ → $ubicacion}; se esperaba $esperado${destino:+ hacia $destino}"
    FALLOS=$(( FALLOS + 1 ))
  fi
}
comprobar "Administración responde" "$URL_ADMIN/salud" 200
comprobar "La web responde" "$URL_WEB/entrar" 200
comprobar "La API responde por CloudFront (sin sesión: 401)" "$URL_WEB/api/v1/auth/me" 401
comprobar "La web obliga HTTPS" "http://${URL_WEB#https://}/entrar" "(301|308)" "$URL_WEB/entrar"
(( SIN_DOMINIO )) || comprobar "Las pantallas anteriores llevan a la web" "$URL_ADMIN/admin/viajes" "(302|307)" "$URL_WEB/viajes"
# Directo a la función, sin la cabecera de CloudFront: 403 si la API ya la exige (frente de backend), 200 si aún no
comprobar "La dirección directa de la API no atiende sin CloudFront" "${URL_API%/}/salud" "(403|200)"

if (( ! SIN_TELEGRAM )); then
  print "\nTelegram: registra el webhook con el mismo archivo (docs/despliegue.md, paso 6):"
  print "  $DOTENV -f $PRINCIPAL/.env.produccion run -- $PY -m datos.telegram_webhook ${URL_API:-<Url de OperacionApp>}"
fi
(( FALLOS )) && fallar "$FALLOS comprobaciones fallaron: decidir con docs/despliegue.md, «Vuelta atrás». Registro: $REGISTRO"
print "\n✓ $( (( ENSAYO )) && print -n "Ensayo terminado: no se cambió nada." || print -n "Despliegue terminado.") Registro: $REGISTRO"
