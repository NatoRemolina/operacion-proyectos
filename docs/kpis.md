# Indicadores (KPIs)

Las métricas de `docs/analitica.md` dicen cuánto; los indicadores dicen además si eso está bien. Cada KPI es una métrica del catálogo único (`app/servicios/metricas.py`) a la que se le añade para qué sirve, hacia dónde es mejor, una meta, un umbral de alerta y un responsable. No hay fórmulas copiadas: el tablero, la consola de monitoreo, la API y las descargas leen la misma definición.

Dónde se ve:

| Qué | Dónde |
|---|---|
| Tablero con semáforos, tendencia semanal, desgloses y personas | `/admin/kpis` (menú «KPIs», solo administración) |
| Ficha de una persona por su ID | `/admin/kpis/persona/{id}` |
| Lo mismo en JSON | `/api/kpis` (con `proyecto_id`, `desde`, `hasta`) y `/api/kpis?persona_id={id}` |
| Descargas | `/admin/kpis/exportar.csv?que=kpis`, `que=consultas`, `que=personas` |
| Metas y umbrales | Pantalla «Reglas y supuestos», ámbito `kpi` |

## Semáforo

| Estado | Si mayor es mejor | Si menor es mejor |
|---|---|---|
| Verde (en meta) | valor ≥ meta | valor ≤ meta |
| Ámbar (atención) | umbral ≤ valor < meta | meta < valor ≤ umbral |
| Rojo (fuera de meta) | valor < umbral | valor > umbral |
| Sin datos | no hay hechos con qué calcular | igual |

Reglas que evitan cifras engañosas:

- **Sin datos no hay color.** Si no hay hechos (ningún gasto, ninguna decisión), el indicador dice «sin datos». Ninguna fórmula divide por cero: devuelve vacío.
- **Un cero solo cuenta si hay de qué contar.** «Cero viajes sobre presupuesto» sin viajes aprobados no es una buena noticia, es ausencia de datos. Los conteos y sumas declaran su base (viajes con presupuesto, gastos recibidos, cotizaciones, decisiones); si la base es cero, el indicador queda en «sin datos».
- **Las metas son supuestos.** Los valores iniciales están abajo; se cambian en «Reglas y supuestos» sin tocar el código y el color cambia en la siguiente consulta. Cada cambio queda en la bitácora («regla editada»).

## Catálogo

Reto 1 es la cotización de viajes; reto 2, los gastos con la mirada de Finanzas. Las metas son las iniciales.

