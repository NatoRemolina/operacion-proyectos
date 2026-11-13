# Regla de negocio

Esta es la fuente única de la regla de negocio de la plataforma. Está escrita a partir del código; cada apartado nombra la función o la constante que la hace cumplir. Si un documento y este dicen cosas distintas, manda este, y si este y el código no coinciden, manda el código (y este documento se corrige).

El modelo de datos que la sostiene está en [`datos.md`](datos.md); la trazabilidad de los gastos (quién cambia qué y qué queda registrado), en [`trazabilidad.md`](trazabilidad.md).

## 1. El ciclo

```
persona (P-0007)
   │ cotiza
   ▼
cotización ──► decisión (opción elegida + porqué)
                  │ crea o actualiza
                  ▼
               VIAJE (V-2026-0012, presupuesto, estado)
                  │ administración aprueba (otra persona)
                  ▼
               gastos ──► validación ──► aprobado solo  ─┐
                              │                          ├─► viaje cerrado
                              └──► revisión de una persona ┘
```

1. **Persona.** Toda cuenta tiene un código `P-NNNN` (el identificador de la fila en `usuarios`) y un perfil de viajero: todos los permisos viajan (`acceso.crear_usuario`, `acceso.crear_perfil_viajero`).
2. **Cotización.** Compara vuelos y hoteles por su costo total esperado (ver «Costo esperado y presupuesto»). Queda en `solicitudes`, con sus opciones en `opciones`.
3. **Decisión.** La persona elige un vuelo (y, si hay, un hotel). Si no elige el vuelo recomendado, tiene que decir por qué; elegir otro hotel no lo exige. Queda en `decisiones`, con todas las opciones mostradas en `elecciones`.
4. **Viaje.** La decisión crea el viaje de la cotización o actualiza el que ya tiene (`viajes.crear_desde_decision`): una cotización, un viaje (índice único en `viajes.solicitud_id`). El código es `V-AAAA-NNNN`: el año de creación y el identificador de la fila (`viajes.codigo_viaje`), así que no se repite ni se desfasa. Nace en `pendiente_aprobacion` con su presupuesto (`viajes.presupuesto_de`).
5. **Aprobación.** Administración aprueba o rechaza el presupuesto. Al aprobar se reconfirma el precio del vuelo (ver «Umbrales»).
6. **Gastos.** Cada recibo, por cualquier canal, se lee, se asigna a un viaje y se valida (`gastos.registrar`, `validacion.revisar`).
7. **Validación.** Si ningún motivo bloquea, el gasto queda `aprobado_auto`; si alguno bloquea, queda en `revision`.
8. **Revisión.** Una persona de administración corrige, aprueba, aprueba con excepción o rechaza (`revision.guardar`).
9. **Cierre.** Administración cierra el viaje aprobado. Un viaje cerrado no admite gastos nuevos (motivo `viaje_cerrado`).

### Estados del viaje

`viajes.TRANSICIONES` (restricción `ck_viajes_estado` en la base):

| Acción | Desde | Hacia | Paso que queda en la bitácora |
|---|---|---|---|
| `aprobar` | `pendiente_aprobacion` | `aprobado` | presupuesto aprobado |
| `rechazar` | `pendiente_aprobacion` | `rechazado` | presupuesto rechazado |
| `reabrir` | `aprobado`, `rechazado`, `cerrado` | `pendiente_aprobacion` | viaje reabierto |
| `cerrar` | `aprobado` | `cerrado` | viaje cerrado |

- Solo administración mueve el estado (`viajes.cambiar_estado`, que comprueba `acceso.es_admin`).
- Una acción desde un estado que no está en la columna «Desde» no se aplica (409 `INVALID_STATE` en la API v1).
- Volver a decidir con el viaje `pendiente_aprobacion` o `rechazado` actualiza el presupuesto y lo devuelve a `pendiente_aprobacion` («presupuesto actualizado»). Con el viaje `aprobado` o `cerrado` la decisión no cambia hasta que administración lo reabra (`viajes.bloquea_decision`; 409 `DECISION_LOCKED`).
- Rechazar exige un motivo de 5 caracteres o más.
- Cada cambio avisa al titular por Telegram si tiene el chat vinculado.

### Estados del gasto

