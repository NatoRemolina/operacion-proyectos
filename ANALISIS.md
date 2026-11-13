# Análisis previo de los dos retos

Documento de trabajo, anterior a cualquier construcción. Fecha: 11 de noviembre de 2026.

Convenciones: **[Verificado]** significa leído en la página oficial del programa en la fecha de este documento. **[Fuente secundaria]** significa que solo se encontró en guías o blogs y no se pudo confirmar en la página oficial. **[Supuesto]** es una hipótesis propia que habría que confirmar con la empresa. **[Simulado]** marca todo dato inventado para la demo.

## 1. Qué pide y qué evalúa la prueba

Lo que se entrega (sección "Envío"):

| # | Entregable | Nivel exigido |
|---|---|---|
| 1 | Reto 2 | Demostración **funcional** (obligatoria) |
| 2 | Reto 1 | Demostración práctica **o** propuesta (admite menos construcción) |
| 3 | Fuentes, scripts, flujos y materiales de prueba propios | Todo lo generado |
| 4 | Explicación de herramientas de IA y proceso | Breve, "elaborado por ti mismo" |
| 5 | Limitaciones y mejoras | Descripción |

Además pide justificar si los retos se abordan por separado o integrados.

Lo que se evalúa (sección "Requisitos generales"), leído como criterios:

1. **Comprensión operativa**: que la solución se parezca al trabajo real de Finanzas y de los project managers, no a un ejercicio técnico.
2. **Resolución de problemas**: encontrar mejoras, "en lugar de limitarse a reproducir los procesos manuales". Digitalizar la hoja de cálculo tal cual no basta.
3. **Usabilidad para no técnicos**: la interfaz importa tanto como la extracción.
4. **Iniciativa**: datos de prueba e investigación propios; la empresa no entrega nada.
5. **Supuestos y limitaciones explícitos**: se premia decir qué no se sabe.
6. **Uso de IA con validación**: no solo qué herramientas, sino "cómo validó sus soluciones".

La última frase del enunciado fija el alcance: no es una plataforma completa, es demostrar que se convierte un problema operativo en una solución práctica. La prioridad de esfuerzo que se deduce: Reto 2 funcional y pulido > documentación honesta > Reto 1 demostrable > integración.

## 2. Reto 2: recolección y organización de gastos

### 2.1 Proceso manual actual (inferido) [Supuesto]

1. Un miembro del equipo gasta (vuelo, hotel, taxi, gasolina, comida, compra del proyecto).
2. El soporte llega por canales distintos: confirmación de vuelo u hotel por correo, foto del recibo por chat o correo, PDF de factura.
3. Alguien de Finanzas persigue los soportes que faltan, abre cada documento y digita en una hoja de cálculo: fecha, proveedor, valor, moneda, categoría, proyecto, quién pagó.
4. Archiva el documento en una carpeta (por proyecto o por mes).
5. Al cierre, suma por proyecto y responde preguntas del project manager ("¿cuánto llevamos en el proyecto X?").

Dónde se pierde tiempo: digitación, búsqueda de soportes dispersos, preguntar a qué proyecto pertenece cada gasto, rehacer consolidados.
Dónde hay errores: valores mal digitados, gasto asignado al proyecto equivocado, duplicados (el mismo hotel llega como confirmación por correo y como factura al salir), moneda sin convertir, recibos ilegibles o perdidos, gastos sin soporte.

### 2.2 Usuarios

- **Miembro del equipo que gasta**: quiere enviar el soporte en segundos desde el celular y olvidarse.
- **Finanzas**: quiere registros correctos, completos y con soporte; revisa excepciones, no cada dato.
- **Project manager**: quiere ver el gasto de su proyecto al día y por categoría, sin pedirle un reporte a Finanzas.

Ninguno es técnico: nada de terminal, nada de JSON a la vista.

### 2.3 Factores relevantes

**Entradas**
- Correos de confirmación (HTML o texto, a veces con PDF adjunto): vuelos, hoteles.
- PDF de facturas (hotel, compras).
- Fotos de recibos: papel térmico, torcidas, con sombra, a veces manuscritas.
- Para la demo, el canal de correo se simula con archivos `.eml` o una carpeta de entrada. Conectar un buzón real exige credenciales de la empresa.

