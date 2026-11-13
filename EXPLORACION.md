# Exploración de ideas y bitácora de decisiones

Documento vivo. Continúa el [ANALISIS.md](ANALISIS.md): aquí se registran las ideas que se exploran, las que se descartan y por qué, y las decisiones que se van cerrando. Inicio: 11 de noviembre de 2026.

> **Bitácora con fecha.** Cada sección refleja el momento en que se escribió; las notas «Estado al 13 de noviembre» dicen qué cambió después. El estado vigente está en el [informe técnico](docs/informe-tecnico.md) y la regla de negocio en [`docs/regla-de-negocio.md`](docs/regla-de-negocio.md).

## 1. Decisiones cerradas

| Fecha | Decisión | Motivo |
|---|---|---|
| 11 nov | Entrega: viernes 13 de noviembre de 2026, en la mañana | Plazo fijado por la empresa |
| 11 nov | Tecnología: Python + FastAPI + SQLite, interfaz web servida por el mismo backend | Un solo comando para ejecutar; fácil para quien evalúa |
| 11 nov | Extracción con un modelo de lenguaje multimodal por API; la clave va en `.env` fuera del repositorio | Ya hay clave disponible |
| 11 nov | La documentación es entregable de primer orden y se escribe para que sirva de contexto a quien lea | Se pidió en la entrevista: alimenta el sistema central de la empresa (ver 2.1) |
| 11 nov | Escenarios de prueba en Estados Unidos y Europa, con pilotos de dron como viajeros | Es la operación real de la empresa (ver 2.1) |
| 11 nov | Reto 1: se entrega una demo que funciona, no solo una propuesta | Decisión propia |
| 11 nov | Reto 1: precios reales obtenidos por extracción (Apify, ver 4.5), con resultados guardados de respaldo y cada dato marcado como en vivo, guardado o simulado | Ataca "reducir el tiempo de búsqueda"; el respaldo permite ejecutar la demo sin cuenta y cubre fallos el día de la presentación |
| 11 nov | Reto 1: SerpApi como fuente principal de precios; Apify queda de respaldo; Firecrawl para el catálogo de reglas (ver 7.4) | La prueba real mostró que entrega tarifas, equipaje y condiciones de cambio, que el extractor de Apify no trae |
| 11 nov | Una sola aplicación web con los dos retos; datos en Postgres de Supabase (SQLite cuando no hay conexión) y despliegue previsto en AWS. Reemplaza la decisión de usar solo SQLite | Decisión propia: producto visible, con monitoreo del recorrido de los datos |
| 11 nov | Antes de construir se explora a fondo y todo queda documentado dentro del repositorio | Parte de lo evaluado es el proceso y el razonamiento |

## 2. Tiempo disponible

Quedan cerca de día y medio de trabajo. Reparto tentativo:

| Bloque | Qué |
|---|---|
| Miércoles 11, tarde | Cerrar la exploración y las decisiones de la sección 5 |
| Miércoles 11, noche a jueves 12, mediodía | Reto 2 funcional de punta a punta, con documentos de prueba |
| Jueves 12, tarde | Reto 1 y punto de unión (si alcanza) |
| Jueves 12, noche | Medición de exactitud, limitaciones, README, repaso de la demo |
| Viernes 13, mañana | Margen y entrega |

Consecuencia: la exploración tiene que cerrarse hoy, y cada idea debe pasar el filtro "¿se puede construir y demostrar en pocas horas?".

## 2.1 Contexto de la empresa

Fuente: explicación verbal en la entrevista (audio de unos 8 minutos, 11 de noviembre). Marcas: **[Entrevista]** es lo dicho con claridad; **[Por confirmar]** es lo que no se entendió bien en la grabación o es deducción propia.

**Qué hace la empresa**
- Servicios de marketing para el sector inmobiliario (*real estate*), sobre todo imagen y video aéreo. [Entrevista]
- Equipo propio de pilotos de dron y equipo de edición. [Entrevista]
- El equipo de edición está en Colombia; la operación es principalmente en Estados Unidos y Europa; el equipo administrativo está repartido. [Entrevista]
- Unos tres años de crecimiento rápido y orgánico, sin estructura organizacional ni procesos formales; todavía en construcción. [Entrevista]

**El área de desarrollo** (creada hace unos cinco meses) [Entrevista]
1. Célula de automatización del vuelo de los drones y de la edición de imágenes, para aumentar la capacidad instalada.
2. Célula de productos y servicios web para clientes, con foco en experiencia de usuario.
3. Célula del sistema interno central, al que llaman "sistema operativo": debe reunir la información hoy dispersa en Google Drive, hojas de cálculo y otras herramientas, y evitar que se pierda al pasar entre Finanzas, Ventas y Operaciones. [Entrevista]

**Por qué existe la vacante** [Entrevista]
- Los desarrollos del área son de mediano y largo plazo, pero la operación sigue siendo manual y los pilotos y editores no tienen tiempo para levantar información.
- Se abren varias vacantes para personas que entren a la operación (en este caso, Gestión de Proyectos y Finanzas), conozcan sus grupos de trabajo, necesidades y dolores, y entreguen **soluciones rápidas, en semanas**.
- **Todo lo que se construya debe quedar documentado**, con su resultado: esa documentación semanal se usa como contexto para construir el sistema central.
- Ejemplo dado en la entrevista: Finanzas tiene problemas para registrar los gastos por proyecto. Es el Reto 2.