| Estado | Qué significa | Quién lo pone |
|---|---|---|
| `procesando` | El recibo llegó y se está leyendo | `gastos.registrar` |
| `revision` | Algún motivo bloquea: lo decide una persona | `validacion.revisar`; `envios.marcar_interrumpido` si la lectura lanza un error; `envios.recuperar_si_atascado` si no terminó en 5 minutos |
| `aprobado_auto` | Todas las validaciones en verde: aprobado sin intervención | `validacion.revisar` |
| `aprobado` | Lo aprobó una persona de administración, corregido o con excepción | `revision.guardar` |
| `rechazado` | Lo rechazó una persona de administración, con motivo | `revision.guardar` |

Los estados del gasto los hace cumplir el código (`validacion`, `revision`, `envios`); la base no tiene una restricción CHECK sobre `gastos.estado`. Lo gastado de un viaje suma solo `aprobado` y `aprobado_auto` (`viajes.gastado`).

## 2. Permisos

El **permiso** (`usuarios.rol`, restricción `ck_usuarios_rol`) decide qué se puede hacer. El **cargo** (pilotaje de dron, edición de video, desarrollo…; tabla `cargos`) dice qué hace la persona en la empresa: es un dato aparte, opcional, que aparece en su ficha y en la analítica y **no da permisos** (`acceso.asignar_cargo`).

| Permiso | Ve | Puede |
|---|---|---|
| Colaborador | Lo suyo: lo que creó o donde es quien viaja (`acceso.alcance`) | Cotizar y decidir sus viajes, cargar y justificar sus gastos, descargar el Excel contable de lo suyo, preguntar al asistente por lo suyo |
| Gestor de proyecto | Lo suyo y todo lo de los proyectos que gestiona (`proyecto_miembros`) | Lo mismo que el colaborador y, **en los proyectos que gestiona, cotizar y decidir por otras personas** (`cotizacion.puede_decidir`, `cotizacion.para_otros_en`). Descarga el Excel contable de sus proyectos y pregunta al asistente por ellos. No aprueba viajes ni revisa gastos |
| Administración | Todo | Además: aprobar, rechazar, reabrir y cerrar viajes; revisar gastos; cargar recibos a nombre de otra persona; administrar cuentas, cargos, proyectos y reglas; indicadores, monitoreo y la pantalla completa del asistente |

Detalles que el código hace cumplir:

- **Ver no es modificar.** Cargar un gasto a un viaje exige que el viaje sea propio (`acceso.es_propio`); verlo no basta. Administración cuenta como propietaria de cualquier viaje en esa comprobación, así que puede cargar en viajes ajenos. Por la API v1, un `viaje_id` ajeno deja el gasto sin viaje y en revisión.
- **Cotizar para otra persona.** Administración puede en cualquier proyecto; el gestor, solo en los que gestiona; el colaborador, nunca (403 `FORBIDDEN`). El gestor decide las cotizaciones que creó para otra persona dentro de su alcance; una cotización ajena que solo ve no la decide (403 `FORBIDDEN`). Registrar un viajero nuevo es tarea de administración.
- **Justificar.** Solo justifica quien hizo el gasto o quien viaja (`justificaciones.puede_justificar`): el gestor y administración la ven, pero no escriben en nombre de otra persona.
- **Lo que no se ve se responde como si no existiera** (404 `NOT_FOUND` en la API v1).
- **El asistente** aplica el mismo alcance en cada consulta: lo decide la sesión, nunca la pregunta ni el modelo (ver [`asistente.md`](asistente.md)).

## 3. Nadie aprueba lo suyo

| Acción sobre lo propio | ¿Bloqueada? | Dónde | Respuesta |
|---|---|---|---|
| Aprobar el presupuesto de su viaje | Sí | `viajes.cambiar_estado` con `viajes.es_propio_de` | Pantalla: aviso. API v1: 403 `SELF_APPROVAL` |
| Rechazar el presupuesto de su viaje | Sí | `viajes.cambiar_estado` | Pantalla: aviso. API v1: 403 `SELF_APPROVAL` |
| Revisar un gasto suyo (corregir, aprobar, aprobar con excepción o rechazar) | Sí | `viajes.revision_permitida`, llamada desde `revision.guardar` | Pantalla: aviso. API v1: 403 `FORBIDDEN` |
| Revisar un gasto ajeno y, al hacerlo, asignárselo a sí mismo (moverlo a un viaje suyo) | Sí | `viajes.revision_permitida` compara el antes y el después | Igual que el anterior |
| Reabrir o cerrar su propio viaje | **No** | `viajes.cambiar_estado` solo bloquea `aprobar` y `rechazar` | Se permite |

