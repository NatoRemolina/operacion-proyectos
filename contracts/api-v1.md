# Contrato de la API v1

Lo que usa la web nueva: ingreso, cotizar y decidir, viajes, gastos y envío de recibos (foto, PDF, correo `.eml` o confirmación HTML), Excel contable, asistente con voz, y la aprobación de viajes y la revisión de gastos de administración.

El OpenAPI que genera la API (`contracts/openapi-v1.json`, `python -m datos.exportar_contrato`) debe coincidir con este documento; una prueba lo comprueba, y si difieren se corrigen los dos en el mismo cambio.

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
| 409 | `IDEMPOTENCY_CONFLICT` | Misma `Idempotency-Key` con un archivo distinto o con otro `viaje_id`; al cotizar, con otro pedido |
| 409 | `EDIT_CONFLICT` | La revisión trae una `version` que ya no es la del gasto, o el recibo todavía se está leyendo |
| 409 | `REQUEST_IN_PROGRESS` | El primer envío con esa clave todavía no creó su gasto (o su cotización): reintentar con la misma clave |
| 409 | `DECISION_LOCKED` | El viaje de la cotización ya está aprobado o cerrado: la decisión no cambia sin que administración lo reabra |
| 409 | `INVALID_STATE` | El estado del viaje no admite esa acción (por ejemplo, cerrar uno pendiente) |
| 409 | `PRICE_CONFIRMATION_REQUIRED` | Al aprobar, el precio del vuelo subió más que la tolerancia: se repite con `confirmar_precio: true`; el cambio va en `fields.precio` |
| 413 | `PAYLOAD_TOO_LARGE` | Archivo de más de 4,5 MB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | El contenido no es JPG, PNG, WebP, PDF, correo (.eml) ni confirmación HTML (.html); en la voz, no es WAV |
| 422 | `VALIDATION_ERROR` | Campos inválidos; detalle por campo en `fields` |
| 429 | `TOO_MANY_ATTEMPTS` | Demasiados intentos de ingreso (con `Retry-After`), o cinco fallos en 24 horas con la contraseña actual en `POST /cuenta/clave` |
| 429 | `TOO_MANY_REQUESTS` | Tope de cotizaciones nuevas del día por persona (regla `tope_cotizaciones_persona_dia`, 20 en la semilla) |
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
  precio_por_confirmar: string | null;        // solo administración: pendiente cuyo precio subió más que la tolerancia
}

interface ViajeDetalle extends ViajeResumen {
  presupuesto_detalle: { concepto: string; valor: Dinero; grupo: string }[];
  motivo: string | null;                      // de rechazo o reapertura
  aprobado_en: string | null;
}

interface GastoResumen {
  id: number;
  viaje: { id: number; codigo: string } | null;
  comercio: string | null; fecha: string | null;
  categoria: string | null;   // vuelo | hotel | alquiler_carro | transporte_terrestre | combustible | comida | parqueo_peajes | compras_proyecto | otros
  total: Dinero; moneda: string | null; total_usd: Dinero;
  estado: EstadoGasto; estado_texto: string;  // "En revisión"
  creado: string;
  propio: boolean;                            // es de la persona de la sesión: nadie revisa sus propios gastos
}

interface GastoDetalle extends GastoResumen {
  subtotal: Dinero; impuesto: Dinero; propina: Dinero;
  motivos: string[];                          // códigos estables, por ejemplo "sin_viaje"
  alertas: string[];                          // textos para mostrar
  canal: string;                              // "web" | "celular" | "correo" | "telegram"; un .eml o un .html que se sube queda "correo"
  documento_id: number | null;
  correo: { remitente: string | null; asunto: string | null } | null;  // si el soporte es un correo (.eml)
  lectura: { origen: string; confianza: number | null };
  justificaciones: Justificacion[];           // en orden de llegada
  version: number;                            // sube con cada cambio; la revisión la manda de vuelta
  motivo_rechazo: string | null;              // por qué se rechazó, si se rechazó
  puede_justificar: boolean;                  // hizo el gasto o viaja: puede contar para qué fue
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
Cuerpo JSON `{"correo": string, "clave": string}`. Respuesta 200 `{"persona": Persona, "csrf_token": string, "demostracion": boolean}` y la cookie de sesión. `demostracion` dice si la plataforma corre en local con cuentas de demostración (la web lo muestra en la barra). Errores: 401 `INVALID_CREDENTIALS`, 429 `TOO_MANY_ATTEMPTS`, 403 `ORIGIN_NOT_ALLOWED`. No lleva `X-CSRF-Token` (todavía no hay sesión).

Límite de intentos (`app/servicios/intentos.py`): con 10 fallos en 15 minutos con un mismo correo desde una misma dirección, 20 desde una dirección con cualquier correo, o 50 con un mismo correo desde cualquier dirección (exista o no la cuenta), responde 429 `TOO_MANY_ATTEMPTS` sin mirar la contraseña, aunque sea la buena. El 429 lleva `Retry-After`: los segundos que faltan para que el fallo que deja la cuenta de intentos en su máximo salga de la ventana, más un segundo porque los momentos se guardan truncados al segundo (nunca menos de 1): quien espera justo eso ya no está limitado. Es el único límite del ingreso: no hay bloqueo por cuenta, así que fallar con el correo de otra persona desde otra dirección no la deja por fuera (el umbral solo por correo es holgado por eso). Un ingreso bueno borra los fallos de su correo. El evento «ingreso limitado» se escribe una vez por ventana para cada correo y dirección, no en cada intento. La dirección es la de quien pide; detrás de CloudFront, la de `CloudFront-Viewer-Address`. El formulario `/entrar` aplica el mismo límite, también con 429 y `Retry-After`.

En la nube, toda petición que no traiga la cabecera secreta `X-Origen-CloudFront` (la añade CloudFront; valor en `ORIGEN_SECRETO`) llegó directo a la dirección de la función y recibe 403 `FORBIDDEN`. La única excepción es `/telegram/webhook`, que trae su propio secreto.

### `GET /auth/me`
200 `{"persona": Persona, "csrf_token": string, "demostracion": boolean}`. Sin sesión: 401. La web lo llama al cargar para saber quién es y para aislar su caché por persona.

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

### `GET /gastos/contable`
El Excel contable: un `.xlsx` (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) con `Content-Disposition: attachment; filename="libro_contable_<desde>_<hasta>[_proyecto_<id>].xlsx"`, `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. Lo genera `app/servicios/contable.py`.

- Parámetros: `desde` y `hasta` (`AAAA-MM-DD`, por la fecha del recibo, ambos incluidos; por omisión, el año en curso, del 1 de enero al 31 de diciembre, en la zona de la empresa, `America/Bogota`, la misma de todos los topes y fechas de la plataforma y declarada en la hoja «Resumen»: así la nube, que corre en UTC, no propone el año siguiente desde las 19:00 del 31 de diciembre) y `proyecto_id` (opcional, de 1 a 2147483647; fuera de ese rango, 422).
- Entran los gastos `aprobado` y `aprobado_auto` que la persona puede ver: administración, todos; quien gestiona, los de sus proyectos y los suyos; el resto, solo los suyos.
- Hoja «Gastos», una fila por gasto: n.º, fecha, viaje, proyecto, código y nombre de la persona, proveedor, categoría, cuenta contable, base, impuesto (vacío si la lectura no lo trae), propina, total, moneda, tasa a USD, total USD, estado, quién aprobó y cuándo (UTC), alertas o excepción y el enlace al gasto en la plataforma. Hoja «Resumen»: totales por proyecto, por cuenta y por moneda, y los parámetros del libro (fechas, filtros, quién lo generó y cuándo).
- La cuenta contable sale de un mapa categoría → cuenta editable en «Reglas y supuestos» (claves `cuenta_contable_<categoría>`, ámbito `supuesto`).
- Ningún texto queda como fórmula: lo que empieza por `=`, `+`, `-`, `@`, tabulador o retorno de carro va precedido de un apóstrofo.
- `proyecto_id` de un proyecto que la persona no gestiona: 403 `FORBIDDEN`, exista o no (no revela qué proyectos existen). Administración con un proyecto inexistente: 404. Fecha ilegible o periodo al revés: 422 con el campo (`desde` o `hasta`) en `fields`. Sin sesión: 401.
- Cada descarga deja el evento `libro contable descargado` (entidad `contabilidad`).

### `GET /gastos/{id}`
200 `GastoDetalle`. 404 si no existe o no es visible.

### `POST /gastos`
`multipart/form-data`: `archivo` (obligatorio), `viaje_id` (opcional), `justificacion` (opcional, hasta 2.000 caracteres: para qué fue el gasto). Cabeceras: `X-CSRF-Token` y `Idempotency-Key` (recomendada: un valor único por archivo, que se repite si se reintenta el mismo envío).

- Sin `viaje_id`, la plataforma resuelve el viaje que corresponde a la persona hoy (`viajes.resolver_para_gasto`). Con `viaje_id`, solo se acepta un viaje propio; si no lo es, el gasto queda sin viaje y en revisión.
- 201 `GastoDetalle` con su estado real tras leer y validar: `aprobado_auto` o `revision`. La web muestra ese estado, no «aprobado» por haber recibido 201.
- Misma clave y mismo archivo (y mismo `viaje_id`): 200 con el mismo gasto, aunque siga `procesando`; no se vuelve a leer. Misma clave con otro archivo u otro `viaje_id`: 409 `IDEMPOTENCY_CONFLICT`. Si el primer envío aún no creó el gasto: 409 `REQUEST_IN_PROGRESS`. La clave es de cada persona: la misma clave de dos personas son dos envíos.
- Si la lectura se interrumpe, el gasto no queda `procesando`: pasa a `revision` con el motivo `lectura_fallida`, y el reintento con la misma clave lo devuelve.
- Cada lectura con el modelo se reserva antes de llamarlo, del tope de la persona (`lecturas_recibo_persona_dia`) y del total de la empresa (`lecturas_recibo_dia`), igual por la web, la API, el buzón y Telegram. Pasado el tope no se llama al modelo: 201 con el gasto en `revision`, motivo `lectura_fallida`, el aviso «Lectura pendiente por tope» y `origen_dato` «pendiente por tope». El soporte queda guardado.
- Si el recibo es del tiquete ya comprado del viaje (de vuelo, con el localizador de la compra o con su mismo importe), se enlaza como soporte del gasto de la compra y la respuesta trae ese gasto: no se crea otro.
- Un PDF de más de 15 páginas no se lee ni se guarda, tampoco el que llega adjunto a un correo (`.eml`): 422 con el número de páginas en `fields.archivo`.
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
- Una `categoria` que no está en el catálogo de la plataforma: 422 con `fields.categoria` y no se aplica nada (también en la pantalla de administración).
- 200 `GastoDetalle` con la `version` nueva. 404 si el gasto no existe.

### `POST /gastos/{id}/justificaciones`
Cuerpo JSON `{"texto": string}` (3 a 2.000 caracteres) y `X-CSRF-Token`. Añade para qué fue el gasto, con las palabras de la persona. 201 `GastoDetalle` con la justificación nueva al final. Solo justifica quien hizo el gasto o quien viaja: un gasto que la persona ve pero no es suyo (el gestor, administración) responde 403 `FORBIDDEN`; uno que no ve, 404. Texto vacío o muy corto: 422. Las notas de voz entran por la web o por Telegram; ver `docs/justificaciones.md`.

### `GET /documentos/{id}/contenido`
El archivo original, con su tipo (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`; de un correo `.eml` se entrega su adjunto si es un PDF o una foto, y si no tiene, su texto como `text/plain` con De, Asunto, Fecha y el cuerpo, nunca el MIME crudo), `Content-Disposition: inline` (una confirmación HTML se guarda reducida a texto plano, sin código ni enlaces, y se entrega como `text/plain` con `Content-Disposition: attachment`), `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. 404 si el gasto al que pertenece no es visible.

### `POST /asistente`
Para los tres permisos, cada uno con el alcance de su sesión: el colaborador ve sus viajes y sus gastos; el gestor, además, los de los proyectos que gestiona; administración, todo. El alcance lo pone la sesión, nunca la pregunta: un viaje, un gasto o una persona fuera de él se responde como si no existiera y no aparece entre las fuentes, y los indicadores de toda la empresa son solo para administración. Sin sesión, 401; 403 solo por `CSRF_INVALID`, `ORIGIN_NOT_ALLOWED` o una sesión sin un permiso válido (`FORBIDDEN`). Cuerpo `{"pregunta": "..."}` (1 a 500 caracteres; solo espacios es 422) y `X-CSRF-Token`. Sigue la misma vía que la plataforma: asesor (agente con herramientas), modelo con herramientas o consultas directas, con el mismo tope diario por persona y el mismo rastro en `asistente_consultas`. Con el asesor puede tardar hasta un minuto.

200 `RespuestaAsistente`: `id` (el de esta respuesta, para seguir la conversación; vacío con el tope), `texto`, `modo` (`asesor`, `modelo`, `determinista` o `tope`), `modo_texto` (el modo en palabras), `fuentes` (`tipo`, `codigo` y `destino`: `{"tipo": "viaje" | "gasto" | "cotizacion", "id"}` o `null` si no tiene pantalla, como una persona), `herramientas`, `duracion_ms`, `usadas` y `tope`. Llegar al tope diario no es un error: responde 200 con `modo: "tope"` y el texto lo explica.

Opcionales en el cuerpo, para una conversación más personal:
- `contexto`: `{"pantalla": "gasto", "id": 123}`, la pantalla desde la que se pregunta. `pantalla` es una de `resumen`, `viajes`, `viaje`, `gastos`, `gasto`, `buzon`, `nuevo_gasto`, `cotizar`, `cotizacion`, `kpis`, `persona`, `monitoreo`, `vuelos`, `reglas`, `usuarios`, `proyectos`, `proyecto`, `mi_cuenta`, `compras` o `compra` (esta, solo para administración); `id` (1 a 2³¹−1) solo en las de un registro. Solo viajan el tipo y el id: el servidor busca el registro y lo describe al asistente («Está viendo el gasto #123, en estado revision») solo si está en el alcance de la sesión; si no existe o no se puede ver, no lo menciona. Así «¿por qué está en revisión este gasto?» se entiende sin repetir el número.
- `anteriores`: los `id` de las respuestas anteriores de la conversación (como mucho 3, de la más vieja a la más nueva). El servidor lee esas preguntas y respuestas de `asistente_consultas`, solo las de la misma persona, y las marca como contexto, no como instrucciones; sirven para «¿y el anterior?» o «explícame más». El cliente nunca manda el texto de lo que respondió el asistente: así nadie le pone en la boca algo que no dijo.
- `historial` (de transición): la forma de antes (como mucho 3 turnos `{"pregunta", "respuesta"}`). Se usa solo si no hay conversación guardada con los `anteriores` que se mandan (o no se mandan), con el mismo recorte y la misma marca de «contexto, no instrucciones»; con `anteriores` válidos se ignora. Así un cliente que aún manda el texto no pierde el hilo.

Cualquier otro campo, una pantalla desconocida, un `id` fuera de rango o más de 3 turnos: 422.

### `POST /asistente/voz`
Para los tres permisos, con los mismos topes por persona. `multipart/form-data` con `audio`: la pregunta grabada en WAV (la web graba y convierte en el navegador), hasta 4,5 MB, y `X-CSRF-Token`. La transcribe el modelo de lectura; no la responde ni la guarda. 200 `{"texto": "..."}` (vacío si no se entendió nada). 413 `PAYLOAD_TOO_LARGE`, 415 `UNSUPPORTED_MEDIA_TYPE` si no es WAV, 422 si llega vacío, 429 `TOO_MANY_REQUESTS` si la persona llegó a su tope del día de preguntas (`asistente_preguntas_dia`) o de dictados (`asistente_dictados_dia`), sin llamar al modelo, y 503 `SERVICE_UNAVAILABLE` si no hay modelo configurado o no respondió.

## Cotizar y decidir

Es el mismo cálculo de las pantallas (`app/servicios/cotizacion.py`): una búsqueda para todos los aeropuertos marcados, el costo total esperado de cada vuelo y la decisión que crea el viaje. Las respuestas del buscador se guardan y una consulta idéntica no se vuelve a pagar.

```ts
interface Lugar { nombre: string; region: string; pais: string; lat: number; lon: number }