**Qué valora quien evalúa** (segundo y tercer audio, 11 de noviembre) [Entrevista]
- **Cuestionar el proceso, no solo automatizarlo**: "si Gestión de Proyectos dice que para llegar al resultado pasa por A, B, C y D, y tú ves que B y C se pueden obviar y llegar de A a D con una herramienta, bienvenido sea". Se espera proactividad.
- **Pequeñas ganancias**: herramientas pequeñas que hagan el día a día más fácil mientras llega el sistema operativo. No se pide una plataforma.
- **Aterrizar necesidades a un alcance tecnológico**: la persona hace parte del equipo operativo, entiende sus necesidades y las traduce.
- **Dejar registro**: "sin contexto no existen las mejores soluciones"; cada pequeña ganancia deja documentación que alimenta el trabajo del área de desarrollo.
- **La IA es bienvenida y ya se usa en la operación**: el ejemplo que dio fue un piloto que, en un proyecto de 600 imágenes en Las Vegas con entrega en dos a tres semanas, le enseñó a una herramienta de IA a hacer el pegado de fotogramas (*stitching*) y multiplicó el avance en una noche. Después el área de desarrollo lo convirtió en herramienta formal.
- **La prueba es un caso que les ocurre hoy**, de interpretación libre, y después se **socializa**: habrá que presentarla y explicarla.

Lo que esto añade al plan:
- Los documentos deben mostrar el proceso **antes y después** (pasos que se eliminan, no solo pasos que se aceleran), con una estimación de tiempo ahorrado.
- Hace falta un guion de demostración para la socialización.
- El ejemplo de Las Vegas confirma que un proyecto es una grabación en una ciudad para un cliente, con plazo de semanas.

**Qué cambia en el planteamiento**

| Tema | Antes (ANALISIS.md) | Ahora |
|---|---|---|
| Geografía y monedas | Viajes nacionales o regionales; COP y USD | Viajes en Estados Unidos y Europa; USD y EUR como monedas de gasto, COP para el equipo en Colombia [Por confirmar: moneda de reporte] |
| Quién viaja | Miembros del equipo en general | Pilotos de dron que van a grabar propiedades |
| Equipaje | Supuesto de equipo de trabajo | Drones y baterías de litio: las baterías van en cabina y tienen límites por aerolínea, lo que pesa en la elección de tarifa [Por confirmar con reglas oficiales] |
| Gastos típicos | Genéricos | Vuelo, hotel, alquiler de carro, combustible, peajes y parqueo, comidas; posibles permisos o tasas de vuelo [Por confirmar] |
| Qué es un "proyecto" | Sin definir | Una grabación en una ciudad para un cliente, con plazo de semanas (ejemplo: Las Vegas, 600 imágenes) |
| Programas de fidelización | LATAM Pass, LifeMiles, Marriott | Faltan los de aerolíneas, hoteles y alquiler de carros de Estados Unidos y Europa, incluidos los programas para empresas pequeñas; hay que verificarlos en fuentes oficiales |
| Documentación | Entregable secundario | Entregable de primer orden: debe servir como contexto para construir el sistema central |
| Destino de la solución | Herramienta independiente | Herramienta puente: útil ya, y con datos y reglas fáciles de migrar al sistema central |

**Consecuencias de diseño**
- Cada solución lleva una ficha estable y estructurada (problema, usuarios, flujo, modelo de datos, reglas de negocio, supuestos, resultado medido), pensada para que sirva de contexto a quien la lea.
- El modelo de datos y las reglas de negocio se documentan aparte del código, y los datos se pueden exportar completos.
- Los documentos de prueba deben parecerse a los de la operación real: recibos en inglés y en otros idiomas europeos, importes en USD y EUR, formatos de fecha distintos, impuestos como *sales tax* e IVA, propinas.
- Se prefiere lo pequeño y terminado sobre lo amplio: la empresa busca soluciones de semanas.

## 3. Lectura de fondo: qué está pidiendo realmente cada reto

### Reto 2 (el obligatorio y funcional)

El enunciado repite tres verbos: **recopilar, organizar, seguir**. El análisis previo cubre bien organizar y seguir; la idea menos trabajada es **recopilar**, que es donde nace el problema: los soportes llegan dispersos y tarde.

Frases del enunciado que marcan el criterio:
- "se recibe en diferentes formatos y a través de diferentes canales": la demo debe mostrar al menos dos canales y tres formatos, no solo un botón de subir archivo.
- "a medida que aumenta el número de proyectos y transacciones": la solución debe escalar por volumen, es decir, que Finanzas revise excepciones y no cada gasto.
- "mejorar la accesibilidad": el project manager consulta sin pedirle nada a Finanzas.

### Reto 1 (demo o propuesta)

El enunciado pide "ayudar a tomar mejores decisiones" y "reducir el tiempo de investigar y comparar". Son dos cosas distintas: una herramienta que decide bien pero obliga a digitar todas las opciones no ahorra tiempo. La fuente de las opciones es el punto débil del enfoque recomendado y merece una idea propia (ver 4.2).

