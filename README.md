# Operación de proyectos: viajes y gastos

> **Este repositorio es un MVP.** Una plataforma que funciona de punta a punta para los dos retos de la prueba (cotizar el viaje por su costo total y recoger, validar y aprobar sus gastos) sobre un mismo eje: el viaje.
>
> - **Demuestra:** el flujo completo de la cotización al cierre del viaje, con precios reales del buscador, lectura automática de recibos, permisos por rol, «nadie aprueba lo suyo», trazabilidad de cada dato, indicadores y despliegue en AWS.
> - **No es todavía:** la arquitectura de servicios objetivo (es una etapa de transición), ni tiene buzón de correo real, Telegram en producción ni una medición publicada de la exactitud de la lectura. Las personas, comercios, membresías y recibos de ejemplo son inventados.
>
> Producción: [web](https://software.nataliaremolinarodriguez.com) · [administración](https://admin.software.nataliaremolinarodriguez.com) · **[Informe técnico](docs/informe-tecnico.md)** · **[Regla de negocio](docs/regla-de-negocio.md)** · [Toda la documentación](#documentación)

Plataforma para una empresa que graba con drones y cuyos pilotos viajan a cada proyecto. Resuelve dos problemas sobre un mismo eje, **el viaje**:

1. **Cotizar el viaje** (reto 1). Compara vuelos y hoteles por su **costo total esperado** (precio, equipaje del equipo, baterías, riesgo de cambio de fecha, millas, traslado por carretera), no por el precio más bajo. La persona decide y explica por qué; la decisión crea el viaje con su presupuesto, y administración lo aprueba.
2. **Recoger los gastos del viaje** (reto 2). Fotos, PDF, correos o mensajes de Telegram se leen solos, se validan contra el viaje y su presupuesto, se aprueban solos cuando todo está claro y llegan a una persona solo las excepciones.

```
persona (P-0007) ─► cotización ─► decisión ─► VIAJE (V-2026-0012, presupuesto, estado) ─► gastos y evidencias
                                                  ▲
                                       aprobación de administración
```

**Por qué integrados y no por separado.** Los dos retos describen el mismo objeto en dos momentos: el reto 1 decide cuánto debería costar un viaje y el reto 2 registra cuánto costó. Resueltos por separado, quedarían dos listas que alguien concilia a mano: a qué proyecto va cada recibo, si un gasto cabe en lo previsto, qué viaje no tiene soportes. Con el viaje como eje, la decisión de la cotización crea el viaje con su presupuesto, que administración aprueba; cada gasto se asigna solo al viaje de la persona (por quién lo envía y las fechas) y se valida contra ese presupuesto; y previsto frente a real se ve en cada viaje y en el tablero de cada proyecto. El análisis inicial (`ANALISIS.md`, sección 4) proponía una integración ligera, con el proyecto como punto de unión y la opción de recortarla si faltaba tiempo. Se amplió a una sola plataforma con el viaje como eje porque la asignación automática del gasto y el control del presupuesto solo funcionan si cada gasto sabe a qué viaje pertenece. El costo es una aplicación y una base compartidas por los dos retos, más acopladas que dos herramientas sueltas, y se declara como etapa de transición (ver «Arquitectura» y «Limitaciones conocidas»).

## Qué hay

| Pieza | Para qué |
|---|---|
| Cuentas, permisos y cargos | Colaborador (lo suyo), gestor de proyecto (además ve sus proyectos y en ellos cotiza y decide por otras personas; no aprueba ni revisa) y administración (todo). El cargo (pilotaje, edición, desarrollo…) es un dato aparte. Todos viajan y nadie aprueba lo suyo |
| Cotización y decisión | Origen y destino en cualquier lugar del mundo, varios aeropuertos por búsqueda, traslado por carretera, precios en vivo o guardados, millas y programas de hotel con efecto en el costo, hotel recomendado, descarte de opciones que no sirven, agente que explica la recomendación, decisión con su porqué |
| Viajes | Código propio, presupuesto, aprobación, rechazo con motivo, reapertura y cierre |
| Monitoreo del vuelo | El día del viaje, estado de cada tramo y aviso por Telegram si hay retraso, cancelación o cambio de puerta |
| Gastos | Foto, PDF (también de varias páginas), correo `.eml` y confirmación en HTML; nueve categorías con su cuenta contable; lectura automática; 20 motivos de revisión (17 bloquean y 3 solo avisan, ver [regla de negocio](docs/regla-de-negocio.md)); bandeja de revisión, aprobación con excepción justificada, envíos idempotentes y revisión versionada |
| Justificaciones | Para qué fue cada gasto, por escrito o con nota de voz transcrita |
| Telegram | Recibos por chat, vinculados a la cuenta con un código de un solo uso (apagado si no se configura) |
| Tablero por proyecto | Presupuesto de los viajes frente a gasto real |
| Indicadores (KPIs) | Metas y semáforo para los dos retos, rastro de cada consulta al buscador y ficha por persona |
| Asistente | Preguntas en lenguaje natural con cifras exactas y fuentes citadas por su código. Cada permiso pregunta solo por lo que puede ver: el colaborador, lo suyo («¿cuánto me queda del presupuesto?»); el gestor, también sus proyectos; administración, todo, con su pantalla completa. Botón flotante en la plataforma y en la web nueva (con dictado por voz); opcionalmente con un asesor (agente alojado) que también lee justificaciones y cotizaciones |
| Monitoreo | Catálogo único de métricas, auditoría, errores con identificador, calidad de los datos |
| API JSON v1 | Contrato para la web nueva (`contracts/api-v1.md`) |
| Web nueva (Next.js) | Sobre la API v1 (`web/`): cotizar desde y hacia cualquier lugar, comparar vuelos y hoteles con desglose y decidir; mis viajes y mis gastos, con carga de recibos, justificación y el Excel contable; el asistente; y, para administración, resumen, viajes por aprobar (con la reconfirmación del precio) y revisión de gastos |

## Cómo responde a cada reto

| El enunciado pide | Dónde se ve | Evidencia |
|---|---|---|
| **Reto 1.** Buscar y elegir vuelos | *Cotizar*: origen y destino en cualquier lugar del mundo, varios aeropuertos en una búsqueda, descartes con su razón | `tests/test_cotizacion_mundial.py` y escenarios guardados |
| Buscar y elegir hoteles | Sección «Hoteles»: ordenados por costo total con la fidelización, el hotel recomendado, el más barato aparte y los descartados por calificación con su razón | Respuestas guardadas de Las Vegas, Lisboa y Denver; `tests/test_fidelizacion.py` |
| Programas de fidelización | Desglose de cada opción: millas solo con membresía o cuenta de empresa (si no, la oportunidad de inscribirse), maleta gratis por estatus, y programas de hotel reconocidos por la marca con tarifa de miembro y puntos. *Reglas* muestra la fuente y la confianza de cada regla; las membresías inventadas se rotulan «Dato de ejemplo» | `tests/test_fidelizacion.py` y pruebas de `costo` |
| Costos totales del viaje | «Costo total esperado» de cada opción: precio, equipaje, baterías en cabina, riesgo de cambio, millas y traslado por carretera; cada vuelo muestra además el total del viaje con el hotel recomendado. Al decidir se suman el hotel, el carro y los viáticos | Escenario Miami → Moab |
| Mejores decisiones en menos tiempo | La recomendación con su porqué; la opción más barata, con la razón de su descarte; y la decisión con sus razones. KPIs de tiempo de la cotización a la decisión y de la decisión a la aprobación | *KPIs* |
| Factores, oportunidades y desafíos | `ANALISIS.md` (§3 y §5), `EXPLORACION.md` y «Limitaciones conocidas» | — |
| Herramienta funcional y escenarios propios | Publicada (ver «Despliegue») y en local sin claves; escenarios en la tabla de abajo | Pruebas automáticas sin claves |
| Lo simulado, claramente identificado | Cada dato muestra su origen en pantalla (en vivo, guardado, supuesto o regla), y el pie dice qué servicios están conectados. Las personas, clientes, comercios y membresías de ejemplo son inventados | — |
| **Reto 2.** Gastos de distintos tipos, formatos y canales | *Cargar soportes* (web, y celular con la cámara), API v1 y Telegram (apagado en producción). Acepta foto, PDF de una o varias páginas, correo `.eml` (se lee el adjunto más útil) y confirmación en HTML; un correo o una confirmación subidos quedan en el canal «correo». Nueve categorías, incluidas transporte terrestre y compras del proyecto | `datos/ejemplos/` y `tests/test_formatos_gastos.py` |
| Revisar y organizar sin trabajo manual | Lectura automática y 20 motivos de revisión (17 bloquean y 3 solo avisan). Lo que está claro se aprueba solo; lo demás llega a la bandeja de excepciones. Nadie aprueba lo suyo, y cada gasto puede llevar su justificación | `tests/test_integridad.py` y `tests/test_autoaprobacion.py` |
| Seguimiento por proyecto | Tablero del proyecto (previsto frente a real), viaje con su presupuesto, KPIs y asistente con fuentes citadas | — |
| Información accesible para Finanzas | Exportación CSV y Excel contable con hojas Gastos y Resumen, según el permiso de quien lo descarga | `tests/test_contable.py` |
| Materiales de prueba propios | `datos/ejemplos/`: 13 soportes sellados «FICTICIO · prueba técnica»: fotos de recibos (comida, gasolina, taxi, uno en euros y un parqueo borroso), PDF (facturas de hotel y de carro, una de dos páginas, la confirmación de un vuelo y una compra del proyecto), dos correos (un tiquete y una reserva con la factura adjunta) y una confirmación de hotel en HTML | `datos/ejemplos/esperados.json`; la exactitud se mide con `datos/medir_exactitud.py` ([`docs/exactitud-lectura.md`](docs/exactitud-lectura.md), pendiente de corrida con clave) |

### Escenarios de prueba

| Escenario | Qué muestra | Resultado esperado |
|---|---|---|
| Miami → Moab, del 8 al 11 de diciembre de 2026 (CNY, GJT y SLC) | Pueblo sin aeropuerto principal: tres aeropuertos con traslado por carretera | La recomendada no es la más barata; desde SLC aparece «Combustible y peajes» |
| Miami → Las Vegas | Ruta directa con hoteles guardados | Vuelos con desglose y hoteles con el total de las noches |
| Madrid → Lisboa | Europa, en euros | Vuelos y hoteles guardados. Con `make demo-monitoreo`, el IB 5634 retrasado 20 minutos y su aviso |
| Recibo borroso | Lectura con poca confianza | Va a revisión por confianza baja |
| El mismo recibo dos veces | Duplicado exacto | El segundo va a revisión como duplicado |
| Viaje propio de administración | Nadie aprueba lo suyo | El servicio lo impide y lo deja en la bitácora |
| Excel contable como colaborador y como gestor | Alcance por permiso | El colaborador solo ve lo suyo y el gestor, solo sus proyectos |

### Tiempo que ahorra (supuesto declarado)

No hay una medición del proceso manual de la empresa. Como referencia, comparar a mano tres aeropuertos, los hoteles y las reglas de equipaje y millas de un viaje toma unos 45 minutos, y transcribir, clasificar y asignar un recibo, unos 5. Con la plataforma, la comparación sale en una pantalla y un recibo claro se aprueba sin intervención. Las dos cifras de referencia son supuestos, no mediciones. Lo real lo miden los KPIs a medida que haya uso: la tasa sin intervención, las horas de la carga a la aprobación y el tiempo de la cotización a la decisión.

## Ejecutar

### Lo más rápido: sin claves y sin Docker

Requiere **Python 3.12** (Docker no lo necesita). Con 3.11 o anterior el código no compila; `make instalar` lo comprueba y usa `python3.12`, o el que se indique con `make instalar PYTHON=/ruta/a/python`.

```bash
make instalar
make ejecutar        # http://localhost:8000
```

Usa SQLite, precios reales guardados (Miami → Las Vegas, Miami → Moab) y lecturas guardadas de los recibos de ejemplo. La pantalla de ingreso muestra las cuentas de demostración.

### Entorno completo con Docker

```bash
make entorno         # PostgreSQL local y la plataforma en http://127.0.0.1:8000
make entorno-web     # además la web nueva y el gateway en http://127.0.0.1:8088
make entorno-abajo   # detener (los datos de demostración se conservan)
```

Es el mismo motor de base que en la nube, con datos de demostración. **No lee `.env`**: ninguna variable de este entorno apunta a la base real.

En `127.0.0.1:8088` el gateway publica un solo origen: `/api/v1/*` va a la API y el resto a la web nueva. La plataforma actual sigue en `127.0.0.1:8000`; las dos comparten la misma base. Abre una en `127.0.0.1` y la otra en `localhost` si quieres tener dos sesiones distintas a la vez (las cookies no se separan por puerto).

### Cuentas de demostración

| Permiso | Correo | Contraseña |
|---|---|---|
| Administración | `admin@demo.local` | `demo-admin-2026` |
| Colaborador (Andrés Molina) | `piloto@demo.local` | `demo-piloto-2026` |
| Colaborador (Laura Pérez) | `piloto2@demo.local` | `demo-piloto2-2026` |
| Gestor de proyecto | `gestor@demo.local` | `demo-gestor-2026` |

Solo existen en local (SQLite, o PostgreSQL con `CUENTAS_DEMO=1`). En una base compartida la primera cuenta de administración sale de `ADMIN_INICIAL_CORREO` y `ADMIN_INICIAL_CLAVE`.

## Recorrido sugerido (10 minutos)

1. **Como colaborador:** *Cotizar viaje* con los valores de ejemplo → ver por qué lo más barato no es lo mejor → elegir y *Guardar decisión*. Nace el viaje `V-…`, pendiente de aprobación.
2. **Como administración:** *Viajes* → aprobar el presupuesto.
3. **Como colaborador:** *Cargar gasto* con los recibos de ejemplo. Van solos al viaje; los claros se aprueban, el ilegible queda en revisión.
4. **Como administración:** *Gastos* → bandeja *En revisión* → corregir y aprobar, o aprobar con excepción.
5. *KPIs* → semáforos de los dos retos → ficha de la persona.
6. *Asistente* → «¿Qué ha reportado P-0002 en su viaje?».
7. *Monitoreo* → viajes, gastos, búsquedas, auditoría y calidad de datos.

Para presentar paso a paso (Miami → Moab con traslado, aprobación por otra cuenta, gastos y monitoreo del vuelo), ver «Guía de demostración» más abajo.

### El mismo recorrido en la web nueva

Con `make entorno-web`, en http://127.0.0.1:8088 y las mismas cuentas:

1. **Como colaborador:** *Cotizar* → origen y destino (un país, una ciudad, un pueblo o un código) → *Buscar y comparar* → ver el desglose de cada opción → elegir y *Guardar decisión*. El viaje aparece en *Viajes*, esperando la aprobación de administración.
2. **Como administración:** *Viajes* → *Por aprobar* → aprobar o rechazar con motivo. Si el precio reconfirmado subió más de la tolerancia, la web muestra «Precio por confirmar» y el botón para aprobar con el precio nuevo.
3. **Como colaborador:** *Gastos* → *Cargar recibo* → elegir el viaje (o dejarlo en automático), el archivo y para qué fue. El estado se ve en la lista y en el detalle; si se rechaza, el detalle ofrece cargar el recibo de nuevo.
4. **Como administración:** *Gastos* → revisión: la decisión va arriba, con «Por qué va a revisión»; aprobar o rechazar con motivo.

Lo que la web nueva todavía no tiene sigue en la plataforma actual (127.0.0.1:8000), y la web enlaza allí cuando hace falta: corregir los datos leídos de un gasto y aprobarlo con excepción, KPIs, monitoreo, reglas, proyectos y usuarios. El asistente y el Excel contable están en las dos. Las dos comparten la base, así que lo hecho en una se ve en la otra.

## Cotizar desde y hacia cualquier lugar del mundo

El origen y el destino son un solo campo, como en Google Flights. Se puede escribir un país, una ciudad, un pueblo o un código de aeropuerto (`moab`, `Lisboa`, `LIS`, `Portugal`).

- **Búsqueda local.** Los datos viven en la base (unos 4.000 aeropuertos con servicio regular, 171.838 ciudades y pueblos de más de 1.000 habitantes y 249 países), así que sugerir no llama a ningún servicio externo. Dos lugares con el mismo nombre se distinguen por región y país (al escribir `miami` salen Miami, Florida; Miami, Oklahoma; Miami, Arizona y Miami, Australia). Ruta: `GET /lugares/buscar`.
- **Aeropuertos cercanos.** Al elegir un lugar se marcan sus aeropuertos con servicio regular dentro de un radio (400 km por defecto, hasta 4); la persona puede quitar alguno. Al elegir un país se proponen sus aeropuertos principales.
- **Autocompletado de Google, combinado.** Con clave del buscador y tras una pausa de 400 ms con al menos 3 letras, las ciudades y aeropuertos de Google se suman a la lista, marcados como «Google». Solo se envía el texto del campo de lugar. Cada respuesta se guarda y el mismo texto no se paga dos veces. Topes (editables en «Reglas y supuestos»): 60 consultas al mes y 15 por persona al día; alcanzado un tope, o sin clave, sigue solo con los datos locales. `PROVEEDOR_LUGARES=local` lo apaga.
- **Varios aeropuertos por búsqueda.** Comparar varios aeropuertos de origen y de destino gasta **una** consulta del buscador (los códigos van unidos por coma y ordenados).
- **Traslado por carretera en el costo.** Cada opción suma el traslado entre el aeropuerto real y el lugar: línea recta × 1,3 como distancia, 70 km/h como velocidad, 0,35 USD por km ida y vuelta (0,12 con carro de alquiler, solo combustible y peajes). También cuenta para la hora límite y para el presupuesto del viaje. A menos de 30 km no hay línea extra. Todos esos valores son reglas editables y la distancia es una estimación, no una ruta de un servicio de mapas.

## Cargos y permisos

- **El permiso** dice qué se puede hacer: *colaborador* (antes «piloto»: cotiza y reporta lo suyo), *gestor de proyecto* (además ve sus proyectos, y en ellos cotiza y decide por otras personas) y *administración* (ve todo, aprueba y revisa). La migración convierte las cuentas «piloto» en colaboradores sin cambiar sus viajes ni sus gastos.
- **El cargo** dice qué hace la persona en la empresa (pilotaje de dron, edición de video, desarrollo de software, ingeniería de datos, producción u otros). Es un dato aparte, sin permisos propios; administración mantiene la lista en la pantalla de Usuarios y asigna el cargo a cada cuenta. Aparece en la ficha, en la lista de usuarios y en la analítica.
- **Todos viajan:** colaboradores, gestores y administración cotizan, reciben viajes a su nombre y reportan gastos.
- **Nadie aprueba lo suyo:** el presupuesto de un viaje y los gastos de una persona de administración los aprueba o los revisa otra persona de administración. El servicio lo impide y deja el intento en la bitácora; reabrir y cerrar el propio viaje sí se permite. Detalle en [`docs/regla-de-negocio.md`](docs/regla-de-negocio.md).

## La opción elegida completa y el monitoreo del vuelo

**Al decidir**, la plataforma carga completa la opción elegida: busca el vuelo de regreso real (el que sale del aeropuerto donde aterrizó la ida) y las opciones de reserva con su tarifa y equipaje. Con la tarifa real recalcula el costo y el presupuesto; sin ella queda la estimada, marcada «(supuesta)». Los tramos de ida y de regreso se guardan en `tramos_vuelo`. Decidir de nuevo la misma opción no paga nada: lee lo guardado.

**Al aprobar**, administración reconfirma el precio con el buscador (siempre en vivo): «precio confirmado», «precio cambió: antes X, ahora Y» o «precio no reconfirmado». Si sube más que la regla `tolerancia_precio_aprobacion` (5 % por defecto, editable en «Reglas y supuestos»), el viaje no se aprueba solo: el tablero muestra la diferencia y el botón «Confirmar precio y aprobar», que aprueba con el precio nuevo sin volver a pagar la consulta.

**El día del viaje**, el tablero «Viajes» de administración muestra el estado de cada vuelo (a tiempo, retrasado, cancelado, terminal, puerta, llegada estimada) y marca «No llega a la grabación» si la llegada más el traslado pasa de la hora límite. Si hay un retraso de 15 minutos o más (o que crece 15 más desde el último aviso), una cancelación o un cambio de terminal o de puerta, se avisa al viajero por Telegram si tiene el chat vinculado; si no, el aviso queda en el tablero. Nunca se avisa dos veces lo mismo.

| Momento | Búsquedas del plan que gasta |
|---|---|
| Cotizar | 1 de vuelos (aunque se comparen varios aeropuertos) y 1 de hoteles |
| Decidir | Hasta 2: el regreso real y las opciones de reserva. Lo que ya está guardado no se paga |
| «Traer tarifas» (bajo demanda) | Las mismas 2 |
| Aprobar | 1 (la reconfirmación). «Confirmar precio y aprobar» no gasta otra |
| Estado del vuelo | 1 por consulta en vivo, solo dentro de la ventana y bajo los topes |

Para cuidar el plan del buscador (250 búsquedas al mes), el estado del vuelo solo se consulta desde 3 horas antes de la salida hasta la llegada (cada hora en la zona horaria de su aeropuerto, que sale de GeoNames: columna `zona` de `lugares`), se reutiliza 60 minutos, y hay topes de 6 consultas por tramo, 12 por viaje y sentido y 30 en vivo por día. Si al plan le quedan menos de 25 búsquedas, el monitoreo se suspende. «Actualizar ahora» salta la caché (una vez por minuto como máximo), nunca la ventana ni los topes. Todos son reglas editables; ver `docs/kpis.md` para cómo se cuentan.

**Sin clave del buscador:** decidir carga lo guardado si existe y, si no, deja el evento «regreso sin datos» y registra solo los tramos de ida; aprobar funciona con el aviso «precio no reconfirmado»; el estado del vuelo usa la respuesta de ejemplo del IB 5634 y cualquier otro vuelo queda «sin datos».

## Modelo de precio esperado y API de lectura

Cada búsqueda de vuelos queda como datos tabulares (`observaciones`), que alimentan un modelo de precio esperado:

```bash
.venv/bin/python -m datos.recolectar --simular   # muestra qué buscaría, sin gastar consultas
.venv/bin/python -m datos.recolectar --max 40    # una consulta del buscador por búsqueda nueva
.venv/bin/python -m datos.entrenar               # entrena y publica sus métricas en datos/modelo/ficha.json
```

El modelo predice el precio de un vuelo por ruta, aerolínea, escalas, duración, horario y anticipación, se valida dejando búsquedas completas fuera del entrenamiento y se compara con la mediana de la ruta. **Solo se muestra en las comparaciones si tiene al menos 200 filas y supera a esa línea base**; su estado se ve en Analítica. Los pesos de la decisión (riesgo de cambio, valor de la milla) no son aprendidos: son reglas y supuestos explícitos.

Además de la API v1, hay rutas JSON de **solo lectura y solo para administración** bajo `/api` (`/api/analitica`, `/api/solicitudes`, `/api/solicitudes/{id}`, `/api/gastos`, `/api/observaciones`, `/api/eventos`), documentadas en `/docs`.

## Integridad de los gastos

- Los importes se validan con `Decimal` (`app/servicios/dinero.py`): un total vacío, cero, negativo o no numérico va a revisión (`importe_invalido`), igual que una fecha que no es real (`fecha_invalida`). Una fecha posterior a hoy avisa (`fecha_futura`) pero no bloquea. El duplicado compara también la moneda.
- Registrar, asignar viaje y aprobar un gasto se hacen con el viaje bloqueado (`db.transaccion()`), así que dos aprobaciones a la vez no pasan el presupuesto.
- Reenviar un recibo no crea otro gasto: la carga web y la API aceptan una clave de envío (`Idempotency-Key`); repetida devuelve el mismo gasto, y con otro archivo, 409.
- La revisión es versionada (`gastos.version`): si otra persona cambió el gasto mientras se revisaba, no se pisa (409 `EDIT_CONFLICT` en la API). Rechazar exige un motivo de 5 caracteres o más, que se guarda en `gastos.motivo_rechazo` y se le avisa a la persona. Misma regla en la web y en `POST /api/v1/gastos/{id}/revision` (ver `contracts/api-v1.md`).
- Quién puede cambiar qué y qué queda registrado: `docs/trazabilidad.md`.

**Excel contable.** Los gastos aprobados de un periodo salen en un `.xlsx` listo para contabilidad, sin copiar nada a mano (`app/servicios/contable.py`). La hoja «Gastos» trae una fila por gasto: fecha, viaje, proyecto, persona, proveedor, categoría y **cuenta contable**, base, impuesto, total, moneda, tasa y total en USD, quién aprobó y cuándo, alertas o excepción y el enlace al gasto en la plataforma. La hoja «Resumen» suma por proyecto, por cuenta y por moneda, y dice con qué parámetros se generó. La cuenta de cada categoría es un supuesto editable en «Reglas y supuestos» (claves `cuenta_contable_…`) que contabilidad debe confirmar con su plan de cuentas. Ningún texto queda como fórmula. Cada quien descarga lo que puede ver: administración, todo; quien gestiona, sus proyectos; el resto, lo suyo. Está en la lista de gastos y en el tablero de cada proyecto, en la web nueva (Gastos → «Excel contable») y en `GET /api/v1/gastos/contable`. Desde la consola, como administración y en solo lectura sobre la base de `DATABASE_URL`:

```bash
.venv/bin/python -m datos.exportar_contable --desde 2026-11-01 --hasta 2026-11-30 [--proyecto ID] --salida libro.xlsx
```

```bash
.venv/bin/python -m datos.comprobar_supabase   # solo lectura: tablas, columnas y permisos que espera esta versión
```

**Respaldo de la base publicada.** El plan gratuito de Supabase no hace respaldos automáticos. `make respaldar` copia la base y los recibos en solo lectura, con conteos y huellas, y `make verificar-respaldo` ensaya la restauración en una base nueva del proyecto de pruebas. Procedimiento, cifrado de la copia y vuelta atrás: `docs/respaldo.md`.

**Llevar lo cotizado de un entorno a otro.** `datos/importar_entorno.py` copia cotizaciones, decisiones, viajes, tramos y respuestas del buscador de una base a otra (por ejemplo, de Docker al proyecto de pruebas), emparejando personas por correo y proyectos y viajeros por nombre. `ensayo` dice qué entraría sin escribir nada; `aplicar` lo carga, sin duplicar en una segunda corrida. Nunca escribe en la base publicada.

```bash
ORIGEN_URL=postgresql://... DESTINO_URL=postgresql://... .venv/bin/python -m datos.importar_entorno ensayo
```

## Guía de demostración (en local, con Docker)

Todo corre en local con una base PostgreSQL desechable y **sin claves**: no toca la base ni los servicios publicados.

**Qué es simulado.** Sin clave del buscador, las cotizaciones usan respuestas reales guardadas en `datos/respaldo/` (Miami a Moab y Las Vegas, capturadas el 11 de noviembre de 2026), y la lectura de recibos usa las lecturas guardadas de los ejemplos. El estado del vuelo usa una respuesta de ejemplo escrita a mano con la forma que documenta el proveedor (no es una consulta real) y una fecha fija. Telegram no está conectado: los avisos quedan en el tablero. La reconfirmación del precio al aprobar necesita la clave: sin ella aprueba con el aviso «precio no reconfirmado».

1. **Levantar el entorno.** `make entorno` (plataforma en http://127.0.0.1:8000) o `make entorno-web` (además la web nueva en http://127.0.0.1:8088). `make entorno-abajo` lo detiene y conserva los datos; `docker compose down -v` los borra. Los pasos 3 a 8 se pueden hacer igual en la web nueva (ver «El mismo recorrido en la web nueva»); el paso 9 se ve en la plataforma actual.
2. **Cuentas de demostración** (la pantalla de ingreso muestra tres con sus contraseñas): `admin@demo.local` (administración), `piloto@demo.local` (colaborador) y `gestor@demo.local` (gestor de proyecto). Hay una cuarta colaboradora, `piloto2@demo.local`, con la contraseña `demo-piloto2-2026` (cuentas de `datos/semilla.py`, solo en local).
3. **Cotizar Miami → Moab** con `piloto@demo.local`: *Cotizar viaje*, 8 a 11 de diciembre de 2026 (las fechas de la respuesta guardada).
   - **Origen:** escribir **MIA** y elegir «Miami International Airport (MIA)», no la ciudad Miami: la ciudad marca también OPF, FLL y BIM, y esa combinación no tiene respuesta guardada (si se elige la ciudad, desmarcar esos tres).
   - **Destino:** elegir «Moab». Se marcan solos los cuatro aeropuertos más cercanos (CNY, GJT, MTJ y TEX): **desmarcar MTJ y TEX** y, en «Agregar otro aeropuerto (nombre o código)», escribir **SLC** y elegirlo. Deben quedar CNY, GJT y SLC, que es la combinación guardada; con otra, sin clave del buscador, la búsqueda queda «sin datos».
4. **Comparar CNY, GJT y SLC con traslado.** Cada opción suma el traslado por carretera entre el aeropuerto y Moab (CNY está a unos 27 km y no suma línea; desde SLC aparece «Combustible y peajes»). La recomendada es por costo total esperado, no la más barata.
5. **Decidir.** Elegir la recomendada (o otra, explicando por qué) y guardar. Se crea el viaje, pendiente de aprobación. Sin clave aparece «regreso sin datos» en la bitácora del viaje: es lo esperado.
6. **Aprobar con otra cuenta.** Entrar como `admin@demo.local`, *Viajes*, aprobar. Para ver que nadie aprueba lo suyo: con la cuenta de administración cotizar y decidir otro viaje e intentar aprobarlo; el servicio lo impide y lo deja en la bitácora. Una segunda cuenta de administración (se crea en *Usuarios*) sí puede aprobarlo.
7. **Cargar un recibo con justificación.** Como colaborador, *Gastos → Cargar soportes*: un archivo de `datos/ejemplos/` y el campo «¿Para qué fue este gasto?». El recibo queda aprobado solo o en revisión según el viaje y las reglas; el borroso (`recibo_parqueo_borroso.png`) va a revisión.
8. **Rechazar con motivo.** Como administración, abrir el gasto en revisión, escribir el motivo (5 caracteres o más) y *Rechazar*: queda guardado y la persona lo ve.
9. **Monitoreo del vuelo.** `make demo-monitoreo` crea un viaje aprobado de Madrid a Lisboa (13 a 16 de diciembre de 2026, llegar antes de las 12:00) con el tramo IB 5634. Después, en `docker-compose.yml` quitar el comentario de `MONITOREO_AHORA: "2026-12-13T06:00"` y recrear la plataforma con `docker compose up -d app`. Abrir *Viajes* como administración: el tablero lee la respuesta de ejemplo y muestra IB 5634 retrasado 20 minutos, terminal 4, puerta J58, con el aviso al viajero (sin Telegram vinculado, queda en el tablero). Repetirlo no gasta búsquedas ni duplica el aviso. Sin `MONITOREO_AHORA` el tablero dice «fuera de la ventana», porque ese vuelo es del 13 de diciembre. `MONITOREO_AHORA` solo se respeta con `ENTORNO=local`.

**Advertencias para quien presenta.**

- **Moab no tiene hoteles guardados.** La búsqueda de hoteles de Moab queda «fallida» y la decisión se guarda solo con el vuelo. Las respuestas de hoteles guardadas son de Las Vegas, Lisboa y Denver.
- **«Costo total esperado» (ficha de la decisión) y presupuesto del viaje no coinciden, y es correcto.** El costo esperado de la ficha suma el riesgo de cambio de fecha y las millas (que restan), el hotel con su tarifa de miembro, el carro y el traslado; los puntos del hotel solo cuentan en la comparación, para ordenar los hoteles. El presupuesto es lo que se espera pagar (`viajes.presupuesto_de`): quita el riesgo de cambio y las millas (valor esperado, no desembolsos), conserva la tarifa de miembro (es lo que se paga de menos) y suma los viáticos (días del viaje por `viaticos_dia_usd`, 75 USD por defecto). Las tres cifras, línea por línea: [`docs/regla-de-negocio.md`](docs/regla-de-negocio.md), sección 8. Por eso un viaje con costo esperado de 980 USD puede tener un presupuesto de 1.153 USD. Conviene no mostrar las dos cifras juntas sin explicarlo.
- IB 5634 no sale de ninguna búsqueda guardada (Madrid a Lisboa del 13 de diciembre trae otros vuelos): por eso el viaje de la demostración lo prepara `make demo-monitoreo` y no se llega a él cotizando.
- Fuera de Docker: `.venv/bin/python -m datos.demo_monitoreo` con SQLite, y `MONITOREO_AHORA=2026-12-13T06:00 ENTORNO=local .venv/bin/uvicorn app.main:app`.

## Pruebas y calidad

```bash
make comprobar         # linter y todas las pruebas (sin claves ni base real)
make entorno           # PostgreSQL y la plataforma en Docker
make probar-postgres   # las mismas pruebas contra una base nueva en ese PostgreSQL
make demo-monitoreo    # prepara el viaje IB 5634 del 13 de diciembre (con make entorno en marcha)
make ganchos           # instala los ganchos de git del repositorio (ver docs/convenciones.md)
make geografia         # vuelve a descargar OurAirports y GeoNames y rehace datos/geografia/
```

Las pruebas de Python cubren permisos por rol (incluida una prueba de humo de cada página para cada rol), la regla del viaje, la validación de gastos, la integridad (envíos idempotentes, transacciones, revisión versionada), Telegram con un bot simulado, el buscador mundial, la fidelización, los formatos de gastos, el monitoreo del vuelo, las métricas contra un conjunto conocido, el borde de la API v1, el asistente y su asesor con un servicio simulado. La web tiene sus pruebas con Vitest (`cd web && npm test`) y la infraestructura las suyas (`cd infra && npm test`). La integración continua corre en cada envío a `main` o `dev` cuatro trabajos: Python, web, infraestructura e imágenes. Cifras medidas y detalle: [informe técnico](docs/informe-tecnico.md#5-pruebas-y-calidad).

Los archivos de `datos/geografia/` están versionados: la demostración y la carga inicial no dependen de internet. La semilla los carga y cada carga queda en `cargas_datos` (fuente, archivo, huella, filas, momento y quién). `datos/geografia/FUENTES.md` lista las huellas de lo descargado.

## Arquitectura

Hoy es **una aplicación FastAPI con una base PostgreSQL (Supabase)**, publicada en AWS: la web nueva en Next.js y la API detrás de CloudFront, con las pantallas de administración en su propio subdominio. Es una etapa de transición hacia la arquitectura objetivo: web Next.js, API Gateway y tres servicios con datos privados (Organización y acceso, Viajes y presupuestos, Gastos y evidencias). La migración va por anillos, sin reescribir; el contrato, el gateway y la web nueva ya existen. Diagrama de producción, modelo de datos, seguridad, costos y hoja de ruta: [informe técnico](docs/informe-tecnico.md). Los documentos están listados en «Documentación», al final.

### Estructura

| Ruta | Contenido |
|---|---|
| `app/main.py` | Arma la aplicación: control de acceso, errores y carga de rutas |
| `app/web.py` | Lo común a las pantallas: plantillas, contexto, páginas de error, cabeceras |
| `app/rutas/` | Una pantalla o área por archivo (se cargan solas); `v1_*.py` es la API v1 |
| `app/api_v1/` | Borde de la API v1: errores, token CSRF, dependencias de permiso |
| `app/servicios/` | Reglas de negocio por dominio: acceso, viajes, gastos, validación, precios, costo, geografía, monitoreo del vuelo, agente, KPIs, asistente, asesor, Telegram |
| `app/db.py` | Tablas, claves foráneas y acceso a datos (SQLite y PostgreSQL con el mismo código) |
| `datos/semilla.py`, `datos/migracion.py` | Datos iniciales y migración idempotente |
| `datos/geografia.py`, `datos/geografia/` | Preparación y archivos de los datos geográficos |
| `datos/asesor.py` | Mantenimiento del asesor: esquemas, verificación, sincronización y prueba en vivo |
| `datos/demo_monitoreo.py`, `datos/comprobar_supabase.py`, `datos/respaldar.py` | Demostración del monitoreo, comprobación de la base en Supabase, respaldo y ensayo de restauración |
| `scripts/ganchos/` | Ganchos de git del repositorio (`make ganchos`) |
| `datos/respaldo/`, `datos/ejemplos/` | Respuestas reales del buscador y recibos de ejemplo |
| `web/` | Web nueva en Next.js |
| `gateway/`, `docker-compose.yml` | Entorno local |
| `infra/` | Infraestructura como código en AWS (CDK) |
| `tests/` | Pruebas |

## Configuración

Copiar `.env.example` a `.env`. Cada bloque activa una parte; sin ninguno la plataforma funciona con datos guardados.

| Variable | Efecto |
|---|---|
| `SERPAPI_KEY` | Precios en vivo para cualquier ruta y fechas, autocompletado de lugares y estado del vuelo |
| `MODELO_API_URL`, `MODELO_API_KEY`, `MODELO_NOMBRE` | Lectura en vivo de recibos y agente de la cotización con modelo de lenguaje; con el formato `gemini`, además la transcripción de notas de voz y el asistente con modelo |
| `MODELO_FORMATO` | Formato de la API del modelo: `gemini` (`generateContent`) o `mensajes`; vacío se deduce de la dirección. El cliente único (`app/servicios/llm.py`) solo habla `gemini`: con `mensajes` los recibos y el agente usan su propia llamada, las notas de voz quedan pendientes de transcribir y el asistente responde sin modelo (modo determinista o asesor) |
| `ASESOR_API_URL`, `ASESOR_API_KEY`, `ASESOR_AGENTE_ID`, `ASESOR_ENTORNO_ID`, `ASESOR_CABECERAS` | Asesor del asistente: un agente alojado cuyas herramientas responde la plataforma, con tope de gasto diario (`asesor_usd_dia`) y su costo en Monitoreo (ver `docs/asistente.md`) |
| `ASESOR_AGENTE_VERSION` | Opcional: versión fija del agente del asesor; vacía, cada sesión usa la última |
| `DATABASE_URL` | PostgreSQL (Supabase) en lugar de SQLite |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Archivos originales en almacenamiento privado |
| `ADMIN_INICIAL_CORREO`, `ADMIN_INICIAL_CLAVE` | Primera cuenta de administración en una base compartida |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_NOMBRE`, `TELEGRAM_WEBHOOK_SECRETO` | Canal de Telegram |
| `PINECONE_API_KEY`, `PINECONE_HOST` | Índice del asistente en un servicio externo (si no, índice local) |
| `ORIGENES_WEB` | Orígenes desde los que la web nueva puede escribir en la API v1 |
| `MONITOREO_AHORA` | Solo con `ENTORNO=local`: fija el «ahora» (UTC, por ejemplo `2026-12-13T06:00`) del monitoreo del vuelo para demostrarlo con un vuelo futuro. Fuera de local se ignora. En `docker-compose.yml` está comentada |
| `PROVEEDOR_LUGARES` | `local+google` (por defecto) combina los datos locales con el autocompletado de Google; `local` usa solo los datos locales |
| `PREPARAR_BASE_LOCAL` | Con una base local que no es SQLite (por ejemplo PostgreSQL en Docker), `1` permite migrarla y sembrarla al arrancar; sin ese permiso la aplicación no la toca. `docker-compose.yml` ya lo pone |
| `DIRECTORIO_ARCHIVOS` | Carpeta donde se guardan los archivos originales cuando no se usa Supabase Storage (por defecto `datos/archivos`) |
| `GEOGRAFIA_DIR` | Carpeta de datos geográficos a cargar en lugar de `datos/geografia/`; las pruebas la apuntan a un subconjunto pequeño |

## Despliegue

Publicada en https://software.nataliaremolinarodriguez.com (web nueva) y https://admin.software.nataliaremolinarodriguez.com (pantallas de administración). Estado y operación: `docs/produccion.md`.

`infra/` describe el despliegue en AWS en tres pilas: `OperacionBase` (secreto y avisos), `OperacionApp` (la API y las pantallas actuales en una función con imagen de contenedor, con sus alarmas) y `OperacionWeb` (la web nueva y administración detrás de CloudFront, con el certificado y los registros de su subdominio; ADR 0002). El orden completo está en `docs/despliegue.md`: respaldo, migración por el puerto 5432, secreto, `cdk diff` revisado antes de aplicarse, despliegue de una pila a la vez, comprobaciones y vuelta atrás. El contexto `-c correo=` es obligatorio en cada orden de CDK. Respaldo y ensayo de restauración: `make respaldar`, `make verificar-respaldo` y `docs/respaldo.md`.

## Atribución de datos

- **Aeropuertos y países:** [OurAirports](https://ourairports.com/data/), de dominio público.
- **Ciudades, pueblos y regiones:** [GeoNames](https://www.geonames.org/), datos `cities1000` y `admin1CodesASCII`, bajo licencia [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Se conservan nombre, nombres alternativos en alfabeto latino, país, región, coordenadas y población. La fuente también se cita en el pie del buscador.
- **Nombres de países en español:** estándar ICU (`Intl.DisplayNames`).

## Limitaciones conocidas

- **Etapa de transición:** una sola aplicación y una sola base. Los servicios con datos privados, la mensajería y la saga de presupuesto están diseñados (`docs/adr/0001`) y no construidos.
- El dinero se guarda en coma flotante; las reglas validan y comparan con decimales exactos y la API lo entrega como cadenas de dos decimales. Pasar las columnas a decimales exactos está pendiente.
- Con pocos gastos y pocas decisiones, varios indicadores muestran el método, no conclusiones; sus metas son supuestos editables.
- El ahorro que muestra la analítica es un valor esperado bajo supuestos editables, no dinero ya ahorrado.
- **Ahorro de cotizaciones anteriores:** el ahorro se calcula contra el vuelo más barato que sirve; las cotizaciones guardadas antes de esa regla conservan el que se calculó contra el más barato de todos, aunque estuviera descartado, así que en una base ya sembrada o importada los indicadores mezclan las dos. Se corrige con un recálculo único del ahorro de esas cotizaciones.
- Los precios son una foto del momento de la consulta; cada opción muestra su origen.
- La distancia y el tiempo por carretera son una estimación (línea recta × factor ÷ velocidad), sin mapas ni rutas reales, y no hay tren, bus ni ferri.
- La web Next.js cubre cotizar, viajes, gastos con el Excel contable, el asistente y la aprobación y revisión de administración; corregir un gasto, aprobar con excepción, KPIs, monitoreo, reglas, proyectos y usuarios siguen en las pantallas actuales.
- Con el asesor, una respuesta del asistente tarda más que sin él (hasta un tope de 75 s; no hay una medición del tiempo típico); si el asesor falla o llega a su tope de gasto del día, responde el asistente sin él y lo dice.
- Varias reglas de aerolíneas vienen de fuentes secundarias o están sin verificar; la página *Reglas* lo indica.
- El canal de Telegram se probó con un bot simulado.
- Extraer precios de buscadores puede ir contra sus términos de uso; para producción corresponde una API con licencia.
- El estado del vuelo se probó solo con una respuesta de ejemplo escrita a mano según la documentación del proveedor; falta comprobarlo con una consulta real. El vuelo de regreso que se carga es el más barato que sale del aeropuerto de llegada; no se elige otro horario.
- Las personas, clientes, comercios y membresías de los datos de ejemplo son inventados.
- **Vuelos de otras fechas:** sin clave del buscador, una ruta con respuesta guardada para otras fechas usa la de fecha más temprana («guardado (otras fechas)»). La hora límite se compara con ese otro día, así que deja de descartar, y los tramos del viaje quedan con esa fecha. Se mejoraría eligiendo la fecha guardada más cercana y desplazando los horarios, o tratando esas opciones como referencia que no se puede decidir.
- **Hoteles de otras fechas:** en el mismo caso, el total del hotel es el de la estancia guardada (por ejemplo, 3 noches) aunque se pidan más, y el presupuesto queda corto. Se mejoraría calculando precio por noche × noches pedidas y marcando la cifra como estimada. La web muestra el total del hotel y sus noches, no el precio por noche.
- **Membresías solo en la semilla:** no hay pantalla para crearlas ni editarlas, y quien viaja no ve las suyas. Las que existen son inventadas y se rotulan «Dato de ejemplo»; los programas de hotel y sus valores son supuestos editables sin verificar. Se mejoraría con una pantalla de membresías para administración y una sección de solo lectura en *Mi cuenta*.
- **Vuelos nocturnos:** la hora límite se ata a la fecha de ida, así que un vuelo que llega al día siguiente se descarta aunque llegue antes de la hora pedida, con un mensaje sin fecha, y el hotel y los viáticos se cuentan desde el día de salida. Se mejoraría dando a la hora límite su propia fecha, mostrando el día en el mensaje y contando las noches desde la llegada.
- **Monitoreo del vuelo sin tarea programada:** el estado de cada tramo se consulta solo mientras alguien tiene abierto el tablero *Viajes* de administración, que lo pide cada 15 s; con el tablero cerrado no se consulta ni se avisa. Se mejoraría con una tarea programada que recorra los tramos dentro de su ventana, con los mismos topes.
- **Pie de página en local:** dice «Datos: Supabase» con cualquier PostgreSQL, también el local de Docker. Se mejoraría distinguiendo un PostgreSQL local de Supabase. (El estado del IB 5634 de la demostración ya se rotula «Estado de ejemplo».)
- **Lectura de recibos sin clave y exactitud sin medir:** sin clave del modelo solo se leen los 13 soportes de ejemplo, reconocidos por la huella del archivo, y su «lectura guardada» es el valor esperado escrito a mano (`datos/ejemplos/esperados.json`), no una salida del modelo. Cualquier otro recibo, o un ejemplo con un byte distinto, queda «sin datos» y se completa a mano. La medición campo por campo de la lectura real ya existe (`datos/medir_exactitud.py`), pero necesita la clave: [`docs/exactitud-lectura.md`](docs/exactitud-lectura.md) está pendiente de corrida.
- **Sin buzón de correo real:** no hay una dirección a la que reenviar una reserva. Un `.eml` o una confirmación `.html` se suben a mano (quedan en el canal «correo», con remitente y asunto), y «Buzón de correo (simulado)», solo para administración, lee los de la carpeta de ejemplos. Se mejoraría con una dirección de correo entrante que identifique a la persona por el remitente (diseñado en [`docs/n8n/automatizaciones.md`](docs/n8n/automatizaciones.md)).
- **Compras del proyecto sin viaje:** ya existen las categorías «Transporte terrestre» y «Compras del proyecto», pero un gasto sin viaje siempre va a revisión y solo se aprueba con excepción, también una compra del proyecto. Se mejoraría validando las compras contra las fechas del proyecto en vez de exigir un viaje.
- **Monedas:** solo hay tasas de cambio para EUR y COP. Un recibo en otra moneda (GBP, CHF, MXN…) queda en revisión y no se aprueba ni con excepción, y *Reglas* edita las tasas que existen pero no crea otras. Se mejoraría sembrando más tasas con su fecha, con un formulario para una tasa nueva y guardando en cada gasto la tasa usada.

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/informe-tecnico.md`](docs/informe-tecnico.md) | **Punto de entrada técnico:** qué es el MVP, arquitectura en producción y local, modelo de datos, seguridad, pruebas, observabilidad, costos, limitaciones y hoja de ruta |
| [`docs/regla-de-negocio.md`](docs/regla-de-negocio.md) | **Fuente única de la regla:** ciclo y estados, permisos, «nadie aprueba lo suyo», motivos de revisión, umbrales, asignación del gasto, costo esperado y presupuesto, fidelización y categorías |
| [`docs/adr/`](docs/adr/) | Decisiones de arquitectura: [0001](docs/adr/0001-arquitectura-objetivo.md) migración por anillos, [0002](docs/adr/0002-hospedaje-de-la-web.md) hospedaje de la web en AWS, [0003](docs/adr/0003-el-viaje-como-eje.md) el viaje como eje |
| [`docs/datos.md`](docs/datos.md) | Modelo relacional, identificadores, reglas que hace cumplir la base y migración |
| [`docs/arquitectura_objetivo.md`](docs/arquitectura_objetivo.md) | Dueño de cada tabla, lo que cruza entre dominios y los cortes más difíciles |
| [`docs/kpis.md`](docs/kpis.md), [`docs/analitica.md`](docs/analitica.md) | Indicadores con meta y semáforo; catálogo de métricas, vistas y señales |
| [`docs/asistente.md`](docs/asistente.md) | Qué ve cada permiso, herramientas, índice, asesor, qué sale hacia los servicios externos y límites |
| [`docs/justificaciones.md`](docs/justificaciones.md) | Justificaciones escritas y notas de voz |
| [`docs/exactitud-lectura.md`](docs/exactitud-lectura.md) | Medición de la exactitud de la lectura de soportes (pendiente de corrida) |
| [`docs/trazabilidad.md`](docs/trazabilidad.md) | Matriz de trazabilidad de la integridad de los gastos |
| [`docs/produccion.md`](docs/produccion.md) | Qué está publicado y dónde, servicios encendidos, cuentas, costos, avisos y cómo se actualiza |
| [`docs/despliegue.md`](docs/despliegue.md) | Orden completo para publicar en AWS: respaldo, migración, secreto, revisión del cambio, despliegue, comprobaciones y vuelta atrás |
| [`docs/respaldo.md`](docs/respaldo.md) | Respaldo de la base publicada, ensayo de restauración y vuelta atrás |
| [`docs/n8n/automatizaciones.md`](docs/n8n/automatizaciones.md) | Automatizaciones con n8n (propuesta diseñada, sin construir) |
| [`docs/mejoras.md`](docs/mejoras.md) | Mejoras de experiencia de uso e ingeniería y su estado |
| [`docs/convenciones.md`](docs/convenciones.md) | Cómo se escribe, se prueba y se integra el código |
| [`docs/referencias/serpapi-google-flights/uso-en-el-proyecto.md`](docs/referencias/serpapi-google-flights/uso-en-el-proyecto.md) | Qué usa la plataforma de cada API del buscador, con enlaces a la documentación oficial |
| [`web/README.md`](web/README.md) | La web nueva: comandos, modo demostración, arquitectura por capas, diseño y pruebas |
| [`contracts/api-v1.md`](contracts/api-v1.md), [`contracts/openapi-v1.json`](contracts/openapi-v1.json) | Contrato de la API v1 y su especificación OpenAPI |
| [`docs/historico/`](docs/historico/README.md) | Diseños y planes ya ejecutados, con fecha |
| [`EXPLORACION.md`](EXPLORACION.md), [`ANALISIS.md`](ANALISIS.md) | Bitácora de análisis y decisiones |
