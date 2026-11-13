# Automatizaciones con n8n (propuesta)

**Estado:** diseño aprobado para construir después de la entrega. El primer flujo, que guarda los soportes en Google Drive, se construye aparte.

## Principio

n8n orquesta, y la plataforma valida, decide y guarda.
- Las reglas, los permisos, «nadie aprueba lo suyo», la versión esperada de cada gasto y los topes de uso siguen en la plataforma.
- n8n hace dos cosas: recibe **avisos firmados** y llama a la API v1 con una **clave de servicio** de permisos acotados.
- Una automatización nunca aprueba ni rechaza por su cuenta: decide siempre una persona con sesión.

Herramientas: Gmail y Google Workspace para el correo, Google Drive y Sheets para los archivos.

## Piezas de la plataforma

| Pieza | Qué hace |
|---|---|
| **Clave de servicio** | Credencial propia de cada flujo. Se puede revocar, se guarda como huella y se muestra una sola vez. Va en una cabecera, sin cookie ni CSRF, y la bitácora la registra con su nombre. Los permisos salen de un catálogo: `soporte:leer`, `gasto:correo`, `contable:leer`, `pendientes:leer`, `vuelos:consultar`. Ninguno permite aprobar ni rechazar |
| **Avisos salientes firmados** | Una función única emite cada evento del catálogo con firma HMAC-SHA256 del cuerpo y la hora, más un id de entrega. Tiene espera corta y nunca bloquea la operación. Si el envío falla, el aviso queda en una bandeja (`avisos_salientes`) que n8n relee cada 5 minutos con un cursor, así no se pierde nada sin añadir colas en AWS |
| **Decisión desde el correo** | El correo de algo por aprobar trae «Aprobar» y «Rechazar». Cada enlace es opaco, vale para una sola persona, una sola entidad y su versión, sirve una vez y vence a las 72 h. Al abrirlo, la plataforma pide ingresar si hace falta, muestra el resumen con la acción ya elegida y pide confirmar (con el motivo si se rechaza). Si otra persona ya decidió, lo dice |
| **Buzón de gastos** | `POST /api/v1/gastos/correo` recibe el `.eml` original. La persona se identifica por el correo de su cuenta activa; un remitente desconocido se rechaza. El Message-ID evita duplicados, y el gasto sigue las mismas reglas de lectura y validación, con un tope diario editable. n8n solo reenvía correos con DKIM y SPF válidos |
| **Pendientes y vuelos** | `GET /api/v1/pendientes` lista gastos en revisión hace más de 48 h (regla editable), justificaciones que faltan y viajes por aprobar. `POST /api/v1/vuelos/consultar` recorre los tramos activos con sus topes, para que el monitoreo no dependa de tener el tablero abierto |

Catálogo de eventos:
- `gasto.registrado`, `gasto.en_revision` (con sus motivos), `gasto.aprobado`, `gasto.rechazado`;
- `viaje.pendiente_aprobacion`, `viaje.aprobado`, `viaje.rechazado`;
- `viaje.presupuesto_80`, cuando un gasto aprobado cruza el umbral editable;
- `justificacion.recibida`.

## Flujos

| Flujo | Disparador | Qué hace |
|---|---|---|
| Soportes a Drive | `gasto.registrado` | Guarda el soporte en «Inflight · Soportes / proyecto / viaje / AAAA-MM» con un nombre legible |
| Aprobación por correo | `viaje.pendiente_aprobacion`, `gasto.en_revision` | Correo a administración (nunca a quien viaja) con resumen, presupuesto frente a gastado, motivos y los botones |
| Resultado al interesado | `viaje.aprobado/rechazado`, `gasto.aprobado/rechazado` | Correo con la decisión y el motivo, además del aviso por Telegram |
| Contabilidad | `gasto.aprobado`, cada lunes y cada día 1 | Fila en la hoja «Gastos aprobados» con las columnas del Excel contable. El libro semanal y el mensual (`GET /api/v1/gastos/contable`) quedan en «Inflight · Contabilidad / AAAA / MM» y se envían a Finanzas |
| Buzón de gastos | Correo con la etiqueta «Gastos» | Envía el `.eml` al buzón y responde con lo leído y el estado |
| Recordatorios y alertas | Cada día a las 8:00, y `viaje.presupuesto_80` | Resumen de lo que espera decisión y de lo que falta justificar; aviso inmediato cuando un viaje llega al 80 % de su presupuesto |
| Monitoreo de vuelos | Cada 15 minutos, si hay tramos activos | Consulta el estado y avisa de cambios |
| Solicitud de viaje por correo | Correo con «Solicitud de viaje» | Lee ruta y fechas, con tope, y responde con un enlace a *Cotizar* ya prellenado; no gasta búsquedas pagas hasta que la persona lo abre |

## Seguridad

- Una clave por flujo, con el permiso mínimo.
- Firmas con hora e id de entrega: n8n descarta los repetidos y los de más de 5 minutos.
- Los enlaces son opacos, de un solo uso y con vencimiento, sin datos personales en la URL.
- Las credenciales de Gmail y Drive se conectan con OAuth dentro de n8n y no viajan en los flujos exportados (`docs/n8n/*.json`).
- Los flujos que llaman al modelo respetan los topes diarios editables.

## Orden de construcción

1. La clave de servicio y los avisos, con los flujos de soportes a Drive, resultado al interesado y contabilidad.
2. La decisión desde el correo y su flujo.
3. El buzón, los pendientes y los vuelos, con sus flujos.
4. La solicitud de viaje por correo.

Cada paso lleva sus pruebas: una firma inválida o vencida se rechaza; el enlace de otra persona o ya usado no decide; la regla «nadie aprueba lo suyo» se aplica también desde el correo; una versión cambiada da conflicto; un remitente desconocido no registra nada; el mismo Message-ID no duplica el gasto; la bandeja no pierde avisos.