"Se espera que identifique los factores relevantes, las oportunidades y los desafíos": el hallazgo de que las millas pertenecen al viajero y no a la empresa es exactamente ese tipo de aporte, y conviene que sea visible en la demo, no solo en un documento.

## 4. Ideas en exploración

Estado: **propuesta** (por discutir), **aceptada**, **descartada**.

### 4.1 Reto 2

| # | Idea | Valor | Costo | Estado |
|---|---|---|---|---|
| 2.1 | **Aprobación automática por confianza**: los gastos con todos los campos claros y validaciones en verde entran directo; solo las excepciones van a la bandeja. Indicador visible: "11 de 14 procesados sin intervención" | Responde a "reducir trabajo manual" con un número | Bajo | Propuesta |
| 2.2 | **Página de captura para celular**: un enlace donde el viajero toma la foto del recibo y elige el proyecto; sin instalar nada | Ataca "recopilar"; se demuestra en vivo con un teléfono | Bajo (es la misma carga, con otra vista) | Propuesta |
| 2.3 | **Buzón simulado**: carpeta de `.eml` que la aplicación "lee" con un botón | Segundo canal sin credenciales | Bajo | Propuesta |
| 2.4 | **Soportes faltantes**: si hay un viaje planeado y no llegó la factura del hotel o el vuelo, el tablero lo avisa | Finanzas deja de perseguir soportes a ciegas | Medio (depende del punto de unión) | Propuesta |
| 2.5 | **Preguntas en lenguaje natural** sobre los gastos ("¿cuánto llevamos en comidas en el proyecto X?") | Vistoso | Medio; riesgo de respuestas erradas | Propuesta, prioridad baja |
| 2.6 | **Medición de exactitud** contra valores esperados de cada documento de prueba, publicada en el repositorio | Responde a "cómo validó" | Bajo | Propuesta |
| 2.7 | Canal real de mensajería (bot de Telegram o WhatsApp) | Muy cercano al uso real | Alto para el plazo; depende de terceros | Propuesta de descarte: queda como mejora |

### 4.2 Reto 1

| # | Idea | Valor | Costo | Estado |
|---|---|---|---|---|
| 1.1 | **Pegar o capturar en vez de digitar**: el usuario pega el texto o una captura de pantalla de los resultados de un buscador y el mismo motor de extracción del Reto 2 lo convierte en opciones comparables | Resuelve la fuente de opciones sin API ni extracción automática de sitios; reutiliza el motor | Medio | Propuesta |
| 1.2 | **Catálogo de reglas de fidelización editable**, cada regla con fuente y fecha de verificación | Las reglas cambian; Finanzas puede mantenerlas sin programar | Bajo | Propuesta |
| 1.3 | **Costo total con desglose** y aviso cuando lo más barato no es lo mejor (equipaje, cambio de fecha, canal que no acumula) | Núcleo del reto | Medio | Propuesta |
| 1.4 | **Dinero frente a puntos** con valor de referencia configurable y alertas de vencimiento | Aprovecha los programas | Bajo una vez existe 1.3 | Propuesta |
| 1.5 | **Ficha de decisión**: resumen de una página con la opción elegida y el porqué, guardada contra el proyecto | Deja registro; es el presupuesto que luego se compara con el gasto real | Bajo | Propuesta |
| 1.6 | Precios reales por API de vuelos y hoteles | Realismo | Medio con extractores ya hechos (ver 4.5); riesgo el día de la evaluación, cubierto con respaldo guardado | **Aceptada** (11 nov), vía Apify |

### 4.4 Documentación y presentación

| # | Idea | Valor | Costo | Estado |
|---|---|---|---|---|
| D.1 | **Mapa antes y después** de cada proceso: pasos actuales, pasos que desaparecen, pasos que quedan, tiempo estimado por gasto o por viaje | Responde directo a "de A a D sin pasar por B y C" | Bajo | Propuesta |
| D.2 | **Ficha de contexto por solución**, con estructura fija (problema, usuarios, flujo, modelo de datos, reglas de negocio, supuestos, resultado medido) | Es el registro que la empresa quiere usar como contexto para su sistema central | Bajo | Propuesta |
| D.3 | **Guion de demostración** de cinco a siete minutos, con un caso de principio a fin (un viaje a una grabación y sus gastos) | La prueba se socializa después de entregarla | Bajo | Propuesta |

### 4.3 Puentes entre los dos retos

| # | Idea | Valor | Costo | Estado |
|---|---|---|---|---|
| P.1 | **Un solo motor "documento → datos"** para recibos (Reto 2) y para opciones de viaje pegadas (Reto 1) | Justifica técnicamente el flujo integrado | Bajo | Propuesta |
| P.2 | **Previsto frente a real** por proyecto: la ficha de decisión es el presupuesto; los gastos que llegan se emparejan por viajero, fechas y ciudad | La historia más útil para Finanzas | Medio | Propuesta |
| P.3 | **Fidelización perdida detectada en los gastos**: al procesar una factura de hotel reservada por agencia, o un vuelo sin número de viajero frecuente, se avisa "esta estadía no acumuló puntos" o "estas millas aún se pueden reclamar" | Los datos del Reto 2 revelan ineficiencias del Reto 1; es una mejora que no existe en el proceso manual | Bajo a medio | Propuesta |

