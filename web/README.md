# Web de viajes y gastos (Next.js)

La web nueva de la plataforma. Cubre **cotizar** (origen y destino en cualquier lugar del mundo, comparar
con desglose y decidir), **mis viajes**, **mis gastos** (cargar un recibo con su justificación y ver su estado
real) y, para administración, **resumen, aprobación de viajes** (con la reconfirmación del precio) y
**revisión de gastos**. Lo que todavía no tiene (corregir los datos leídos de un gasto, aprobar con excepción,
KPIs, asistente, monitoreo, reglas, proyectos y usuarios) sigue en la plataforma actual, y la web enlaza allí
cuando hace falta.

La web consume solo la API v1 descrita en [`contracts/api-v1.md`](../contracts/api-v1.md); no tiene acceso a
ninguna base de datos.

## Requisitos

- Node **26** (LTS vigente; ver `.nvmrc`). `package.json` lo declara en `engines`.
  Con otra versión npm solo avisa, pero las comprobaciones oficiales se hacen con la 26.
- npm 11. Instalar siempre con `npm ci` para respetar `package-lock.json`.

## Comandos

```bash
npm ci                 # instalar exactamente lo del lockfile
npm run dev            # desarrollo en http://localhost:3000
npm run lint           # ESLint, incluidas las reglas de capas (falla con cualquier aviso)
npm run typecheck      # genera los tipos de rutas y ejecuta tsc --noEmit
npm test               # Vitest + Testing Library
npm run build          # compilación de producción (salida standalone)
```

## Modo demostración

```bash
FUENTE_DATOS=demo npm run dev
```

Usa adaptadores en memoria con datos ficticios. Toda pantalla muestra la franja
**«Datos de demostración»** y la pantalla de ingreso enseña la cuenta: `piloto@demo.local` /
`demo1234`. Nada se envía a la API ni se guarda: al recargar se pierden los recibos cargados
(la sesión dura lo que la pestaña).

Como el modo demo no lee recibos, aplica una regla fija para poder ver ambos resultados:

| Recibo | Viaje | Resultado |
|---|---|---|
| Imagen | automático (hay viaje en curso) o uno propio | **Aprobado** |
| PDF | cualquiera | **En revisión** (lectura dudosa) |
| Cualquiera | sin viaje propio | **En revisión** (sin viaje) |

La idempotencia se comporta como en el contrato: reintentar con la misma clave y el mismo
archivo devuelve el mismo gasto; la misma clave con otro archivo da conflicto.

`FUENTE_DATOS` se lee en el servidor en cada petición, así que la misma imagen sirve para
demo y para la API real. Un valor distinto de `http` o `demo` hace que cada página responda
un error 500 con el motivo en el registro, en vez de mostrar datos equivocados.

## Con la API real

La web llama a `NEXT_PUBLIC_API_BASE` (por defecto `/api/v1`) desde el navegador, con la
cookie de sesión (`credentials: "include"`) y sin caché. **No hay `rewrites` en Next**: en local
el gateway de `docker compose` pone la web y la API en el mismo origen.

```bash
docker compose --profile web up -d    # desde la raíz del repositorio → http://127.0.0.1:8088
```

Para desarrollar sin gateway, copia `.env.example` a `.env.local` y apunta
`NEXT_PUBLIC_API_BASE` a la API (por ejemplo `http://127.0.0.1:8000/api/v1`). La API debe
aceptar ese origen y la cookie debe poder viajar; lo más simple es usar el gateway.

`NEXT_PUBLIC_API_BASE` se incrusta al compilar: en Docker se pasa como `--build-arg`, no como
variable de entorno del contenedor. Nunca pongas secretos en variables `NEXT_PUBLIC_`.

## Docker

```bash
docker build -t inflight-web .
docker run --rm -p 3000:3000 -e FUENTE_DATOS=demo inflight-web
```

Compilación de producción con `next build` y salida `standalone`, Node 26 Alpine, usuario `node`
sin privilegios y puerto 3000. El contenedor nunca usa el modo de desarrollo.

## Arquitectura

Inversión de dependencias (sección 13 del plan): la interfaz depende de puertos, no de `fetch`.

