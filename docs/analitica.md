# Analítica y monitoreo

La plataforma no tiene "un tablero": tiene un sistema de medición. Cada gasto y cada búsqueda dejan hechos; de los hechos salen métricas con una sola definición; las métricas alimentan pantallas, descargas y una API; y cada corrección humana vuelve como dato para evaluar la lectura automática.

## Capas

| Capa | Qué es | Dónde está |
|---|---|---|
| 1. Hechos | Registros que solo se añaden: bitácora (`eventos`), llamadas al modelo de lenguaje (`llamadas_modelo`), respuestas del buscador (`busquedas`), opciones mostradas en cada decisión (`elecciones`), errores (`errores`) | `app/db.py` |
| 2. Modelo analítico | Vistas con el hecho y sus dimensiones ya unidas: `v_h_gasto`, `v_h_busqueda`, `v_h_decision`, `v_h_lectura`, `v_h_evento` | `datos/semilla.py` (`VISTAS`) |
| 3. Métricas | Catálogo único: nombre, fórmula, unidad y para qué sirve. Todas aceptan proyecto, desde y hasta | `app/servicios/metricas.py` |
| 4. Señales | Importe atípico, duplicado aproximado, calibración de la confianza, campos corregidos | `app/servicios/inteligencia.py`, `app/servicios/validacion.py` |
| 5. Consumo | Consola `/admin/monitoreo`, descargas CSV, `/api/metricas` | `app/main.py`, `app/templates/monitoreo.html` |

Las vistas no copian datos. Con el volumen actual se calculan al consultarlas; si crece, se materializan sin tocar lo demás.

## Catálogo de métricas

| Nombre en la API | Definición | Decisión que apoya |
|---|---|---|
| `tasa_sin_intervencion` | Gastos aprobados solos ÷ gastos recibidos | Cuánto trabajo manual se evita |
| `tiempo_a_aprobado` | Mediana, en segundos, entre "documento recibido" y la aprobación | Dónde se atasca la revisión |
| `tasa_correccion` | Campos que difieren entre lo leído y lo aprobado ÷ campos leídos | Calidad real de la lectura |
| `pendientes_revision` | Gastos en estado de revisión | Carga de quien revisa |
| `gasto_real` | Suma en USD de los gastos aprobados | Control financiero |
| `costo_por_recibo` | Costo estimado de tokens ÷ lecturas | Elección de modelo |
| `acuerdo_recomendacion` | Decisiones que eligen la opción recomendada ÷ decisiones | Validez de las reglas |
| `ahorro_capturado` | Costo esperado del más barato del buscador − costo esperado de lo elegido | Valor del comparador |
| `tasa_reutilizacion` | Búsquedas resueltas con respuestas guardadas ÷ búsquedas | Costo del buscador |
| `decisiones_etiquetadas` | Decisiones con todas sus opciones registradas | Avance hacia un modelo de decisión |

```
GET /api/metricas                       catálogo
GET /api/metricas?nombre=gasto_real&proyecto_id=1&desde=2026-11-01&hasta=2026-11-30
```

La API exige sesión de administrador, igual que la consola.

## Señales automáticas

- **Importe atípico.** Por categoría y moneda, se compara con la mediana y la desviación absoluta mediana de los gastos aprobados. Son medidas robustas: un gasto enorme anterior no mueve la referencia. Con menos de cuatro gastos comparables no opina.
- **Duplicado aproximado.** Mismo comercio (normalizado), fecha a un día de distancia e importe con 1 % de diferencia, además del duplicado exacto por huella del archivo.
- **Calibración.** Tasa de corrección por tramo de confianza declarada. Sirve para mover el umbral de aprobación automática con evidencia.
- **Ciclo de retroalimentación.** La lectura original se conserva junto a lo aprobado; la diferencia es la etiqueta de evaluación.
- **Datos para el modelo de decisión.** Cada decisión guarda todas las opciones mostradas, su orden, cuál se recomendó, cuál se eligió y las razones marcadas. Ninguna opción llega preseleccionada, para no fabricar etiquetas.

Todas van a revisión humana con su explicación; ninguna rechaza por sí sola.

## Registro de errores

Cada petición recibe un identificador (cabecera `X-Peticion`). Si algo falla, el error queda en la tabla `errores` y en los logs con ese identificador, y la persona lo ve en pantalla para poder reportarlo. Se consulta en la pestaña Auditoría.

## Conectar Power BI o Tableau

Las herramientas externas son una capa de consumo más; no hace falta para operar. Si se quieren usar:

1. En la base, crear un rol de solo lectura con permiso únicamente sobre las vistas:
   ```sql
   create role lectura_bi login password '…';
   grant usage on schema public to lectura_bi;
   grant select on v_h_gasto, v_h_busqueda, v_h_decision, v_h_lectura, v_h_evento to lectura_bi;
   ```
2. Conectar con el conector de PostgreSQL de la herramienta, usando la dirección del agrupador de conexiones en modo sesión y SSL obligatorio.
3. Modelar con las vistas como tablas de hechos. Las fechas son texto ISO (`AAAA-MM-DD HH:MM:SS`, en UTC): convertirlas a fecha y hora en la herramienta.
4. Mantener las fórmulas de la tabla de arriba; si una cifra del tablero externo no coincide con `/api/metricas`, manda la API.

Costos a considerar frente a la consola incluida: licencia por persona, un segundo ingreso y datos que salen de la plataforma.

## Límites actuales

Con pocos gastos y pocas decisiones, varias cifras son demostrativas: prueban que la tubería funciona, no describen el negocio. El pronóstico de gasto por proyecto, el modelo de decisión y la vigilancia de deriva del modelo de precios quedan diseñados y esperan datos.