- **Qué es «lo suyo».** Un viaje es propio si la persona es su titular o quien viaja; ser administración no cuenta (`viajes.es_propio_de`). Un gasto es propio si se carga a su perfil de viajero, a un viaje suyo, o si lo subió sin cargarlo a otra persona (`viajes.gasto_propio_de`). Un recibo que administración sube a nombre de otra persona es de esa persona.
- **Cada intento queda en la bitácora** con el paso «autoaprobación impedida» (`viajes.impedir_autoaprobacion`), con quién lo intentó y sobre qué.
- **Lo propio de administración** lo aprueba otra cuenta de administración. Con una sola cuenta, sus viajes y sus gastos esperan hasta que exista otra (`viajes.hay_otro_admin` lo dice en pantalla).
- **Dos códigos de error para la misma regla.** El contrato de la API v1 usa `SELF_APPROVAL` para el viaje propio y `FORBIDDEN` para el gasto propio. Los dos responden 403 y dejan el mismo evento; quien consuma la API debe tratar ambos como «no se puede decidir sobre lo propio».

## 4. Validación de los gastos: motivos de revisión

`validacion.revisar` evalúa cada gasto y deja en `gastos.motivos` los códigos de lo que encontró (`validacion.MOTIVOS`). Si al menos uno **bloquea**, el gasto va a revisión; si solo hay avisos, se aprueba solo y los avisos quedan visibles para quien lo consulte.

| Código | Texto en pantalla | Bloquea (va a revisión) / Solo avisa | Cuándo |
|---|---|---|---|
| `importe_invalido` | Importe no válido | Bloquea | El total está vacío, es cero, negativo, NaN o no numérico, o un componente (subtotal, impuesto, propina) es negativo. Ni con excepción se aprueba |
| `fecha_invalida` | Fecha no válida | Bloquea | La fecha no es una fecha real en formato AAAA-MM-DD. Ni con excepción se aprueba |
| `fecha_futura` | Fecha posterior a hoy | **Solo avisa** | La fecha es posterior a hoy en el huso más adelantado del planeta (UTC+14). No bloquea porque los recibos y viajes de demostración son de diciembre de 2026 |
| `campo_faltante` | Campo faltante | Bloquea | Falta comercio, fecha, total o moneda |
| `total_no_cuadra` | El total no cuadra | Bloquea | Subtotal + impuesto + propina difiere del total en más de 0,02 |
| `ilegible` | Lectura poco confiable | Bloquea **solo** por confianza baja | Confianza de lectura por debajo de 0,85: bloquea. Campos marcados como dudosos por la lectura con confianza suficiente: **solo avisa**. Cuando una persona revisa, la confianza deja de ser criterio |
| `sin_proyecto` | Sin proyecto | Bloquea | El gasto no tiene proyecto (sin viaje, el proyecto no se deduce) |
| `fuera_de_fechas` | Fecha fuera del proyecto | Bloquea | Solo sin viaje: la fecha cae fuera de las fechas del proyecto (un tiquete anterior al inicio es `compra_anticipada`) |
| `sin_tasa` | Moneda sin tasa de cambio | Bloquea | No hay tasa configurada para la moneda (hoy hay EUR y COP). Sin total en USD, ni con excepción se aprueba |
| `duplicado` | Posible duplicado | Bloquea | Otro gasto no rechazado con el mismo comercio (sin tildes, mayúsculas ni signos), la misma fecha, el mismo total y la misma moneda |
| `duplicado_aproximado` | Parecido a otro gasto | Bloquea | Mismo comercio, fecha a un día o menos e importe con una diferencia del 1 % o menos |
| `atipico` | Importe atípico | Bloquea | Con al menos 4 gastos aprobados de la misma categoría y moneda, el total supera la mediana + 3,5 desviaciones robustas (tres veces la mediana si todos los importes son iguales) y el doble de la mediana (`inteligencia.es_atipico`). Con menos historia no opina |
| `sin_puntos` | Fidelización perdida | **Solo avisa** | Un hotel reservado por una agencia (Booking, Expedia, Hotels.com…): esa estadía no acumula puntos en el programa del hotel |
| `compra_anticipada` | Compra anticipada | **Solo avisa** | Con viaje: vuelo, hotel, alquiler de carro o compras del proyecto con fecha anterior al viaje (`validacion.SE_COMPRAN_ANTES`). Sin viaje: un vuelo anterior al inicio del proyecto |
| `lectura_fallida` | Lectura fallida | Bloquea | La lectura del recibo falló, o el gasto quedó en `procesando` más de 5 minutos. Una lectura fallida nunca se aprueba sola |
| `sin_viaje` | Sin viaje asignado | Bloquea | No se pudo asignar el gasto a un viaje (ver sección 6) |
| `viaje_no_aprobado` | Viaje sin presupuesto aprobado | Bloquea | El viaje está pendiente de aprobación o rechazado |
| `viaje_cerrado` | Viaje cerrado | Bloquea | El viaje ya se cerró |
| `fuera_del_viaje` | Fecha fuera del viaje | Bloquea | La fecha cae fuera del viaje con su margen (un día antes de la ida, dos después del regreso), salvo una `compra_anticipada` |
| `presupuesto_superado` | Presupuesto del viaje superado | Bloquea | Lo aprobado del viaje más este gasto supera el presupuesto más la tolerancia del 10 % |

