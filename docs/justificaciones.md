# Justificación de los gastos

Cada gasto puede llevar una explicación de la persona que lo hizo: para qué fue, dicho con sus propias palabras, por escrito o en una nota de voz. Hoy sirve a quien revisa y al asistente de administración. Más adelante es la materia prima de un análisis de lenguaje por persona (temas, claridad, tono). Para que ese análisis tenga sentido hace falta mucho texto, y por eso se empieza a recoger desde ya.

## Cómo se pide

| Canal | Cómo se recoge |
|---|---|
| Web | Campo «¿Para qué fue este gasto?» al cargar el recibo (vale para todos los archivos del envío) y en el detalle de cada gasto, con texto o una nota de voz adjunta. Si el gasto está en revisión, la página lo pide expresamente |
| Telegram | Si la foto trae un pie, ese pie es la justificación (sin el código del viaje). Si no, el bot pregunta para qué fue. El siguiente mensaje o nota de voz de la persona, dentro de 30 minutos, queda como justificación de ese gasto |
| API v1 | Campo `justificacion` al enviar el recibo y `POST /api/v1/gastos/{id}/justificaciones` para añadir otra después |

Es opcional en todos los canales: un gasto nunca queda bloqueado por no tenerla.

## Qué se guarda

Tabla `justificaciones`, una fila por justificación (un gasto puede tener varias):

| Campo | Contenido |
|---|---|
| `gasto_id`, `usuario_id` | El gasto y la persona que lo explica |
| `tipo`, `canal` | `texto` o `audio`; `web`, `celular`, `telegram` o `api` |
| `texto` | Lo escrito, o la transcripción de la nota de voz (precedida del pie, si lo hubo) |
| `transcripcion` | `no_aplica` (texto), `pendiente` (sin modelo configurado), `hecha` o `fallida` |
| `documento_id` | El audio original, guardado como evidencia del viaje |
| `palabras`, `creado` | Longitud y momento, útiles para el análisis |

La nota de voz se transcribe con el mismo modelo que lee los recibos; cada llamada queda en `llamadas_modelo` con el uso `transcripcion`. Si el modelo no está configurado o falla, el audio se conserva y la transcripción queda pendiente o fallida para reintentarla (`justificaciones.transcribir`).

## Reglas

- **Solo justifica quien hizo el gasto o quien viaja.** El gestor y administración ven la justificación, pero no escriben en nombre de otra persona: el análisis futuro depende de que cada texto sea de quien dice ser.
- **Ninguna regla de aprobación lee su contenido.** La justificación informa a quien revisa; no aprueba ni rechaza nada por sí sola.
- El asistente de administración la indexa como una ficha más, con los códigos de persona, viaje y gasto, para responder preguntas como «¿qué explicó P-0002 de sus gastos en revisión?».
- `justificaciones.cobertura()` dice qué parte de los gastos tiene justificación: el primer indicador que hay que vigilar antes de cualquier análisis.

## Antes de analizar el lenguaje de las personas

Lo que hace falta decidir, y que no está construido:

1. **Volumen.** Con pocas decenas de justificaciones por persona, cualquier medida de tono o estilo es ruido. Conviene fijar un mínimo (por ejemplo, 30 por persona y varios viajes) antes de mostrar un resultado.
2. **Aviso y propósito.** Las personas deben saber que sus justificaciones se guardan y para qué se analizan. Es información personal y, en Europa, el análisis de cómo se expresa alguien entra en el tratamiento de datos que exige base legal, transparencia y, según el uso, una evaluación de impacto.
3. **Uso de los resultados.** Un análisis de sentimiento no debe decidir sobre una persona (evaluaciones, sanciones) sin revisión humana. Su uso razonable es agregado: qué categorías generan más fricción, qué explicaciones faltan, qué reglas confunden.
4. **Acceso.** Solo administración, con registro de quién consulta.
5. **Idioma y canal.** Hay texto escrito y voz transcrita, en español y en inglés; el análisis debe distinguirlos.