interface LugarSugerido {
  tipo: "lugar" | "aeropuerto" | "pais";
  id: string; nombre: string; region: string; pais: string;
  lat: number | null; lon: number | null;
  tambien: string | null;                     // otro nombre con que coincidió
  aviso: string | null;                       // por qué no trae aeropuertos
  origen: "local" | "google";                 // la interfaz marca los de Google
  aeropuertos: { iata: string; nombre: string | null; municipio: string | null;
                 km: number | null; horas: number | null; grande: boolean }[];
}

interface LineaCosto {
  concepto: string; valor_usd: Dinero;
  origen: "buscador" | "regla" | "supuesto";  // de dónde sale el valor
  tipo: "precio" | "equipaje" | "riesgo_cambio" | "millas" | "traslado" | "otro";
}

interface OpcionVuelo {
  id: number; aerolinea: string; numeros: string[];
  desde: string | null; hasta: string | null; // aeropuertos reales del vuelo
  sale: string; llega: string;                // hora local, "2026-12-08 07:35"
  escalas: number; duracion_min: number | null;
  precio_usd: Dinero;                         // precio del buscador
  tarifa: { nombre: string; permite_cambio: boolean; reales: boolean };
  costo_total_usd: Dinero;                    // precio + equipaje + riesgo de cambio − millas + traslado
  desglose: { precio_usd: Dinero; equipaje_usd: Dinero; riesgo_cambio_usd: Dinero; millas_usd: Dinero; traslado_usd: Dinero };
  lineas: LineaCosto[];
  avisos: string[];
  descartada: string | null;                  // la razón, si no sirve
  recomendada: boolean; mas_barata: boolean;  // la más barata entre las que sirven, no entre las descartadas
  origen_dato: string | null;                 // "en vivo" | "guardado" | "guardado (otras fechas)"
  esperado_usd: Dinero; frente_esperado_pct: number | null;   // modelo de precios, si hay uno utilizable
  total_con_hotel_usd: Dinero;                // vuelo + hotel recomendado (una suma, no todas las combinaciones); null sin hotel
  fuente_url: string;                         // este vuelo en Google Flights: la búsqueda con su ida elegida
  vendedor_url: string;                       // ruta firmada (5 min, esta sesión) que abre la página oficial: GET …/vendedor?t=…
}

interface LineaHotel {
  concepto: string; valor_usd: Dinero;
  origen: "buscador" | "supuesto";
  tipo: "tarifa" | "tarifa_miembro" | "puntos";
}

interface OpcionHotel {
  id: number; nombre: string; noche_usd: Dinero;
  total_usd: Dinero;                          // tarifa del buscador para todas las noches
  costo_total_usd: Dinero;                    // tarifa − tarifa de miembro − puntos (estos dos, solo con membresía)
  lineas: LineaHotel[];
  avisos: string[];                           // «Acumula solo con reserva directa», la oportunidad de inscribirse
  calificacion: number | null; clase: number | null;
  programa: string | null;                    // reconocido por la marca del nombre (Marriott Bonvoy, Hilton Honors...)
  socio: boolean;                             // el viajero o la empresa tiene membresía de ese programa
  membresia_de_ejemplo: boolean;              // esa membresía es un dato inventado para la demostración
  descartado: string | null;                  // la razón (calificación bajo el mínimo), si no sirve
  origen_dato: string | null;
  recomendada: boolean;                       // menor costo total entre los que sirven
  mas_barata: boolean;                        // menor tarifa entre los que sirven, si no es la recomendada
  fuente_url: string;                         // este hotel en Google Hotels con las fechas, para verificar el precio
}