```
src/
  app/                      rutas delgadas del App Router
    (public)/entrar
    (private)/layout.tsx    comprueba la sesión (experiencia de uso; los permisos los aplica la API)
    (private)/cotizar, cotizar/[id]
    (private)/viajes, viajes/[id]
    (private)/gastos, gastos/nuevo, gastos/[id]
    (private)/resumen       inicio de administración
  features/<auth|cotizar|viajes|gastos|administracion>/
    domain/                 tipos y puertos (AuthRepository, CotizarRepository, ViajesRepository,
                            GastosRepository, AdministracionRepository)
    application/            hooks con TanStack Query y casos de uso (envío con idempotencia)
    infrastructure/         adaptador HTTP (fetch + zod) y adaptador en memoria
    ui/                     contenedores y componentes de presentación
  shared/                   lo mismo para piezas comunes: errores, cliente HTTP, componentes base
  composition/              único lugar que elige HTTP o demo y lo inyecta con un Provider estable
  config/                   lectura y validación de FUENTE_DATOS y NEXT_PUBLIC_API_BASE
  test/                     ayudantes y fábricas de pruebas
```

Reglas que ESLint hace cumplir (`eslint.config.mjs`):

- `domain` no importa React, Next, TanStack, zod, ni las capas de aplicación, interfaz o infraestructura.
- `application` y `ui` no importan infraestructura ni la composición.
- Solo `composition` importa adaptadores concretos.
- `fetch` solo aparece dentro de `infrastructure`.

Decisiones:

- **Errores de aplicación estables** (`shared/domain/errores.ts`): el adaptador traduce cada
  código HTTP o `error.code` del contrato a un `tipo` (`sesion_vencida`, `no_encontrado`,
  `demasiado_grande`, …). Una respuesta que no cumple el esquema zod es un error de `contrato`.
- **CSRF**: el token llega en `login` o `me`, vive solo en memoria del cliente HTTP y va en
  `X-CSRF-Token` en toda escritura.
- **Caché por persona**: las claves de TanStack Query empiezan por `["persona", id]` y la caché
  se vacía al entrar y al salir, así ningún dato de una sesión sobrevive a la siguiente.
- **Envío de recibos**: `fetch` + `FormData` (sin Server Actions). Cada archivo elegido recibe
  una `Idempotency-Key`; reintentar reutiliza la misma, elegir otro archivo genera una nueva.
  Se muestra el estado que devuelve la API («Aprobado» o «En revisión…»), nunca «aprobado» por
  haber recibido un 201. El progreso se anuncia en una región `aria-live`; `fetch` no informa
  el avance de la subida, así que se anuncia la fase, no un porcentaje.
- **Dinero**: cadenas decimales del servidor, formateadas con `Intl.NumberFormat` sin pasar
  por números de coma flotante.

## Diseño y accesibilidad

Dirección visual del diseño en Figma: marca «INFLIGHT / SOLUTIONS», navegación lateral grafito
en escritorio y barra inferior en celular, acción primaria cian oscuro, fondo gris claro con
tarjetas blancas y tipografía Mulish (servida por `next/font`, sin peticiones a terceros).

Tokens en `src/app/globals.css`. Contrastes medidos (WCAG 2.x):

| Par | Contraste |
|---|---|
| Blanco sobre marca `#00727f` | 5,66:1 |
| Éxito `#0f7653` sobre su fondo suave | 4,96:1 |
| Aviso `#9a6200` sobre su fondo suave | 4,63:1 |
| Error `#b42318` sobre su fondo suave | 5,75:1 |
| Cian claro `#5fd0dc` sobre grafito `#111c24` | 9,50:1 |
| Borde de campo `#7f8c9b` sobre blanco | 3,43:1 |

Además: foco visible de 3 px, etiquetas en todos los campos, zonas táctiles de 44 px, enlaces
subrayados, estados siempre con texto y símbolo (no solo color), un `h1` por página, y nada
se desborda a 360 px. Son comprobaciones hechas con capturas y pruebas, no una certificación.

## Pruebas

- `gastos-http.test.ts`: adaptador HTTP ante 200, 401, 404, JSON inválido, JSON con otra forma,
  error sin JSON, fallo de red, CSRF + `Idempotency-Key` en el envío y 413.
- `pantalla-gastos.test.tsx` (**ARCH-01**): la misma pantalla de gastos funciona con el
  adaptador en memoria y con otra implementación del puerto, sin tocar la interfaz.
- `pantalla-nuevo-gasto.test.tsx`: archivo elegido, estado devuelto (aprobado y en revisión),
  viaje elegido, 413, límite de tamaño previo, reintento con la misma clave y sesión vencida.
- `formulario-entrar.test.tsx`, `gastos-memoria.test.ts`, `configuracion.test.ts`.

Las pruebas de extremo a extremo (Playwright) contra la API real quedan para la integración.
