# Informe técnico

Punto de entrada técnico de la plataforma de operación de proyectos: viajes y gastos. Fecha: 13 de noviembre de 2026.

La regla de negocio completa está en [`regla-de-negocio.md`](regla-de-negocio.md); cómo ejecutarla y recorrerla, en el [`README`](../README.md).

## 1. Qué es: un MVP

Es un **producto mínimo viable** que resuelve los dos retos de la prueba sobre un mismo eje, el viaje: **cotizar** un viaje por su costo total esperado (reto 1) y **recoger, validar y aprobar** sus gastos con revisión solo de las excepciones (reto 2). Está publicado y funciona de punta a punta, pero es una etapa de transición: una sola aplicación y una sola base, con contrato, gateway y web nueva ya separados para poder partirla después ([ADR 0001](adr/0001-arquitectura-objetivo.md)).

**Alcance**

| Entra | No entra (hoja de ruta) |
|---|---|
| Cuentas con tres permisos y cargo aparte; nadie aprueba lo suyo | Servicios separados con datos privados, mensajería y saga de presupuesto |
| Cotización con origen y destino en cualquier lugar del mundo, varios aeropuertos, traslado por carretera, fidelización de aerolíneas y hoteles, hotel recomendado y descartes | Reserva y pago de lo elegido; consulta de saldos reales de los programas |
| Decisión con su porqué, viaje con código y presupuesto, aprobación con reconfirmación del precio, monitoreo del vuelo el día del viaje | Monitoreo del vuelo con tarea programada (hoy solo con el tablero abierto) |
| Gastos por web, celular, API, correo (`.eml` y `.html` subidos) y Telegram; lectura automática, 20 motivos de revisión, aprobación sin intervención, revisión versionada, justificaciones con voz | Buzón de correo real; Telegram con el bot de producción |
| Excel contable, KPIs con semáforo, analítica, monitoreo, asistente con fuentes citadas para los tres permisos | Automatizaciones con n8n (diseñadas en [`n8n/automatizaciones.md`](n8n/automatizaciones.md)) |
| Web nueva en Next.js para cotizar, viajes, gastos, aprobación y revisión | Corregir un gasto, aprobar con excepción, KPIs, monitoreo, reglas, proyectos y usuarios en la web nueva (siguen en las pantallas de administración) |

**Qué es real, qué es simulado y qué es supuesto**

| Real | Simulado | Supuesto (editable y rotulado) |
|---|---|---|
| Cuentas, sesiones y permisos | Personas, clientes, comercios y membresías de los datos de ejemplo («Dato de ejemplo») | Valor de la milla y del punto de hotel, tarifa de miembro, viáticos por día, probabilidad de cambio de fecha |
| Precios en vivo del buscador de vuelos y hoteles (con clave), y respuestas reales guardadas sin ella | Los 13 materiales de prueba de `datos/ejemplos/`, sellados «FICTICIO · prueba técnica» | Distancia y tiempo por carretera (línea recta × factor ÷ velocidad) |
| Lectura de recibos y notas de voz con modelo de lenguaje (con clave) | El buzón de correo («Buzón de correo (simulado)» lee los `.eml` de la carpeta de ejemplos) | Cuentas contables de cada categoría, que contabilidad debe confirmar |
| Base PostgreSQL y almacenamiento de Supabase, despliegue en AWS con dominio propio | El estado del vuelo IB 5634, escrito a mano con la forma que documenta el proveedor («Estado de ejemplo») | Reglas de aerolíneas tomadas de fuentes secundarias (la página *Reglas* muestra fuente y confianza) |
| Asesor del asistente (agente alojado) e índice en Pinecone | Telegram: probado con un bot simulado; apagado en producción | Metas de los KPIs y tiempo ahorrado por viaje y por recibo (no hay medición del proceso manual) |

## 2. Arquitectura actual en producción

Publicada en `https://software.nataliaremolinarodriguez.com` (web nueva) y `https://admin.software.nataliaremolinarodriguez.com` (pantallas de administración). Operación diaria: [`produccion.md`](produccion.md); orden de publicación y vuelta atrás: [`despliegue.md`](despliegue.md).