interface Cotizacion {
  id: number;
  estado: "buscando" | "comparando" | "decidido";
  creado: string; solicitado_por: string | null;
  proyecto: { id: number; nombre: string } | null;
  viajero: { id: number; nombre: string } | null;
  origen: { codigo: string; aeropuertos: string[]; lugar: Lugar | null };
  destino: { codigo: string; aeropuertos: string[]; lugar: Lugar | null };
  ciudad_hotel: string | null; ida: string; regreso: string; noches: number;
  hora_limite: string | null;                 // "18:00" del día de ida
  baterias_n: number; baterias_wh: number; maleta: boolean; prob_cambio_pct: number;
  carro_usd: Dinero;
  equipo: { nivel: "ok" | "aviso" | "bloqueo"; texto: string };
  origen_dato: string | null;                 // de dónde salieron los vuelos; "fallida" si no hubo
  aviso: string | null;                       // «lo más barato no es lo mejor», cuando aplica
  fallos: string[];
  recomendacion: string;                      // explicación determinista de la recomendada
  vuelos: OpcionVuelo[];                      // los que sirven, del menor al mayor costo total esperado
  descartados: OpcionVuelo[];
  hoteles: OpcionHotel[];                     // los que sirven, del menor al mayor costo total (con la fidelización)
  hoteles_descartados: OpcionHotel[];
  hotel_recomendado_id: number | null;
  recomendada_id: number | null; mas_barata_id: number | null;
  decision: { id: number; vuelo_id: number; hotel_id: number | null; motivo: string | null; razones: string[];
              total_usd: Dinero;              // costo total esperado de lo decidido (con riesgo de cambio y millas)
              siguio_recomendacion: boolean; creado: string;
              aviso: string | null } | null; // si se decidió sin consultar en vivo por el tope del día
  viaje: { id: number; codigo: string; estado: EstadoViaje; estado_texto: string;
           presupuesto_usd: Dinero } | null; // lo que aprueba administración: sin riesgo ni millas, con viáticos
  fuente_url: string;                         // la búsqueda de vuelos en Google Flights (ver «Fuente de los precios»)
  fuente_hoteles_url: string;                 // la búsqueda de hoteles en Google Hotels con las fechas
  puede_decidir: boolean;                     // la persona puede guardar o cambiar la decisión ahora
  bloqueo: string | null;                     // por qué ya no, si es el caso
}
```

### `GET /lugares`
Parámetros: `q` (hasta 80 caracteres), `google` (`0` o `1`), `limite` (1–20, por defecto 8). Sugerencias para el campo de origen o destino: lugares con sus aeropuertos cercanos (distancia y horas por carretera), aeropuertos y países. Sin `google` responde al instante con los datos propios; con `google=1` suma el autocompletado de Google con los mismos topes del formulario (por persona y día, y por mes) y, si no consulta, lo dice en `aviso_google`. 200 `{"resultados": LugarSugerido[], "aviso_google": string | null, "carretera": {"factor", "velocidad_kmh"}}`. Menos de 2 letras: `resultados` vacío.

### `GET /cotizaciones/formulario`
Lo necesario para llenar una cotización: `proyectos` (cada uno con `para_otra_persona`: administración puede en todos; el gestor, en los que gestiona), `viajeros` que la persona puede elegir (un colaborador y un gestor sin proyectos, solo a sí mismos; gestión con proyectos y administración, a cualquiera), `viajero_propio_id`, `elige_viajero`, `razones` de la decisión (`{clave, texto}`) y `precios_en_vivo` (sin clave del buscador solo hay precios para las rutas guardadas).

### `POST /cotizaciones`
Cuerpo JSON con `X-CSRF-Token` e `Idempotency-Key` opcional:

```json
{"proyecto_id": 1, "viajero_id": null,
 "origen": {"texto": "Miami (MIA)"},
 "destino": {"aeropuertos": ["CNY", "GJT", "SLC"], "lugar": {"nombre": "Moab", "region": "Utah", "pais": "Estados Unidos", "lat": 38.57332, "lon": -109.54984}},
 "ida": "2026-12-08", "regreso": "2026-12-11", "hora_limite": "18:00", "ciudad_hotel": "",
 "baterias_n": 4, "baterias_wh": 77, "maleta": true, "prob_cambio_pct": 25, "carro_dia_usd": "65.00"}
```

- Cada lado lleva los aeropuertos marcados (hasta 8, se comparan en una sola búsqueda) con el lugar, o un `texto` con ciudad o código. El aeropuerto principal es el marcado más cercano al lugar; el traslado por carretera se calcula hasta el lugar.
- `viajero_id` omitido: viaja quien cotiza. Otra persona: administración en cualquier proyecto y el gestor solo en los proyectos que gestiona; si no, 403 `FORBIDDEN`.
- 201 `Cotizacion` con la comparación lista. Un lugar o código que no se reconoce, fechas imposibles, un proyecto que no existe: 422 con el campo en `fields`.
- Misma `Idempotency-Key` y mismo pedido: 200 con la misma cotización, sin volver a buscar. Con otro pedido: 409 `IDEMPOTENCY_CONFLICT`. Si el primero todavía está buscando: 409 `REQUEST_IN_PROGRESS`. Un pedido rechazado (422) deja la clave libre.
- Cada cotización nueva puede gastar dos búsquedas pagas: pasado el tope del día por persona (regla `tope_cotizaciones_persona_dia`, 20 en la semilla), 429 `TOO_MANY_REQUESTS`. Repetir una ya hecha con su clave no cuenta.

### `GET /cotizaciones/{id}`
200 `Cotizacion`. La ven quien la creó, quien viaja, el gestor del proyecto y administración; los demás reciben 404.

### `POST /cotizaciones/{id}/decision`
Cuerpo JSON `{"vuelo_id": 76, "hotel_id": null, "motivo": "", "razones": ["costo_total"]}` y `X-CSRF-Token`.

- Si el vuelo no es el recomendado, `motivo` (5 caracteres o más) es obligatorio: 422 con `fields.motivo`. Un vuelo que no es de la cotización: 422 con `fields.vuelo_id`. El hotel es opcional.
- Guarda la decisión con todas las opciones mostradas y crea el viaje (o actualiza el de la cotización) con su presupuesto, `pendiente_aprobacion`. 200 `Cotizacion` con `decision` y `viaje` (`V-2026-0012`).
- El mismo envío repetido no duplica la decisión.
- Deciden quien viaja, quien la creó y administración; quien la creó para otra persona, solo si el proyecto está en su alcance. El gestor que solo la ve recibe 403 `FORBIDDEN`. Con el viaje ya aprobado o cerrado: 409 `DECISION_LOCKED`.
- Si no hay vuelos que cumplan (todos descartados), se puede elegir un descartado con `motivo`.
- Decidir consulta el regreso y las opciones de reserva del vuelo (dos búsquedas; lo guardado no se paga). Pasado el tope del día por persona (regla `decisiones_en_vivo_dia`, 10 en la semilla), se decide con lo guardado y `decision.aviso` lo dice.
- `id`, `vuelo_id`, `hotel_id`, `proyecto_id` y `viajero_id` son enteros de 1 a 2³¹−1; fuera de ese rango, 422.

### `POST /cotizaciones/{id}/fuente`
Cuerpo JSON `{"destino": "vuelos"}` (con `"vuelo_id": 76`, la página de ese vuelo) o `{"destino": "hoteles", "hotel_id": 90}` (sin `hotel_id`, la lista de hoteles) y `X-CSRF-Token`. Deja en la bitácora de la cotización el paso `fuente abierta` con quién, adónde y la URL, y responde 200 `{"destino": "vuelos", "url": "https://www.google.com/travel/flights?..."}`. La web lo llama al hacer clic en «Ver en Google Flights» o «Ver en Google Hotels»; el enlace se abre igual aunque el registro falle.

- **Fuente de los precios.** `fuente_url` es el `search_metadata.google_flights_url` de la respuesta guardada del buscador para esa ruta y esas fechas; si falta, se construye con los aeropuertos y las fechas (la misma forma `tfs` que usa el buscador). En hoteles, el enlace guardado no trae fechas: se toma su texto de búsqueda y se le añaden («Moab hotels from 2026-12-08 to 2026-12-11»), y cada hotel lleva la búsqueda con su nombre. Solo se aceptan enlaces `https://www.google.com/travel/...` sin credenciales ni puerto; un enlace guardado que no cumpla se reemplaza por el construido. El enlace siempre lleva las fechas de la cotización: si el precio mostrado salió de una respuesta guardada de otras fechas (`origen` «guardado (otras fechas)»), Google puede mostrar otro precio. Sin ciudad guardada, los hoteles se buscan con el destino.
- La URL siempre la arma el servidor: el cuerpo no acepta `url` (422). Un `vuelo_id` o `hotel_id` que no es de la cotización: 422 con `fields.vuelo_id` o `fields.hotel_id`.
- La abre quien ve la cotización (también el gestor del proyecto); a los demás, 404.

### `GET /cotizaciones/{id}/vuelos/{vuelo_id}/vendedor?t=…`
Navegación en otra pestaña (la abre «Ver desglose»), no una llamada de datos. Se usa tal como llega en `OpcionVuelo.vendedor_url`: el parámetro `t` es un token firmado con la sesión, ligado a la cotización y al vuelo, que vence a los 5 minutos (la web vuelve a pedir la cotización cada 4). Responde 200 `text/html`: una página mínima que envía por POST el pedido de un solo uso del vendedor (`booking_request` del buscador: su dirección y el cuerpo del envío) a Google, que redirige a la página oficial del vendedor con ese itinerario. Elige la aerolínea si vende el itinerario; si no, el primer vendedor.