En resumen: de los 20 códigos, **17 bloquean**, **3 solo avisan** (`fecha_futura`, `sin_puntos`, `compra_anticipada`) y `ilegible` bloquea por la confianza baja, no por las dudas solas.

**Revisión por una persona** (`revision.guardar`, la misma regla en la web y en la API v1):

- **Aprobar** vuelve a evaluar las reglas con los datos corregidos y el viaje bloqueado; solo aprueba si ya no queda ningún motivo que bloquee.
- **Aprobar con excepción** aprueba aunque quede un motivo, con un porqué de 8 caracteres o más que queda en las alertas del gasto. No se puede con `importe_invalido` ni `fecha_invalida` (`revision.SIN_EXCEPCION`), ni sin total, sin moneda o sin tasa de cambio (la condición de `revision._aplicar`).
- **Rechazar** exige un motivo de 5 caracteres o más, que se guarda en `gastos.motivo_rechazo` y se le avisa a la persona.
- **Versión esperada.** Quien revisa manda la versión que vio; si el gasto cambió mientras tanto, no se aplica nada (409 `EDIT_CONFLICT` en la API).

## 5. Umbrales y tolerancias

| Valor | Cifra | Dónde vive | ¿Se edita en *Reglas y supuestos*? |
|---|---|---|---|
| Confianza mínima de lectura para aprobar sin revisión | 0,85 | `app/config.py`, `UMBRAL_CONFIANZA` | No: constante del código |
| Margen del viaje para un gasto | 1 día antes de la ida y 2 después del regreso | `app/servicios/viajes.py`, `MARGEN_ANTES` y `MARGEN_DESPUES` | No: constante del código |
| Tolerancia sobre el presupuesto del viaje | 10 % | Regla `tolerancia_presupuesto` (0.10) | Sí |
| Tolerancia de subida del precio al aprobar | 5 % | Regla `tolerancia_precio_aprobacion` (0.05) | Sí |
| Motivo para rechazar un viaje o un gasto | 5 caracteres o más | `viajes.cambiar_estado`; `revision.MINIMO_RECHAZO` | No |
| Motivo para aprobar un gasto con excepción | 8 caracteres o más | `revision.MINIMO_EXCEPCION` | No |
| Porqué de la decisión | Obligatorio (5 caracteres o más) **solo si no se elige el vuelo recomendado** | `cotizacion.decidir` | No |
| Diferencia para «el total no cuadra» | 0,02 | `validacion.revisar` | No |
| Duplicado aproximado | ±1 día e importe con una diferencia del 1 % o menos | `validacion.revisar` | No |
| Historia mínima para `atipico` | 4 gastos aprobados de la misma categoría y moneda | `inteligencia.MIN_HISTORIA` | No |
| Gasto atascado en lectura | 5 minutos | `envios.VIGENCIA` | No |
| Viáticos por día | 75 USD | Regla `viaticos_dia_usd` | Sí |
| Calificación mínima de un hotel | 3,5 | Regla `hotel_calificacion_minima` | Sí |
| Tasas de cambio a USD | EUR 1,08 y COP 0,00025 | Reglas `tasa_EUR_USD`, `tasa_COP_USD` | Sí (las que existen; no se crean monedas nuevas desde la pantalla) |
| Cuenta contable de cada categoría | Ver sección 10 | Reglas `cuenta_contable_<categoría>` | Sí |

