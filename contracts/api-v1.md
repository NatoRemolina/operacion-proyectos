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
| 403 | `SELF_APPROVAL` | Administración intenta aprobar o rechazar el presupuesto de su propio viaje; el intento queda en la auditoría |
| 404 | `NOT_FOUND` | No existe o no es visible para la persona |
| 409 | `IDEMPOTENCY_CONFLICT` | Misma `Idempotency-Key` con un archivo distinto o con otro `viaje_id` |
| 409 | `EDIT_CONFLICT` | La revisión trae una `version` que ya no es la del gasto, o el recibo todavía se está leyendo |
| 409 | `REQUEST_IN_PROGRESS` | El primer envío con esa clave todavía no creó su gasto: reintentar con la misma clave |
| 409 | `INVALID_STATE` | El estado del viaje no admite esa acción (por ejemplo, cerrar uno pendiente) |
| 409 | `PRICE_CONFIRMATION_REQUIRED` | Al aprobar, el precio del vuelo subió más que la tolerancia: se repite con `confirmar_precio: true`; el cambio va en `fields.precio` |
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
  propio: boolean;                            // es de la persona de la sesión (titular o viajero)
  precio_por_confirmar: string | null;        // pendiente cuyo precio subió más que la tolerancia: "antes … ahora …"
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
  version: number;                            // sube con cada cambio; la revisión la manda de vuelta
  motivo_rechazo: string | null;              // por qué se rechazó, si se rechazó
}

interface Justificacion {
  id: number;
  tipo: "texto" | "audio";
  canal: string;                              // "web" | "celular" | "telegram" | "api"
  texto: string | null;                       // lo escrito o la transcripción de la nota de voz
  transcripcion: "no_aplica" | "pendiente" | "hecha" | "fallida";
  creado: string;
}