**Campos a extraer**
- Comunes: fecha del gasto, proveedor, valor total, moneda, impuestos (y propina si aparece), medio de pago, número de factura o código de reserva, categoría.
- Vuelo: pasajero, ruta, fechas, aerolínea, localizador.
- Hotel: huésped, ciudad, fechas de entrada y salida, noches.
- Combustible y transporte: ciudad, placa o trayecto si aparece.
- Metadatos: quién lo envió, por qué canal, cuándo, archivo original.

**Asignación a proyecto**: es el dato que casi nunca está en el documento. Fuentes posibles, en orden de confianza: lo indica quien sube el gasto; se deduce de un viaje planeado (viajero + fechas + ciudad coinciden con un viaje de un proyecto); lo sugiere el modelo por texto del correo; queda "sin asignar" para revisión. Nunca asignar en silencio con baja confianza.

**Duplicados**: mismo proveedor + fecha + valor (con tolerancia), o mismo número de factura o localizador. Caso típico: reserva de hotel por correo y factura final con valor distinto por consumos. Se marcan como "posible duplicado" y decide una persona.

**Datos faltantes o dudosos**: cada campo con indicador de confianza; campos obligatorios vacíos mandan el gasto a revisión. Validaciones deterministas (no del modelo): total = subtotal + impuestos, fecha no futura, moneda reconocida, valor fuera de rango para la categoría.

**Monedas**: guardar siempre valor y moneda originales, más el valor convertido a la moneda de reporte con la tasa y su fecha. En la demo, tasas de cambio fijas [Simulado].

**Revisión humana**: bandeja con el documento original al lado de los campos extraídos; aprobar, corregir o rechazar. La automatización propone, Finanzas confirma. Es el punto que más confianza le da a un equipo financiero.

**Trazabilidad**: cada registro enlaza a su archivo original (con huella para detectar reenvíos idénticos) y conserva quién aprobó o corrigió y cuándo.

**Salida**: tablero por proyecto (total, por categoría, por persona, pendientes de revisión) y exportación a Excel o CSV, porque Finanzas seguirá usando su hoja o su sistema contable.

### 2.4 Enfoques posibles

| | A. Aplicación web ligera | B. Automatización sin código | C. Script por lotes |
|---|---|---|---|
| Qué es | Subir o arrastrar documentos; extracción con modelo de lenguaje multimodal a un esquema fijo; validaciones; bandeja de revisión; tablero por proyecto; exportación | n8n, Make o Zapier: buzón + formulario → extracción → Google Sheets | Carpeta de entrada → script → Excel |
| A favor | Cubre todo el flujo incluida la revisión; reproducible en local; se controla la experiencia de usuario; fácil de demostrar y defender | Muy cercana al uso real; rápida de armar; el equipo ya conoce Sheets | Mínimo esfuerzo; fácil de validar |
| En contra | Más construcción; el canal de correo queda simulado | Depende de cuentas y credenciales de terceros; difícil de entregar para que el evaluador la ejecute; revisión humana y duplicados quedan pobres | No sirve a usuarios no técnicos; sin revisión ni tablero |
| Riesgo | Alcance | Que el evaluador no pueda correrla | Parecer solo "reproducir el proceso manual" |

**Recomendación: A**, con dos decisiones que reducen riesgo:
- Un "modo sin clave": si no hay clave de API, la aplicación usa extracciones guardadas de los documentos de prueba, así el evaluador puede ejecutarla sin configurar nada.
- La entrada de correo se modela como una carpeta de `.eml`, y en el documento de mejoras se explica cómo se conectaría un buzón real (por ejemplo, una dirección tipo gastos@ a la que el equipo reenvía).

### 2.5 Alcance de la demo

Dentro:
- Carga de PDF, imagen y `.eml`.
- Extracción a esquema estructurado, con confianza por campo.
- Validaciones, detección de posibles duplicados, conversión de moneda con tasas simuladas.
- Bandeja de revisión con documento al lado.
- Tablero por proyecto y exportación a Excel.
- Juego de 12 a 15 documentos ficticios que incluya casos difíciles: recibo borroso, moneda extranjera, duplicado, gasto sin proyecto, total que no cuadra.
- Una medición sencilla de exactitud: valores esperados de cada documento de prueba frente a lo extraído (responde a "cómo validó").