Al **aprobar**, administración reconfirma el precio del vuelo con el buscador. Si sube más que `tolerancia_precio_aprobacion`, el viaje no se aprueba solo: se muestra la diferencia y «Confirmar precio y aprobar» aprueba con el precio nuevo y ajusta el presupuesto, sin pagar otra consulta (`viajes._reconfirmar_precio`; 409 `PRICE_CONFIRMATION_REQUIRED` en la API). Sin clave del buscador se aprueba con el aviso «precio no reconfirmado».

*Reglas y supuestos* (`/reglas`, solo administración) edita cualquier fila de la tabla `reglas`. Un valor numérico sigue siendo numérico (se rechaza «80 USD») y cada cambio deja el evento «regla editada».

## 6. A qué viaje va un gasto

`viajes.resolver_para_gasto(persona, viaje_indicado)` decide, en este orden:

1. **El viaje que la persona indica** (en la web, en la API con `viaje_id` o en Telegram con el código `V-…` en el mensaje), solo si es suyo (para administración, cualquiera). Si no lo es, el gasto queda sin viaje.
2. **El viaje que fijó como activo** (en Telegram), si sigue aprobado y lo puede ver.
3. **El viaje aprobado que está en curso hoy** (de un día antes de la ida a dos después del regreso). Si hay más de uno, pregunta.
4. **El próximo viaje aprobado** (los tiquetes se compran antes). Si hay dos que salen el mismo día, pregunta.
5. Si solo tiene viajes aprobados ya pasados, **pregunta** en vez de adivinar.
6. Si no tiene ninguno aprobado, **el único pendiente de aprobación**; con varios, pregunta.

El viaje define el proyecto y quién viaja del gasto. **Sin viaje**, el gasto se guarda igual con el motivo `sin_viaje` y va a revisión. En la web y en la API la persona elige el viaje al cargar (o lo deja en automático); en Telegram, si hay varios candidatos, el bot los ofrece con botones y el gasto se asigna al elegir. Después, administración puede asignarlo en la revisión. Asignar o cambiar el viaje vuelve a validar el gasto (`gastos.asignar_viaje`); lo que una persona ya aprobó conserva su estado, pero no se puede llevar a un viaje que no lo admite.

Registrar, asignar viaje y aprobar se hacen con el viaje bloqueado (`db.transaccion`, `db.bloquear_viaje`), así que dos aprobaciones a la vez no gastan el mismo saldo.

## 7. Justificaciones

Cada gasto puede llevar una o varias justificaciones: para qué fue, por escrito o en una nota de voz transcrita (tabla `justificaciones`; detalle en [`justificaciones.md`](justificaciones.md)).

- Se pide en la carga web («¿Para qué fue este gasto?»), en el detalle del gasto, en Telegram (el pie de la foto o el siguiente mensaje dentro de 30 minutos) y en la API v1.
- **Es opcional:** un gasto nunca queda bloqueado por no tenerla.
- **Ninguna regla de aprobación lee su contenido.** Informa a quien revisa y al asistente.
- Solo la escribe quien hizo el gasto o quien viaja.

## 8. Costo esperado y presupuesto

Son tres cifras distintas, y es correcto que no coincidan.

| | Comparación | Ficha de la decisión | Presupuesto del viaje |
|---|---|---|---|
| Para qué | Ordenar y recomendar vuelos y hoteles | El costo total esperado de lo elegido | Lo que se espera pagar; contra él se validan los gastos |
| Dónde | `costo.evaluar` (vuelos), `costo.evaluar_hotel` (hoteles) y el total del viaje con el hotel recomendado | `decisiones.total`, calculado en `cotizacion.decidir` | `viajes.presupuesto_de` |
| Precio del tiquete, equipaje de mano y maleta | Sí | Sí | Sí |
| Riesgo de cambio de fecha (probabilidad × costo) | Sí | Sí | **No**: es valor esperado |
| Millas del viajero y de la cuenta de empresa (restan) | Sí | Sí | **No**: es valor esperado |
| Traslado por carretera (taxi o combustible) | Sí | Sí | Sí: se pagará, aunque sea un supuesto |
| Tarifa del hotel | Sí | Sí | Sí |
| Tarifa de miembro del hotel (resta) | Sí, con membresía | Sí, con membresía | Sí, con membresía: es un descuento que se paga de menos |
| Puntos del programa del hotel (restan) | Sí, con membresía: ordenan los hoteles | **No** | **No**: es valor esperado, como las millas |
| Carro de alquiler | **No** | Sí | Sí |
| Viáticos (días del viaje × `viaticos_dia_usd`) | No | No | Sí |