- Para llegar al pedido: el regreso del vuelo (guardado o 1 búsqueda) y las opciones de reserva con su `booking_token` (1 búsqueda). El mismo itinerario dentro de la hora lo sirve el buscador de su caché: no se guarda otra copia y se anota como «caché del buscador».
- El `booking_request` **solo viaja en esta respuesta**: no se guarda en la base, en el respaldo ni en los registros (la respuesta del buscador se guarda sin él). Cabeceras `no-store`, `Referrer-Policy: no-referrer` y una CSP con `default-src 'none'`, el script por `nonce` y `form-action https:` (Chrome aplica la directiva también a la redirección de Google a la aerolínea; el destino ya lo valida el servidor).
- Lista blanca de salida: solo `https://www.google.com/travel/clk…` (también sin `www`), sin credenciales, puerto, `..` ni caracteres de control; una redirección abierta como `/url?q=` queda fuera.
- **303 a la página del vuelo en Google Flights**, sin buscar nada, si: falta el token, es de otra sesión u otro vuelo, o venció; no hay clave del buscador; el tope del día (regla `enlace_vendedor_persona_dia`, 20 búsquedas pagas por persona desde la medianoche de Bogotá, regresos y fallidas incluidos; repetir el mismo itinerario en la hora no cuenta) se alcanzó; hay más de 6 repeticiones del mismo itinerario en la hora; la respuesta del buscador es rara, solo trae billetes separados o un vendedor fuera de la lista blanca; o cualquier fallo al prepararlo.
- La abre **toda persona que ve la cotización** (también el gestor del proyecto). Lo ajeno: 404 y una navegación desde otro sitio (`Sec-Fetch-Site: cross-site`): 403, las dos como página legible. Sin sesión: 401 (JSON, del control de acceso general).
- Cada apertura deja en la bitácora de la cotización el paso `página oficial abierta` (quién, opción, vendedor y dominio de salida, o por qué fue a Google Flights) y una fila en `clics_fuente`.

### `GET /cotizaciones/{id}/vuelos/{opcion_id}/reserva`
Primera capa del desglose (aparece en 2 a 5 s, sin esperar a la lectura de la página): las opciones de reserva del buscador para el itinerario, **de lo guardado**, sin consultar ni gastar cupo. Las trae el enlace a la página oficial (`…/vendedor`) que abre el mismo clic; la respuesta guardada nunca lleva el pedido de un solo uso.

```json
{"estado": "listo", "consultado": "2026-11-13T15:10:00Z", "en_vivo": true,
 "tarifas": [{"vendedor": "American", "nombre": "Basic Economy", "precio": 458, "equipaje": ["1 free carry-on", "1st checked bag: 110"],
              "cambios": ["No ticket changes"], "reembolso": ["No refunds"], "otras": ["Seat selection for a fee"],
              "elige": "la ida AA 1851, sale 9:48 am, y el regreso AA 3321, sale 11:06 pm"}],
 "vendedores": [{"vendedor": "American", "aerolinea": true, "precio_desde": 458}]}
```

`elige` dice qué vuelos elegir en la página del vendedor, con su hora de salida (algunos vendedores abren la lista del día sin el vuelo elegido); con billetes separados, cada tiquete trae el suyo y su `nombre` es `ida` o `regreso`. `estado: sin_datos` mientras no haya nada guardado. `consultado` es null si las tarifas vienen del respaldo del repositorio (la web las marca «de referencia»).

`en_vivo` dice si el clic que abre el desglose consulta el buscador en vivo: hay clave y a la persona le queda cupo de búsquedas pagas del día (`enlace_vendedor_persona_dia`; en 0, apagado), o el propio clic acaba de reservarlo, porque se reserva antes de buscar. Con el cupo agotado el clic va a Google Flights y no hay nada que esperar. Si es verdadero, el clic que abre el desglose lo consulta en vivo (de 18 a 30 s) y lo nuevo se guarda en `busquedas`, que comparten todas las instancias, así que llega a esta misma ruta: la web recuerda el momento del clic y reintenta cada 2 s, hasta 40 s, mientras no haya tarifas con `consultado` posterior al clic o de la hora anterior a él. Lo de esa hora vale como de este clic: el mismo pedido dentro de la hora el buscador lo sirve de su caché y no se guarda otra copia, así que nada más nuevo va a llegar (y cubre la diferencia de relojes entre el navegador y el servidor). Si el servidor responde con error mientras espera, deja de preguntar. Mientras espera, muestra lo guardado marcado «Precios guardados del {fecha}: actualizando con el buscador…» (o «de referencia», sin `consultado`), o «Consultando el buscador…» si no hay nada; los «Ir a…» siguen funcionando y el precio final lo da la página del vendedor. Al llegar lo nuevo, lo reemplaza sin marca. A los 40 s sin nada nuevo, o tras un error, deja lo guardado con «El buscador no respondió a tiempo; los precios son del {fecha}»; si no hay nada, «El buscador no trajo opciones de reserva para este vuelo» (o, tras un error, «No se pudieron traer las opciones del buscador»). Con `en_vivo: false`, un solo pedido: lo guardado es todo lo que hay. La ve quien ve la cotización; lo ajeno, 404.

### `POST /cotizaciones/{id}/vuelos/{opcion_id}/ir`
Cuerpo JSON `{"vendedor": "American", "tarifa": "Main Cabin"}` (los nombres como los muestra el desglose; «Tarifa» si el vendedor no la nombra) y `X-CSRF-Token`. Responde 200, `no-store`:

```json
{"camino": "buscador", "url": "https://www.google.com/travel/clk/f?...", "campos": [["u", "…"], ["adurl", ""]],
 "vendedor": "American", "tarifa": "Main Cabin", "motivo": null,
 "guia": "En American, elige la ida AA 1851, sale 9:48 am, y el regreso AA 3321, sale 11:06 pm; Main Cabin desde 694 USD."}
```

- Con billetes separados, `tarifa` es el tramo del tiquete: `ida` o `regreso` (`{"vendedor": "COPA", "tarifa": "ida"}`).
- Tres caminos, en orden: **`buscador`**: el pedido de un solo uso de esa tarifa o de ese tiquete en las opciones de reserva del buscador (el mismo enlace del «Continue» de Google; 2 a 5 s, contado en `enlace_vendedor_persona_dia`). Con billetes separados el buscador puede no traer opciones (prueba del 16 nov, MDE → MIA). **`pagina`**: el analizador abre la página del vuelo, elige el mismo regreso de la cotización (si la página lo muestra; si no, el más barato), despliega el vendedor (o el diálogo de billetes separados), pulsa el «Continue» de esa tarifa o tiquete e intercepta el envío que Google iba a hacer, sin que salga del servidor. **`google`**: la página del vuelo en Google Flights (sin `campos`).
- Si otro vendedor lleva ahora ese tramo, `vendedor` es el actual y `motivo` lo dice («Avianca ya no vende este tramo; ahora lo vende eDreams a 316 USD»); `guia` empieza con ese aviso.
- Cada clic encola una captura completa con motivo `clic` si la tarifa la confirmó el buscador o la página, o está en lo guardado del vuelo; hasta `capturas_clic_persona_dia` (10) por persona y día.
- Con `campos`, el navegador de la persona hace un POST a `url` (siempre `https://www.google.com/travel/clk…`) y Google lo lleva al vendedor. Los `campos` viajan **solo en esta respuesta**: no se guardan ni se registran.
- Topes por día: regla `ir_a_persona_dia` (20, por persona) y `ir_a_dia` (60, en total). Alcanzado uno, `camino: google` con el motivo. Comparte con las lecturas el turno del analizador (una a la vez) y el cerrojo.
- Bitácora `ir a vendedor`: quién, opción, vendedor, tarifa, camino, dominio y duración; la captura previa al clic queda en `analisis_vuelo` (`accion: ir_a`).
- Lo ajeno o un vuelo de otra cotización: 404. Sin CSRF: 403. Un vendedor o tarifa con caracteres raros, o un campo `url`: 422.

### `GET /cotizaciones/{id}/vuelos/{opcion_id}/ir?vendedor=…&tarifa=…&t=…`
Navegación en otra pestaña (la abre «Ir a…»), siempre con la dirección que trae cada tarifa en `ir_url` (en `…/reserva` y en `AnalisisVuelo.datos.tarifas`): el token `t` está firmado con la sesión, la cotización, el vuelo, el vendedor y la tarifa, y vence a los 5 minutos. Sin él (un enlace enviado por correo, viejo o de otra tarifa): 403 con una página legible, sin hacer el pedido ni gastar nada. Con `vendedor` o `tarifa` ausentes o fuera de forma (1 a 60 caracteres) o un `t` de más de 64: 422 con una página legible, no JSON. Con todo en regla, una página mínima que muestra «Preparando tu enlace a {vendedor} · {tarifa}…», llama a `POST …/ir` con la sesión y envía el formulario directo, sin clic intermedio (o va a Google Flights). Única pausa: si `POST …/ir` entrega otro vendedor que el pedido, muestra `guia` (que empieza con el aviso) y espera un clic en «Ir a {vendedor}». Si falla, lo explica y ofrece Google Flights. CSP con `default-src 'none'`, script por `nonce`, `connect-src 'self'` y `form-action https:`; `no-store`. Abrirla no gasta el tope; desde otro sitio (`Sec-Fetch-Site: cross-site`), 403.

### `POST /cotizaciones/{id}/vuelos/{opcion_id}/analisis`
Con `X-CSRF-Token` y sin cuerpo. Lee la página del vuelo en Google Flights (la búsqueda de la cotización con la ida de ese vuelo elegida; el analizador elige el regreso más barato para llegar a las opciones de reserva) y responde 200 `AnalisisVuelo`. Tarda unos segundos (hasta 55); la web muestra «Leyendo la página del vuelo…» mientras tanto.

