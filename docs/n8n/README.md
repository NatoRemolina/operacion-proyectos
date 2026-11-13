# n8n: soportes de gastos a Google Drive

Cada vez que se registra un gasto (web, celular, Telegram, asistente o API), la plataforma avisa a n8n y n8n guarda el soporte original en Google Drive, ordenado así:

```
Inflight · Soportes / <proyecto> / <código del viaje> / <AAAA-MM> / <fecha · comercio · total moneda · código>.<extensión>
```

Por ejemplo: `Inflight · Soportes / Casa en Moab / V-2026-0012 / 2026-12 / 2026-12-09 · Shell · 54.00 USD · V-2026-0012.png`. Un gasto sin viaje va a la carpeta `Sin viaje`; uno sin fecha leída, al mes en curso.

n8n solo orquesta: la plataforma valida, decide y guarda; n8n copia el archivo.

## Cómo funciona

```
Plataforma ──POST firmado──▶ n8n: Webhook → Configuración → Verificar firma ─┬─ inválido → responde 401 (repetido → 200)
                                                                             └─ válido → responde 202 → Descargar soporte
                                                                                ──▶ carpetas (busca o crea 4 niveles) → Subir a Drive
```

1. **Aviso firmado** (`gasto.registrado`). La plataforma hace un POST JSON a `N8N_WEBHOOK_URL` con:
   - `X-Inflight-Evento: gasto.registrado`
   - `X-Inflight-Entrega: <uuid>`: el id de la entrega; se repite en los reintentos.
   - `X-Inflight-Firma: t=<segundos unix>,v1=<hex>`, con `hex = HMAC-SHA256(N8N_WEBHOOK_SECRETO, "<t>.<cuerpo tal cual>")`.
   - Cuerpo: `evento`, `entrega`, `gasto_id`, `viaje`, `proyecto`, `fecha`, `comercio`, `total`, `moneda`, `enlace_soporte`, `enlace_vence_en_segundos`. Nada más: ni la persona, ni el archivo.
2. **Verificar firma** (nodo Code) rechaza el aviso si la firma no coincide, si tiene más de 5 minutos, si el enlace no apunta a la plataforma configurada (así la clave de servicio nunca viaja a otro sitio) o si esa entrega ya se procesó.
3. **Descargar soporte**: GET al `enlace_soporte` (vence a los 15 minutos) con la cabecera `X-Clave-Servicio`. La plataforma exige las dos cosas: un enlace filtrado no sirve sin la clave, y la clave sola no recorre los soportes por número. La descarga queda en la bitácora del gasto con el nombre de la clave («n8n»).
4. **Carpetas**: para cada nivel (raíz, proyecto, viaje, mes) busca la carpeta por nombre exacto dentro de la anterior y, si no existe, la crea.
5. **Subir a Drive** con el nombre legible.

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

En la nube van en el secreto de la función (hay que añadirlas a `CLAVES` en `infra/poblar_secreto.py`).

### 4. En n8n

1. **Credencial de la clave de servicio**: abrir el nodo «Descargar soporte» → *Credential for Header Auth* → *Create new credential* → **Name** `X-Clave-Servicio`, **Value** la clave `isk_…` del paso 1 → *Save*.
2. **Credencial de Google Drive**: abrir el nodo «Buscar carpeta raíz» → *Credential to connect with* → *Create new credential* → *Sign in with Google* → elegir la cuenta donde vivirán los soportes y aceptar los permisos de Drive → *Save*. Después, en cada uno de los otros nodos de Google Drive (las otras tres búsquedas, las cuatro «Crear carpeta …» y «Subir a Drive») elegir esa misma credencial en el desplegable.
3. **Secreto**: si el plan de n8n tiene *Variables* (Overview → Variables), crear `INFLIGHT_WEBHOOK_SECRETO` con el secreto del paso 2. Si no, abrir el nodo «Configuración» y pegarlo en `secreto_webhook` en lugar de `PEGAR_AQUI_N8N_WEBHOOK_SECRETO` (queda visible para quien edite el flujo).
4. En «Configuración», revisar `url_plataforma` (la misma que `URL_PUBLICA`) y `carpeta_raiz`.
5. *Save* y, cuando todo lo anterior esté listo, activar el flujo (interruptor *Inactive → Active*).

### 5. Probar

Registrar un gasto con un recibo de ejemplo y comprobar:

- En n8n → *Executions*: una ejecución terminada en verde.
- En Drive: el archivo en `Inflight · Soportes / … / AAAA-MM`.
- En la plataforma: `python -m datos.avisos estado` muestra el aviso como `entregado`, y la bitácora del gasto tiene «aviso entregado» y «soporte descargado por integración» (fuente `n8n`).

## Seguridad

- La clave de servicio se guarda como huella (SHA-256), tiene un solo permiso (`soportes:leer`) y solo sirve en `/api/v1/servicio/…`: no abre ninguna otra parte de la API.
- La firma cubre la hora y el cuerpo exacto; n8n rechaza avisos de más de 5 minutos y entregas repetidas (recuerda las últimas 500).
- El enlace al soporte se firma con una clave derivada del secreto del aviso: rotar `N8N_WEBHOOK_SECRETO` invalida los enlaces pendientes.
- Para rotar la clave de servicio: crear otra, cambiarla en la credencial de n8n y revocar la anterior.

## Pendiente

- Los avisos pendientes se reintentan cuando llega otro gasto o al correr `python -m datos.avisos reintentar`. Para que el reintento no dependa de eso, falta programar esa orden (por ejemplo, una regla de EventBridge cada 5 minutos que invoque la función).
- Los demás eventos del diseño (`gasto.aprobado`, `gasto.rechazado`, `viaje.aprobado`, `viaje.presupuesto_80`) usarían la misma bandeja y la misma firma; no están hechos.
- Si la plataforma reintenta una entrega que n8n ya había recibido (por ejemplo, porque la respuesta tardó más de 3 segundos), n8n la reconoce por su id y no la duplica, siempre que el flujo esté activo (la memoria de entregas solo se guarda en ejecuciones de producción).
