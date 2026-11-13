# Respaldo y restauración de la base publicada

## Por qué hace falta

La base publicada vive en Supabase, en una organización con **plan gratuito**. Ese plan **no hace respaldos automáticos**: Supabase los incluye desde el plan Pro (diarios, 7 días) y recomienda que los proyectos gratuitos exporten sus datos con regularidad y guarden la copia fuera de Supabase ([documentación](https://supabase.com/docs/guides/platform/backups)). Además, los respaldos de la base **no incluyen los archivos de Storage**: los recibos del bucket `soportes` se copian aparte.

Tamaño al 12 de noviembre de 2026: 13 MB de base y 8 recibos (148 kB). Una copia completa tarda segundos.

## Qué hace `datos/respaldar.py`

| Orden | Qué hace | Qué escribe |
|---|---|---|
| `respaldar` | Copia el esquema `public` con `pg_dump` (formato restaurable `base.dump` y estructura legible `estructura.sql`), descarga los recibos del bucket y guarda `manifiesto.json` con el conteo de filas de cada tabla y la huella SHA-256 de cada archivo | **Nada en la base de origen**: `pg_dump` solo lee y los conteos van en una sesión de solo lectura |
| `verificar` | Comprueba las huellas, restaura la copia en una base **nueva** del destino y compara tabla por tabla con el manifiesto | Solo la base nueva que se indica con `--base` |

`pg_dump` y `pg_restore` corren en Docker con la imagen `postgres:17`, la misma versión del servidor; no hay que instalar nada. La conexión viaja en variables de entorno del contenedor: nunca aparece en la línea de órdenes ni en la salida.

Protecciones de `verificar` (con pruebas en `tests/test_respaldar.py`):
- se niega a restaurar en el mismo servidor y usuario de los que salió la copia (el manifiesto guarda una huella del origen, sin la contraseña);
- se niega a usar `postgres` u otra base principal, y a reutilizar una base que ya existe;
- se detiene si un archivo del respaldo no coincide con su huella.

## Archivos de conexión (locales, ignorados por git)

| Archivo | Para qué | Contenido |
|---|---|---|
| `.env.supabase-publicada` | Origen del respaldo | `DATABASE_URL` (Session pooler, puerto 5432; puede traer `[YOUR-PASSWORD]`), `DATABASE_PASSWORD`, `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` del proyecto publicado |
| `.env.supabase-pruebas` | Destino del ensayo | La misma forma, del proyecto de pruebas |

Las claves se escriben solo en esos archivos; nunca en un chat, un ticket ni un archivo versionado.

## Procedimiento antes de la migración final

1. **Copiar** (solo lectura sobre la publicada):
   ```
   make respaldar
   ```
   Deja la carpeta en `~/Respaldos/operacion-proyectos/AAAA-MM-DD_HHMM/`.
2. **Ensayar la restauración** en el proyecto de pruebas:
   ```
   make verificar-respaldo RESPALDO=~/Respaldos/operacion-proyectos/AAAA-MM-DD_HHMM BASE=restauracion_AAAAMMDD
   ```
   Debe terminar con «Todas las tablas coinciden con el manifiesto».
3. **Ensayar la migración con los datos reales**: apuntar la migración (`python -m datos.semilla`) a esa base restaurada y comprobar con `python -m datos.comprobar_supabase` que queda en orden. Así la migración final ya se habrá hecho una vez sobre una copia exacta.
4. **Cifrar la copia** antes de moverla: los respaldos tienen correos, contraseñas cifradas y recibos. En macOS, una imagen de disco cifrada:
   ```
   hdiutil create -encryption AES-256 -srcfolder ~/Respaldos/operacion-proyectos/AAAA-MM-DD_HHMM -volname respaldo respaldo-AAAA-MM-DD.dmg
   ```
   Pide la contraseña de forma interactiva. Guardar el `.dmg` fuera del equipo (otro disco o almacenamiento propio de la empresa) y borrar la carpeta sin cifrar.

## El día de la migración final

1. Respaldo fresco justo antes (pasos 1 y 2).
2. Migración, `comprobar_supabase` y prueba rápida: entrar, ver viajes, cargar un recibo.
3. **Vuelta atrás, decidida de antemano:** si algo falla, restaurar `base.dump` sobre el proyecto publicado y volver a desplegar la versión anterior de la aplicación. Esta restauración se hace a mano y con la aplicación detenida, porque reemplaza datos de producción. Con las variables `PG*` del proyecto publicado cargadas en la terminal (puerto 5432, el agrupador de sesión) y `RESPALDO` apuntando a la carpeta de la copia:
   1. **Guardar el estado fallido** con `make respaldar` (otra carpeta): lo que se borra en el paso siguiente queda recuperable.
   2. **Borrar lo que la copia no trae.** La migración añade tablas con claves foráneas hacia las de antes (`envios_soporte`, `envios_cotizacion`, `tramos_vuelo`, `cargos`…) y vistas nuevas; mientras existan, `pg_restore --clean` no puede borrar las tablas de antes, termina con errores y deja la base mezclada. La lista se genera comparando las tablas del código con las del manifiesto, así que incluye sola cada tabla nueva:
      ```
      python -m datos.respaldar vuelta-atras --respaldo "$RESPALDO" > vuelta_atras.sql
      docker run --rm -i -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE=postgres -e PGSSLMODE=require postgres:17 \
        psql -v ON_ERROR_STOP=1 --single-transaction -q < vuelta_atras.sql
      ```
      Conviene leer `vuelta_atras.sql` antes de correrlo: solo trae `drop view` de las vistas del código y `drop table` de las tablas que la copia no tiene.
   3. **Restaurar en una sola transacción**: si algo falla, no cambia nada de lo que restaura y se puede repetir tras corregir.
      ```
      docker run --rm -i -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGSSLMODE=require postgres:17 \
        pg_restore --no-owner --no-privileges --clean --if-exists --single-transaction --exit-on-error -d postgres < "$RESPALDO/base.dump"
      ```
   4. **Comprobar** que los conteos coinciden con el manifiesto (`python -m datos.comprobar_supabase` y la tabla `filas` de `manifiesto.json`).

   Con el tamaño actual tarda menos de un minuto. Los recibos se vuelven a subir solo si se borró alguno. El procedimiento está probado en PostgreSQL con una migración que añade tablas y cambia la restricción de permisos (`tests/test_vuelta_atras.py`, con `PRUEBAS_POSTGRES_SERVIDOR`): sin el paso 2 la restauración falla y, por ser una sola transacción, no deja nada a medias.

## Después: respaldo con la plataforma en uso

| Opción | Cómo | Costo | Pérdida máxima |
|---|---|---|---|
| A. Plan Pro de Supabase | Respaldo diario automático, 7 días, restauración desde el panel | 25 USD/mes | 1 día |
| B. Respaldo nocturno propio | Una tarea programada en AWS ejecuta `respaldar` y copia el resultado a un bucket S3 privado y cifrado, con 14 días de retención y alarma si falla | Centavos al mes | 1 día |
| C. Pro con recuperación a un punto en el tiempo | Restauración al minuto | ~125 USD/mes | Unos 2 minutos |

Recomendación: la opción B mientras el volumen sea pequeño, y la A cuando la operación dependa de la plataforma a diario. Cualquiera de ellas se ensaya con `verificar` al menos una vez al mes: un respaldo que no se ha restaurado nunca no está probado.