```
                                  navegador (HTTPS)
                    ┌──────────────────┴───────────────────┐
                    ▼                                      ▼
     CloudFront  software.…                   CloudFront  admin.software.…
       │  /_next/static/*  ──► S3 privado (solo CloudFront, OAC)   │
       │  /api/v1/*  ─────────────────────────┐                    │ todo
       │  resto      ──► Lambda web           │                    │
       │                 (Next.js, arm64, 1 GB)                    │
       │                                      ▼                    ▼
       │                       Lambda API: FastAPI + pantallas Jinja
       │                       (imagen de contenedor, arm64, 2 GB, 180 s)
       │                         │         │          │          │          │
       ▼                         ▼         ▼          ▼          ▼          ▼
  certificado ACM          Supabase    SerpApi    modelo de   asesor     Pinecone
  registros Route 53       PostgreSQL  (Google    lectura     (agente    (índice del
                           17 +        Flights,   (recibos,   alojado    asistente)
                           Storage     Hotels,    voz, agente con tope
                           (agrupador  estado     de la       de gasto)
                           6543)       del vuelo) cotización)

  Telegram ── webhook ──► dirección de la función de la API (apagado en producción)
  OperacionBase: Secrets Manager (configuración) y SNS (avisos por correo)
  CloudWatch: registros con 30 días de retención y cinco alarmas
```

| Pila de CDK (`infra/`) | Qué tiene |
|---|---|
| `OperacionBase` | Secreto de configuración y tema de avisos con su suscripción por correo |
| `OperacionApp` | La función de la API con imagen de contenedor, su dirección y cinco alarmas |
| `OperacionWeb` | La función de la web, el bucket de estáticos, dos distribuciones de CloudFront, el certificado y los registros A y AAAA de los dos subdominios |

Decisiones que explican la forma: una sola aplicación con el viaje como eje ([ADR 0003](adr/0003-el-viaje-como-eje.md)), migración por anillos ([ADR 0001](adr/0001-arquitectura-objetivo.md)) y la web en AWS detrás de un solo origen con la API ([ADR 0002](adr/0002-hospedaje-de-la-web.md)).

**Código.** `app/main.py` arma la aplicación; `app/rutas/` tiene una pantalla o área por archivo y la API v1 en `v1_*.py`; `app/servicios/` tiene la regla de negocio por dominio, que las pantallas y la API llaman por igual; `app/db.py` declara las tablas y funciona igual con SQLite y PostgreSQL. La web nueva (`web/`) solo habla con la API v1 ([`web/README.md`](../web/README.md)). El contrato está en `contracts/api-v1.md` y `contracts/openapi-v1.json`.

### Arquitectura local con Docker

```
make entorno-web
  127.0.0.1:8088  gateway Caddy ──► /api/v1/*  ──► app (FastAPI, 127.0.0.1:8000) ──► PostgreSQL local (datos de demostración)
                                └─► resto      ──► web (Next.js)
```

- `make entorno` levanta PostgreSQL y la aplicación; `make entorno-web` suma la web y el gateway. Es la misma forma que en la nube: el gateway hace en local lo que CloudFront hace en producción.
- **No lee `.env`**: ninguna variable de ese entorno apunta a la base publicada. Sin claves, las cotizaciones usan respuestas reales guardadas y la lectura usa los valores esperados de los ejemplos.
- Sin Docker, `make ejecutar` corre la aplicación con SQLite.

## 3. Modelo de datos

El diagrama entidad-relación, los identificadores (`P-0007`, `V-2026-0012`), las reglas que hace cumplir la base y la migración están en [`datos.md`](datos.md). La aplicación declara **36 tablas** y siete vistas analíticas; el asistente para colaborador y gestor suma una más, `asistente_dictados` (el cupo de dictados por voz).

Atributos de las tablas que el diagrama de `datos.md` no detalla:

