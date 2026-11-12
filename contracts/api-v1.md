# Contrato de la API v1 (recorrido mínimo)

Fuente de verdad mientras se construye. Cuando la API exista, el OpenAPI que genera (`contracts/openapi-v1.json`) debe coincidir con este documento; si difieren, se corrige uno de los dos en el mismo cambio.

Base: `/api/v1`. Mismo origen que la web (el gateway envía `/api/v1/*` a la API y el resto a la web).

## Reglas comunes

| Regla | Detalle |
|---|---|
| Identidad | Cookie de sesión `HttpOnly` (`sesion` en local, `__Host-sesion` en HTTPS). Nunca en `localStorage`. El rol y la persona salen siempre de la sesión, jamás del cuerpo |
| Escrituras | Toda petición que no sea GET lleva `X-CSRF-Token` con el valor recibido en `login` o `me`. Además el origen debe ser el mismo o estar en `ORIGENES_WEB` |
| Lo ajeno | Un recurso que la persona no puede ver responde **404**, igual que uno inexistente |
| Caché | Toda respuesta lleva `Cache-Control: no-store` |
| Dinero | Cadenas decimales con dos cifras: `"54.00"`. Nunca números de coma flotante. `null` si no se pudo leer |
| Fechas | Fecha de un recibo: `"2026-12-09"` (sin hora). Instantes de auditoría: `"2026-11-12T04:13:13Z"` (UTC) |
| Listados | `{"items": [...], "siguiente": "<cursor>" \| null}`. Parámetros `limite` (1–100, por defecto 20) y `cursor`. Orden: más reciente primero |
| Petición | Cada respuesta trae la cabecera `X-Peticion` y, en los errores, el mismo valor en `request_id` |

## Errores

Siempre JSON, nunca HTML ni redirecciones:

```json
{"error": {"code": "VALIDATION_ERROR", "message": "Hay datos que no son válidos.", "fields": {"viaje_id": "No es un número"}}, "request_id": "a1b2c3d4e5f6"}
```

| Estado | `code` | Cuándo |
|---|---|---|
| 401 | `UNAUTHENTICATED` | Sin sesión o sesión vencida. La web vuelve a la pantalla de ingreso |
| 401 | `INVALID_CREDENTIALS` | Correo o contraseña incorrectos (mensaje genérico) |
| 403 | `CSRF_INVALID` | Falta o no coincide `X-CSRF-Token` |
| 403 | `ORIGIN_NOT_ALLOWED` | Escritura desde un origen no permitido |
| 403 | `FORBIDDEN` | Operación reservada a otro rol |
| 404 | `NOT_FOUND` | No existe o no es visible para la persona |
| 409 | `IDEMPOTENCY_CONFLICT` | Misma `Idempotency-Key` con un archivo distinto |
| 413 | `PAYLOAD_TOO_LARGE` | Archivo de más de 4,5 MB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | El contenido no es JPG, PNG, WebP, PDF ni correo |
| 422 | `VALIDATION_ERROR` | Campos inválidos; detalle por campo en `fields` |
| 429 | `TOO_MANY_ATTEMPTS` | Demasiados intentos de ingreso |
| 500 | `INTERNAL_ERROR` | Fallo interno, ya registrado |

Un gasto que queda **en revisión** no es un error: es una respuesta correcta con `estado: "revision"`.

## Tipos

```ts
type Rol = "colaborador" | "gestor" | "admin";   // el permiso; antes del 12 nov 2026 «colaborador» se llamaba «piloto»
type EstadoViaje = "pendiente_aprobacion" | "aprobado" | "rechazado" | "cerrado";
type EstadoGasto = "procesando" | "revision" | "aprobado_auto" | "aprobado" | "rechazado";
type Dinero = string | null;   // "54.00"

interface Persona { id: number; codigo: string; nombre: string; rol: Rol; correo: string; cargo: string | null }
// `cargo`: qué hace la persona en la empresa («Pilotaje de dron», «Edición de video»...). Lo mantiene administración y no da permisos.

interface ViajeResumen {
  id: number; codigo: string;                 // "V-2026-0001"
  estado: EstadoViaje; estado_texto: string;  // "Aprobado"
  en_curso: boolean;
  origen: string; destino: string;            // códigos IATA
  ida: string; regreso: string;               // fechas
  proyecto: { id: number; nombre: string } | null;
  titular: { id: number; codigo: string; nombre: string } | null;
  presupuesto_usd: Dinero; gastado_usd: Dinero; en_revision_usd: Dinero;
  ejecucion_pct: number | null;               // gastado ÷ presupuesto, entero
  gastos: number;
}

interface ViajeDetalle extends ViajeResumen {
  presupuesto_detalle: { concepto: string; valor: Dinero; grupo: string }[];
  motivo: string | null;                      // de rechazo o reapertura
  aprobado_en: string | null;
}

interface GastoResumen {
  id: number;
  viaje: { id: number; codigo: string } | null;
  comercio: string | null; fecha: string | null; categoria: string | null;
  total: Dinero; moneda: string | null; total_usd: Dinero;
  estado: EstadoGasto; estado_texto: string;  // "En revisión"
  creado: string;
}

interface GastoDetalle extends GastoResumen {
  subtotal: Dinero; impuesto: Dinero; propina: Dinero;
  motivos: string[];                          // códigos estables, por ejemplo "sin_viaje"
  alertas: string[];                          // textos para mostrar
  canal: string;                              // "web" | "celular" | "correo" | "telegram"
  documento_id: number | null;
  lectura: { origen: string; confianza: number | null };
  justificaciones: Justificacion[];           // en orden de llegada
}

interface Justificacion {
  id: number;
  tipo: "texto" | "audio";
  canal: string;                              // "web" | "celular" | "telegram" | "api"
  texto: string | null;                       // lo escrito o la transcripción de la nota de voz
  transcripcion: "no_aplica" | "pendiente" | "hecha" | "fallida";
  creado: string;
}
```

