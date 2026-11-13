# n8n: soportes y lecturas de gastos a Google Drive

Cada vez que se registra un gasto (web, celular, Telegram, asistente o API), la plataforma avisa a n8n con lo que leyó de la factura, y n8n guarda en Google Drive el soporte original, la lectura en JSON al lado y una fila en la hoja «Lecturas». Los archivos quedan ordenados así:

```
Inflight · Soportes / <proyecto> / <código del viaje> / <AAAA-MM> / <fecha · comercio · total moneda · código>.<extensión>
```

Por ejemplo: `Inflight · Soportes / Casa en Moab / V-2026-0012 / 2026-12 / 2026-12-09 · Shell · 54.00 USD · V-2026-0012.png`, y al lado `… · V-2026-0012 · lectura.json`. Un gasto sin viaje va a la carpeta `Sin viaje`; uno sin fecha leída, al mes en curso.

n8n solo orquesta: la base es la de la plataforma (Supabase), que valida, decide y guarda la lectura original en `gastos.extraido`; n8n copia el archivo, la lectura y una fila a Drive para compartirlos o auditarlos.

## Cómo funciona

```
Plataforma ──POST firmado──▶ n8n: Webhook → Configuración → Verificar firma ─┬─ inválido → responde 401 (repetido → 200)
                                                                             └─ válido → responde 202 → Descargar soporte
                                                                                ──▶ carpetas (busca o crea 4 niveles) → Subir a Drive
                                                                                ──▶ Preparar lectura → Subir lectura (JSON) → Fila de la hoja → Agregar a la hoja
```

1. **Aviso firmado** (`gasto.registrado`). La plataforma hace un POST JSON a `N8N_WEBHOOK_URL` con:
   - `X-Inflight-Evento: gasto.registrado`
   - `X-Inflight-Entrega: <uuid>`: el id de la entrega; se repite en los reintentos.
   - `X-Inflight-Firma: t=<segundos unix>,v1=<hex>`, con `hex = HMAC-SHA256(N8N_WEBHOOK_SECRETO, "<t>.<cuerpo tal cual>")`.
   - Cuerpo: `evento`, `entrega`, `gasto_id`, `viaje`, `proyecto`, `persona` (código, no el nombre), `fecha`, `comercio`, `categoria`, `total`, `moneda`, `total_usd`, `estado`, `alertas`, `enlace_gasto`, `lectura`, `enlace_soporte` y `enlace_vence_en_segundos`. El archivo no viaja en el aviso: se descarga con el enlace.
   - `lectura` es la lectura original del modelo: comercio, fecha, categoría, base, impuesto, propina, total, moneda, método de pago, canal de reserva, ciudad, **número de factura**, **identificación tributaria del proveedor** (NIT, RUT, NIF, VAT o EIN), **líneas de detalle** (`descripcion`, `cantidad`, `total`), confianza y dudas. `null` si la lectura falló. Todos los números viajan como texto con dos decimales (`"119.00"`), para que la firma se verifique igual en JavaScript.
2. **Verificar firma** (nodo Code) rechaza el aviso si la firma no coincide, si tiene más de 5 minutos, si el enlace no apunta a la plataforma configurada (así la clave de servicio nunca viaja a otro sitio) o si esa entrega ya se procesó.
3. **Descargar soporte**: GET al `enlace_soporte` (vence a los 15 minutos) con la cabecera `X-Clave-Servicio`. La plataforma exige las dos cosas: un enlace filtrado no sirve sin la clave, y la clave sola no recorre los soportes por número. La descarga queda en la bitácora del gasto con el nombre de la clave («n8n»).
4. **Carpetas**: para cada nivel (raíz, proyecto, viaje, mes) busca la carpeta por nombre exacto dentro de la anterior y, si no existe, la crea.
5. **Subir a Drive** con el nombre legible.
6. **Preparar lectura** y **Subir lectura**: el gasto y su `lectura` como JSON, en la misma carpeta y con el mismo nombre base (`… · lectura.json`).
7. **Fila de la hoja** y **Agregar a la hoja**: una fila por gasto en la pestaña «Lecturas» (*append or update* por la columna `Gasto`, así que un reintento no la duplica). La hoja se escribe en modo `RAW`: un texto que empieza con `=` nunca se vuelve fórmula, un número de factura «000123» conserva sus ceros y «12-10» no se convierte en fecha; los importes y la confianza van como números. Si la hoja no está configurada, el flujo termina después de subir los archivos.