| Tabla | Qué guarda | Columnas principales |
|---|---|---|
| `proyectos` | Una grabación para un cliente | `nombre`, `cliente`, `ciudad`, `fecha_inicio`, `fecha_fin`, `moneda` |
| `proyecto_miembros` | Qué proyectos gestiona cada persona | `usuario_id`, `proyecto_id`, `papel` |
| `viajeros` | Perfil operativo de quien viaja | `nombre`, `base`, `rol` (el nombre del cargo, o «Viajero») |
| `membresias` | Programas de fidelización | `viajero_id` (vacío = cuenta de la empresa), `programa`, `entidad`, `estatus`, `ejemplo` (dato inventado) |
| `solicitudes` | La cotización | Origen y destino (código, lugar elegido y aeropuertos marcados), `ida`, `regreso`, `llegar_antes`, equipo (`baterias_n`, `baterias_wh`, `maleta`), `prob_cambio`, `carro_dia`, y para la analítica `precio_min_buscador`, `costo_mas_barato`, `costo_mejor`, `ahorro_potencial` |
| `opciones` | Cada vuelo u hotel ofrecido | `solicitud_id`, `tipo`, `titulo`, `precio`, `moneda`, `datos` y `tarifas` (JSON), `origen_dato`, `capturado` |
| `decisiones` | La elección y su porqué | `vuelo_id`, `hotel_id`, `tarifa`, `desglose` (JSON con líneas, avisos, regreso y hotel evaluado), `total`, `motivo`, `razones`, `recomendado_id`, `siguio_recomendacion`, `posicion_elegida` |
| `elecciones` | Una fila por opción mostrada al decidir: conjunto etiquetado para un modelo de decisión futuro | `decision_id`, `opcion_id`, `posicion`, `elegida`, `recomendada`, `descartada`, `precio`, `costo_esperado`, `rasgos` |
| `reglas` | Reglas de aerolíneas y hoteles, supuestos, metas de KPIs y cuentas contables | `ambito`, `entidad`, `tarifa`, `clave`, `valor`, `nota`, `fuente`, `confianza`, `verificado` |
| `busquedas` | Respuestas del buscador, compartidas entre instancias | `clave`, `cuerpo`, `creado` |
| `envios_cotizacion` | Idempotencia de las cotizaciones de la API | `usuario_id` + `clave` (únicos), `huella`, `estado`, `solicitud_id`, `expira` |
| `asistente_consultas` | Rastro del asistente | `usuario_id`, `pregunta`, `herramientas`, `fuentes`, `modo`, `duracion_ms`, `momento` |
| `fichas_rag` | Índice local del asistente y copia de lo enviado a Pinecone | `ficha_id`, `tipo`, `entidad`, `entidad_id`, `persona_id`, `viaje_id`, `proyecto_id`, `fecha`, `canal`, `texto`, `normalizado` |
| `indice_rag` | Qué versión de cada ficha tiene cada destino | `destino` (`local` o `pinecone`), `entidad`, `entidad_id`, `ficha_id`, `huella`, `indexado_en` |
| `llamadas_modelo` | Cada llamada al modelo y cada sesión del asesor | `uso`, `modelo`, tokens de entrada y salida, latencia, estado, error, `costo_usd` |

**Estados del gasto:** `procesando`, `revision`, `aprobado_auto`, `aprobado` y `rechazado` ([`regla-de-negocio.md`](regla-de-negocio.md), sección 1). No hay restricción CHECK sobre `gastos.estado`; sí sobre `viajes.estado` y `usuarios.rol`.

**Vistas analíticas** (`datos/semilla.py`, `VISTAS`): `v_h_gasto`, `v_h_busqueda`, `v_h_decision`, `v_h_lectura`, `v_h_evento`, `v_h_viaje` y `v_h_consulta`. Unen cada hecho con sus dimensiones; no copian datos. Uso y conexión de herramientas externas de análisis: [`analitica.md`](analitica.md).

**Dueño de cada tabla** en la arquitectura objetivo: [`arquitectura_objetivo.md`](arquitectura_objetivo.md).

## 4. Seguridad

