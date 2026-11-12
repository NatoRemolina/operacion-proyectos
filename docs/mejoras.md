# Mejoras de experiencia de uso e ingeniería

Resultado de cuatro revisiones de la plataforma (recorridos por rol, interfaz y accesibilidad, textos y respuestas, ingeniería de la interacción), hechas sobre el código y sobre 35 pantallas renderizadas en siete anchos. Cada hallazgo se comprobó contra el código antes de anotarlo; las cifras de contraste se recalcularon de forma independiente.

**Criterio.** La plataforma actual (pantallas servidas por el backend) es la que se entrega y se demuestra; la web nueva en Next.js la irá reemplazando. Por eso en la plataforma actual se corrigen los **errores y callejones sin salida**, y lo demás queda como **requisito de diseño de la web nueva**, para no hacer dos veces el mismo trabajo.

| Estado | Significado |
|---|---|
| Corregida | Ya está en la plataforma, con prueba |
| Asignada | Tiene dueño en un frente de trabajo concreto |
| Web nueva | Requisito de diseño para Next.js; no se toca en las pantallas actuales |
| Pendiente | Sin dueño todavía |

## Errores y callejones (plataforma actual)

| Id | Problema | Estado | Dónde |
|---|---|---|---|
| E01 | Al cotizar, el viajero por defecto no era quien cotiza: el viaje nacía a nombre de otra persona | Corregida | `viaje_nuevo.html`, `rutas/cotizaciones.py` |
| E02 | Una regla numérica mal escrita (`1,08`, `80 USD`) tumbaba cargas y cotizaciones | Corregida | `rutas/administracion.py`, `validacion.py`, `costo.py` |
| E03 | Sesión vencida: la carga decía «Revisa la conexión», el ingreso no volvía a la página pedida y el tablero mantenía viva la sesión | Corregida | `main.py`, `cargar.html`, `viajes_admin.html`, `acceso.py` |
| E04 | El formulario de decisión se mostraba a quien no podía decidir y acababa en error | Corregida | `viaje.html`, `rutas/cotizaciones.py` |
| E05 | Un viaje rechazado dejaba al piloto sin salida | Corregida | `viaje_detalle.html`, `inicio.html`, `ficha.html` |
| E06 | El gestor no podía abrir el tablero de su propio proyecto | Corregida | `acceso.py`, `rutas/proyectos.py`, `inicio.html` |
| E07 | Ver un viaje bastaba para cargarle gastos ajenos y para gastar consultas de pago | Corregida | `servicios/viajes.py`, `rutas/cotizaciones.py` |
| E08 | Una URL inexistente o un dato mal formado respondían JSON crudo; el secreto del webhook con caracteres no ASCII daba error 500 | Corregida | `main.py`, `rutas/telegram.py` |
| E09 | «Desactivar» alternaba el estado (un doble envío reactivaba la cuenta); decidir dos veces duplicaba la decisión | Corregida | `rutas/administracion.py`, `rutas/cotizaciones.py` |
| E10 | No había prueba de humo de todas las páginas por rol | Corregida | `tests/test_humo.py` |
| E11 | La vista de consultas al buscador tenía descarga pero no campo de fecha: la exportación fallaba | Corregida | `rutas/analisis.py` |
| E12 | Un mensaje de validación del revisor quedaba guardado como alerta del gasto y lo veía el piloto | Asignada: `integridad` | `rutas/gastos.py` |
| E13 | Rechazar un gasto no pedía motivo ni confirmación; el piloto no sabía por qué | Asignada: `integridad` | `rutas/gastos.py`, `gasto.html` |
| E14 | La revisión no comprobaba el estado que vio quien revisa: dos revisores se pisaban | Asignada: `integridad` | `rutas/gastos.py` |
| E15 | Importes nulos, cero o negativos; duplicado exacto sin comparar moneda; fechas futuras | Asignada: `integridad` | `validacion.py` |
| E16 | Telegram marcaba como procesada una entrega que había fallado | Asignada: `integridad` | `servicios/telegram.py` |
| E17 | La carga web no era idempotente: reintentar creaba otro gasto | Asignada: `integridad` | `servicios/gastos.py` |
| E18 | Sin transacción real: dos aprobaciones simultáneas podían pasar el presupuesto | Asignada: `integridad` | `db.py`, `rutas/gastos.py` |

## Textos y mensajes

| Id | Problema | Estado |
|---|---|---|
| T01 | Las alertas del gasto están escritas para el sistema («Confianza de lectura 62 %», «TimeoutError») y las lee el piloto | Asignada: `integridad` (textos en `validacion.py`); Web nueva para su presentación |
| T02 | Vocabulario mezclado: soporte, recibo y gasto; cotización, consulta y solicitud; titular y viajero | Web nueva (glosario abajo) |
| T03 | Horas en UTC y fechas en formato ISO: un piloto en Miami ve el día siguiente | Web nueva |
| T04 | Importes con tres formatos distintos | Web nueva |
| T05 | Tras cargar un recibo no se dice si quedó aprobado o en revisión | Web nueva (pantalla «Enviar recibo» del frente `web-next`) |
| T06 | Los estados vacíos dicen cosas falsas («carga los ejemplos» a quien no puede) | Web nueva |
| T07 | Éxito y error se ven iguales en la bandeja de aprobación | Web nueva |
| T08 | Los avisos viajan en la dirección de la página: se repiten al recargar | Web nueva (la API v1 responde JSON, sin avisos en la dirección) |
| T09 | Los botones en espera solo se atenúan; en celular parece colgado | Web nueva |
| T10 | Bot de Telegram: silencio ante fallos, `/start` repetido pide vincular de nuevo, «Aprobado» con dos sentidos | Pendiente: con Telegram real (27 respuestas propuestas en la revisión) |