Si n8n no responde o responde con error, el gasto se registra igual: el aviso queda pendiente en la tabla `avisos_salientes` y se reintenta a los 1, 5, 30, 120 y 720 minutos (con la misma entrega y con un enlace y una firma nuevos). Los pendientes se reintentan cuando se registra otro gasto y n8n responde, o con `python -m datos.avisos reintentar`. Estado de la bandeja: `python -m datos.avisos estado`.

## Configuración, paso a paso

El flujo ya está creado en la instancia de n8n, **inactivo**, con el nombre «Inflight · Soportes de gastos a Google Drive». También se puede importar desde [`soportes-a-drive.json`](soportes-a-drive.json) (menú ⋯ → *Import from File*); el archivo no tiene secretos ni credenciales.

### 1. Clave de servicio (en la plataforma)

Desde el equipo, con la conexión a la base de la plataforma:

```bash
python -m datos.claves_servicio crear n8n --permiso soportes:leer
```

Muestra la clave (`isk_…`) **una sola vez**. Otras órdenes: `listar` y `revocar <número>`. Una clave revocada deja de servir en el acto (401).

### 2. Secreto del aviso

Un valor aleatorio largo, el mismo en la plataforma y en n8n. Para generarlo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3. Variables de la plataforma

| Variable | Valor | Si falta |
|---|---|---|
| `N8N_WEBHOOK_URL` | La *Production URL* del nodo «Aviso gasto.registrado»: `https://<instancia>.app.n8n.cloud/webhook/inflight/gasto-registrado` | Avisos apagados |
| `N8N_WEBHOOK_SECRETO` | El secreto del paso 2 | Avisos apagados |
| `URL_PUBLICA` | `https://software.nataliaremolinarodriguez.com` (sin barra final) | En local se usa `http://localhost:8000`; fuera de local, avisos apagados |

En la nube van en el secreto de la función: `infra/poblar_secreto.py` ya las incluye en `CLAVES`, así que basta con tenerlas en el archivo de origen al poblar el secreto.

### 4. En n8n

1. **Credencial de la clave de servicio**: abrir el nodo «Descargar soporte» → *Credential for Header Auth* → *Create new credential* → **Name** `X-Clave-Servicio`, **Value** la clave `isk_…` del paso 1 → *Save*.
2. **Credencial de Google Drive**: abrir el nodo «Buscar carpeta raíz» → *Credential to connect with* → *Create new credential* → *Sign in with Google* → elegir la cuenta donde vivirán los soportes y aceptar los permisos de Drive → *Save*. Después, en cada uno de los otros nodos de Google Drive (las otras tres búsquedas, las cuatro «Crear carpeta …» y «Subir a Drive») elegir esa misma credencial en el desplegable.
3. **Secreto**: si el plan de n8n tiene *Variables* (Overview → Variables), crear `INFLIGHT_WEBHOOK_SECRETO` con el secreto del paso 2. Si no, abrir el nodo «Configuración» y pegarlo en `secreto_webhook` en lugar de `PEGAR_AQUI_N8N_WEBHOOK_SECRETO` (queda visible para quien edite el flujo).
4. En «Configuración», revisar `url_plataforma` (la misma que `URL_PUBLICA`) y `carpeta_raiz`.
5. **Hoja de lecturas**: en Google Drive, crear una hoja de cálculo «Inflight · Lecturas de facturas» con una pestaña llamada `Lecturas` y esta primera fila (los encabezados, en este orden):

   `Gasto | Fecha de carga (UTC) | Estado | Proyecto | Viaje | Persona | Comercio | NIT o ID fiscal | N.º factura | Fecha | Categoría | Base | Impuesto | Propina | Total | Moneda | Total USD | Confianza | Dudas | Alertas | Líneas | Soporte en Drive | Lectura en Drive | Gasto en la plataforma`

   Copiar la dirección de la hoja (`https://docs.google.com/spreadsheets/d/…/edit`) en `hoja_lecturas` del nodo «Configuración». En el nodo «Agregar a la hoja» → *Credential to connect with* → *Create new credential* (Google Sheets) → *Sign in with Google* con la misma cuenta → *Save*. «Subir lectura» usa la credencial de Google Drive del punto 2.