| Reto | Nombre en la API | Indicador (unidad) | Fórmula | Meta inicial | Responsable | Decisión que apoya |
|---|---|---|---|---|---|---|
| 1 | `tasa_reutilizacion` | Búsquedas resueltas sin pagar otra consulta (%) | Consultas resueltas con una respuesta guardada (misma búsqueda u otras fechas) ÷ consultas resueltas | ≥ 60 · rojo < 30 | Operaciones | Si conviene guardar más rutas o recolectar por adelantado antes de pagar consultas |
| 1 | `tasa_consultas_fallidas` | Consultas al buscador que fallan (%) | Consultas fallidas ÷ todas las consultas al buscador | ≤ 5 · rojo > 15 | Operaciones | Si hay que revisar la clave, el plan o el proveedor de precios |
| 1 | `latencia_buscador` | Mediana de espera de una consulta en vivo (ms) | Mediana de la duración de las consultas en vivo | ≤ 8000 · rojo > 20000 | Operaciones | Si la espera al cotizar justifica precargar rutas frecuentes |
| 1 | `cupo_usado` | Cupo mensual del buscador ya usado (%) | Búsquedas usadas este mes ÷ búsquedas del plan, según la cuenta del buscador | ≤ 70 · rojo > 90 | Operaciones | Cuándo frenar consultas en vivo o ampliar el plan |
| 1 | `anticipacion_compra` | Días entre la decisión y la ida (días) | Promedio de días entre la decisión vigente de cada cotización y la fecha de ida | ≥ 21 · rojo < 7 | Operaciones | Pedir a los proyectos que confirmen fechas antes: comprar tarde cuesta más |
| 1 | `acuerdo_recomendacion` | Decisiones que siguen la recomendación (%) | Decisiones que eligen la opción recomendada ÷ decisiones con recomendación registrada | ≥ 70 · rojo < 50 | Operaciones | Si las reglas y supuestos del comparador reflejan lo que de verdad importa al viajar |
| 1 | `ahorro_identificado` | Ahorro identificado por el comparador (USD) | Suma por cotización de: costo esperado del vuelo más barato que sirve − costo esperado del recomendado | ≥ 100 · rojo < 0 | Finanzas | Cuánto vale comparar por costo total y no por precio |
| 1 | `ahorro_capturado` | Ahorro capturado en decisiones (USD) | Suma por decisión vigente de: costo esperado del más barato que sirve − costo esperado de lo elegido | ≥ 100 · rojo < 0 | Finanzas | Si las decisiones reales convierten el análisis en dinero |
| 1 | `captura_ahorro` | Ahorro capturado sobre identificado (%) | Ahorro capturado ÷ ahorro identificado | ≥ 80 · rojo < 50 | Finanzas | Dónde se pierde el ahorro: en la recomendación o en la decisión |
| 1 | `horas_cotizacion_decision` | Mediana de la cotización a la decisión (h) | Mediana de horas entre la cotización y su primera decisión | ≤ 24 · rojo > 72 | Operaciones | Si las personas deciden a tiempo o los precios se van mientras esperan |
| 1 | `horas_decision_aprobacion` | Mediana de la decisión a la aprobación (h) | Mediana de horas entre el nacimiento del viaje (la decisión) y la aprobación del presupuesto | ≤ 24 · rojo > 72 | Finanzas | Si la aprobación de presupuestos es un cuello de botella |
| 1 | `exactitud_modelo` | Error del precio esperado, MAPE (%) | Promedio de \|precio del buscador al decidir − precio esperado\| ÷ precio del buscador, por vuelo mostrado | ≤ 15 · rojo > 30 | Operaciones | Si el precio esperado ya sirve para presupuestar o hay que juntar más datos |
| 2 | `ejecucion_presupuesto` | Gasto aprobado sobre presupuesto aprobado (%) | Gasto aprobado de los viajes aprobados o cerrados ÷ su presupuesto | ≤ 100 · rojo > 110 | Finanzas | Si los presupuestos están bien calculados (viáticos, carro, hotel) |
| 2 | `viajes_sobre_presupuesto` | Viajes con gasto aprobado mayor al presupuesto (viajes) | Viajes aprobados o cerrados cuyo gasto aprobado supera el presupuesto | ≤ 0 · rojo > 1 | Finanzas | A quién pedir explicación y qué presupuesto ajustar |
| 2 | `tasa_sin_intervencion` | Gastos aprobados sin intervención (%) | Gastos aprobados solos ÷ gastos recibidos | ≥ 70 · rojo < 40 | Finanzas | Cuánto trabajo manual evita la lectura automática; si mover el umbral de confianza |
| 2 | `dias_recibo_a_carga` | Mediana de días del recibo a la carga (días) | Mediana de días entre la fecha impresa en el recibo y su llegada a la plataforma | ≤ 3 · rojo > 10 | Finanzas | Si hay que recordar a las personas que carguen sus recibos durante el viaje |
| 2 | `horas_carga_a_aprobacion` | Mediana de la carga a la aprobación del gasto (h) | Mediana de horas entre «documento recibido» y la aprobación del gasto | ≤ 24 · rojo > 72 | Finanzas | Si la revisión necesita más manos o reglas más finas |
| 2 | `tasa_correccion` | Campos corregidos sobre campos leídos (%) | Campos que difieren entre lo leído y lo aprobado ÷ campos leídos | ≤ 5 · rojo > 15 | Finanzas | Si la lectura es confiable o hay que cambiar de modelo o de instrucciones |
| 2 | `gastos_sin_viaje` | Gastos que no pertenecen a ningún viaje (gastos) | Gastos sin viaje asignado | ≤ 0 · rojo > 2 | Finanzas | Cumplimiento de la regla «todo gasto pertenece a un viaje» |
| 2 | `pendientes_revision` | Gastos esperando revisión (gastos) | Gastos en estado de revisión | ≤ 5 · rojo > 15 | Finanzas | Carga de quien revisa hoy |
| 2 | `revision_mas_antigua` | Días del gasto más antiguo en revisión (días) | Días desde que llegó el gasto más antiguo que sigue en revisión | ≤ 2 · rojo > 7 | Finanzas | Que ningún recibo quede olvidado |
| 2 | `costo_por_recibo` | Costo de leer un recibo (USD) | Costo estimado de los tokens de lectura ÷ recibos leídos | ≤ 0.01 · rojo > 0.05 | Operaciones | Qué modelo de lectura usar |