| Tema | Cómo está |
|---|---|
| Contraseñas | Argon2id; mínimo 10 caracteres. Con un correo que no existe se hace el mismo trabajo, y el mensaje es el mismo para correo o contraseña equivocados (`acceso.autenticar`) |
| Bloqueo por intentos | Desde el quinto fallo, espera progresiva de 1, 2, 4… minutos, hasta 30 (`acceso.MAX_FALLOS`) |
| Sesiones | Token aleatorio en una cookie `HttpOnly`, `Secure` y `SameSite=Lax`; en la base solo se guarda su huella, así que se revoca al salir o al desactivar la cuenta. Vida de 12 horas y 2 de inactividad |
| Cookies `__Host-` | Fuera de local la cookie es `__Host-sesion`: atada al nombre exacto, sin dominio, solo HTTPS. Por eso la sesión de `software.` no vale en `admin.software.` (ADR 0002) |
| CSRF y origen | Pantallas: cada escritura comprueba `Sec-Fetch-Site` o, sin él, que `Origin` coincida con `Host` (`acceso.mismo_origen`). API v1: cookie de sesión, `X-CSRF-Token` (HMAC del token de la sesión, sin guardar nada) y un origen permitido (`ORIGENES_WEB`) en cada escritura |
| Permisos por registro | Cada consulta lleva el alcance de la sesión (`acceso.alcance`, `acceso.puede_ver`); el rol nunca sale del cuerpo de la petición. Lo que no se ve se responde como si no existiera. `/admin`, `/api` y `/docs` exigen administración |
| Nadie aprueba lo suyo | En el servicio, para la web y la API; cada intento queda en la bitácora ([`regla-de-negocio.md`](regla-de-negocio.md), sección 3) |
| Seguridad por filas | Todas las tablas de PostgreSQL tienen RLS activa y ningún permiso para los roles públicos de Supabase; la aplicación entra con su propia credencial. `python -m datos.comprobar_supabase` lo verifica en solo lectura |
| Archivos | El tipo se decide por el contenido, no por lo que declara quien sube; máximo 4,5 MB y 6 archivos por carga. Un `.html` se reduce a texto sin scripts, estilos ni enlaces y solo se descarga. Los originales van a un bucket privado |
| Secretos | Solo en Secrets Manager (producción) y en archivos `.env*` fuera de git. `infra/poblar_secreto.py` fusiona y nunca muestra valores. Los ganchos de git rechazan secretos en las líneas añadidas ([`convenciones.md`](convenciones.md)) |
| Fallo cerrado | Fuera de local, la aplicación no arranca sin base ni almacenamiento (`app/config.py`). La base publicada nunca se migra al arrancar |
| Cabeceras | `nosniff`, `X-Frame-Options SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`, HSTS fuera de local y `Cache-Control: no-store` en las respuestas JSON. En la web nueva, CloudFront suma su política de cabeceras de seguridad; `/api/v1/*` y administración llevan las de la aplicación. TLS 1.2 como mínimo |
| Contenido de terceros | Lo que escriben las personas (notas, justificaciones, recibos) es dato para el asistente, nunca instrucción; ninguna herramienta del asistente escribe ([`asistente.md`](asistente.md)) |

**Límites y topes** (todos editables en *Reglas y supuestos* salvo los de archivos y sesión):

| Qué | Tope |
|---|---|
| Cotizaciones nuevas por persona y día | 20 (`tope_cotizaciones_persona_dia`; 429 en la API) |
| Decisiones por persona y día que consultan en vivo | 10 (`decisiones_en_vivo_dia`) |
| Autocompletado de lugares | 60 al mes y 15 por persona y día |
| Estado del vuelo | 6 consultas por tramo, 12 por viaje y sentido, 30 en vivo por día; se suspende si al plan le quedan menos de 25 |
| Preguntas y dictados al asistente | 40 y 40 por persona y día |
| Gasto del asesor | 2 USD por día para toda la empresa (`asesor_usd_dia`), de los que colaboradores y gestores pueden usar 1 (`asesor_usd_dia_colaboradores`) |
| Una consulta idéntica al buscador o un archivo idéntico ya leído | No se vuelve a pagar |

**Qué datos salen a terceros**

| Servicio | Qué recibe |
|---|---|
| Supabase | Toda la base y los archivos originales (es el almacenamiento de la plataforma) |
| SerpApi | Códigos de aeropuerto, fechas y opciones de la búsqueda; el texto del campo de lugar para el autocompletado; el número de vuelo para su estado. Ningún dato de la persona |
| Proveedor del modelo de lectura | La imagen, el PDF o el texto del recibo; las notas de voz para transcribir; la comparación que explica el agente de la cotización; la pregunta y los resultados de herramientas del asistente cuando responde con modelo |
| Asesor (agente alojado) | La pregunta, la fecha, quién pregunta (código y permiso) y los resultados de las herramientas que pida, solo dentro del alcance de esa persona. Cada sesión se borra del servicio al terminar |
| Pinecone | El texto de las fichas y sus metadatos (códigos, comercios, importes, estados, alertas, textos libres). Sin nombres, correos, contraseñas ni archivos |
| Telegram (apagado en producción) | Los avisos al viajero: códigos, rutas, importes y motivos |

