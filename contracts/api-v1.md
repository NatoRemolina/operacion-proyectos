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
| 415 | `UNSUPPORTED_MEDIA_TYPE` | El contenido no es JPG, PNG, WebP, PDF, correo (.eml) ni confirmación HTML (.html) |
| 422 | `VALIDATION_ERROR` | Campos inválidos; detalle por campo en `fields` |
| 429 | `TOO_MANY_ATTEMPTS` | Demasiados intentos de ingreso |
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

- Parámetros: `desde` y `hasta` (`AAAA-MM-DD`, por la fecha del recibo, ambos incluidos; por omisión, el mes en curso en la hora de Nueva York, `America/New_York`: es un supuesto, la zona de la empresa, para que la nube, que corre en UTC, no proponga el mes siguiente desde las 19:00 o 20:00 del último día) y `proyecto_id` (opcional, de 1 a 2147483647; fuera de ese rango, 422).
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
El archivo original, con su tipo (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`; un correo se entrega como `text/plain`), `Content-Disposition: inline` (una confirmación HTML se guarda reducida a texto plano, sin código ni enlaces, y se entrega como `text/plain` con `Content-Disposition: attachment`), `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. 404 si el gasto al que pertenece no es visible.

### `POST /asistente`
Para los tres permisos, cada uno con el alcance de su sesión: el colaborador ve sus viajes y sus gastos; el gestor, además, los de los proyectos que gestiona; administración, todo. El alcance lo pone la sesión, nunca la pregunta: un viaje, un gasto o una persona fuera de él se responde como si no existiera y no aparece entre las fuentes, y los indicadores de toda la empresa son solo para administración. Sin sesión, 401; 403 solo por `CSRF_INVALID`, `ORIGIN_NOT_ALLOWED` o una sesión sin un permiso válido (`FORBIDDEN`). Cuerpo `{"pregunta": "..."}` (1 a 500 caracteres; solo espacios es 422) y `X-CSRF-Token`. Sigue la misma vía que la plataforma: asesor (agente con herramientas), modelo con herramientas o consultas directas, con el mismo tope diario por persona y el mismo rastro en `asistente_consultas`. Con el asesor puede tardar hasta un minuto.

200 `RespuestaAsistente`: `texto`, `modo` (`asesor`, `modelo`, `determinista` o `tope`), `modo_texto` (el modo en palabras), `fuentes` (`tipo`, `codigo` y `destino`: `{"tipo": "viaje" | "gasto" | "cotizacion", "id"}` o `null` si no tiene pantalla, como una persona), `herramientas`, `duracion_ms`, `usadas` y `tope`. Llegar al tope diario no es un error: responde 200 con `modo: "tope"` y el texto lo explica.

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

## Fuera de este contrato (siguientes fases)

Reproceso de una lectura fallida, proyectos, usuarios, asignaciones y auditoría. Siguen en las pantallas de administración; la hoja de ruta está en `docs/informe-tecnico.md`.