```ts
interface AnalisisVuelo {
  id: number | null; opcion_id: number;
  estado: "pendiente" | "listo" | "fallido" | "no_disponible";
  motivo: string | null;          // «la página pidió verificación», «Llegaste al tope de lecturas…», etc.
  url: string | null;             // https://www.google.com/travel/flights?... (la página leída)
  leido: string | null;           // cuándo terminó la lectura (UTC)
  duracion_ms: number | null;
  reutilizado: boolean;           // lectura de menos de 60 minutos del mismo vuelo: no se abrió la página otra vez
  precio_buscador_usd: Dinero;    // el precio que sigue usando la comparación
  aviso_precio: string | null;    // si la página muestra otro precio total, lo dice
  datos: {
    precio_total: number | null;
    tramos: { fecha; sale; llega; aerolinea; duracion; ruta; escalas; detalle_escalas: string[]; emisiones }[];
    tarifas: { vendedor; nombre; precio: number; equipaje: string[]; cambios: string[]; reembolso: string[]; otras: string[] }[];
    vendedores: { vendedor: string; aerolinea: boolean; precio_desde: number | null }[];
    equipaje: string[]; cambios: string[]; reembolso: string[];
    regreso_elegido: { precio: number; aerolinea; escalas; sale; llega; desde; hasta; duracion } | null;
    notas: string[]; avisos: string[];
  } | null;                       // solo con estado «listo»; el texto es el de la página (en inglés)
  extracto: string | null;        // con «fallido»: el comienzo del texto que mostró la página
  captura_url: string | null;     // GET de la captura PNG, como evidencia (también de una lectura fallida, salvo verificación)
}
```

- Un análisis por itinerario (números de vuelo y fecha) y fechas de la cotización, **de cualquier cotización**: si hay uno `listo` de menos de 60 minutos, uno `fallido` de menos de 10 (para no repetirlo enseguida) o uno `pendiente` de menos de 2, se devuelve con `reutilizado: true` y no se abre la página. Una `pendiente` de más de 2 minutos se da por `fallido: la lectura no terminó`.
- Si llega `pendiente` (otra persona la está leyendo), la web la sigue con `GET …/analisis` cada 3 s, hasta 15 veces.
- `no_disponible` (no se guarda nada, no cuenta para los topes y el desglose muestra solo lo del buscador): `ANALIZADOR=apagado`, entorno sin analizador, analizador que no responde a la conexión o función inexistente, tope del día por persona (regla `analisis_persona_dia`, 10) o en total (regla `analisis_vuelo_dia`, 40), u otra lectura en curso (una a la vez; el turno se toma en una transacción con cerrojo, y en AWS la función tiene concurrencia reservada de 1).
- `fallido` con su `motivo`: la página pidió verificación o aceptar condiciones (nunca se resuelven), llevó a otro sitio o quiso abrir otra pestaña, tardó demasiado (plazo total de 45 s), el analizador respondió algo que no se entiende o no se pudo guardar la lectura.
- Lo leído **no reemplaza** el precio del buscador. Al decidir, la lectura vigente se copia a la decisión (`desglose.analisis_google`).
- La pide quien ve la cotización; un vuelo de otra cotización o una cotización ajena: 404.

### `GET /cotizaciones/{id}/vuelos/{opcion_id}/analisis`
200 `AnalisisVuelo` con la última lectura del vuelo (para seguir una en curso); 404 si nunca se leyó.

### `GET /cotizaciones/{id}/analisis/{analisis_id}/captura`
200 `image/png` con la captura de la página leída (hasta 4000 px de alto), `no-store`. Se ve desde cualquier cotización que tenga ese itinerario, aunque la lectura la pidiera otra. Lo ajeno o sin captura: 404.

### `GET /cotizaciones/{id}/evidencia` (pieza 5)
200 `Evidencia`: la evidencia completa de la decisión vigente, que guarda el trabajador programado (`app/tareas.py`) sin que la decisión espere. Una captura del vuelo (Google Flights con el detalle de cada tramo, y la página de la aerolínea con el total y los impuestos) y otra del hotel elegido (Google Hotels) al decidir; una del vuelo cada día hasta la compra o la ida; una final al registrar la compra.

```ts
interface Evidencia {
  estado: "sin_evidencia" | "guardando" | "guardada";   // guardando: «Guardando la evidencia del vuelo…»
  guardada: string | null;                              // «Evidencia guardada a las HH:MM» (UTC, ISO 8601)
  capturas: {
    id: number; tipo: "vuelo" | "hotel"; motivo: "decision" | "seguimiento" | "compra";
    estado: "pendiente" | "en_curso" | "lista" | "fallida"; fallo: string | null; intentos: number;
    creado: string | null; terminado: string | null;
    datos: { google?: object; aerolinea?: object; hotel?: object } | null;   // todo lo leído
    imagenes: string[];      // GET …/evidencia/{captura_id}/imagen/{n}: PNG de página completa
    texto_url: string | null; // GET …/evidencia/{captura_id}/texto: text/plain, hasta 300 KB
  }[];
  seguimiento: { momento: string | null; motivo: string; precio_google_usd: Dinero; total_aerolinea_usd: Dinero }[];
}
```

Solo con permiso de ver la cotización (lo ajeno, 404; sin sesión, 401). Imágenes y texto con `Cache-Control: private, no-store` y `nosniff`. `GET /compras/{id}` trae la misma `evidencia`.

### `GET /cotizaciones/{id}/evidencia/{captura_id}/imagen/{n}` y `…/texto`
La captura `n` (0 a 9) en `image/png` y el texto visible completo en `text/plain`, de una captura `lista` de esa cotización. Lo demás: 404.

## Integraciones (clave de servicio)

Las rutas bajo `/api/v1/servicio/` son para integraciones como n8n, no para personas: no usan cookie ni `X-CSRF-Token`. Cada petición lleva `X-Clave-Servicio: isk_…`, una clave de servicio creada por administración (`python -m datos.claves_servicio crear n8n --permiso soportes:leer`), que se muestra una sola vez y se guarda como huella. Sin clave, con una clave inexistente o revocada: 401 `UNAUTHENTICATED`; con una clave sin el permiso de la operación: 403 `FORBIDDEN`. Lo que hace la clave queda en la bitácora con su nombre (por ejemplo, «n8n»). Configuración del flujo: `docs/n8n/README.md`.

### `GET /servicio/gastos/{id}/soporte?vence=…&firma=…`
Permiso `soportes:leer` y, además, el enlace firmado que trae el aviso `gasto.registrado` (vence a los 15 minutos): un enlace filtrado no sirve sin la clave, y la clave sola no recorre los soportes por número. Sin enlace, con la firma alterada, con otro gasto o con el vencimiento cambiado: 403 `LINK_INVALID`; vencido: 403 `LINK_EXPIRED`. Responde el archivo original del soporte, con su tipo, `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. 404 si el gasto no existe o no tiene soporte.

### Aviso saliente `gasto.registrado`
No es un endpoint de la API sino lo que la plataforma envía a `N8N_WEBHOOK_URL` cada vez que se registra un gasto, por cualquier canal (apagado si faltan `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_SECRETO` o, fuera de local, `URL_PUBLICA`). POST JSON compacto con las cabeceras `X-Inflight-Evento: gasto.registrado`, `X-Inflight-Entrega: <uuid>` (se repite en los reintentos) y `X-Inflight-Firma: t=<segundos unix>,v1=<hex>`, donde `hex = HMAC-SHA256(N8N_WEBHOOK_SECRETO, "<t>.<cuerpo>")`. Cuerpo: `evento`, `entrega`, `gasto_id`, `viaje` (código o `null`), `proyecto`, `persona` (código), `fecha`, `comercio`, `categoria`, `total` (`"54.00"` o `null`), `moneda`, `total_usd`, `estado`, `alertas`, `enlace_gasto`, `lectura`, `enlace_soporte` y `enlace_vence_en_segundos`. `lectura` es la lectura original del modelo (`gastos.extraido`): los campos del gasto más `numero_factura`, `id_fiscal` y `lineas` (`descripcion`, `cantidad`, `total`), `confianza` y `dudas`; `null` si la lectura falló. Los importes, las cantidades y la confianza (en `lectura` y en el cuerpo) viajan como texto con dos decimales; `gasto_id` y `enlace_vence_en_segundos` son enteros. Así la firma se puede verificar volviendo a serializar el JSON en JavaScript. `lectura.origen_dato` dice de dónde salió (`en vivo`, `guardado` o `reutilizado`); la persona se resuelve como en el Excel contable. Tiempo de espera: 2 s para conectar y 3 s en total; un fallo no afecta el registro del gasto y el aviso se reintenta con espera creciente (1, 5, 30, 120 y 720 minutos) al registrarse el siguiente gasto o con `python -m datos.avisos reintentar`; después queda como `fallido` en `avisos_salientes`.

## Fuera de este contrato (siguientes fases)

Reproceso de una lectura fallida y las pantallas de analítica de precios y flujo de la información, que siguen en la plataforma anterior. La hoja de ruta está en `docs/informe-tecnico.md`.

## Revisión completa de gastos

Lecturas que la revisión de administración necesita en la web nueva, además de `GET /gastos/{id}`. La escritura sigue siendo `POST /gastos/{id}/revision`, con las reglas de arriba.

### `GET /gastos/{id}/revision`
Solo administración (403 `FORBIDDEN` para colaborador y gestor, aunque vean el gasto). 404 si no existe. 200 `DatosRevision`:

```ts
interface DatosRevision {
  gasto_id: number; version: number;          // la misma versión que devuelve la ficha
  metodo_pago: string | null; canal_reserva: string | null;   // editables, no salen en GastoDetalle
  lectura_original: {                          // lo que leyó el modelo, intacto; null si la lectura falló
    comercio: string | null; fecha: string | null; categoria: string | null;
    subtotal: Dinero; impuesto: Dinero; propina: Dinero; total: Dinero; moneda: string | null;
    metodo_pago: string | null; canal_reserva: string | null;
    confianza: number | null; dudas: string[];
  } | null;
  soporte: { documento_id: number; nombre: string | null;
             forma: "imagen" | "pdf" | "descarga" } | null;   // según lo que entrega /documentos/{id}/contenido
  categorias: { clave: string; nombre: string }[];            // las de la plataforma, en orden
  viajes: { id: number; codigo: string; estado: EstadoViaje; estado_texto: string; titular: string | null;
            origen: string | null; destino: string | null; ida: string | null; regreso: string | null;
            propio: boolean }[];               // propio: viaje de quien revisa; cargar el gasto ahí lo haría suyo
  propio: boolean;                             // nadie revisa lo suyo
  aviso_propio: string | null;                 // por qué no se revisa y si hay otra persona que pueda
}
```

- `viajes`: a los que se puede reasignar el gasto con `viaje_id` en la revisión; todos salvo los rechazados, el más reciente primero (las mismas opciones que la revisión de las pantallas de administración). Los marcados `propio` son de quien revisa: reasignar el gasto a uno de ellos responde 403 (nadie revisa lo suyo), y la web lo explica antes de enviar.
- El archivo del soporte se pide a `GET /documentos/{documento_id}/contenido`, y `forma` dice cómo mostrar lo que entrega: `imagen` y `pdf` al lado (un correo `.eml` con su PDF o su foto adjunta también); `descarga` es texto: un correo sin adjunto legible (su texto con De, Asunto y Fecha, en línea) o una confirmación HTML guardada como texto (se descarga como `.txt`).

### `GET /gastos/{id}/justificaciones/{jid}/audio`
La nota de voz de una justificación, tal como llegó (`audio/ogg`, `audio/mpeg` o `audio/mp4`), con `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. Se oye si se ve el gasto; si no, o si la justificación es de otro gasto o es escrita, 404.