**Pendiente de seguridad.** La política de contenido (CSP) de las pantallas de administración permite `'unsafe-inline'` en scripts y estilos (`app/web.py`, `CABECERAS_SEGURAS`): las plantillas Jinja tienen scripts en línea. Se quita moviendo esos scripts a archivos propios o usando un *nonce* por respuesta. Otros pendientes: desplegar con un usuario propio con MFA (hoy con la cuenta raíz), topes propios para el agente de la cotización y la lectura de recibos, y que `mismo_origen` acepte el origen declarado de `admin.` para navegadores que no mandan `Sec-Fetch-Site` (ADR 0002).

## 5. Pruebas y calidad

Cifras medidas el 13 de noviembre de 2026 sobre el commit `7d645f6` más esta documentación:

| Conjunto | Orden | Resultado |
|---|---|---|
| Python (pytest, SQLite temporal y servicios simulados) | `.venv/bin/python -m pytest -q` | 703 pruebas en 42 archivos: **700 pasan, 3 se omiten** (dos necesitan el PostgreSQL de Docker en el puerto 5433 y una, Docker para el ensayo de vuelta atrás) |
| Linter de Python | `.venv/bin/python -m ruff check .` | Sin hallazgos |
| Web (Vitest) | `cd web && npx vitest run` | **262 pruebas en 33 archivos, todas pasan** |
| Infraestructura (pruebas de las pilas de CDK) | `cd infra && npm test` | **37 pruebas en 12 grupos, todas pasan** |

Qué cubren las de Python: permisos por rol (con una prueba de humo de cada página para cada rol), la regla del viaje, la validación de gastos, la integridad (envíos idempotentes, transacciones, revisión versionada), el buscador mundial, el monitoreo del vuelo, las métricas contra un conjunto conocido, el borde de la API v1, el asistente y su asesor, Telegram con un bot simulado y el comportamiento detrás de CloudFront. `make probar-postgres` corre las mismas contra un PostgreSQL nuevo en Docker; los cambios que tocan la base se prueban además en un proyecto de Supabase de pruebas ([`convenciones.md`](convenciones.md)).

**Integración continua** (`.github/workflows/pruebas.yml`), en cada envío a `main` o `dev` y en cada solicitud de cambio, con cuatro trabajos y sin claves:

| Trabajo | Qué hace |
|---|---|
| `calidad` | `ruff check .` y `pytest -q` con Python 3.12 |
| `web` | Tipos, linter, Vitest y compilación de Next.js |
| `infra` | Tipos y pruebas de las pilas; síntesis con dominio y sin él; comprueba que la zona DNS se importa y nunca se crea |
| `imagenes` | Construye las imágenes de la API y de la web y comprueba que la web arranca y responde en `/entrar` |

**Exactitud de la lectura.** `datos/medir_exactitud.py` lee los 13 soportes de ejemplo con el lector real y compara campo por campo con `datos/ejemplos/esperados.json`. Necesita la clave del modelo, así que [`exactitud-lectura.md`](exactitud-lectura.md) está **pendiente de corrida**: hoy no hay una cifra medida de exactitud de la lectura.

**Modelo de precio esperado.** Validado dejando búsquedas completas fuera del entrenamiento: error medio de 115,96 USD (36,3 %) frente a 142,65 USD (48,7 %) de la mediana de la ruta. Se usa como señal («caro para su ruta»), no entra en el costo total ([`EXPLORACION.md`](../EXPLORACION.md), 9.1).

## 6. Observabilidad