Además del semáforo, el tablero muestra los desgloses que piden los retos: consultas al buscador por origen, tipo, persona y ruta; cotizaciones por persona y por ruta; ejecución del presupuesto por viaje, por proyecto y por grupo de compra (vuelo, hotel, carro, viáticos); gasto aprobado por moneda con su equivalente en USD; y los gastos que más tiempo llevan en revisión.

El gasto por cargo sale en `kpis.por_cargo` (y en la clave `por_cargo` de `/api/kpis`): por cada cargo, los viajes, el gasto aprobado y el gasto en revisión, en USD. El cargo de un viaje es el de su titular; el de un gasto, el del titular de su viaje o, si no tiene viaje, el de quien lo cargó. Las cuentas sin cargo salen como «Sin cargo». Aplica los filtros de proyecto y fechas; el filtro por persona no, porque el desglose es de toda la empresa.

`exactitud_modelo` cruza el precio esperado que se mostró al decidir (`elecciones.rasgos`) con el precio del buscador de ese mismo momento y, cuando existan compras, con `compras.precio_pagado` del vuelo elegido. Sin decisiones con precio esperado dice «sin datos todavía». El detalle por ruta y por mes, y frente a lo pagado, está en la sección «Rutas frecuentes y precios» (`GET /api/v1/kpis/rutas-frecuentes`), junto con las cifras de precio de las rutas más cotizadas. Cómo se calculan y de dónde salen: `docs/datos-para-modelos.md`. No depende de la persona: no sale en la ficha por persona.

Todos los indicadores aceptan los filtros de proyecto y fechas. Hay dos que no dependen de ellos: el cupo, que es de la cuenta del buscador, y el costo por recibo, que no se reparte por proyecto (igual que en Monitoreo).

## Tendencia semanal

Los indicadores principales (reutilización, acuerdo con la recomendación, captura del ahorro, horas a la aprobación, ejecución del presupuesto, aprobados sin intervención, días del recibo a la carga) se calculan para cada una de las últimas ocho semanas, de lunes a domingo, hasta la fecha «hasta» del filtro o hasta hoy. Cada semana usa la misma fórmula con los hechos de esa semana; no hay tablas de instantáneas, así que una corrección de datos se refleja también hacia atrás.

## Lo que se conserva de cada consulta al buscador

Cada consulta al buscador de precios (vuelos, hoteles, regreso, reserva, reconfirmación del precio, estado del vuelo o autocompletado) deja una fila en `consultas_buscador`, escrita desde `app/servicios/precios.py` sin cambiar lo que esas funciones devuelven.