## Reglas y supuestos

Solo administración (403 `FORBIDDEN` para colaborador y gestor). La lógica es la de `app/servicios/reglas.py`, la misma que la pantalla de administración `/reglas`.

### `GET /reglas`
200 `CatalogoReglas`:

```ts
interface Regla {
  id: number; ambito: string; entidad: string | null; tarifa: string | null; clave: string;
  valor: string;                       // siempre texto; `numerica` dice si es un número
  numerica: boolean;
  nota: string | null; fuente: string | null;     // fuente: una dirección http(s) o la descripción de dónde sale
  confianza: string | null;            // oficial, buscador, secundaria, sin verificar, supuesto
  verificado: string | null;           // AAAA-MM-DD
}
interface CatalogoReglas {
  grupos: { clave: string; titulo: string; reglas: Regla[] }[];
  membresias: { id: number; titular: string; de_empresa: boolean; programa: string | null;
                entidad: string | null; estatus: string | null; ejemplo: boolean }[];   // solo lectura
}
```

- Grupos, en este orden si existen: `aerolinea` (Aerolíneas), `hotel` (Programas de hotel), `bateria` (Baterías), `supuesto` (Supuestos), `kpi` (Metas de los KPI), `cuenta_contable` (Cuentas contables: los supuestos `cuenta_contable_<categoría>`, que no se repiten entre los supuestos) y, al final, cualquier otro ámbito.
- `ejemplo` en una membresía: dato inventado para la demostración; la web lo rotula «Dato de ejemplo».

### `POST /reglas/{id}`
Cuerpo JSON `{"valor": "0.25"}` (hasta 500 caracteres) y `X-CSRF-Token`. 200 `Regla` con el valor nuevo y `verificado` de hoy.

- Una regla numérica sigue siendo numérica: solo dígitos con, a lo sumo, un separador decimal (`^\d+(?:[.,]\d+)?$`; «0,25» se guarda «0.25»). Un texto, un negativo, un exponente («1e3»), guiones bajos («1_000») o un vacío responden 422 `VALIDATION_ERROR` con `fields.valor` y no se guarda nada. «1,000» (de uno a tres dígitos, coma y tres dígitos) es ambiguo: 422 con «¿Mil o uno? Escribe 1000 o 1.0».
- Una regla de texto guarda el texto sin espacios al principio ni al final.
- Deja el evento «regla editada» con el valor anterior y el nuevo. 404 si la regla no existe.

## KPIs

Solo administración, como la pantalla `/admin/kpis`: otra cuenta recibe 403 `FORBIDDEN`. Las cifras salen de la misma definición que la pantalla y que `/api/metricas` (`app/servicios/kpis.py`). Filtros comunes: `proyecto_id` (0 o ausente: todos), `desde` y `hasta` (`AAAA-MM-DD`; una fecha que no es válida se ignora, como en la pantalla).

### `GET /kpis`
200 `TableroKpis`:

- `kpis`: cada indicador de los dos retos con `valor` (número en su `unidad`, o `null` sin datos), `meta`, `alerta`, `sentido` (`mayor` o `menor` es mejor), `estado` (`verde`, `ambar`, `rojo`, `sin datos` o `fuera de rango`), `responsable`, `formula` y `principal`. `fuera de rango` es un valor imposible para el indicador (días u horas negativos, una proporción sobre 100 %): un dato malo que hay que revisar, nunca en meta. El ahorro sí puede ser negativo.
- `resumen`: cuántos hay en cada estado (`verde`, `ambar`, `rojo`, `sin_datos`, `fuera_de_rango`). `tendencia`: los principales semana a semana (8 semanas, de lunes a domingo, hasta `hasta` u hoy).
- `cotizacion` y `gastos`: los desgloses de la pantalla. Los conteos van como `{etiqueta, valor}`.
- `personas` (una fila por cuenta con lo suyo) y `por_cargo`. `proyectos` y `retos` sirven para armar los filtros y los títulos.

### `GET /kpis/personas/{id}`
200 `FichaPersona`: datos de la cuenta (sin contraseña), totales, indicadores de la persona, cotizaciones, viajes, gastos, evidencias y `eventos`, la línea de tiempo con los hechos sobre lo suyo (200 como máximo, del más reciente). Deja el evento «ficha consultada». Una persona que no existe: 404.

### `GET /kpis/exportar.csv?que=kpis|consultas|personas`
El mismo CSV de la pantalla con los filtros comunes, `text/csv` con BOM y `no-store`. Deja el evento «exportación». Otro valor de `que`: 422.

### `GET /kpis/rutas-frecuentes?n=10`
200 `RutasFrecuentes`: las `n` rutas (1 a 50; otro valor: 422) con más cotizaciones y viajes de los últimos 90 días. Por ruta: `por_anticipacion` (mediana en USD por tramo de días: `0-7`, `8-21`, `22-45`, `46+`), `mediana`, `volatilidad` (desviación absoluta mediana), `tendencia` (`sube`, `baja` o `estable` según el historial diario), `prima_flexibilidad` (tarifa con cambio gratis o maleta incluida menos la básica del mismo itinerario, en USD y %), `aerolinea_agencia` y `senal` (`por debajo`, `dentro` o `por encima` del rango habitual; orientativa, no predice). `null` donde no hay datos. Además `exactitud` (MAE y MAPE del precio esperado, en total, por ruta y por mes, y `contra_pagado`: lo pagado frente a lo cotizado al decidir, solo con compras `comprada` y activas; sin datos, `mensaje` «sin datos todavía»), `tarifas_vistas`, `pocos_datos` y `aviso`. Antes de responder pone al día las tarifas vistas, como mucho cada 10 minutos. Solo administración.

## Monitoreo

Solo administración, como `/admin/monitoreo`: otra cuenta recibe 403 `FORBIDDEN`. Mismos filtros que los KPIs. Las cifras salen del catálogo de métricas (`app/servicios/metricas.py`), la misma definición de la pantalla.

### `GET /monitoreo?pestana=viajes|gastos|busquedas|modelo|cupos|auditoria|calidad`
200 `PestanaMonitoreo` (sin `pestana`: gastos; otra: 422). Cada pestaña llega lista para mostrar:

- `cifras`: `{etiqueta, valor, unidad, pie}`; `valor` es `null` sin datos.
- `tablas`: `{titulo, columnas, filas, vacio, nota, barras}`. Cada columna dice su `unidad` (`USD`, `%`) si es una cifra. Una celda es texto, número, `null` o un enlace `{texto, href}` a una página de la web (`/viajes/7`). `barras` marca las tablas cuya segunda columna se puede dibujar (embudo, gasto por categoría).
- `exportar`: las vistas de la pestaña que se pueden descargar.
- La pestaña Modelo incluye el costo del asesor, con su tope diario (supuesto `asesor_usd_dia`). La Auditoría no se filtra por proyecto.

### `GET /monitoreo/exportar.csv?vista=v_h_…`
El mismo CSV de la pantalla con los filtros, `text/csv` con BOM y `no-store`. Deja el evento «exportación». Solo las vistas de la capa analítica (`v_h_viaje`, `v_h_gasto`, `v_h_busqueda`, `v_h_decision`, `v_h_lectura`, `v_h_evento`, `v_h_consulta`); otra: 422.

## Vuelos

Estado de cada tramo de los viajes aprobados, el día del viaje. Solo administración, como el tablero de `/admin/viajes`: otra cuenta (también quien viaja) recibe 403 `FORBIDDEN`. Las reglas (ventana, caché, topes y avisos al viajero) son las de `app/servicios/monitoreo_vuelos.py`.