## Endpoints

### `POST /auth/login` (pública)
Cuerpo JSON `{"correo": string, "clave": string}`. Respuesta 200 `{"persona": Persona, "csrf_token": string}` y la cookie de sesión. Errores: 401 `INVALID_CREDENTIALS`, 429 `TOO_MANY_ATTEMPTS`, 403 `ORIGIN_NOT_ALLOWED`. No lleva `X-CSRF-Token` (todavía no hay sesión).

### `GET /auth/me`
200 `{"persona": Persona, "csrf_token": string}`. Sin sesión: 401. La web lo llama al cargar para saber quién es y para aislar su caché por persona.

### `POST /auth/logout`
Con `X-CSRF-Token`. 204 sin cuerpo; revoca la sesión en el servidor y borra la cookie.

### `GET /viajes`
Parámetros: `estado` (opcional), `limite`, `cursor`. Devuelve los viajes visibles para la persona: los suyos; el gestor, además los de sus proyectos; administración, todos. `{"items": ViajeResumen[], "siguiente"}`.

### `GET /viajes/{id}`
200 `ViajeDetalle`. 404 si no existe o no es visible.

### `GET /gastos`
Parámetros: `viaje_id`, `estado` (opcionales), `limite`, `cursor`. Mismo alcance que los viajes. `{"items": GastoResumen[], "siguiente"}`.

### `GET /gastos/{id}`
200 `GastoDetalle`. 404 si no existe o no es visible.

### `POST /gastos`
`multipart/form-data`: `archivo` (obligatorio), `viaje_id` (opcional), `justificacion` (opcional, hasta 2.000 caracteres: para qué fue el gasto). Cabeceras: `X-CSRF-Token` y `Idempotency-Key` (recomendada: un valor único por archivo, que se repite si se reintenta el mismo envío).

- Sin `viaje_id`, la plataforma resuelve el viaje que corresponde a la persona hoy (`viajes.resolver_para_gasto`). Con `viaje_id`, solo se acepta un viaje propio; si no lo es, el gasto queda sin viaje y en revisión.
- 201 `GastoDetalle` con su estado real tras leer y validar: `aprobado_auto` o `revision`. La web muestra ese estado, no «aprobado» por haber recibido 201.
- Misma clave y mismo archivo: 200 con el mismo gasto. Misma clave y otro archivo: 409.
- Errores: 413, 415, 422.

### `POST /gastos/{id}/justificaciones`
Cuerpo JSON `{"texto": string}` (3 a 2.000 caracteres) y `X-CSRF-Token`. Añade para qué fue el gasto, con las palabras de la persona. 201 `GastoDetalle` con la justificación nueva al final. Solo justifica quien hizo el gasto o quien viaja: un gasto que la persona ve pero no es suyo (el gestor, administración) responde 403 `FORBIDDEN`; uno que no ve, 404. Texto vacío o muy corto: 422. Las notas de voz entran por la web o por Telegram; ver `docs/justificaciones.md`.

### `GET /documentos/{id}/contenido`
El archivo original, con su tipo (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`; un correo se entrega como `text/plain`), `Content-Disposition: inline`, `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. 404 si el gasto al que pertenece no es visible.

## Fuera de este contrato (siguientes fases)

Cotizar y decidir, transiciones del viaje, revisión de gastos (guardar, aprobar, rechazar, excepción), reproceso de una lectura fallida, proyectos, usuarios, asignaciones y auditoría. Ver la sección 9 del plan fullstack.