Por eso un viaje con un costo esperado de 980 USD puede tener un presupuesto de 1.153 USD.

## 9. Fidelización

**Aerolíneas** (`costo.evaluar`):

- Las millas **solo restan** si el viajero tiene membresía en esa aerolínea (5 millas por USD) o la empresa tiene cuenta (1 por USD), al valor de `valor_milla_usd` (0,012 USD). Sin membresía no restan: la comparación muestra la oportunidad («Inscribirse en … es gratis y acumularía ~N millas»).
- Una tarifa básica que según la regla de la aerolínea no acumula, no resta millas.
- La maleta facturada es gratis por estatus si la regla de la aerolínea lo dice y el viajero tiene ese estatus.

**Hoteles** (`costo.evaluar_hotel`):

- El programa se reconoce por la **marca** que aparece en el nombre del hotel (`costo.programa_hotel`): Marriott Bonvoy, Hilton Honors (Hampton, DoubleTree…), World of Hyatt, IHG One Rewards (Holiday Inn, Crowne Plaza…) y ALL Accor (Novotel, Ibis…). Marcas, puntos por USD, valor del punto y descuento de miembro son reglas editables con su fuente y confianza «supuesto».
- La tarifa de miembro y los puntos **solo restan con membresía** (los puntos, solo en la comparación: no entran en la ficha ni en el presupuesto) del viajero o de la empresa en ese programa, o si la regla `inscripcion_gratis_hotel` vale «sí» (por defecto «no»). Sin ellas, inscribirse aparece como oportunidad.
- Los hoteles se ordenan por **costo total** (tarifa, tarifa de miembro y puntos) y el primero es el **hotel recomendado**; el más barato se marca aparte si no es el mismo.
- Un hotel con **calificación por debajo de 3,5** (`hotel_calificacion_minima`) se descarta con su razón. Sin calificación no se descarta: falta el dato, no es un mal hotel.
- La membresía de hotel de la semilla (Andrés Molina en Hilton Honors) y las de aerolínea son inventadas y se rotulan «Dato de ejemplo».

## 10. Categorías y cuentas contables

Las categorías están en `app/config.py` (`CATEGORIAS`). La lectura del recibo elige una; si no reconoce ninguna, `otros`. La cuenta contable de cada una es un **supuesto** editable (`cuenta_contable_<categoría>`, sembrado desde `contable.CUENTAS`) que contabilidad debe confirmar con su plan de cuentas.

| Clave | Categoría | Cuenta contable (supuesto) | Se compra antes del viaje |
|---|---|---|---|
| `vuelo` | Vuelo | 6110 Viajes: pasajes aéreos | Sí |
| `hotel` | Hotel | 6120 Viajes: alojamiento | Sí |
| `alquiler_carro` | Alquiler de carro | 6130 Viajes: alquiler de vehículos | Sí |
| `transporte_terrestre` | Transporte terrestre: taxi, bus, tren, aplicación | 6135 Viajes: transporte terrestre | No |
| `combustible` | Combustible | 6140 Viajes: combustible | No |
| `comida` | Comida | 6150 Viajes: alimentación | No |
| `parqueo_peajes` | Parqueo y peajes | 6160 Viajes: parqueaderos y peajes | No |
| `compras_proyecto` | Compras del proyecto | 6210 Proyectos: compras y materiales | Sí |
| `otros` | Otros | 6190 Viajes: otros gastos de viaje | No |

«Se compra antes del viaje» quiere decir que una fecha anterior al viaje solo avisa (`compra_anticipada`) en vez de bloquear (`fuera_del_viaje`).

El Excel contable (`app/servicios/contable.py`) saca los gastos aprobados de un periodo con su cuenta; cada quien descarga lo que puede ver: administración, todo; el gestor, sus proyectos; el colaborador, lo suyo.
