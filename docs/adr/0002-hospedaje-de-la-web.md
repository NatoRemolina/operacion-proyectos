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

## Dominio (decisión del 12 de noviembre de 2026)

**El dominio se gestiona en AWS con Route 53, integrado al mismo código de infraestructura.** Así el dominio, el certificado, CloudFront y los registros viven en el mismo stack de CDK y se revisan con el mismo `cdk diff`.

| Pieza | Cómo |
|---|---|
| Registro del dominio | `nataliaremolinarodriguez.com`, registrado en Route 53 (un `.com` cuesta unos 15 USD al año) |
| Zona DNS | Una zona alojada en Route 53 (0,50 USD al mes más centavos por consultas; las que apuntan a CloudFront no se cobran). **La creó la dueña y es suya:** la pila la importa por su identificador y nunca la crea ni la borra |
| Nombres | La web en `software.nataliaremolinarodriguez.com`; las pantallas actuales en `admin.software.nataliaremolinarodriguez.com`. El subdominio es una variable del despliegue (`-c subdominio=`, por omisión `software`) |
| Certificado | ACM en `us-east-1`, pedido y validado por CDK en la propia zona, solo para esos dos nombres: sin pasos a mano. Gratis |
| Registros | *Alias* A y AAAA de los dos nombres hacia su distribución. **El dominio raíz y `www` no se tocan:** quedan para la página personal de la dueña, y la pila rechaza un subdominio `www` |
| Configuración | `ORIGENES_WEB` con el dominio de la web: con dominio la fija la pila de la API; sin dominio va en el secreto |

**Sin las variables del dominio**, el mismo stack publica en la dirección gratuita de CloudFront (`https://<id>.cloudfront.net`), con HTTPS incluido y el mismo comportamiento de sesión y CSRF. El dominio se activa con dos variables del despliegue (`-c dominio=… -c zonaId=…`, que van juntas); sin ellas no se crean certificado ni registros, y la zona nunca se crea.

Alternativas descartadas: Cloudflare como DNS (funciona, pero deja una parte fuera de CDK y la validación del certificado a mano) y Cloudflare como proxy delante de CloudFront (dos CDN en cadena, más reglas que mantener).

## Tiempo máximo de respuesta (decisión del 12 de noviembre de 2026)

CloudFront espera a la API **60 segundos** como máximo (`readTimeout` del origen de la API en `infra/lib/web-stack.ts`, en las dos distribuciones). La web conserva los 30 s por omisión: sus páginas no hacen trabajo largo.

**Por qué 60 s.** Es el plazo total que ya se dan el asistente y el agente de la cotización en su conversación con el modelo (`PLAZO_TOTAL_S = 60` en `app/servicios/asistente.py` y `app/servicios/agente.py`), y más de un minuto frente a una pantalla quieta ya no es una espera razonable para nadie. CloudFront admite hasta 120 s sin pedir cuota: si la medición del primer despliegue lo pide, se sube en el mismo stack, con su `cdk diff`.

**Qué pasa al superarlo.** Ante un `POST` que no responde a tiempo, CloudFront corta la conexión, no reintenta y el navegador recibe un 504. La función **no se detiene**: termina su trabajo (tiene 180 s) y lo guarda. Con un `GET`, CloudFront reintentaría hasta 3 veces; hacia la API la pila lo deja en **un solo intento** (`connectionAttempts: 1`), porque el tablero de vuelos (`GET /admin/viajes/vuelos`, cada 15 s) consulta el buscador pago dentro de un `GET` y un reintento repetiría la consulta.