| Capa | Qué hay |
|---|---|
| Alarmas (`OperacionApp`) | Fallos de la función, peticiones rechazadas por concurrencia, lentitud (p95 de 20 s dos periodos seguidos), líneas `ERROR peticion=` en el registro y respuestas 5xx. Avisan por correo al tema de `OperacionBase` |
| Registros | CloudWatch con 30 días de retención. Cada petición lleva un identificador (`X-Peticion`); un error queda en la tabla `errores` y en el registro con ese identificador, y la persona lo ve en pantalla para reportarlo |
| Bitácora | `eventos`: cada paso del viaje y del gasto, con quién, cuándo, la fuente y la duración. Incluye los intentos de aprobar lo propio y cada regla editada |
| Uso de servicios pagos | `consultas_buscador` (cada consulta, su origen y quién), `llamadas_modelo` (tokens, latencia y costo, también del asesor), `cargas_datos` (cada carga de datos de referencia) |
| Métricas | Un catálogo único (`app/servicios/metricas.py`) que leen las pantallas, las descargas y la API ([`analitica.md`](analitica.md)) |
| KPIs | 21 indicadores (11 del reto 1, 10 del reto 2) con meta, umbral y semáforo; «sin datos» cuando no hay de qué contar ([`kpis.md`](kpis.md)) |
| Monitoreo | `/admin/monitoreo`: viajes, gastos, búsquedas, modelo de lenguaje (con el costo del asesor), auditoría, errores y calidad de los datos |
| Costo de la cuenta | Presupuesto de AWS de 5 USD al mes con avisos al 50, 80 y 100 % del gasto y del pronóstico |

## 7. Costos por servicio

| Servicio | Plan o tarifa | Costo esperado con el uso actual | Control |
|---|---|---|---|
| AWS (Lambda, CloudFront, S3, Secrets Manager, SNS, CloudWatch, Route 53) | Por uso | Unos 1,5 USD al mes fijos (zona DNS, secreto y alarmas) más el uso, que con el tráfico actual son unos pocos dólares. El dominio, unos 15 USD al año. Con `-c caliente=1` se suma una instancia siempre lista (sin cifra medida) | Presupuesto `cuenta-mensual` de 5 USD con avisos ([`produccion.md`](produccion.md), [ADR 0002](adr/0002-hospedaje-de-la-web.md)) |
| Supabase | Plan gratuito | 0 USD. Sin respaldos automáticos: el Pro, con respaldo diario, cuesta 25 USD al mes | Respaldo manual y ensayo de restauración ([`respaldo.md`](respaldo.md)) |
| SerpApi | 250 búsquedas al mes | Cotizar gasta 2 búsquedas (vuelos y hoteles); decidir, hasta 2; aprobar, 1; el estado del vuelo, 1 por consulta en vivo | Topes por persona, por viaje y por día; reutilización de lo guardado (KPI `tasa_reutilizacion`, `cupo_usado`) |
| Modelo de lectura | Por tokens | Precio de referencia de 0,5 USD por millón de tokens de entrada y 3 de salida (supuestos editables `modelo_usd_por_millon_*`, en `datos/semilla.py`). Meta: 0,01 USD o menos por recibo | Una llamada por recibo; un archivo idéntico no se vuelve a leer; KPI `costo_por_recibo` |
| Asesor del asistente | Por sesión, a precio de lista del servicio | Hasta 2 USD al día para toda la empresa (1 de ellos para colaboradores y gestores) | `asesor_usd_dia`; el costo real de cada sesión queda en `llamadas_modelo` y en Monitoreo |
| Pinecone | Índice `asistente-fichas` | Sin cifra registrada en el repositorio; el índice solo recibe lo nuevo o cambiado | El índice local queda siempre como respaldo |
| Telegram | Gratis | 0 USD (apagado en producción) | — |

## 8. Decisiones

| Decisión | Dónde |
|---|---|
| Migrar por anillos, sin reescribir | [ADR 0001](adr/0001-arquitectura-objetivo.md) |
| Web en AWS detrás de un solo origen con la API, con dominio en Route 53 y 60 s de espera en CloudFront | [ADR 0002](adr/0002-hospedaje-de-la-web.md) |
| El viaje como eje de los dos retos | [ADR 0003](adr/0003-el-viaje-como-eje.md) |
| SerpApi como fuente de precios (Apify de respaldo, Amadeus cerrado), Supabase como base, XGBoost solo para el precio esperado | [`EXPLORACION.md`](../EXPLORACION.md), secciones 1, 7.4 y 9 |
| El cargo separado del permiso; todos viajan; «nadie aprueba lo suyo» | [`regla-de-negocio.md`](regla-de-negocio.md), secciones 2 y 3, y el [diseño del buscador mundial y los cargos](historico/diseno/2026-11-12-buscador-mundial-y-cargos.md) del 12 de noviembre, hoy en el [histórico](historico/README.md) |

