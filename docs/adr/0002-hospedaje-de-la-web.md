# ADR 0002 · Hospedaje de la web Next.js en AWS

Estado: aceptada · Fecha: 12 de noviembre de 2026 · Resuelve una decisión abierta del ADR 0001 (anillo 4)

## Contexto

La web Next.js (`web/`) consume la API v1 de la aplicación FastAPI. Hoy:

- **El backend** corre en AWS: una función Lambda con imagen de contenedor y el adaptador web de Lambda (`Dockerfile`, `infra/lib/app-stack.ts`), expuesta por una URL de función, descrita con CDK y desplegada solo tras revisar `cdk diff`.
- **La sesión** vive en una cookie `HttpOnly` (`__Host-sesion` en HTTPS). Toda escritura lleva `X-CSRF-Token` y la API rechaza orígenes que no estén en `ORIGENES_WEB` (`contracts/api-v1.md`).
- **En local,** un gateway Caddy publica un solo origen: `/api/v1/*` va a la API y el resto a la web (`gateway/Caddyfile`, `docker-compose.yml`).
- **La web** ya compila como servidor independiente (`output: "standalone"` en `web/next.config.ts`) dentro de su propia imagen (`web/Dockerfile`, puerto 3000).

El ADR 0001 dejó abierto dónde se hospeda la web. Las opciones evaluadas fueron Vercel y AWS.

## Decisión

**La web se hospeda en AWS, con el mismo patrón que el backend, detrás de un solo origen.**

| Pieza | Cómo |
|---|---|
| Entrada | Una distribución de CloudFront con el dominio de la empresa y certificado de ACM |
| `/api/v1/*` | Origen: la URL de función de la API actual, sin caché (las respuestas ya llevan `Cache-Control: no-store`) |
| `/_next/static/*` | Origen: un bucket S3 privado con los archivos estáticos de la compilación, con caché larga (llevan huella en el nombre) |
| Todo lo demás | Origen: una función Lambda nueva con la imagen de `web/` y el adaptador web de Lambda (puerto 3000, comprobación de lista en `/entrar`) |
| Pantallas actuales (Jinja) | Subdominio propio de administración, apuntando a la API actual. Comparten rutas con la web nueva (`/viajes`, `/gastos`), así que no pueden estar en el mismo origen |
| Infraestructura | En el mismo proyecto CDK de `infra/`, en un *stack* nuevo para la web; cada despliegue pasa por `cdk diff` aprobado |

La web no tiene secretos: llama a la API con `NEXT_PUBLIC_API_BASE=/api/v1`, una ruta del mismo origen.

## Por qué AWS y no Vercel

| Criterio | AWS (elegido) | Vercel |
|---|---|---|
| Sesión y seguridad | Un solo origen: la cookie `HttpOnly` y el token CSRF funcionan igual que en local | La web queda en otro dominio. Hay que pasar la API por un proxy de Vercel o usar cookies entre dominios, que los navegadores bloquean cada vez más |
| Operación | La misma receta del backend: imagen, adaptador de Lambda, CDK, alarmas, presupuesto, registros y región `us-east-1` junto a la base | Otro proveedor, otra cuenta y otro panel; los datos de las personas pasan por un tercero más |
| Costo con el tráfico actual | Unos pocos dólares al mes (Lambda, CloudFront y S3 cobran por uso) | El plan gratuito no admite uso comercial; el de pago cuesta 20 USD por persona al mes |
| Coherencia con el ADR 0001 | Es el «gateway administrado» del anillo 4: CloudFront hace en la nube lo que Caddy hace en local | Duplica el borde: Vercel por delante y la API detrás |
| Vistas previas por rama | Hay que construirlas si se quieren | Vienen incluidas: es su principal ventaja |

## Consecuencias

- El entorno local con Caddy sigue siendo el modelo exacto de producción: lo que funciona en `127.0.0.1:8088` funciona detrás de CloudFront.
- `ORIGENES_WEB` en producción contiene solo el dominio de la empresa.
- Las pantallas actuales siguen disponibles para administración en su subdominio, con su propia sesión (las cookies `__Host-` no se comparten entre subdominios), mientras la web nueva las reemplaza.
- La web suma una función con arranque en frío. Se mide en el primer despliegue; si molesta, se reserva concurrencia mínima, igual que con el backend.
- **Nada de esto se despliega hasta que la dueña declare el producto final.** La entrega del 13 de noviembre se demuestra en local con Docker.

## Pendiente de comprobar al implementar

- Next.js 16 en modo independiente detrás del adaptador web de Lambda: respuestas en flujo, optimización de imágenes y encabezados de caché.
- Que CloudFront reenvíe la cookie de sesión y los encabezados `Origin` y `X-CSRF-Token` hacia la API, y nada de eso hacia los archivos estáticos.
- El nombre exacto del subdominio de administración y del dominio principal.

## Condición para revisar esta decisión

Si el equipo de frontend pasa a trabajar por separado y necesita vistas previas por rama, o si el tráfico de la web crece tanto que una función Lambda deja de ser la opción más barata, se reevalúa: Vercel con proxy hacia la API, o un servicio de contenedores en AWS.