### 4.5 Fuentes de datos reales para el Reto 1: catálogo de Apify

Consulta del catálogo público de Apify el 11 de noviembre de 2026 (sin cuenta, sin ejecutar nada). Apify ofrece extractores ya hechos ("Actors") que se pagan por uso; el plan gratuito incluye 5 USD de crédito al mes.

| Necesidad | Candidato más usado | Precio publicado | Qué entrega | Qué no entrega |
|---|---|---|---|---|
| Vuelos | `lergassy/google-flights-scraper` (676 usuarios en 30 días, 4.9 con 11 reseñas) | 0,001 USD por vuelo | Itinerarios de Google Flights por ruta y fechas: aerolínea, horarios, escalas, precio, moneda, nivel de precio (bajo, típico, alto), vendedores con enlace | **Equipaje, condiciones de tarifa y penalidades por cambio**: su documentación dice que no están en los datos de Google Flights |
| Hoteles | `voyager/booking-scraper` (1.239 usuarios en 30 días, 4.5 con 34 reseñas) | 0,005 USD por alojamiento, más 0,005 por detalle adicional | Alojamientos de Booking por ciudad y fechas: precio, moneda, calificación, desayuno, dirección | Puntos de programas de fidelización (Booking es una agencia: reservar ahí no acumula en los programas de las cadenas) |
| Hoteles, varias fuentes | Varios extractores de Google Hotels | 0,004 a 0,005 USD por hotel | Precio por vendedor, lo que permite comparar reserva directa frente a agencia | Por revisar |
| Alquiler de carro | Extractores de Kayak y Skyscanner | 0,001 a 0,0015 USD por resultado | Por revisar | Por revisar |

Lectura:
- El costo es despreciable para una demo: una búsqueda de 50 vuelos y 20 hoteles ronda los 0,15 USD.
- Los datos reales cubren el **precio base**, pero no lo que hace la diferencia en el costo total (equipaje, flexibilidad de la tarifa). Esa parte tiene que salir de reglas propias por aerolínea y familia tarifaria, o de datos que complete el usuario. La herramienta aporta justo donde el buscador no llega.
- La comparación de vendedores en hoteles sirve directamente para el aviso "reservar por agencia no acumula puntos".
- Riesgos: depende de una cuenta de terceros; los extractores pueden fallar o cambiar; extraer datos de estos sitios puede ir contra sus términos de uso. Si se usa, la demo debe poder correr con resultados guardados y marcar cuáles son en vivo.

Estado: aceptada el 11 de noviembre. No se ha ejecutado ningún extractor todavía; falta el token de la cuenta en `.env` (`APIFY_TOKEN`).

## 5. Preguntas abiertas (por decidir hoy)

1. ~~**Nivel de integración**: ¿una aplicación con los puentes P.1 a P.3, o dos demos separadas?~~ Resuelto: una sola plataforma con el viaje como eje (ver `ANALISIS.md`, sección 4, «Lo que se decidió después», y el README, «Por qué integrados y no por separado»).
2. **Fuente de opciones del Reto 1**: ¿escenarios simulados fijos, pegar y capturar (idea 1.1), o ambos?
3. **Canales del Reto 2**: ¿carga web + buzón simulado + página para celular?
4. ~~A qué se dedica la empresa y dónde opera~~: resuelto el 11 de noviembre, ver 2.1. La verificación de programas de fidelización y reglas de baterías está en 7.1.
5. **Forma de entrega**: ¿repositorio privado, archivo comprimido, video de demostración? El enunciado es confidencial, lo que afecta si `ENUNCIADO.md` se versiona y dónde se aloja el repositorio.
6. **Explicación de las herramientas usadas**: el enunciado pide explicarlas (punto 4 del envío, redactado por la persona que presenta la prueba). Hay que decidir dónde vive ese texto.

## 6. Ideas descartadas

Ninguna todavía.

## 7. Reto 1: verificación de supuestos y abordaje

Fecha: 11 de noviembre de 2026. Estado: **abordaje propuesto, pendiente de visto bueno para construir**.

### 7.1 Supuestos verificados

Búsquedas genéricas en la web, sin datos de la empresa. "Oficial" es la fuente del regulador o del operador; "secundaria" son guías de terceros que coinciden entre sí pero deben confirmarse en la página de cada aerolínea antes de tratarlas como regla firme.

