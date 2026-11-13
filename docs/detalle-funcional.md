# Detalle funcional

Detalle de cada función de la plataforma, movido desde el [README](../README.md) para que este se lea alrededor de la lógica de negocio. La regla completa está en [`regla-de-negocio.md`](regla-de-negocio.md) y la visión técnica, en la [guía técnica](guia-tecnica.md) y el [informe técnico](informe-tecnico.md). Las rutas escritas como código (`docs/…`, `app/…`, `contracts/…`) son relativas a la raíz del repositorio.

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
- **Nadie aprueba lo suyo:** el presupuesto de un viaje y los gastos de una persona de administración los aprueba o los revisa otra persona de administración. El servicio lo impide y deja el intento en la bitácora; reabrir y cerrar el propio viaje sí se permite. Detalle en [`docs/regla-de-negocio.md`](regla-de-negocio.md).

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