### `GET /vuelos?fecha=AAAA-MM-DD`
200 `VuelosDelDia` con `tramos`. Sin fecha (o con una no válida): los de hoy (UTC) más los de ayer o mañana que están en su ventana.

- Pensado para pedirse cada 15 s con la pestaña visible: cada tramo se consulta solo dentro de su ventana (desde 3 h antes de la salida hasta la llegada), con caché y topes por tramo, viaje y día; fuera de eso responde lo último conocido.
- Cada tramo: estado (`estado` y `estado_texto`), `retraso` en minutos, `terminal` y `puerta`, horas locales programadas y estimadas, `no_llega` (con el retraso no llega a la hora límite de la grabación), `omitida` (por qué no se consultó la última vez) y `aviso` (el último aviso al viajero).
- `origen`: `en vivo` o `guardado`; `origen_texto`: «En vivo» o «Estado de ejemplo» (la respuesta guardada del repositorio, que se usa sin clave del buscador o si la consulta falla). Null si el tramo nunca trajo datos.

### `POST /vuelos/{tramo_id}/actualizar`
Con `X-CSRF-Token`, sin cuerpo. «Actualizar ahora»: salta la caché (una vez por minuto), nunca la ventana ni los topes. 200 `ResultadoActualizacion` con `consultado`, `motivo` si no consultó, `mensaje` en palabras y el `tramo` actualizado. Un tramo que no existe: 404.

## Proyectos

Lo que hacen hoy las pantallas `/admin/proyectos` y `/proyectos/{id}`, con la misma regla (`app/servicios/proyectos.py`): administración ve, crea y edita todos; quien gestiona ve el tablero de los proyectos que gestiona; el resto no ve ninguno. El `id` va de 1 a 2147483647; fuera de ese rango, 422.

```ts
interface ProyectoResumen {
  id: number; nombre: string; cliente: string | null; ciudad: string | null;
  fecha_inicio: string; fecha_fin: string;   // "2026-12-15"
  moneda: string;                            // "USD"
  viajes: number; gastos: number;            // en cualquier estado
  previsto_usd: Dinero;     // presupuesto de los viajes del proyecto que no se rechazaron
  real_usd: Dinero;         // gastos aprobados (aprobado y aprobado_auto)
  diferencia_usd: Dinero;   // real − previsto: positivo es sobrecosto
}
interface CategoriaProyecto { clave: "vuelo" | "hotel" | "alquiler_carro" | "viaticos"; nombre: string;
                              previsto_usd: Dinero; real_usd: Dinero; diferencia_usd: Dinero }
interface TableroProyecto {
  proyecto: ProyectoResumen;
  categorias: CategoriaProyecto[];   // solo las que tienen previsto o real; «viaticos» reúne lo que se paga en el viaje
  previsto_usd: Dinero; real_usd: Dinero; diferencia_usd: Dinero;
  en_revision: number;               // gastos del proyecto que esperan revisión
  faltantes: string[];               // categorías con previsto y sin gasto aprobado
  viajes: ViajeResumen[];            // los que no se rechazaron
  gastos: (GastoResumen & { viajero: string | null })[];   // todos, por fecha del recibo
  periodo_contable: { desde: string; hasta: string };    // el año en curso (1 ene–31 dic, zona de la empresa, America/Bogota) que propone el Excel contable
}
```

### `GET /proyectos`
Parámetros `limite` y `cursor` (solo dígitos 0–9; otro valor, 422). Administración, todos; quien gestiona, los suyos; colaborador: 403 `FORBIDDEN`. `{"items": ProyectoResumen[], "siguiente"}`, más reciente primero. Las cifras son las mismas del tablero.

### `POST /proyectos`
Solo administración (403 `FORBIDDEN`). Cuerpo JSON `{"nombre", "cliente", "ciudad", "fecha_inicio", "fecha_fin", "moneda"}` y `X-CSRF-Token`; un campo de más responde 422. 201 `ProyectoResumen`. Validación, con el campo en `fields` (422): `nombre` de 3 caracteres o más, fechas `AAAA-MM-DD` con `fecha_fin` no anterior a `fecha_inicio`, `moneda` de tres letras (se guarda en mayúsculas). Deja el evento `proyecto creado`.

### `GET /proyectos/{id}`
200 `TableroProyecto`. 404 si no existe o si la persona no lo gestiona ni es de administración. El Excel contable del proyecto es `GET /gastos/contable?proyecto_id={id}&desde&hasta` (ver arriba).

### `POST /proyectos/{id}`
Solo administración. Mismo cuerpo y validación que el alta; se mandan todos los campos. 200 `ProyectoResumen`. 404 si no existe. Deja el evento `proyecto editado`.

### `GET /proyectos/{id}/exportar.csv`
Los gastos del proyecto en CSV (`text/csv`, `Content-Disposition: attachment; filename="gastos_proyecto_<id>.csv"`): el mismo archivo que la pantalla actual. Mismo alcance que el tablero; lo ajeno responde 404.

## Usuarios y cargos

Solo administración: colaborador y gestor reciben 403 `FORBIDDEN` en todo. Lo que hace hoy `/admin/usuarios`, con la misma regla (`app/servicios/usuarios.py`) y los mismos eventos (`cuenta creada`, `rol cambiado`, `cuenta desactivada`/`reactivada`, `cargo asignado`, `proyectos asignados`, `contraseña restablecida`, `cargo creado`/`renombrado`/`desactivado`/`reactivado`). Las escrituras llevan `X-CSRF-Token`; un campo de más responde 422. Una cuenta o un cargo inexistente: 404. Los `id` (en la ruta, `cargo_id` y cada uno de `proyectos_ids`) van de 1 a 2147483647; fuera de ese rango, 422.

```ts
interface Usuario {
  id: number; codigo: string;             // "P-0004"
  correo: string; nombre: string;
  rol: Rol; rol_texto: string;           // "gestor de proyecto"
  cargo: { id: number; nombre: string } | null;     // no da permisos
  proyectos: { id: number; nombre: string }[];     // los que gestiona
  activo: boolean;
  telegram: { vinculado: boolean; usuario: string | null };
  ultima_sesion: string | null;  creado: string | null;   // instantes UTC
}
interface ResultadoUsuario { usuario: Usuario; mensaje: string }
interface Cargo { id: number; nombre: string; activo: boolean; personas: number }
```

La contraseña (inicial o restablecida) nunca sale en una respuesta.

### `GET /usuarios`
Parámetros `limite` y `cursor` (solo dígitos 0–9; otro valor, 422). Todas las cuentas, activas o no, la más reciente primero. `{"items": Usuario[], "siguiente"}`.

### `POST /usuarios`
Cuerpo `{"correo", "nombre", "rol", "clave", "cargo_id": number | null}`. 201 `ResultadoUsuario`. El correo se guarda en minúsculas y sin espacios; la cuenta recibe su perfil de viajero. 422 con el campo en `fields`: `correo` sin `@` o ya usado, `rol` que no es `colaborador`, `gestor` ni `admin`, `clave` de menos de 10 caracteres, `cargo_id` inexistente o desactivado.

### `POST /usuarios/{id}/rol`
Cuerpo `{"rol"}`. Cierra las sesiones abiertas de la cuenta (el permiso nuevo exige entrar de nuevo); quien deja de ser gestor pierde sus proyectos. El mismo permiso que ya tiene no hace nada: 200 con «Sin cambios…» en `mensaje`, sin cerrar sesiones ni dejar evento. Comprobar y escribir van en una transacción en fila con los demás cambios que pueden quitar administración, así dos administraciones a la vez no la dejan sin ninguna. Nadie se quita su propio rol de administración ni deja la plataforma sin ella: 409 `INVALID_STATE` con el motivo en `message`. Rol desconocido: 422 `fields.rol`.

### `POST /usuarios/{id}/estado`
Cuerpo `{"activo": boolean}`. Desactivar cierra sus sesiones; reactivar limpia el bloqueo por intentos. Si ya estaba así responde 200 con «Sin cambios…» en `mensaje`. Nadie desactiva su propia cuenta ni a la última administración activa: 409 `INVALID_STATE`.

### `POST /usuarios/{id}/cargo`
Cuerpo `{"cargo_id": number | null}`. El cargo no da permisos: no cierra sesiones. Cargo inexistente o desactivado: 422 `fields.cargo_id`.

### `POST /usuarios/{id}/proyectos`
Cuerpo `{"proyectos_ids": number[]}`: reemplaza los proyectos que gestiona; los que no existen se ignoran. Solo para cuentas con permiso de gestor: si no, 422 `fields.proyectos_ids` (al volverla gestora no hereda nada).

### `POST /usuarios/{id}/clave`
Cuerpo `{"clave"}` (10 caracteres o más; si no, 422 `fields.clave`). Cierra sus sesiones, desvincula su Telegram y anula los códigos de vínculo pendientes (antes le avisa por ese chat, si lo tiene), y limpia el bloqueo por intentos. La propia no se restablece aquí: 409 `INVALID_STATE` (se cambia en «Mi cuenta», que pide la actual).

### `GET /cargos`
`{"items": Cargo[]}`: el catálogo completo, sin paginar, por nombre.

### `POST /cargos`
Cuerpo `{"nombre"}`. 201 `Cargo`. Al menos 3 letras y sin repetir otro (sin importar mayúsculas): si no, 422 `fields.nombre`.

### `POST /cargos/{id}`
Cuerpo `{"nombre"?, "activo"?}`: renombra o activa/desactiva; lo que no se manda no cambia. Un cargo nunca se borra: quien lo tiene lo conserva aunque se desactive. 200 `Cargo`.

## Mi cuenta

Para cualquier permiso. La cuenta sale siempre de la sesión: nadie lee ni cambia la de otra persona por aquí. Misma regla que la pantalla actual `/mi-cuenta` (`app/servicios/usuarios.py` y `telegram.py`).

