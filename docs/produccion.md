# Producción

Estado de la plataforma publicada y cómo se opera. Para publicar o actualizar, el orden completo está en `docs/despliegue.md`; para el respaldo y la vuelta atrás de la base, en `docs/respaldo.md`.

## Dónde está

| Qué | Dirección |
|---|---|
| Web nueva (Next.js) | https://software.nataliaremolinarodriguez.com |
| Pantallas de administración (Jinja) | https://admin.software.nataliaremolinarodriguez.com |
| API v1 | `/api/v1/*` en el mismo origen de la web |

- **El dominio** está registrado en Route 53, con bloqueo de transferencia y renovación automática. La zona DNS es de la cuenta y no la maneja CDK. El dominio raíz y `www` quedan libres para otro sitio; las pilas solo escriben los registros de `software.` y `admin.software.`.
- **Las sesiones van por subdominio:** la de `software.` no vale en `admin.software.`, porque las cookies `__Host-` son de un solo nombre. Pasar a administración pide entrar otra vez (ADR 0002).

## Qué corre

| Pila | Contenido |
|---|---|
| `OperacionBase` | El secreto de configuración (Secrets Manager) y el tema de avisos (SNS), con la suscripción por correo |
| `OperacionApp` | La API y las pantallas Jinja en una función Lambda con imagen de contenedor (arm64, 2 GB, 180 s) y su dirección de función. Cinco alarmas: fallos de la función, peticiones rechazadas, lentitud, líneas `ERROR peticion=` y respuestas 5xx |
| `OperacionWeb` | La web en una función Lambda (arm64, 1 GB), los estáticos en un bucket S3 privado (solo CloudFront lo lee, con OAC), dos distribuciones de CloudFront (web y administración), el certificado de ACM y los cuatro registros A y AAAA de los subdominios. La web sale con cabeceras de seguridad (HSTS, nosniff, `X-Frame-Options SAMEORIGIN` y Referrer-Policy) |

**La base de datos** es el proyecto publicado de Supabase (PostgreSQL 17). La función se conecta por el agrupador de transacción (puerto 6543); la migración se corre por el de sesión (5432). Todas las tablas tienen seguridad por filas y ninguna da permisos a los roles públicos (`python -m datos.comprobar_supabase`).

## Servicios encendidos

| Servicio | Estado | Tope |
|---|---|---|
| Buscador de vuelos y hoteles | Encendido | Cotizaciones por persona y día (`tope_cotizaciones_persona_dia`), autocompletado por mes y por persona; el monitoreo del vuelo se suspende si al plan le quedan pocas búsquedas |
| Lectura de recibos y transcripción de notas de voz | Encendida | Una llamada por recibo |
| Asistente con el asesor (agente alojado) | Encendido | Preguntas por persona y día (`asistente_preguntas_dia`), dictados por voz por persona y día (`asistente_dictados_dia`) y tope de gasto diario del asesor |
| Búsqueda por significado del asistente (Pinecone) | Encendida | Índice `asistente-fichas`, espacio `fichas-nube` |
| Telegram | Apagado | Se publica con el paso 6 de `docs/despliegue.md` |

**Pinecone se pone al día** desde un equipo con la configuración de producción. `ENTORNO=nube` hace que las fichas vayan al mismo espacio que lee la función:

```
ENTORNO=nube dotenv -f .env.produccion run -- python -m datos.indexar
```

Solo envía lo nuevo o cambiado. El índice local se mantiene siempre como respaldo.

## Cuentas

En producción no existen las cuentas de demostración del README: solo se crean sobre una base local.

- **La primera cuenta de administración** salió de `ADMIN_INICIAL_CORREO` y `ADMIN_INICIAL_CLAVE` al sembrar la base por primera vez.
- **Las demás** las crea administración en `https://admin.software.nataliaremolinarodriguez.com/admin/usuarios`, con su permiso (colaborador, gestor o administración) y su cargo.
- **Las contraseñas** nunca se escriben en el repositorio.

## Operación diaria

- **Avisos:** las alarmas avisan por correo al tema de `OperacionBase`. La suscripción se confirma una vez, con el enlace que envía AWS.
- **Costo:** el presupuesto de la cuenta (`cuenta-mensual`, fuera de CDK) avisa por correo al 50, 80 y 100 % del gasto y del pronóstico. En reposo no hay nada encendido: sin la instancia caliente (`-c caliente=1`), el costo fijo es de unos 1,5 USD al mes (zona DNS, secreto y alarmas); lo demás se cobra por uso.
- **Registros:** CloudWatch, con 30 días de retención. Una petición con error deja `ERROR peticion=<id>`; ese mismo identificador sale en la página de error de quien la vio.
- **Secreto:** se actualiza con `infra/poblar_secreto.py`, que fusiona con lo que ya hay y nunca muestra valores. La función lo lee al arrancar, así que el cambio entra en las instancias nuevas (tras desplegar `OperacionApp` o cuando se apagan las encendidas).
- **Respaldo:** el plan gratuito de Supabase no hace respaldos automáticos. Antes de cada migración: `make respaldar` y el ensayo de restauración (`docs/respaldo.md`).

## Cómo se actualiza

1. Revisar y unir a `dev`. Verificar en SQLite, PostgreSQL, la web y `infra/`.
2. Crear una carpeta limpia del commit que se publica.
3. Si cambia el esquema: respaldo y migración.
4. Si cambian claves: el secreto.
5. Revisar el `cdk diff` y desplegar una pila a la vez.

Todo está en `docs/despliegue.md`, con la vuelta atrás de cada parte. Desplegar solo la web o solo la API es `cdk deploy OperacionWeb --exclusively` o `cdk deploy OperacionApp --exclusively`, con el mismo contexto.

## Pendientes para operar con más garantías

- **Desplegar con un usuario propio con MFA,** no con el usuario raíz de la cuenta. Mejor aún: desde la integración continua, con un rol y aprobación manual.
- **Topes para el agente de cotización y la lectura de recibos** (auditoría, H-29 y H-30).
- **Una regla de limpieza de imágenes viejas** en ECR.
- **Un respaldo nocturno automático** de la base (`docs/respaldo.md`, opción B).
- **Un ambiente previo a producción** en AWS.
- **Telegram con el bot de producción.**