6. *Save* y, cuando todo lo anterior esté listo, activar el flujo (interruptor *Inactive → Active*).

### 5. Probar

Registrar un gasto con un recibo de ejemplo y comprobar:

- En n8n → *Executions*: una ejecución terminada en verde.
- En Drive: el archivo en `Inflight · Soportes / … / AAAA-MM` y, al lado, `… · lectura.json` con el número de factura, la identificación tributaria y las líneas.
- En la hoja «Lecturas»: una fila con el gasto, los datos de la factura y los tres enlaces.
- En la plataforma: `python -m datos.avisos estado` muestra el aviso como `entregado`, y la bitácora del gasto tiene «aviso entregado» y «soporte descargado por integración» (fuente `n8n`).

## Seguridad

- La clave de servicio se guarda como huella (SHA-256), tiene un solo permiso (`soportes:leer`) y solo sirve en `/api/v1/servicio/…`: no abre ninguna otra parte de la API.
- La firma cubre la hora y el cuerpo exacto; n8n rechaza avisos de más de 5 minutos y entregas repetidas (recuerda las últimas 500).
- El enlace al soporte se firma con una clave derivada del secreto del aviso: rotar `N8N_WEBHOOK_SECRETO` invalida los enlaces pendientes.
- Para rotar la clave de servicio: crear otra, cambiarla en la credencial de n8n y revocar la anterior.
- **Datos personales que salen a Drive:** el soporte original (puede traer el nombre de quien viaja o del huésped), la lectura en JSON y la fila de la hoja: código de la persona (no su nombre), comercios, importes, identificación tributaria del proveedor, método de pago (por ejemplo «Visa 4417», con los últimos dígitos de la tarjeta) y las descripciones de las líneas, que pueden nombrar a huéspedes. Compartir la carpeta y la hoja solo con contabilidad.
- **Lo que guarda n8n:** el flujo no guarda las ejecuciones exitosas (`saveDataSuccessExecution: none`), porque llevarían la lectura y el archivo; las fallidas sí, para poder revisarlas, y n8n Cloud las borra según la retención del plan.

## Para los flujos siguientes
- **Permisos:** una clave lleva una lista de permisos `recurso:acción` del catálogo `PERMISOS` de `app/servicios/claves_servicio.py` (hoy solo `soportes:leer`). Un flujo nuevo añade su permiso al catálogo y su endpoint bajo `/api/v1/servicio/` lo pide con `autorizar`. Ninguna clave aprueba, rechaza ni revisa: un permiso con esas acciones no entra al catálogo (la aplicación no arranca) ni a una clave, y `autorizar` lo niega aunque esté escrito a mano en la base.
- **Eventos:** todo aviso sale de `avisos.emitir(evento, datos)` con un evento del catálogo `EVENTOS` de `app/servicios/avisos.py` (hoy solo `gasto.registrado`), con la misma firma, la misma bandeja y los mismos reintentos. Cada evento declara si lleva el enlace temporal al soporte.

## Pendiente

- Los avisos pendientes se reintentan cuando llega otro gasto o al correr `python -m datos.avisos reintentar`. Para que el reintento no dependa de eso, falta programar esa orden (por ejemplo, una regla de EventBridge cada 5 minutos que invoque la función).
- Los demás eventos del diseño (`gasto.aprobado`, `gasto.rechazado`, `viaje.aprobado`, `viaje.presupuesto_80`) usarían la misma bandeja y la misma firma; no están hechos. Con ellos, la fila de la hoja se actualizaría con lo que corrige administración (hoy refleja la lectura y el estado al registrarse).
- Si la plataforma reintenta una entrega que n8n ya había recibido (por ejemplo, porque la respuesta tardó más de 3 segundos), n8n la reconoce por su id y no la duplica, siempre que el flujo esté activo (la memoria de entregas solo se guarda en ejecuciones de producción).