Fuera: buzón o chat reales, usuarios y permisos, flujo de aprobación y reembolso, integración contable, validación tributaria de facturas, aplicación móvil.

## 3. Reto 1: reservas de viaje y programas de fidelización

### 3.1 Proceso manual actual (inferido) [Supuesto]

1. El project manager avisa: quién viaja, a dónde, cuándo, para qué proyecto.
2. Alguien abre varias pestañas (aerolíneas, agencias en línea, cadenas hoteleras), copia precios en un chat o una hoja.
3. Compara a ojo, normalmente por la tarifa visible, sin sumar equipaje, traslados ni condiciones de cambio.
4. Si se acuerda, revisa si hay millas o puntos; rara vez calcula si conviene usarlos.
5. Consulta con el viajero y con quien aprueba; para entonces el precio pudo cambiar.

Dónde se pierde tiempo: búsqueda repetida en muchos sitios, ida y vuelta de mensajes, rehacer la búsqueda cuando cambia una fecha.
Dónde hay errores: elegir la tarifa más barata que termina más cara (equipaje, cambio de fecha), reservar hotel en una agencia y perder puntos y beneficios, dejar vencer millas, no dejar registro de por qué se eligió una opción.

### 3.2 Factores relevantes

**Costo total del viaje, no precio del tiquete**
- Vuelo: tarifa + tasas, equipaje de bodega (el más importante si se viaja con equipo de trabajo [Supuesto: por el tipo de empresa, cámaras o drones]), selección de asiento, penalidad por cambio y reembolso según familia tarifaria.
- Hotel: tarifa por noche × noches, impuestos, desayuno, cancelación gratuita, distancia al sitio del proyecto.
- Terrestre: traslados aeropuerto–hotel–sitio; un hotel barato lejos puede salir más caro.
- Tiempo: escalas largas o vuelos que obligan a una noche adicional.
- Probabilidad de cambio: los proyectos mueven fechas; una tarifa flexible puede ser la opción económica.
- Moneda y tasa de cambio.

**Programas de fidelización: reglas comprobadas**

| Regla | Programa | Estado |
|---|---|---|
| Solo personas naturales pueden ser socias; la cuenta es unipersonal | LATAM Pass (Colombia) | [Verificado] Términos y condiciones, 3.A.1 y 1.11 |
| Personas jurídicas no son elegibles ni pueden acumular millas, salvo excepciones de los términos | LifeMiles | [Verificado] Términos y condiciones |
| Solo el socio que se hospeda acumula puntos; habitaciones de contrato o facturación maestra no acumulan | Marriott Bonvoy | [Verificado] Términos 2.5 |
| Millas vencen a los 36 meses desde su acumulación sin categoría élite; con categoría élite no expiran | LATAM Pass (Colombia) | [Verificado] 5.A |
| Cada acumulación extiende la vigencia 12 meses; redimir no la extiende | LifeMiles | [Verificado] Política de expiración |
| Puntos se pierden tras 24 meses sin actividad calificable | Marriott Bonvoy | [Verificado] 1.4 |
| Acumulación según categoría élite, tarifa, ruta y valor del pasaje en USD sin tasas | LATAM Pass | [Verificado] 5.B.1.1 |
| 10 puntos base por USD en la mayoría de marcas, 5 en algunas | Marriott Bonvoy | [Verificado] 2.1.a |
| Reservas por agencias en línea o terceros no acumulan puntos, ni noches élite, ni dan beneficios de estatus | Marriott Bonvoy | [Verificado] 2.1.f |
| Quinta noche gratis al redimir cinco noches seguidas con puntos | Marriott Bonvoy | [Verificado] 3.3.d |
| Quinta noche gratis en premios estándar para socios con estatus; vencimiento por inactividad; terceros no acumulan | Hilton Honors | [Fuente secundaria] la página oficial no se pudo leer |
| Programas para empresas (LATAM Corporate, Hilton for Business, IHG Business Edge) | Varios | No verificado: existencia y condiciones por confirmar |