interface ResumenAdmin {
  presupuesto_aprobado_usd: Dinero;           // viajes aprobados y cerrados
  gastado_usd: Dinero;                        // gastos aprobados de esos viajes
  disponible_usd: Dinero;                     // aprobado − gastado
  en_revision_usd: Dinero;                    // gastos que esperan revisión, en USD
  ejecucion_pct: number | null;
  viajes_por_aprobar: number; gastos_en_revision: number;
  pendientes: ViajeResumen[];                 // hasta 5
  revision: GastoResumen[];                   // hasta 5
  actividad: {                                // los 10 gastos más recientes
    gasto_id: number; comercio: string | null;
    persona: { id: number; codigo: string; nombre: string } | null;   // titular del viaje o, sin viaje, quien lo cargó
    viaje: { id: number; codigo: string } | null;
    total: Dinero; moneda: string | null; total_usd: Dinero;
    estado: EstadoGasto; estado_texto: string; creado: string;
  }[];
  nota: string;                               // cómo se calcula el disponible
  datos_demostracion: boolean;                // local con cuentas de demostración
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

### `POST /viajes/{id}/estado`
Solo administración. Cuerpo JSON `{"accion": "aprobar|rechazar|reabrir|cerrar", "motivo": "...", "confirmar_precio": false}` y `X-CSRF-Token`. Llama a `viajes.cambiar_estado`, la misma regla que la pantalla de administración:

- Colaborador y gestor: 403 `FORBIDDEN`.
- Nadie aprueba ni rechaza su propio presupuesto, tampoco un administrador: 403 `SELF_APPROVAL` y el intento queda en la auditoría (`autoaprobación impedida`).
- `aprobar` y `rechazar` solo desde pendiente; `reabrir` desde aprobado, rechazado o cerrado; `cerrar` desde aprobado. Otra combinación: 409 `INVALID_STATE`.
- `rechazar` exige `motivo` de 5 caracteres o más (422 con `fields.motivo`); la persona lo ve en su viaje.
- Al aprobar se reconfirma el precio del vuelo. Si subió más que la tolerancia: 409 `PRICE_CONFIRMATION_REQUIRED` con el cambio en `fields.precio`; con `confirmar_precio: true` se aprueba y el presupuesto pasa al precio nuevo. Sin clave del buscador se aprueba con el aviso «Precio no reconfirmado».
- 200 `{"viaje": ViajeDetalle, "mensaje": string}`: el mensaje dice lo que pasó, con el aviso de precio si lo hubo. 404 si el viaje no existe.

### `GET /resumen`
Solo administración (403 `FORBIDDEN` para colaborador y gestor). 200 `ResumenAdmin`: las cifras salen del catálogo de métricas (`metricas.viajes`, `pendientes_revision`), la misma definición que los tableros. Disponible = aprobado − gastos aprobados; las reservas de tiquetes se sumarán cuando existan.

### `GET /gastos`
Parámetros: `viaje_id`, `estado` (opcionales), `limite`, `cursor`. Mismo alcance que los viajes. `{"items": GastoResumen[], "siguiente"}`.

### `GET /gastos/{id}`
200 `GastoDetalle`. 404 si no existe o no es visible.

### `POST /gastos`
`multipart/form-data`: `archivo` (obligatorio), `viaje_id` (opcional), `justificacion` (opcional, hasta 2.000 caracteres: para qué fue el gasto). Cabeceras: `X-CSRF-Token` y `Idempotency-Key` (recomendada: un valor único por archivo, que se repite si se reintenta el mismo envío).

- Sin `viaje_id`, la plataforma resuelve el viaje que corresponde a la persona hoy (`viajes.resolver_para_gasto`). Con `viaje_id`, solo se acepta un viaje propio; si no lo es, el gasto queda sin viaje y en revisión.
- 201 `GastoDetalle` con su estado real tras leer y validar: `aprobado_auto` o `revision`. La web muestra ese estado, no «aprobado» por haber recibido 201.
- Misma clave y mismo archivo (y mismo `viaje_id`): 200 con el mismo gasto, aunque siga `procesando`; no se vuelve a leer. Misma clave con otro archivo u otro `viaje_id`: 409 `IDEMPOTENCY_CONFLICT`. Si el primer envío aún no creó el gasto: 409 `REQUEST_IN_PROGRESS`. La clave es de cada persona: la misma clave de dos personas son dos envíos.
- Si la lectura se interrumpe, el gasto no queda `procesando`: pasa a `revision` con el motivo `lectura_fallida`, y el reintento con la misma clave lo devuelve.
- Errores: 413, 415, 422.

### `POST /gastos/{id}/revision`
Solo administración. Cuerpo JSON `RevisionGasto` y `X-CSRF-Token`:
`{"version": 3, "accion": "guardar|aprobar|excepcion|rechazar", "motivo": "...", "total": "54.00", "moneda": "USD", ..., "viaje_id": 12}`.
Los campos de datos que no se mandan se conservan; los importes van como cadena. Es la misma regla que la revisión de la web (`app/servicios/revision.py`):

- `version` debe ser la del gasto: si otra persona lo cambió mientras tanto (u otro proceso, como la lectura o la asignación de viaje), 409 `EDIT_CONFLICT` y no se aplica nada. Cada revisión sube la versión.
- Nadie revisa ni aprueba lo suyo, tampoco un administrador: 403 `FORBIDDEN` con el mensaje, y el intento queda en la auditoría.
- `rechazar` exige `motivo` de 5 caracteres o más (si no, 422); se guarda en `motivo_rechazo`, queda en el evento y le llega a la persona por Telegram si tiene el chat vinculado.
- `aprobar` vuelve a evaluar las reglas con el viaje bloqueado: si no pasan, guarda las correcciones y el gasto sigue en `revision` (200, con sus `motivos`). `excepcion` aprueba con `motivo` de 8 caracteres o más, salvo un importe o una fecha que no son válidos, o sin total, moneda o tasa (422).
- Un importe que no es un número finito: 422 por campo. Uno negativo o cero se guarda y queda en revisión con `importe_invalido`.
- 200 `GastoDetalle` con la `version` nueva. 404 si el gasto no existe.

### `POST /gastos/{id}/justificaciones`
Cuerpo JSON `{"texto": string}` (3 a 2.000 caracteres) y `X-CSRF-Token`. Añade para qué fue el gasto, con las palabras de la persona. 201 `GastoDetalle` con la justificación nueva al final. Solo justifica quien hizo el gasto o quien viaja: un gasto que la persona ve pero no es suyo (el gestor, administración) responde 403 `FORBIDDEN`; uno que no ve, 404. Texto vacío o muy corto: 422. Las notas de voz entran por la web o por Telegram; ver `docs/justificaciones.md`.

### `GET /documentos/{id}/contenido`
El archivo original, con su tipo (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`; un correo se entrega como `text/plain`), `Content-Disposition: inline`, `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. 404 si el gasto al que pertenece no es visible.

## Fuera de este contrato (siguientes fases)

Cotizar y decidir, reproceso de una lectura fallida, proyectos, usuarios, asignaciones y auditoría. Ver la sección 9 del plan fullstack.