### Glosario para la web nueva

| Concepto | Término único |
|---|---|
| Lo que la persona fotografía o envía | recibo |
| El registro que nace del recibo | gasto |
| La comparación de vuelos y hoteles | cotización |
| Una llamada al buscador de precios | búsqueda |
| Quien viaja | viajero («colaborador» es un permiso; «Pilotaje de dron», un cargo) |
| La elección de vuelo y hotel | decisión (el documento: ficha de decisión) |
| La aprobación del dinero | aprobación del presupuesto |
| Dinero autorizado / usado | presupuesto / gastado |
| Identificadores `P-` y `V-` | código |
| Audios y textos del chat | nota del viaje |

## Interfaz y accesibilidad (WCAG 2.2 AA)

Requisitos de diseño para la web nueva; el encargo `web-next` ya incluye los marcados con ✓.

| Id | Problema medido | Corrección |
|---|---|---|
| A01 ✓ | 151 de 244 campos sin nombre accesible | `<label for>` en todo campo |
| A02 ✓ | En celular, aprobar y comparar quedan fuera de pantalla (tablas de 766 a 1028 px en 345) | Tarjetas apiladas en lugar de tablas anchas |
| A03 ✓ | Foco (2,23:1) y borde de campos (1,54:1) bajo 3:1 | Foco en color de marca; borde `#7f8c9b` (3,43:1) |
| A04 ✓ | «Sobre el presupuesto» solo con color; rojo y azul con la misma luminancia (1,02:1) | Texto y porcentaje junto a la barra |
| A05 ✓ | Etiqueta verde «Aprobado» 4,40:1 | `#0f7653` (5,02:1) |
| A06 | Contador del menú 2,94:1 | Fondo `#9a6200` (5,10:1) y texto oculto «pendientes» |
| A07 ✓ | Enlaces distinguidos solo por color | Subrayados |
| A08 ✓ | Zonas táctiles de 13 a 30 px | Mínimo 44 px |
| A09 | Filtros activos sin estado programático | `aria-current` y estilo propio |
| A10 | Tablero que se actualiza solo sin pausa y que borra lo escrito | Casilla para pausar; no recargar con un campo enfocado |
| A11 | Siete gráficas sin alternativa textual | Etiqueta y datos en tabla desplegable |
| A12 ✓ | 20 de 35 pantallas saltan de `h1` a `h3` | Jerarquía sin saltos |
| A13 | 300 encabezados de tabla sin `scope` | `scope` y tablas clave-valor con `th` de fila |
| A14 | Menú desplegable sin cerrar con Escape | Cierre con Escape y al salir el foco |
| A15 | Sin sistema de botones (tamaños, estados, peligro) | Un primario por tarjeta; acciones destructivas con confirmación |
| A16 | Ocho tamaños de letra y 57 estilos en línea | Escala tipográfica y espaciados como variables |
| A17 | `/analitica` desborda la página a 320–390 px | Pendiente (pantalla de administración) |

## Recorridos por rol

| Id | Problema | Estado |
|---|---|---|
| R01 | Gestor sin pantalla propia; ve lo ajeno rotulado como propio | Parcial: corregido el acceso a sus proyectos (E06); pantalla propia en la web nueva |
| R02 | En la comparación se pierde toda la selección al fallar una validación o preguntar al agente | Web nueva |
| R03 | La comparación muestra tres cifras por vuelo | Web nueva |
| R04 | El detalle del viaje no muestra lo elegido ni el porqué al administrador que aprueba | Web nueva |
| R05 | Tras aprobar o rechazar un gasto no se pasa al siguiente ni se confirma | Web nueva |
| R06 | El recorrido de cinco pasos no enlaza a cada paso | Web nueva |

## Ingeniería

| Id | Problema | Estado |
|---|---|---|
| I01 | Cada consulta cuesta dos viajes de red en la nube (comprobación de conexión en cada préstamo) | Pendiente: antes de publicar |
| I02 | Monitoreo · calidad hace 51 consultas | Pendiente |
| I03 | Estáticos sin política de caché | Pendiente: antes de publicar |
| I04 | La cotización busca vuelos y hoteles en serie y puede dejar cotizaciones huérfanas si el proveedor responde algo inesperado | Pendiente |
| I05 | La política de contenido permite scripts en línea | Web nueva (sin scripts en línea) |
| I06 | Lógica de negocio dentro de rutas (comparación, revisión, tablero previsto/real) | Pendiente: al extraer servicios (ver `docs/arquitectura_objetivo.md`) |
| I07 | El cambio de contraseña no limita intentos | Pendiente |
| I08 | La cookie no se borra al salir en HTTPS (falta `secure` al borrarla; la sesión sí se revoca) | Pendiente: antes de publicar |