```ts
interface MiCuenta {
  persona: Persona;
  rol_texto: string;                  // "gestor de proyecto"
  telegram: { vinculado: boolean; usuario: string | null; canal_activo: boolean };   // canal_activo: el bot está configurado
}
```

### `GET /cuenta`
200 `MiCuenta`. En producción el bot de Telegram está apagado: `canal_activo: false`.

### `POST /cuenta/clave`
Cuerpo `{"actual", "nueva"}` y `X-CSRF-Token`. La actual que no coincide: 422 `fields.actual`; cada fallo cuenta para la cuenta durante 24 horas (evento `contraseña actual equivocada`) y, desde el quinto, cada fallo cierra sus sesiones y responde 429 `TOO_MANY_ATTEMPTS`. El ingreso no queda bloqueado: la persona vuelve a entrar, pero durante los 15 minutos siguientes al último fallo el cambio responde 429 sin mirar la contraseña. El 429 lleva `Retry-After` con los segundos que faltan. Acertar la actual borra esos fallos. La nueva de menos de 10 caracteres o igual a la actual: 422 `fields.nueva`. Al cambiarla se desvincula su Telegram, se anulan los códigos de vínculo pendientes, se cierran todas las sesiones de la persona y esta se renueva: 200 `{"csrf_token", "mensaje"}` con la cookie nueva; el token CSRF anterior deja de servir. Deja el evento `contraseña cambiada por la persona`. La contraseña nunca sale en la respuesta.

### `POST /cuenta/telegram/vinculo`
Con `X-CSRF-Token`, sin cuerpo. 200 `{"codigo", "enlace": string | null, "minutos"}`: un código de un solo uso (en la base queda solo su huella) para escribir `/start <codigo>` en el chat del bot, o el enlace que lo abre si el bot tiene nombre configurado. Con el canal apagado: 409 `INVALID_STATE` con el motivo.

### `POST /cuenta/telegram/desvincular`
Con `X-CSRF-Token`, sin cuerpo. 200 `MiCuenta` con `telegram.vinculado: false`. Deja el evento `Telegram desvinculado`.
## Buzón de correo (simulado)

Solo administración (403 `FORBIDDEN` para colaborador y gestor). **Es una simulación**: lee los correos (`.eml`) y las confirmaciones en HTML de la carpeta de ejemplos de la plataforma (`datos/ejemplos`) como si llegaran a un buzón de gastos; no está conectado a ningún correo real. La lógica es la de `app/servicios/buzon.py`, la misma que la pantalla de carga de administración.

### `GET /buzon`
200 `BuzonSimulado`:

```ts
interface BuzonSimulado {
  simulado: true;
  aviso: string;                        // el texto que dice que es simulado
  mensajes: { nombre: string; formato: "correo" | "html"; remitente: string | null; asunto: string | null }[];
  viajes: { id: number; codigo: string; estado: EstadoViaje; estado_texto: string; titular: string | null;
            origen: string | null; destino: string | null; ida: string | null; regreso: string | null;
            propio: boolean }[];   // aprobados o pendientes; propio: viaje de quien lee
}
```

### `POST /buzon/lectura`
Cuerpo JSON `{"nombres": ["reserva_hotel.eml"], "viaje_id": 12}` (de 1 a 20 nombres; `viaje_id` opcional) y `X-CSRF-Token`. 200 `{"leidos": GastoResumen[], "errores": {nombre, mensaje}[]}`.

- Cada correo se lee como cualquier recibo, por el canal `correo`: lectura, validación y estado real (`aprobado_auto` o `revision`). Con `viaje_id`, el viaje define el proyecto y la persona; sin él, el gasto queda a nombre de quien lee y sin viaje.
- Un nombre que no está en el buzón (otro formato, una ruta, uno que no existe) va a `errores` y no crea nada.
- Leer dos veces el mismo correo crea otro gasto, que las reglas marcan como posible duplicado.
- Un `viaje_id` que no existe: 422 con `fields.viaje_id`. Sin nombres: 422.

## Compras

La solicitud de compra del tiquete nace al decidir una cotización (`Cotizacion.compra`: «Solicitud de compra enviada» y su estado). La lleva **solo administración**: toda esta sección responde 403 `FORBIDDEN` a las demás personas, y nadie decide la compra de su propio viaje (403 `SELF_APPROVAL`, con rastro en la bitácora). Una compra activa por viaje: cambiar la decisión actualiza la misma solicitud mientras no se haya decidido.

Estados: `solicitada` → `en_analisis` → `se_comprara` | `no_se_comprara` → `comprada` | `cancelada`. Cada cambio lleva la `version` que se vio: si otra persona la cambió, 409 `EDIT_CONFLICT`; un cambio que no corresponde al estado, 409 `INVALID_STATE`.

```ts
interface Compra {
  id: number; estado: EstadoCompra; estado_texto: string; version: number;
  viaje: { id: number; codigo: string; estado: string; presupuesto_usd: Dinero };
  solicitud_id: number | null; solicitada_por: string | null; motivo: string | null;
  vendedor: string | null; localizador: string | null;
  precio_pagado_usd: Dinero; precio_cotizado_usd: Dinero;   // cotizado: la tarifa del buscador al decidir
  anticipacion_dias: number | null;                          // días entre la compra y la ida
  creado: string | null; decidido: string | null; comprada: string | null;
  frente_presupuesto: { presupuesto_usd: Dinero; cotizado_usd: Dinero; diferencia_usd: Dinero } | null;   // con la compra registrada
  aviso: string | null;   // con el tiquete comprado y el viaje reabierto o rechazado: decidir si se conserva o se cancela
}
interface CompraDetalle extends Compra {
  vuelo: { opcion_id: number | null; numeros: string[]; aerolinea: string | null; sale: string | null; llega: string | null;
           precio_usd: Dinero; vendedor_url: string | null; fuente_url: string | null } | null;
  clics: { destino: "google_flights" | "google_hotels" | "vendedor" | "hotel_oficial"; dominio: string | null;
           momento: string | null; opcion_id: number | null; usuario: string | null }[];
  analisis: AnalisisVuelo | null;   // la última lectura de la página del vuelo
}
```

### `GET /compras?estado=…`
200 `{"items": Compra[]}`: las compras activas, la más reciente primero (hasta 200). Leer una compra nunca la cambia ni le sube la versión: lo que el estado del viaje le hace a la compra pasa al cambiar el estado del viaje (`POST /viajes/{id}/estado`): «Se va a comprar» vuelve a «En análisis» si el viaje se reabre o se cierra; con el tiquete comprado, reabrir o rechazar deja un evento y `aviso`; volver a aprobar con el tiquete comprado no consulta el buscador y el presupuesto usa lo pagado.

### `GET /compras/{id}`
200 `CompraDetalle`: el vuelo con el mismo enlace a la página oficial que usa «Ver desglose» («Comprar en {vendedor}»), los clics a las fuentes (`clics_fuente`) y la última lectura de la página.

### `POST /compras/{id}/estado`
Cuerpo `{"accion": "en_analisis" | "se_comprara" | "no_se_comprara" | "cancelada", "version": 2, "motivo": ""}` con `X-CSRF-Token`. «Se va a comprar» exige el viaje **aprobado**; «No se va a comprar» y «Cancelada» exigen motivo (5 caracteres o más; 422 con `fields.motivo`). Cada decisión avisa al viajero en la bitácora de su viaje (`aviso al viajero`). 200 `Compra` con la versión nueva.

### `POST /compras/{id}/registro`
Cuerpo `{"version": 3, "localizador": "QX7Z2P", "precio_pagado": "461.30", "vendedor": "American"}` con `X-CSRF-Token`, solo desde `se_comprara`. Guarda localizador (5 a 8 letras o números), precio pagado y vendedor, calcula `anticipacion_dias` y responde 200 `Compra` en `comprada` con `frente_presupuesto`. Crea además el gasto del tiquete (categoría `vuelo`, `origen_dato` «compra registrada»): `aprobado` si lo pagado no supera lo cotizado al decidir en más de la regla `tolerancia_tiquete_pct` (10 %); si lo supera o no hubo precio cotizado, `revision` con el motivo `tiquete_sobre_cotizado`, y lo aprueba otra persona de administración. Lo aprobado suma en lo gastado del viaje y entra al Excel contable. Si el recibo de ese tiquete ya estaba cargado (con el importe a un 1 % o un dólar y el mismo localizador, el mismo comercio o un número de vuelo del itinerario decidido en el comercio, las líneas o lo leído), se enlaza ese gasto en vez de crear otro. Si no se enlaza ninguno pero el viaje ya tiene un gasto de vuelo con soporte y el mismo importe, el del tiquete nace en `revision` con el motivo `tiquete_duplicado` («Posible duplicado del gasto #N (mismo importe)»): nunca se aprueba en silencio. Lo mismo al revés: un recibo de vuelo que no se une al tiquete y tiene su importe queda en `revision` con esa alerta, también cuando se le asigna el viaje después (Telegram); si se une, la asignación devuelve el gasto del tiquete. Volver a validar el gasto no quita ese motivo; lo aprueba en revisión otra persona de administración. Un archivo que ya es el soporte de otro gasto no se une al tiquete: queda aparte, como posible duplicado. Cancelar una compra `comprada` devuelve su gasto a `revision` con el motivo `compra_cancelada` («Compra cancelada: revisar reembolso»).

### `POST /compras/{id}/analisis`
Con `X-CSRF-Token`. Pide (o reutiliza) la lectura de la página del vuelo de la compra: 200 `AnalisisVuelo`.

### Rastro de los enlaces (`clics_fuente`)
Cada «Ver en Google Flights/Hotels», cada apertura de la página oficial (`…/vendedor`) y cada «Ir a…» deja una fila: quién, cotización, vuelo, viaje y compra (si existen), destino (`google_flights`, `google_hotels`, `vendedor`) y dominio de salida.
