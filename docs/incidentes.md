# Incidentes

Cada incidente se escribe sin culpables: qué pasó, cuánto duró, por qué no se vio antes, qué se arregló y qué impide que se repita. Las cifras salen de la base publicada, consultada solo con lectura.

## 13 nov 2026 · El asesor del asistente falló en cada pregunta durante 8 horas

**Impacto.** Las 8 sesiones del asesor registradas en producción, entre las 13:33 y las 21:39 UTC, fallaron con el mismo motivo. Ninguna de las 9 preguntas registradas hasta entonces la respondió el asesor: el asistente respondió igual con la vía siguiente, 8 con el modelo de lenguaje y 1 en modo determinista. Nadie recibió un error: las respuestas fueron más pobres (sin el razonamiento del asesor), pero correctas en sus cifras, porque todas las vías usan las mismas consultas.

**Causa.** `ASESOR_AGENTE_VERSION` quedó mal pegada en el archivo de producción y llegó así al secreto: no era un número. El asesor validaba la versión al abrir cada sesión, así que fallaba antes de llamar al servicio. La versión se copiaba a mano después de cada `python -m datos.asesor --sincronizar`.

**Por qué no se vio.**
- Las alarmas miraban los errores de la aplicación (`ERROR peticion=`) y las respuestas 5xx. Un fallo del asesor no produce ninguno de los dos: el asistente lo trata como esperado y responde con otra vía.
- El motivo quedaba en el evento `asesor sin respuesta` y en «Últimos errores del modelo», en Monitoreo. Para verlo había que ir a buscarlo.
- Ni la carga del secreto ni el arranque revisaban la forma del valor.

**Arreglo inmediato.** Corregir el valor en `.env.produccion` y volver a cargar el secreto (`docs/despliegue.md`, paso 3).

**Qué impide que se repita** (`docs/mejoras.md`, I10 a I13):

| Capa | Antes | Ahora |
|---|---|---|
| Carga del secreto | Subía cualquier texto | `infra/poblar_secreto.py` revisa la forma de lo escrito a mano y no sube nada si algo está mal, tampoco si el valor malo ya estaba en el secreto |
| Arranque | Nada | Una línea `ERROR peticion=arranque` por variable mal escrita: la cuenta la alarma `ErroresDeLaAplicacion` |
| Comportamiento | El asesor fallaba en cada pregunta | Una versión forzada mal escrita se ignora y se usa la del candado; la configuración a medias apaga el asesor, y la respuesta lo dice |
| Origen de la versión | Copiada a mano | Candado versionado `app/asesor_agente.json`, escrito por `--sincronizar` |
| Detección | Leer los errores uno por uno | Alarma `CaidasDelAsesor` (3 caídas en 15 min) y cifra «Respondió el asesor» en Monitoreo |
| Comprobación tras desplegar | No había | Paso 7 de `docs/despliegue.md`: sin `ERROR peticion=arranque` y una pregunta que cuente como del asesor |

**Lección.** Lo opcional puede degradarse, pero no en silencio. Cada vía de respaldo necesita su propia señal, porque desde fuera una respuesta del respaldo se ve igual que una del camino principal.