| Supuesto | Resultado | Fuente | Efecto en la herramienta |
|---|---|---|---|
| Las baterías de litio de repuesto van en cabina | **Confirmado.** Hasta 100 Wh: permitidas en cabina. De 101 a 160 Wh: requieren aprobación de la aerolínea y máximo dos de repuesto. Más de 160 Wh: prohibidas en vuelos de pasajeros. Nunca en bodega | Oficial: [FAA PackSafe](https://www.faa.gov/hazmat/packsafe/airline-passengers-and-batteries), [TSA](https://tsa.gov/travel/security-screening/whatcanibring/items/lithium-batteries-more-100-watt-hours), [EASA](https://easa.europa.eu/en/newsroom-and-events/press-releases/easa-publishes-new-recommendations-managing-risks-lithium) | El equipo del piloto es un dato de la solicitud. Una tarifa sin equipaje de mano completo no sirve |
| La regla depende del modelo de dron | **Confirmado en parte.** Batería de un dron plegable común: cerca de 77 Wh (pasa sin trámite). Batería de un dron industrial grande: 263 Wh (no puede volar con el pasajero; hay que enviarla o alquilar en destino) | Secundaria: [Pilot Institute](https://pilotinstitute.com/drones-on-airplanes/) | La solicitud pide capacidad (Wh) y cantidad de baterías; la herramienta clasifica: sin trámite, requiere aprobación, no puede viajar |
| La tarifa más barata puede no admitir equipaje de mano | **Confirmado con matices.** United: su tarifa básica en rutas nacionales solo admite artículo personal. Delta y American: la básica sí incluye equipaje de mano. Ryanair y easyJet: solo bolso pequeño bajo el asiento; la maleta de cabina se paga aparte | Secundaria: [The Points Guy](https://thepointsguy.com/glossary/what-is-basic-economy/), [Which?](https://www.which.co.uk/reviews/airlines/article/most-generous-airline-hand-luggage-aF9jK9M1uoMk) | Catálogo de reglas por aerolínea y tarifa, editable, cada una con fuente y fecha |
| La tarifa más barata puede no acumular millas | **Hallazgo nuevo.** American: la tarifa básica no acumula millas desde diciembre de 2025. Delta: su tarifa básica no acumula | Secundaria: [AwardFares](https://awardfares.com/blog/aadvantage-business-guide/) | La opción barata pierde dos veces: paga equipaje y no acumula. Es un aviso visible en la comparación |
| Cargos ocultos de hotel (*resort fees*) | **Corregido.** Desde el 12 de mayo de 2025 una norma federal de Estados Unidos obliga a mostrar el precio total con cargos obligatorios incluidos. Los impuestos pueden seguir fuera del precio inicial | [Hotel Dive](https://www.hoteldive.com/news/ftc-junk-fees-rule-takes-effect-hotels/747738/), [Thrifty Traveler](https://thriftytraveler.com/news/hotels/new-federal-junk-fees-rule/) | Baja de prioridad. Queda como comprobación: ¿el precio extraído incluye impuestos? |
| Existen programas de fidelización para empresas pequeñas | **Confirmado.** Estados Unidos: American (la empresa acumula y el viajero conserva lo suyo), Delta, United. Europa: Lufthansa, Air France-KLM, British Airways. Son gratuitos y la empresa acumula aparte del viajero. Tasas vigentes de 2026: sin confirmar | Secundaria: [The Points Guy](https://thepointsguy.com/loyalty-programs/airline-loyalty-programs-small-businesses/), oficial: [Lufthansa](https://business.lufthansagroup.com/us/en/program/partner-plus-benefit/25-years-partner-plus-benefit) | Resuelve la incógnita de "programas de fidelización de la empresa": se modelan dos niveles, cuenta de empresa y membresía del viajero |
| El clima mueve las fechas de grabación | Sin verificar; es deducción propia | — | La probabilidad de cambio es un dato que el usuario ajusta, con un valor por defecto declarado como supuesto |

### 7.2 Abordaje

**Qué es:** un comparador de viajes de grabación que responde una sola pregunta: *para este piloto, con este equipo, ¿cuál es la opción que menos cuesta de verdad, y por qué?*

**Flujo (cinco pasos)**

1. **Solicitud.** Proyecto, viajero, origen, ciudad de la grabación, fecha y hora, noches, equipo (cantidad y capacidad de baterías, maleta facturada sí o no) y probabilidad de cambio de fecha.
2. **Búsqueda.** Vuelos y hoteles traídos por extracción (ver 4.5). Cada resultado se guarda y queda marcado como en vivo o guardado. Sin cuenta, la demo corre con los guardados.
3. **Enriquecimiento con reglas propias.** A cada opción se le aplica el catálogo: equipaje según aerolínea y tarifa, costo de cambio, si acumula, beneficios por estatus del viajero, cuenta de empresa.
4. **Comparación.** Primero se descartan las opciones que no cumplen (no llega a tiempo, la batería no puede viajar). Las demás se ordenan por costo total esperado, con el desglose a la vista y un aviso cuando la más barata del buscador no es la mejor.
5. **Ficha de decisión.** Una página con la opción elegida, las descartadas y el motivo; queda guardada contra el proyecto y se puede exportar.

**Fórmula**

> costo total esperado = precio base + equipaje + traslados + (probabilidad de cambio × costo de cambiar) − valor de lo acumulado − beneficios por estatus

Cada término lleva su origen: extraído, regla del catálogo o supuesto del usuario.

**Limitación central y cómo se maneja.** Con el extractor de Apify, la búsqueda de vuelos no dice qué tarifa es ni qué equipaje incluye. La prueba con SerpApi (ver 7.4) mostró que esa información sí se puede obtener: familias tarifarias con precio, equipaje y condiciones de cambio. El catálogo de reglas propias queda para lo que ningún buscador entrega: baterías, acumulación de millas por tarifa y efecto del estatus del viajero.

**Modelo de datos (borrador)**

| Tabla | Contenido |
|---|---|
| `viajeros` | Nombre, ciudad base |
| `membresias` | Viajero o empresa, programa, estatus |
| `solicitudes` | Proyecto, viajero, origen, destino, fechas, equipo, probabilidad de cambio |
| `opciones` | Solicitud, tipo (vuelo u hotel), datos extraídos, origen del dato (en vivo o guardado), fecha de captura |
| `reglas` | Aerolínea o cadena, tarifa, qué incluye, costos, si acumula, fuente, fecha de verificación |
| `decisiones` | Solicitud, opción elegida, desglose, motivo, quién aprobó |

**Alcance**

| Entra | Queda como mejora |
|---|---|
| Vuelos y hoteles con precios extraídos y respaldo guardado | Alquiler de carro extraído (en la primera versión es un valor diario estimado y editable) |
| Catálogo de reglas editable con fuente y fecha | Disponibilidad de asientos con millas |
| Clasificación de baterías por capacidad | Reserva y pago |
| Dos niveles de fidelización: empresa y viajero | Consulta de saldos reales de los programas |
| Ficha de decisión guardada contra el proyecto | Alertas de precio y seguimiento |

**Decisiones tomadas por defecto** (se pueden cambiar): el carro va como estimado y no extraído; "programas de fidelización de la empresa" se modela en dos niveles; la opción de pegar o capturar resultados (idea 1.1) queda como respaldo si la extracción falla, no como vía principal.

**Riesgos**

- Los precios son una foto del momento; la ficha guarda fecha y hora de captura.
- Extraer datos de buscadores puede ir contra sus términos de uso. Se declara en las limitaciones y se propone una API con licencia como camino de producción.
- Las reglas del catálogo vienen en parte de fuentes secundarias; cada una muestra su fuente y fecha para que quien la use sepa cuánto confiar.

### 7.4 Fuente de precios: opciones evaluadas y prueba real

**Opciones evaluadas (11 nov)**

| Opción | Resultado |
|---|---|
| Amadeus Self-Service | Descartada: el portal cerró el 17 de julio de 2026 ([comunicado](https://amadeus.com/en/industry-messaging/statement-regarding-amadeus-for-developers-portal)) |
| SerpApi (Google Flights y Google Hotels) | **Elegida como fuente principal.** Probada, ver abajo |
| Apify (extractores de terceros) | Respaldo; el extractor de vuelos no trae equipaje ni tarifa |
| Firecrawl (extracción de páginas con IA) | Elegida para llenar el catálogo de reglas desde páginas oficiales de aerolíneas. Probada con la página de tarifa básica de United: confirma que en rutas nacionales no admite equipaje de mano, que en rutas transatlánticas sí, y que el estatus del viajero levanta la restricción |
| Navegador automatizado propio | Descartada por tiempo y fragilidad |
| Duffel | Camino de producción (API con licencia); su modo de prueba no da precios reales |
| Pegar o capturar resultados | Respaldo manual |

**Prueba real con SerpApi** (11 nov, Miami a Las Vegas, ida 8 dic y regreso 11 dic de 2026, tres consultas)

1. Búsqueda: 11 itinerarios de ida con aerolínea, número de vuelo, horarios, escalas y precio de ida y vuelta, más el rango de precio típico de la ruta (180 a 330 USD).
2. Detalle del vuelo directo de American, que devuelve las familias tarifarias:

| Tarifa | Precio (USD) | Equipaje de mano | Primera maleta | Cambios | Reembolso |
|---|---|---|---|---|---|
| Basic Economy | 458 | Incluido | 110 | No permite | No |
| Main Cabin | 588 | Incluido | 100 | Gratis, con diferencia de tarifa | No |
| Main Plus | 800 | Incluido | Incluida | Gratis, con diferencia de tarifa | No |
| Main Select | 858 | Incluido | 100 | Gratis, con diferencia de tarifa | Total |

Lectura:
- Este es el dato que faltaba para calcular el costo total esperado con valores reales y no estimados: la diferencia entre la tarifa que no admite cambios y la que sí es de 130 USD en este ejemplo.
- Ver las tarifas de un vuelo cuesta dos consultas adicionales (regreso y reserva). Con un plan gratuito limitado, el detalle se pide solo para las mejores opciones y todo resultado se guarda.
- Las respuestas guardadas no contienen la clave.

### 7.3 Antes y después

| Hoy (supuesto) | Con la herramienta |
|---|---|
| A. Recibir la necesidad del viaje | A. Llenar una solicitud |
| B. Buscar en varias páginas y copiar precios | Desaparece |
| C. Comparar a ojo y consultar condiciones de cada tarifa | Desaparece |
| D. Proponer y aprobar por mensajes | D. Aprobar la ficha de decisión |
| Sin registro del porqué | El registro queda hecho |

## 8. Estado de la construcción

Al cierre del 11 de noviembre:

| Parte | Estado |
|---|---|
| Base (configuración, datos, semilla, bitácora de eventos) | Hecha |
| Reto 1: solicitud, precios, costo total, descarte, ficha de decisión | Hecho; probado con los precios reales guardados |
| Reto 2: tres canales, lectura, validación, bandeja de revisión, corrección | Hecho; probado con lecturas guardadas. **La lectura en vivo con el modelo no se ha probado** (falta la clave) |
| Tablero previsto frente a real, soportes faltantes, exportación | Hecho |
| Flujo de la información y catálogo de reglas editable | Hecho |
| Supabase | Código listo; **sin probar** (faltan los datos de conexión) |
| Despliegue en AWS | Pendiente; hay `Dockerfile`, sin probar |
| Medición de exactitud, documentos de `docs/`, guion | Pendiente |

> **Estado al 13 de noviembre.** Supabase está conectado y la migración aplicada en la base publicada; la plataforma está desplegada en AWS con dominio propio ([`docs/produccion.md`](docs/produccion.md)); la medición de exactitud está escrita y pendiente de correr con la clave del modelo ([`docs/exactitud-lectura.md`](docs/exactitud-lectura.md)); los documentos están en `docs/` y el guion de demostración en el README.

Resultado del caso de ejemplo (Miami a Las Vegas, piloto con cuatro baterías de 77 Wh, maleta, 25 % de probabilidad de cambio, llegada antes de las 18:00): el buscador pone primero un vuelo de 279 USD con escala; por costo total esperado gana el vuelo directo en tarifa estándar (561 USD esperados frente a 566), y cuatro opciones se descartan por llegar tarde. La diferencia es pequeña y depende de supuestos editables; lo que aporta la herramienta es que la comparación queda explícita.

## 9. Ampliación: datos, modelo, analítica y agente

Decisiones del 11 de noviembre (noche):

| Tema | Decisión | Motivo |
|---|---|---|
| Alcance | Por fases: lo que cabe antes del viernes se construye; React y la infraestructura completa en AWS quedan diseñados para una segunda fase | El plazo no alcanza para todo sin dejar piezas a medias |
| Modelo | XGBoost para **precio esperado** con datos reales del buscador. Los pesos de la decisión siguen siendo reglas explícitas | No hay historial de viajes de la empresa con su resultado; aprender pesos sin él sería inventarlos |
| Agente | LangGraph dentro del backend; n8n se propone para automatizaciones de operación | Se versiona con el código y no saca datos a un servidor ajeno |
| Front | La interfaz actual se mantiene; el backend expone una API en JSON para conectar React después | Rehacer pantallas no añade funciones antes de la entrega |

Estado al cierre del día:

| Parte | Estado |
|---|---|
| Registro tabular de cada vuelo visto (`observaciones`) e historial de 60 días por ruta | Hecho; 29 filas de 2 búsquedas |
| Recolector (`datos/recolectar.py`): 10 rutas por 4 anticipaciones | Escrito y probado en modo simulación; **sin ejecutar** (gasta cupo) |
| Entrenamiento (`datos/entrenar.py`) | Funciona de punta a punta; con 29 filas el modelo queda marcado como **no utilizable** (mínimo 200) y no se muestra |
| Analítica (`/analitica`) | Hecha: frecuencia, ahorro identificado, historial de precios, estado del modelo, gastos |
| Agente | Modo determinista probado; **modo con modelo de lenguaje escrito y sin probar** (falta la clave) |
| API en JSON | Hecha, con documentación automática |

Cómo se mide el ahorro: costo total esperado de la opción más barata del buscador menos el de la recomendada. En las dos consultas registradas da 1,35 USD (Miami a Las Vegas) y 39 USD (Madrid a Lisboa). Son cifras pequeñas y dependen de supuestos; se presentan como método, no como resultado de negocio.

### 9.1 Resultado de la recolección y del modelo (11 nov, noche)

Recolección: 40 consultas en vivo, 10 rutas (seis de Estados Unidos, cuatro de Europa) por cuatro anticipaciones (7, 21, 45 y 75 días). Con las dos búsquedas previas: **760 vuelos reales de 42 búsquedas**, 23 aerolíneas. Cupo restante del buscador: 205 de 250.

| | Error medio (USD) | Error porcentual |
|---|---|---|
| Modelo (XGBoost) | 115,96 | 36,3 % |
| Línea base (mediana de la ruta) | 142,65 | 48,7 % |

Validación: cinco pliegues dejando búsquedas completas fuera del entrenamiento. El modelo supera a la línea base y pasa el mínimo de 200 filas, así que queda **en uso**: cada vuelo muestra cuánto está por encima o por debajo de lo esperado.

Lectura honesta:
- Un error del 36 % es alto. El dato sirve como señal ("este vuelo está caro para su ruta"), no como precio de referencia exacto, y no entra en el cálculo del costo total.
- Lo que más pesa es el rango típico de la ruta, que el propio buscador entrega (57 % de la ganancia). El modelo añade sobre todo el efecto de aerolínea, horario y escalas dentro de la ruta.
- Anticipación y día de la semana están mezclados: cada anticipación se capturó en una sola fecha, así que el modelo no puede separar "faltan 7 días" de "sale un miércoles". Para separarlos hace falta recolectar en varios días.
- Todo se capturó el mismo día. No hay serie de tiempo propia: el modelo no dice cuándo comprar.

### 9.2 Conexión a Supabase (11 nov, noche)

| Parte | Resultado |
|---|---|
| Base de datos | Conectada por el agrupador de sesiones. 12 tablas creadas por la aplicación al arrancar; 760 observaciones, 2.562 puntos de historial, 25 reglas y los datos de ejemplo cargados |
| Archivos | Bucket privado `soportes`; los soportes originales se guardan y se leen desde ahí |
| Recorrido completo contra la nube | Pasó: dos viajes, una decisión, ocho gastos (seis aprobados solos, dos a revisión), tablero, analítica y flujo |
| Tiempos desde el equipo local | Entre 0,2 y 2 segundos por página; cada consulta tarda unos 190 ms por la distancia a la región. Desplegada en la misma región debería ser mucho menor (sin medir) |

Ajustes que pidió la conexión remota: modo de confirmación automática para que cada consulta sea un solo viaje de red, memoria corta (60 s) para los catálogos y conversión de valores decimales. Seguridad del proyecto: las tablas no se exponen por la API pública y tienen seguridad por filas activada; la aplicación entra con la contraseña de la base, que vive solo en `.env`.

Sin configuración, la aplicación sigue usando SQLite y carpeta local, de modo que quien evalúe puede ejecutarla sin cuenta.

## 10. Visión del producto (nota de voz, 11 nov)

Fuente: nota de voz de unos siete minutos en la que la persona que presenta la prueba explica la idea completa. Transcripción automática; lo marcado **[Por confirmar]** no se oyó con claridad.

**Recorrido que describe**

1. Una persona de la empresa (piloto o gestor de proyecto) entra a la plataforma **con sus credenciales** y hace una solicitud de viaje: fechas, horas, origen y destino.
2. La plataforma consulta los precios en el buscador y devuelve las mejores opciones.
3. **Todo lo consultado se guarda**, para no desperdiciar lo que ya se pagó por consultar y para formar un conjunto de datos propio.
4. Al principio, las mejores opciones las ordena un **agente con los parámetros que la empresa define como importantes** (fechas, horarios, si incluye maleta y demás reglas de negocio), para que la persona no tenga que revisarlas todas.
5. La persona elige la opción y **dice por qué**. Esa elección queda como la variable objetivo, y el motivo como contexto en texto.
6. Con suficientes elecciones guardadas se entrena un modelo (árbol de decisión, con sus pesos) que propone la mejor opción directamente.
7. El registro de gastos del segundo reto vive **en la misma plataforma**, en otra sección.
8. Hay **dos tipos de usuario**: el individual, que hace solicitudes, y el administrador, que ve todos los datos y la analítica (viajes tomados, costos, gráficas).
9. Es un producto mínimo viable, pero con estructura completa: interfaz, servidor, base de datos y despliegue.

**Contraste con lo construido**

| Idea | Estado |
|---|---|
| Solicitud con fechas, horas, origen y destino | Hecho |
| Consulta de precios y mejores opciones | Hecho |
| Guardar todo lo consultado como datos tabulares | Hecho (`observaciones`, `historial_ruta`, respaldos) |
| Ordenar según reglas de negocio de la empresa | Hecho en parte: costo total esperado, descartes y catálogo de reglas. **Falta** una pantalla donde la empresa declare sus prioridades en lenguaje llano |
| Agente que recomienda | Hecho (grafo de estados); el modo con modelo de lenguaje sigue sin probar |
| Elegir y decir por qué | Hecho en parte: la decisión guarda un motivo en texto libre. **Falta** guardar el motivo de forma estructurada y marcar si se siguió la recomendación |
| Elección como variable objetivo | **Falta** dejar el conjunto etiquetado listo: cada opción mostrada, con la marca de cuál se eligió |
| Modelo que aprende de las elecciones | Fase 2 por diseño: requiere historial. Hoy hay un modelo de precio esperado, que es otra cosa |
| Reto 2 en la misma plataforma | Hecho |
| Credenciales y dos tipos de usuario | **Falta.** Hoy hay una contraseña compartida y un nombre libre |
| Analítica para el administrador | Hecha, pero visible para cualquiera |
| Despliegue | Pendiente |

**Lectura.** La idea coincide con la arquitectura actual y corrige el orden correcto del aprendizaje: primero reglas y agente, después modelo, cuando existan elecciones reales. Lo que falta para que la plataforma cuente esa historia completa son tres piezas: usuarios con rol, motivo estructurado de la decisión y conjunto de datos etiquetado.

> **Estado al 13 de noviembre.** Las tres piezas están hechas: cuentas con contraseña propia y tres permisos (colaborador, gestor y administración), con el cargo aparte; la decisión guarda las razones marcadas y si se siguió la recomendación; y cada opción mostrada queda en `elecciones` con la marca de cuál se eligió. La analítica es solo para administración y la plataforma está desplegada ([`docs/produccion.md`](docs/produccion.md)). Sigue faltando la pantalla para declarar prioridades en lenguaje llano.