| Operación | Cuánto puede tardar | Si pasa de 60 s |
|---|---|---|
| Asistente (`/admin/asistente`, en `admin.`) | El asesor tiene 75 s (`app/servicios/asesor.py`); si falla antes de 20 s se prueba el modelo, con otros 60 s | La respuesta queda en `asistente_consultas` y en la bitácora, y el costo del asesor queda registrado, pero la persona ve el error. La pantalla solo lista las preguntas recientes: tiene que preguntar de nuevo, y eso cuenta otra vez en el tope diario y en el costo |
| Lectura de un recibo (`POST /api/v1/gastos`, `/cargar`) | Hasta 3 intentos de 45 s con el modelo (`app/servicios/llm.py`), o 90 s en el formato «mensajes» (`app/servicios/extraccion.py`) | El soporte y el gasto quedan guardados. Reenviar con la misma `Idempotency-Key` devuelve el mismo gasto, aunque siga en lectura (`app/servicios/envios.py`); la página de carga ya manda una clave por archivo. Si la lectura se corta, el gasto pasa a revisión de administración |
| Cotizar una ruta nueva (`POST /api/v1/cotizaciones`, `/viajes`) | Hasta 60 s por consulta al buscador (`app/servicios/precios.py`), al menos dos consultas (vuelos y hoteles), más el agente | La cotización y las respuestas del buscador quedan guardadas. Reenviar con la misma `Idempotency-Key` devuelve la misma cotización sin volver a pagar el buscador (`app/servicios/cotizacion.py`) |
| Telegram | No pasa por CloudFront: el webhook apunta a la dirección de la función | Sin cambio |

Mejoras posibles, sin hacer: que el asistente reciba el plazo que le queda y corte antes de los 60 s, y que su pantalla muestre la última respuesta guardada.

## Consecuencias

- El entorno local con Caddy sigue siendo el modelo exacto de producción: lo que funciona en `127.0.0.1:8088` funciona detrás de CloudFront.
- `ORIGENES_WEB` en producción contiene solo el dominio de la empresa.
- Las pantallas actuales siguen disponibles para administración en su subdominio, con su propia sesión, mientras la web nueva las reemplaza. **La sesión de `software.` no vale en `admin.software.`:** la cookie `__Host-sesion` queda atada al nombre exacto que la creó y no se comparte entre subdominios. Pasar a administración, por ejemplo desde los enlaces de la web a Proyectos, Usuarios o la revisión completa de un gasto, pide entrar otra vez.
- **Un navegador que no manda `Sec-Fetch-Site` recibe 403 en los formularios de administración.** Detrás de CloudFront, `Host` es el de la dirección de función, y `mismo_origen` (`app/servicios/acceso.py:244`) solo acepta un `Origin` igual a `Host` cuando falta esa cabecera. Todos los navegadores actuales la mandan (Chrome y Edge desde 2019, Firefox desde 2021, Safari desde la versión 16.4, de 2023), así que hoy solo afecta a navegadores viejos. La web nueva no tiene el problema: `origen_permitido` (`:255`) acepta además los orígenes de `ORIGENES_WEB`. Se corregiría de la misma forma: que `mismo_origen` acepte también un `Origin` declarado (el de `admin.` en la configuración). Otra opción es que una función de CloudFront pase el nombre que pidió el visitante en una cabecera propia y la aplicación compare `Origin` con ella, confiando en esa cabecera solo cuando la petición viene de CloudFront.
- La web suma una función con arranque en frío. Se mide en el primer despliegue; si molesta, se reserva concurrencia mínima, igual que con el backend.
- **Nada de esto se despliega hasta que la dueña declare el producto final.** La entrega del 13 de noviembre se demuestra en local con Docker.

## Pendiente de comprobar al implementar

- Next.js 16 en modo independiente detrás del adaptador web de Lambda: respuestas en flujo, optimización de imágenes y encabezados de caché.
- ~~Que CloudFront reenvíe la cookie de sesión y los encabezados `Origin` y `X-CSRF-Token` hacia la API, y nada de eso hacia los archivos estáticos.~~ Resuelto: `/api/v1/*` y `admin.` usan la política AllViewerExceptHostHeader y los estáticos ninguna (`infra/lib/web-stack.ts`, `tests/test_detras_de_cloudfront.py`). Detrás de CloudFront `Host` es el de la función, así que los formularios de `admin.` dependen de `Sec-Fetch-Site`, que mandan todos los navegadores actuales.
- ~~El nombre del dominio de la empresa y el del subdominio de administración.~~ Resuelto: ver «Dominio».

## Condición para revisar esta decisión

Si el equipo de frontend pasa a trabajar por separado y necesita vistas previas por rama, o si el tráfico de la web crece tanto que una función Lambda deja de ser la opción más barata, se reevalúa: Vercel con proxy hacia la API, o un servicio de contenedores en AWS.