| Columna | Qué guarda |
|---|---|
| `momento` | Cuándo se hizo (UTC) |
| `solicitud_id` | Cotización que la pidió; vacío si la pidió el recolector |
| `usuario_id` | Cuenta que estaba usando la plataforma |
| `tipo` | `vuelos`, `hoteles`, `regreso`, `tarifas`, `reconfirmacion`, `estado_vuelo` o `autocompletado` |
| `origen` | `en vivo`, `guardado`, `guardado (otras fechas)` o `fallida` |
| `clave` | Nombre de la búsqueda, el mismo de `busquedas.clave` y del archivo en `datos/respaldo/`. Si se usaron otras fechas, el archivo que de verdad se usó |
| `duracion_ms` | Lo que tardó, incluida la lectura de lo guardado |
| `resultados` | Cuántos vuelos, hoteles o tarifas trajo |
| `precio_min`, `precio_mediana` | Precio más bajo y mediana de lo que trajo, en USD |
| `error` | Mensaje del buscador si falló, o el aviso de que no había nada guardado ni clave para consultar |

No se duplica nada: la respuesta completa del buscador ya queda en `busquedas` (y en `datos/respaldo/`) y cada vuelo en `observaciones`; la fila solo las referencia por la clave. Es una tabla de registro, sin claves foráneas a propósito, como `eventos`: el hecho se conserva aunque cambie lo demás. Se consulta con la vista `v_h_consulta`, que le añade el proyecto, la ruta de la cotización y el nombre de la persona.

Casos a tener en cuenta al leer las cifras:

- Una consulta en vivo que falla deja una fila `fallida`; si después se recupera con una respuesta de otras fechas, deja otra fila con ese origen. Son dos intentos distintos.
- Si no hay respuesta guardada para unas tarifas y no se permitió consultar en vivo, no se buscó nada (se supone la tarifa básica): no queda fila.
- Cargar la opción elegida hace dos consultas al buscador, el regreso real (`regreso`) y las opciones de reserva (`tarifas`), y cada una deja su fila; «Traer tarifas» hace las mismas dos y también deja dos filas. El cupo descuenta una por fila en vivo.
- Las consultas anteriores a esta tabla solo están en la bitácora (`eventos`, pasos «consulta externa» y «lectura de respaldo»). Desde ahora Monitoreo cuenta las consultas en vivo, reutilizadas y fallidas desde esta tabla, con los mismos filtros de proyecto y fechas.

### Consultas de autocompletado

Las consultas al autocompletado de Google (`tipo = 'autocompletado'`) se muestran aparte y **no entran** en la tasa de reutilización, en la tasa de consultas fallidas ni en la latencia del buscador. Las que se sirven de lo guardado no dejan fila (serían una por pulsación) y, mezcladas, bajarían la tasa de reutilización y moverían la latencia. El tablero las muestra como su propio dato (`autocompletado` en el resumen del buscador): las búsquedas que gastaron este mes (en vivo o fallidas) frente a los topes `tope_autocompletado_mes` (60 por defecto) y `tope_autocompletado_persona_dia` (15), y el proveedor activo (`local` o `local+google`). Cuentan para el cupo mensual del buscador.

### Consultas del estado del vuelo

El monitoreo del vuelo el día del viaje (`app/servicios/monitoreo_vuelos.py`) deja una fila con `tipo = 'estado_vuelo'` por cada consulta del estado de un tramo, y `precios.estado_vuelo` la escribe. La clave es `estado_vuelo_<número>_<fecha>.json` (con la hora en la clave si fue en vivo). Origen de la fila:

- `en vivo`: consultó al buscador (`engine=google`, `q = "Flight IB5634"`); gasta una búsqueda del plan. La respuesta queda solo en la tabla `busquedas`, no se escribe en `datos/respaldo/`.
- `guardado`: sin clave del buscador (o con la consulta fallida) se leyó la respuesta guardada de ese vuelo y fecha; no gasta cupo. Hoy solo existe la de ejemplo, IB 5634 del 13 de diciembre de 2026.
- `fallida`: no había respuesta guardada ni clave, o la consulta falló.
- Una respuesta sin el bloque del vuelo para esa fecha deja la fila con `resultados` en 0 y el motivo en `error`.

A diferencia del autocompletado, estas filas **sí entran** en la tasa de reutilización, en la de consultas fallidas y en la latencia del buscador, y aparecen en «por tipo». La reconfirmación del precio al aprobar (`reconfirmacion`, siempre en vivo) y el regreso real al decidir (`regreso`) se tratan igual.