Fuentes oficiales consultadas: [Marriott Bonvoy](https://www.marriott.com/loyalty/terms/default.mi), [LATAM Pass Colombia](https://latampass.latam.com/co/es/reglamentos-generales/terminos-y-condiciones), [LifeMiles](https://www.lifemiles.com/terms-conditions). Fuentes secundarias para Hilton: [AwardWallet](https://awardwallet.com/hotels/hilton-honors/hilton-5th-night-free/), [NerdWallet](https://www.nerdwallet.com/article/travel/hotel-points-expire), [The Points Guy](https://thepointsguy.com/news/why-no-hotel-points-ota/).

**Consecuencia central de estas reglas**: en los programas de consumo, las millas y puntos pertenecen al **viajero**, no a la empresa. "Los programas de fidelización de la empresa" puede significar tres cosas distintas, y el diseño cambia según cuál sea:
1. Cuentas personales de los empleados que la empresa aprovecha (estatus de un viajero frecuente, sus millas).
2. Un programa corporativo aparte, donde la empresa sí acumula.
3. Puntos de una tarjeta de crédito corporativa transferibles a aerolíneas u hoteles.

Es la pregunta más importante para la empresa. La demo debe modelar "membresías por viajero" y admitir además una cuenta de empresa.

**Decisiones que la herramienta debe apoyar**
- **Pagar con dinero o con puntos**: valor obtenido por milla = (precio en dinero − tasas del premio) ÷ millas requeridas. Se compara contra un valor de referencia por programa [Simulado y configurable]; si lo supera, conviene redimir.
- **Valor de lo que se acumula**: millas ganadas × valor de referencia, como descuento efectivo sobre la opción.
- **Canal de reserva**: avisar cuando la opción más barata está en una agencia en línea y se pierden puntos y beneficios de estatus.
- **Beneficios de estatus con valor en dinero**: equipaje incluido, desayuno, salida tardía.
- **Alertas de vencimiento**: millas próximas a vencer pesan a favor de redimir.
- **Concentrar o repartir**: acumular en un programa para alcanzar estatus frente a tomar siempre lo más barato.

**Restricciones y riesgos**
- Los precios cambian en minutos; una comparación es una foto.
- La disponibilidad de asientos y noches premio es limitada y no se consulta por vías públicas simples.
- Extraer precios automáticamente de los sitios de aerolíneas suele estar prohibido en sus términos; las API de búsqueda exigen cuenta y tienen cuotas.
- Las reglas de los programas cambian con poco aviso (LATAM Pass: 30 días).
- Si la empresa se beneficia de millas de un empleado hace falta una política interna clara.
- Política de viajes de la empresa (topes, clases permitidas, anticipación) desconocida.

### 3.3 Enfoques posibles

| | A. Comparador de costo total con motor de reglas | B. Búsqueda con datos reales por API | C. Asistente conversacional que investiga |
|---|---|---|---|
| Qué es | Solicitud de viaje → opciones (simuladas o pegadas por el usuario) → costo total, valor de puntos, opción con millas, alertas → recomendación explicada | Lo mismo, con precios reales desde una API de vuelos y hoteles | Un agente con modelo de lenguaje que busca en la web y recomienda |
| A favor | Reproducible; muestra el razonamiento de negocio, que es lo evaluado; reglas verificadas y citadas; no depende de terceros | Realismo; ahorra de verdad el tiempo de búsqueda | Flexible; impresiona en una demo |
| En contra | Los precios no son reales (hay que decirlo con claridad) | Exige crear cuentas y claves; cuotas; no entrega disponibilidad con puntos; riesgo de que falle el día de la evaluación | Precios inventados o desactualizados; resultados no repetibles; difícil de validar |

**Recomendación: A**, con la fuente de opciones separada del motor de comparación, de modo que conectar una API real (B) sea una mejora documentada y no una reescritura. Uso acotado del modelo de lenguaje, donde aporta sin inventar cifras: convertir en datos estructurados opciones que el usuario pega desde un sitio, y redactar en lenguaje llano la explicación de la recomendación a partir de números ya calculados.

### 3.4 Alcance de la demo

Dentro:
- Formulario de solicitud de viaje (proyecto, viajero, ruta, fechas, equipaje, probabilidad de cambio).
- Tres o cuatro escenarios [Simulado] diseñados para que la opción "más barata" no sea la mejor.
- Tabla comparativa de costo total con desglose.
- Perfil de fidelización por viajero y de empresa [Simulado].
- Cálculo dinero frente a puntos y alertas (vencimiento, canal que no acumula).
- Recomendación con explicación.
- Resultado: "presupuesto de viaje" guardado contra el proyecto.

Fuera: precios y disponibilidad en vivo, reserva o pago, consulta de saldos reales de millas, disponibilidad real de premios.

## 4. ¿Integrar los dos retos?

Hay un vínculo natural: el Reto 1 produce el **costo previsto** de un viaje para un proyecto; el Reto 2 produce el **gasto real** por proyecto.

| Opción | A favor | En contra |
|---|---|---|
| Independientes | Menor riesgo; cada una se entiende sola | Se pierde la historia más interesante para Finanzas |
| Integración total (una plataforma) | Coherencia | Contradice el alcance del enunciado; riesgo de no terminar |
| **Integración ligera (recomendada)** | Una sola aplicación con datos compartidos (proyecto, viajero, viaje) y un único punto de unión | Algo más de diseño inicial |

Integración ligera, en concreto:
- El viaje elegido en el Reto 1 queda como presupuesto del proyecto.
- Cuando llega al Reto 2 la confirmación del vuelo o del hotel, se empareja con ese viaje (viajero + fechas + ciudad), lo que resuelve la asignación a proyecto sin que nadie la digite.
- El tablero del proyecto muestra previsto frente a real.

Orden de construcción: primero el Reto 2 completo, luego el Reto 1, al final el punto de unión. Si el tiempo no alcanza, se recorta la unión y ambos siguen funcionando por separado.

**Lo que se decidió después.** La integración ligera se amplió: en lugar del proyecto como punto de unión, **el viaje es el eje**. Cada persona tiene un código; la decisión del Reto 1 crea un viaje a su nombre con presupuesto, que administración aprueba; cada gasto del Reto 2 se asigna solo a ese viaje (por quién lo envía y las fechas) y se valida contra su presupuesto; el proyecto agrupa viajes y gastos para comparar previsto frente a real. La unión dejó de ser lo primero que se recorta, porque la asignación automática del gasto y el control del presupuesto dependen de ella. El razonamiento para quien evalúa está en el README («Por qué integrados y no por separado»).

## 5. Supuestos e información faltante

Supuestos de trabajo:
- Equipo pequeño (decenas de personas), varios proyectos simultáneos en distintas ciudades.
- Operación en más de una moneda (al menos COP y USD).
- Finanzas trabaja hoy con hojas de cálculo y carpetas compartidas.
- Los viajes son mayormente nacionales o regionales, de pocos días.

Preguntas para la empresa:
1. ¿Qué significa "programas de fidelización de la empresa"? ¿Cuentas personales, programa corporativo o tarjeta de crédito? ¿Cuáles programas?
2. ¿Quién reserva hoy y quién aprueba? ¿Existe política de viajes (topes, anticipación)?
3. ¿Cuántos viajes y cuántos gastos al mes? ¿Cuántos proyectos activos?
4. ¿Por qué canales llegan realmente los soportes (correo, WhatsApp, Slack, Drive)?
5. ¿Dónde termina la información: hoja de cálculo, sistema contable, cuál?
6. ¿Se reembolsa a empleados, se usan anticipos o tarjeta corporativa?
7. ¿En qué países y monedas se opera? ¿Hay requisitos tributarios sobre los soportes?
8. ¿Cómo se identifican los proyectos (código, cliente, centro de costo)?
9. ¿Los proyectos tienen presupuesto de viaje definido de antemano?

## 6. Decisiones pendientes antes de construir

- Plazo de entrega.
- Enfoque por reto y nivel de integración.
- Tecnología (propuesta: Python con una interfaz web sencilla y base de datos local en un archivo).
- Modelo de lenguaje para la extracción y disponibilidad de clave de API (va en un `.env` excluido del repositorio).
