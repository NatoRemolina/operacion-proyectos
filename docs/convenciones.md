# Convenciones del proyecto

Cómo se escribe, se prueba y se integra el código de este repositorio. Vale para cualquier persona que contribuya.

## Estilo

- **Español** en nombres, comentarios, mensajes de commit y textos de interfaz. Voz neutra: el código y la documentación describen lo que hace el sistema, no quién lo escribió.
- Comentarios solo donde explican un **porqué** que el código no deja ver.
- Se siguen los patrones existentes: rutas por área en `app/rutas/` (se cargan solas), lógica en `app/servicios/`, tablas declaradas con `db._tabla` en el módulo de su servicio, menú declarado como datos (`MENU`). No se introducen marcos ni capas nuevas sin una decisión registrada en `docs/adr/`.
- Textos para personas no técnicas: claros, sin jerga ni nombres internos. Los códigos de motivo (`importe_invalido`, `sin_viaje`…) son estables y no se renombran.
- Dinero: se valida y se compara con `Decimal` (`app/servicios/dinero.py`); nunca se compara un importe con `==` en coma flotante.

## API v1 (`/api/v1`, contrato en `contracts/`)

- Errores siempre en JSON con `code`, `message` y `request_id`; nunca HTML ni redirecciones.
- Toda escritura exige la cookie de sesión, el encabezado `X-CSRF-Token` y un `Origin` permitido (`ORIGENES_WEB`).
- El permiso se comprueba por registro con el alcance de la sesión (`acceso.alcance`, `acceso.puede_ver`); el rol nunca sale del cuerpo de la petición.
- Nadie aprueba ni revisa lo suyo (`viajes.revision_permitida`), tampoco por la API.
- Un envío con `Idempotency-Key` repetida devuelve el mismo resultado; con otro contenido, 409.
- Cambiar un endpoint obliga a regenerar el contrato (`python -m datos.exportar_contrato`) y a pasar `test_el_openapi_versionado_coincide_con_la_api`.

## Datos y migraciones

- Las migraciones son **idempotentes** (`datos/migracion.py`): ejecutarlas dos veces no cambia nada salvo el registro de auditoría. No hay archivos SQL sueltos ni un historial paralelo.
- Toda tabla nueva queda con seguridad por filas y sin permisos para los roles públicos en PostgreSQL.
- Arrancar en local solo prepara la base si es SQLite o si `PREPARAR_BASE_LOCAL=1` (la base desechable de `docker-compose.yml`). La base publicada nunca se prepara al arrancar: se migra solo con el procedimiento de `docs/despliegue.md` (respaldo reciente de esa misma base, puerto 5432 y confirmación escrita del destino).
- Todo dato que entra deja rastro: quién, cuándo, de dónde y qué (`eventos`, `consultas_buscador`, `cargas_datos`).
- Antes de migrar la base publicada: respaldo y ensayo de restauración (`docs/respaldo.md`).

## Servicios de pago y externos

- Cada consulta paga (buscador, modelo) se guarda y se registra; una consulta idéntica no se vuelve a pagar.
- Toda ruta que pueda gastar cupo tiene tope (por persona, por día, por viaje) y responde con datos guardados o «sin datos» cuando no hay clave.
- Las pruebas nunca llaman a un servicio en vivo: se simula el cliente.

## Pruebas

- Primero la prueba que falla, después el cambio.
- Antes de unir una rama, las pruebas pasan en los tres motores:
  - `make probar` (SQLite)
  - `make probar-postgres` (PostgreSQL de Docker, con `make entorno` arriba)
  - el proyecto de Supabase de pruebas cuando el cambio toca la base o las transacciones.
- Una prueba que solo vale en SQLite lo declara con `skipif(not config.ES_SQLITE)`.
- En `web/`: `npm run typecheck`, `npm run lint -- .` y `npm test`.

## Ramas, commits e integración

- Cada frente trabaja en su rama y su carpeta (`git worktree`), dueño de sus archivos. Se integra en una rama de trabajo, no directamente en `main`.
- Cada cambio pasa por una revisión antes de unirse; los hallazgos se corrigen en una ronda con su prueba y se vuelve a revisar.
- Commits pequeños, en español, con **un solo autor**: sin líneas `Co-authored-by`.
- Lo que no se versiona nunca: archivos `.env*`, credenciales, respaldos de la base, datos personales, configuración personal de herramientas.

## Ganchos de git

`make ganchos` instala los ganchos de `scripts/ganchos/` en la carpeta de git del repositorio (valen para todas sus carpetas de trabajo) sin cambiar la configuración de git:

| Gancho | Qué rechaza |
|---|---|
| `pre-commit` | Errores de `ruff` en los `.py` del commit; secretos en las líneas añadidas (claves de servicio, tokens, llaves privadas, cadenas de conexión con contraseña, datos de reserva); y, si existen, las palabras y rutas que cada equipo liste en `.git/info/palabras-vetadas` y `.git/info/rutas-vetadas` |
| `commit-msg` | Mensajes con líneas `Co-authored-by` y las palabras de `.git/info/palabras-vetadas` |

Las listas de `.git/info/` son locales: cada persona decide las suyas y no se versionan.