Qué se cuenta y contra qué tope, todos reglas editables en «Reglas y supuestos»:

| Regla | Valor | Qué cuenta |
|---|---|---|
| `monitoreo_horas_antes` | 3 | Solo se consulta desde 3 horas antes de la salida programada hasta la llegada (programada o estimada, la más tardía). Cada hora se interpreta en la zona horaria de su aeropuerto (`lugares.zona`, de GeoNames) |
| `monitoreo_cache_min` | 60 | Una consulta se reutiliza 60 minutos; «Actualizar ahora» la salta, pero como mucho una vez por minuto por tramo |
| `monitoreo_tope_tramo` | 6 | Consultas por tramo (`tramos_vuelo.consultas`): cuenta todas las hechas, también las leídas de lo guardado o sin bloque |
| `monitoreo_tope_viaje` | 12 | Suma de `tramos_vuelo.consultas` del viaje **por sentido**: agotar la ida no deja sin monitoreo el regreso |
| `monitoreo_tope_dia` | 30 | Filas `estado_vuelo` con origen `en vivo` del día (UTC) del momento de consulta, para toda la plataforma; las guardadas no cuentan |
| `cupo_minimo_monitoreo` | 25 | Si el plan del buscador tiene menos búsquedas restantes que esto, el monitoreo se suspende (solo se sabe con la clave configurada) |

Casos a tener en cuenta:

- Cuando no se consulta (fuera de ventana, tope, caché, cupo bajo) no hay fila en `consultas_buscador`: el motivo queda en el tramo (`tramos_vuelo.omitida`) y en la bitácora del viaje, una vez por motivo, porque el tablero pregunta cada 15 segundos.
- El tope del tramo y el del viaje se cuentan en `tramos_vuelo.consultas`, que se incrementa antes de llamar al buscador con una escritura condicional: dos pestañas o un doble clic pagan una sola consulta.
- Con `MONITOREO_AHORA` (solo en local) el «ahora» del tope diario es el simulado, pero `consultas_buscador.momento` guarda la hora real del reloj: las consultas de la demostración no cuentan para el tope del día simulado.
- El proveedor no da los minutos de retraso: se calculan como hora real menos programada.

## Ficha por persona

`/admin/kpis/persona/{id}` muestra todo lo de una persona por su código (`P-0007`): permiso, cargo, sus cotizaciones con las fechas estimadas, sus viajes (`V-2026-0012`) con presupuesto, gastado y en revisión, sus gastos por estado y por canal, sus evidencias, la línea de tiempo de los hechos sobre lo suyo y sus indicadores con el mismo semáforo. La misma información sale de `kpis.ficha_persona(usuario_id)`, para que otras partes de la plataforma la reutilicen.

A una persona le pertenece lo que la tiene como titular, con la misma regla de `viajes.titular_de`:

| Hecho | Pertenece a |
|---|---|
| Cotización | El titular de su viaje; si aún no hay viaje, la cuenta activa del viajero; si no la hay, quien cotizó |
| Viaje | Su titular |
| Gasto y evidencia | El titular de su viaje; si no tiene viaje, quien lo cargó |
| Hecho de la bitácora | La persona dueña de la cotización, viaje o gasto al que se refiere, aunque lo haya registrado otra (por ejemplo, la aprobación) |

Así, si administración cotiza para un colaborador, la cotización aparece en la ficha del colaborador y no en la de administración. Si se pide un indicador filtrado por persona sobre un hecho sin regla de pertenencia, la consulta falla en lugar de devolver los datos de todos. Ver una ficha deja el evento «ficha consultada».

## Límites

- Con pocos datos los semáforos prueban el método, no describen el negocio.
- Las metas iniciales son supuestos razonables, no acuerdos con Finanzas ni con Operaciones: deben fijarlas ellos.
- La tendencia recalcula ocho semanas en cada visita. Con el volumen actual es inmediato; si crece, se puede materializar sin cambiar las fórmulas.
- El cupo del buscador solo se ve con la clave configurada.
