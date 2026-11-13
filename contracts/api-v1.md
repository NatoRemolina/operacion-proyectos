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
| 429 | `TOO_MANY_ATTEMPTS` | Demasiados intentos de ingreso, o cinco fallos seguidos con la contraseña actual en `POST /cuenta/clave` |
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

- Parámetros: `desde` y `hasta` (`AAAA-MM-DD`, por la fecha del recibo, ambos incluidos; por omisión, el año en curso, del 1 de enero al 31 de diciembre, en la hora de Nueva York, `America/New_York`: es un supuesto, la zona de la empresa, para que la nube, que corre en UTC, no proponga el año siguiente desde las 19:00 o 20:00 del 31 de diciembre) y `proyecto_id` (opcional, de 1 a 2147483647; fuera de ese rango, 422).
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
El archivo original, con su tipo (`image/jpeg`, `image/png`, `image/webp`, `application/pdf`; de un correo `.eml` se entrega su adjunto si es un PDF o una foto, y si no tiene, su texto como `text/plain` con De, Asunto, Fecha y el cuerpo, nunca el MIME crudo), `Content-Disposition: inline` (una confirmación HTML se guarda reducida a texto plano, sin código ni enlaces, y se entrega como `text/plain` con `Content-Disposition: attachment`), `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. 404 si el gasto al que pertenece no es visible.

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
             forma: "imagen" | "pdf" | "descarga" } | null;   // descarga: correo (.eml) o confirmación HTML
  categorias: { clave: string; nombre: string }[];            // las de la plataforma, en orden
  viajes: { id: number; codigo: string; estado: EstadoViaje; estado_texto: string; titular: string | null;
            origen: string | null; destino: string | null; ida: string | null; regreso: string | null }[];
  propio: boolean;                             // nadie revisa lo suyo
  aviso_propio: string | null;                 // por qué no se revisa y si hay otra persona que pueda
}
```

- `viajes`: a los que se puede reasignar el gasto con `viaje_id` en la revisión; todos salvo los rechazados, el más reciente primero (las mismas opciones que la revisión de las pantallas de administración).
- El archivo del soporte se pide a `GET /documentos/{documento_id}/contenido`.

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

- Una regla numérica sigue siendo numérica: se acepta la coma decimal («0,25» se guarda «0.25»); un texto, un negativo, un vacío o un valor no finito responden 422 `VALIDATION_ERROR` con `fields.valor` y no se guarda nada.
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
  periodo_contable: { desde: string; hasta: string };    // el mes en curso que propone el Excel contable
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
Cuerpo `{"actual", "nueva"}` y `X-CSRF-Token`. La actual que no coincide: 422 `fields.actual`; cada fallo cuenta con el mismo contador del ingreso (evento `contraseña actual equivocada`) y al quinto seguido se cierran sus sesiones y responde 429 `TOO_MANY_ATTEMPTS` (el ingreso queda con el bloqueo progresivo). La nueva de menos de 10 caracteres o igual a la actual: 422 `fields.nueva`. Al cambiarla se desvincula su Telegram, se anulan los códigos de vínculo pendientes, se cierran todas las sesiones de la persona y esta se renueva: 200 `{"csrf_token", "mensaje"}` con la cookie nueva; el token CSRF anterior deja de servir. Deja el evento `contraseña cambiada por la persona`. La contraseña nunca sale en la respuesta.

### `POST /cuenta/telegram/vinculo`
Con `X-CSRF-Token`, sin cuerpo. 200 `{"codigo", "enlace": string | null, "minutos"}`: un código de un solo uso (en la base queda solo su huella) para escribir `/start <codigo>` en el chat del bot, o el enlace que lo abre si el bot tiene nombre configurado. Con el canal apagado: 409 `INVALID_STATE` con el motivo.

### `POST /cuenta/telegram/desvincular`
Con `X-CSRF-Token`, sin cuerpo. 200 `MiCuenta` con `telegram.vinculado: false`. Deja el evento `Telegram desvinculado`.