## 9. Limitaciones

**Reto 1: cotizar**

- Los precios son una foto del momento de la consulta; cada opción muestra su origen.
- La distancia y el tiempo por carretera son una estimación, sin mapas ni rutas reales, y no hay tren, bus ni ferri.
- Sin clave del buscador, una ruta guardada para otras fechas usa la de fecha más temprana: la hora límite se compara con ese otro día y el total del hotel es el de la estancia guardada aunque se pidan más noches.
- Un vuelo que llega al día siguiente se descarta aunque llegue antes de la hora pedida, porque la hora límite se ata a la fecha de ida.
- Las membresías solo existen en la semilla: no hay pantalla para crearlas ni editarlas.
- La web muestra el total del hotel y sus noches, no el precio por noche.
- Varias reglas de aerolíneas y los programas de hotel vienen de fuentes secundarias o son supuestos sin verificar.
- El estado del vuelo solo se probó con una respuesta de ejemplo, y solo se consulta con el tablero de administración abierto.
- Extraer precios de buscadores puede ir contra sus términos de uso; en producción corresponde una API con licencia.

**Reto 2: gastos**

- La exactitud de la lectura con modelo no está medida todavía (pendiente de corrida con clave).
- Sin clave del modelo solo se leen los 13 soportes de ejemplo, con su valor esperado escrito a mano.
- No hay buzón de correo real: un `.eml` o `.html` se sube a mano.
- Un gasto sin viaje siempre va a revisión, también una compra del proyecto.
- Solo hay tasas de cambio para EUR y COP; otra moneda no se aprueba ni con excepción.
- Telegram se probó con un bot simulado y está apagado en producción.

**Plataforma**

- Una sola aplicación y una sola base: los servicios con datos privados, la mensajería y la saga de presupuesto están diseñados y no construidos.
- El dinero se guarda en coma flotante; las reglas validan con decimales exactos.
- Con pocos datos, varios indicadores muestran el método y no conclusiones; el ahorro es un valor esperado.
- El pie de página dice «Datos: Supabase» con cualquier PostgreSQL, también el local.
- La web nueva no cubre todavía corregir un gasto, aprobar con excepción, KPIs, monitoreo, reglas, proyectos y usuarios.
- La CSP de las pantallas de administración permite scripts en línea.

## 10. Hoja de ruta

En orden de prioridad:

1. **Operar con garantías** (antes de crecer el uso): desplegar con un usuario con MFA o desde la integración continua con aprobación; respaldo nocturno automático de la base; topes para el agente de la cotización y la lectura de recibos; correr la medición de exactitud con clave; Telegram con el bot de producción; regla de limpieza de imágenes en ECR; un ambiente previo a producción ([`produccion.md`](produccion.md)).
2. **Cerrar huecos del MVP**: tarea programada para el monitoreo del vuelo; pantalla de membresías; más tasas de cambio con fecha; compras del proyecto validadas contra las fechas del proyecto sin exigir viaje; hora límite con su propia fecha; precio por noche de los hoteles guardados; recorridos de extremo a extremo de la web en un navegador (Playwright).
3. **Automatizaciones con n8n** ([`n8n/automatizaciones.md`](n8n/automatizaciones.md)): clave de servicio y avisos firmados con soportes a Drive, resultado al interesado y contabilidad; decisión desde el correo; buzón de gastos real, pendientes y vuelos; solicitud de viaje por correo.
4. **Mejoras de uso e ingeniería pendientes** ([`mejoras.md`](mejoras.md)): textos de las alertas para quien reporta, accesibilidad pendiente, consultas del monitoreo, cotización en paralelo, lógica de las rutas a los servicios, tope al cambio de contraseña, CSP sin scripts en línea.
5. **Arquitectura objetivo por anillos** ([ADR 0001](adr/0001-arquitectura-objetivo.md)): terminar la web nueva (anillo 1) y retirar las pantallas de administración; decimales exactos; esquemas privados por dominio (anillo 2); Gastos como primer servicio con outbox y saga de presupuesto (anillo 3); una función por servicio (anillo 4).
6. **Aprendizaje**: con elecciones suficientes, un modelo de decisión entrenado sobre `elecciones`; recolectar precios en varios días para separar anticipación y día de la semana en el modelo de precio esperado.
