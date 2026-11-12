# Plan de construcción: buscador mundial, cargos y monitoreo del vuelo

> Para quien ejecute: se implementa tarea por tarea; cada paso usa casillas (`- [ ]`) para seguir el avance.

**Objetivo:** cotizar desde y hacia cualquier lugar del mundo con el mejor acceso, que toda persona de la empresa viaje con su cargo, y seguir el vuelo el día del viaje.

**Arquitectura:** todo vive en la aplicación FastAPI actual. Servicios nuevos en `app/servicios/` (`geografia.py`, `monitoreo_vuelos.py`), cambios acotados en `precios.py`, `costo.py`, `viajes.py`, `acceso.py` y en las rutas de cotización, gastos, viajes y administración. Los datos geográficos se preparan una vez y viajan en el repositorio. La web Next.js solo recibe el cargo y el nuevo nombre del permiso.

**Tecnología:** Python 3.12, FastAPI, SQLAlchemy Core (SQLite y PostgreSQL), Jinja, JavaScript sin dependencias en las pantallas actuales; Next.js 16 con zod en `web/`.

**Diseño:** `docs/diseno/2026-11-12-buscador-mundial-y-cargos.md`. Léase junto con este plan.

## Restricciones globales

- Entrega el viernes 13 por la mañana. Orden fijo de tareas; lo que no alcance queda fuera completo, nunca a medias.
- El mismo código en SQLite y PostgreSQL. Pruebas sin internet y sin claves.
- Comparar varios aeropuertos gasta **una** búsqueda al cotizar y **una** al decidir (regreso con `departure_token`).
- Valores fijados por el diseño, todos como reglas editables en `reglas` (ámbito `supuesto`):
  - radio 400 km; 4 aeropuertos como máximo; solo aeropuertos con servicio regular;
  - distancia por carretera = línea recta × 1,3; velocidad 70 km/h; bajo 30 km no hay línea de traslado;
  - traslado sin carro: 0,35 USD/km ida y vuelta, grupo `traslados`; con carro (`carro_dia` > 0): 0,12 USD/km ida y vuelta, grupo `combustible`;
  - monitoreo: ventana desde 3 h antes de la salida hasta la llegada, caché de 30 min, tope de 6 consultas por tramo, aviso por retraso ≥ 15 min (o que crece 15 min más), cancelación, cambio de terminal o de puerta;
  - `deep_search` desactivado.
- Cargos iniciales: «Pilotaje de dron», «Edición de video», «Desarrollo de software», «Ingeniería de datos», «Producción».
- El permiso `piloto` pasa a `colaborador` en base, código, API v1 y web.
- Datos: OurAirports (dominio público) y GeoNames `cities1000` (CC BY 4.0, citar en README y en el pie del buscador).
- Trazabilidad: todo dato que entra queda registrado (quién, cuándo, de dónde, qué) en `eventos`, `consultas_buscador` o la tabla nueva `cargas_datos` de la tarea 5; cada tarea lo prueba.
- Sin push ni despliegue. Voz neutra; sin menciones a asistentes en lo versionado. Antes de cada commit: `git grep -i -E "claude|anthropic"` sin resultados nuevos.
- Verificación de cada tarea: `.venv/bin/ruff check .` y `.venv/bin/python -m pytest -q`; en `web/`: `npm run typecheck` (genera los tipos de Next antes de `tsc`), `npx eslint --max-warnings=0 .`, `npx vitest run`.

## Puntos de atención

Entradas que el diseño implica y que ninguna prueba obvia cubre; cada una tiene su prueba en la tarea que la posee:

1. **Lugar sin aeropuertos con servicio regular en el radio** (una isla o un pueblo muy aislado): la sugerencia lo dice («Sin aeropuertos con vuelos regulares a menos de 400 km») y la persona puede marcar aeropuertos buscándolos por nombre. Prueba en la tarea 6.
2. **Homónimos** (Moab de Utah y Moab de Jordania; San José de Costa Rica y de California): se distinguen por región y país, y la población ordena. Prueba en la tarea 6.
3. **Sin clave del buscador o consulta en vivo fallida con varios códigos:** se usa una respuesta guardada si la hay; si no, la cotización muestra «sin datos» y no falla. Prueba en la tarea 8.
4. **El traslado cruza la medianoche o la hora límite:** llegada 22:40 + 3 h de traslado frente a límite 16:00 del día siguiente se compara con fecha y hora, no solo con la hora. Prueba en la tarea 9.
5. **La consulta de estado no trae el bloque del vuelo** (número inexistente, fecha fuera de rango): el tramo queda «sin datos», no se avisa y cuenta para el tope. Prueba en la tarea 11.

---

### Tarea 1: Unir la web Next.js a `dev`

**Archivos:** rama `worktree-web-next` → `dev`. Sin cambios de código salvo conflictos.

- [ ] **Paso 1:** `git merge --no-ff worktree-web-next` en `dev`. Esperado: sin conflictos (la rama solo toca `web/`).
- [ ] **Paso 2:** backend `.venv/bin/python -m pytest -q` en verde; en `web/`: `npm ci`, `npx tsc --noEmit`, `npx eslint --max-warnings=0 .`, `npx vitest run` en verde.
- [ ] **Paso 3:** `make entorno-web` y recorrido en `http://127.0.0.1:8088`: entrar como `piloto@demo.local`, ver viajes, enviar un recibo con justificación, verlo en `127.0.0.1:8000`. Apagar con `make entorno-abajo`.
- [ ] **Paso 4:** commit del merge (mensaje por defecto de git en español: «Une la web Next.js a dev»).

### Tarea 2: Permiso colaborador y cargos

**Archivos:**
- Modificar: `app/db.py` (tabla `cargos`, columna `usuarios.cargo_id`, restricción `ck_usuarios_rol` con `colaborador`), `datos/migracion.py`, `datos/semilla.py`, `app/servicios/acceso.py`, `app/rutas/administracion.py`, `app/templates/usuarios.html`, `app/api_v1/esquemas.py`, `app/servicios/consultas.py` o donde se arme `Persona`, `contracts/api-v1.md`, `contracts/openapi-v1.json` (regenerar), todos los usos de `"piloto"` como permiso (`git grep -n "'piloto'\|\"piloto\""`), plantillas y pruebas.
- Web: `web/src/features/auth/domain/auth.ts`, su esquema zod en `auth-http.ts`, `web/src/shared/ui/marco-privado.tsx`, fábricas y datos de demostración.
- Crear: `tests/test_cargos.py`.

**Interfaces que produce:**
- `acceso.ROLES = ("colaborador", "gestor", "admin")`; `acceso.NOMBRE_ROL["colaborador"] == "colaborador"`.
- `acceso.cargos(solo_activos: bool = True) -> list[dict]` (`id`, `nombre`, `activo`, `personas`).
- `acceso.crear_cargo(nombre: str) -> int` (nombre único sin distinguir mayúsculas; `ValueError` si existe o tiene menos de 3 letras).
- `acceso.cambiar_cargo(cargo_id: int, nombre: str | None = None, activo: bool | None = None) -> None`.
- `acceso.crear_usuario(correo, nombre, rol, clave, viajero_id=None, cargo_id=None) -> int`: crea perfil de viajero para **todo** rol, con `viajeros.rol` = nombre del cargo o «Viajero».
- `Persona` (API v1) gana `cargo: str | None`; `Rol = Literal["colaborador", "gestor", "admin"]`.

- [ ] **Paso 1: pruebas que fallan** en `tests/test_cargos.py`:
  - `test_la_migracion_pasa_piloto_a_colaborador_con_su_cargo`: tras `migracion.ejecutar()`, `piloto@demo.local` tiene `rol == "colaborador"` y cargo «Pilotaje de dron»; ninguna fila con `rol='piloto'`; ejecutar dos veces no cambia nada.
  - `test_toda_cuenta_tiene_perfil_de_viajero`: gestor y admin de demostración tienen `viajero_id` no nulo tras migrar; `crear_usuario(..., "gestor", ...)` crea perfil.
  - `test_administracion_crea_renombra_y_desactiva_cargos`: `POST /admin/cargos` crea «Fotografía»; nombre repetido da aviso; desactivar un cargo con personas lo desactiva y no lo borra; un cargo inactivo no aparece al crear cuentas.
  - `test_el_cargo_no_da_permisos`: una cuenta `colaborador` con cargo «Edición de video» recibe 403 en `/admin/usuarios` y ve solo lo suyo en `/gastos`.
  - `test_la_api_devuelve_rol_y_cargo`: `GET /api/v1/auth/me` del piloto devuelve `rol == "colaborador"` y `cargo == "Pilotaje de dron"`.
- [ ] **Paso 2:** correr `pytest tests/test_cargos.py -q`: fallan.
- [ ] **Paso 3:** implementar. Rutas nuevas en `administracion.py`: `POST /admin/cargos` (crear) y `POST /admin/cargos/{cid}` (`accion` = `renombrar` | `estado`); `POST /admin/usuarios/{uid}` gana `accion == "cargo"` con `cargo_id`. La migración: actualizar filas, recrear la restricción solo si no incluye `colaborador`, sembrar los cinco cargos, asignar «Pilotaje de dron» a quien era piloto y crear perfiles faltantes.
- [ ] **Paso 4:** actualizar pruebas existentes que dicen `piloto` como permiso; regenerar `python -m datos.exportar_contrato`; actualizar `contracts/api-v1.md`.
- [ ] **Paso 5:** web: tipo `Rol`, esquema zod con `cargo`, el marco privado muestra el cargo bajo el nombre; ajustar fábricas y pruebas.
- [ ] **Paso 6:** verificación completa (backend y web) en verde.
- [ ] **Paso 7:** commit «Permiso colaborador y cargos de la empresa».

### Tarea 3: Todos viajan y nadie aprueba lo suyo

**Archivos:** `app/rutas/cotizaciones.py` (línea del `if _yo().get("rol") == "piloto"`), `app/servicios/viajes.py` (`cambiar_estado`), `app/rutas/gastos.py` (`gasto_guardar`), `app/templates/viajes_admin.html`, `app/templates/gasto.html`. Crear `tests/test_autoaprobacion.py`.

**Interfaces:**
- `viajes.es_propio_de(viaje: dict, u: dict) -> bool` (titular o viajero de la persona).
- `viajes.cambiar_estado` devuelve `(False, "Nadie aprueba ni rechaza su propio presupuesto: debe hacerlo otra persona de administración.")` para `aprobar` y `rechazar` sobre un viaje propio.
- Revisión de gasto propio: redirección con aviso «Nadie revisa sus propios gastos: debe hacerlo otra persona de administración.».

- [ ] **Paso 1: pruebas que fallan:**
  - `test_un_gestor_cotiza_y_el_viaje_queda_a_su_nombre`: el gestor de demostración cotiza (respuesta guardada MIA-LAS) sin elegir viajero, decide y el viaje tiene `usuario_id` del gestor.
  - `test_admin_no_aprueba_su_propio_presupuesto`: admin cotiza para sí, decide; `POST /admin/viajes/{vid}` con `accion=aprobar` deja el viaje `pendiente_aprobacion` y muestra el aviso; un segundo admin (creado en la prueba) sí lo aprueba.
  - `test_admin_no_revisa_su_propio_gasto`: admin carga un recibo propio; `POST /gastos/{gid}` con `accion=aprobar` no cambia el estado.
  - `test_con_un_solo_admin_se_explica_en_pantalla`: con un solo admin activo y un viaje propio pendiente, `/admin/viajes` muestra «Hace falta otra persona de administración para aprobarlo».
  - `test_admin_cotiza_para_otra_persona_como_hoy`: admin elige `viajero_id` de Laura y el viaje queda a nombre de Laura.
- [ ] **Paso 2:** correr: fallan.
- [ ] **Paso 3:** implementar. En `viaje_crear`, todo rol con `viajero_id` cotiza para sí salvo que gestor o admin elijan otro viajero explícitamente (campo `para_otra_persona`); la regla de bloqueo vive en el servicio, no en la plantilla.
- [ ] **Paso 4:** verificación en verde. Commit «Todas las cuentas viajan y nadie aprueba lo suyo».

### Tarea 4: El cargo en la analítica

**Archivos:** `datos/semilla.py` (vistas `v_h_viaje`, `v_h_gasto`), `app/servicios/kpis.py` y su plantilla, `app/templates/` de la ficha por persona. Prueba en `tests/test_kpis.py`.

**Interfaces:** columna `cargo` (texto) en `v_h_viaje` y `v_h_gasto`; `kpis.por_cargo() -> list[dict]` con `cargo`, `viajes`, `gasto_usd`, `en_revision`.

- [ ] **Paso 1: prueba que falla** `test_gasto_y_viajes_por_cargo`: con un gasto aprobado del piloto y uno de una cuenta «Edición de video», `kpis.por_cargo()` devuelve dos filas con sus sumas; la página `/admin/kpis` muestra «Gasto por cargo».
- [ ] **Paso 2:** implementar (vistas recreadas en ambos motores, la exportación CSV de vistas sigue funcionando).
- [ ] **Paso 3:** verificación. Commit «El cargo en la analítica».

### Tarea 5: Datos geográficos del mundo

**Archivos:**
- Crear: `datos/geografia.py` (preparación), `datos/geografia/aeropuertos.csv`, `datos/geografia/lugares.csv.gz`, `datos/geografia/paises.csv`, `datos/geografia/regiones.csv`, `datos/geografia/FUENTES.md`, `tests/datos/geografia_mini/` (los mismos cuatro archivos, pocas filas), `app/servicios/geografia.py` (tablas y carga).
- Modificar: `datos/semilla.py` (carga idempotente), `Makefile` (`make geografia`).

**Interfaces:**
- Tablas: `aeropuertos_mundo` (`iata` único, `nombre`, `municipio`, `pais`, `region`, `lat`, `lon`, `grande` 0/1), `lugares` (`id` = geonameid, `nombre`, `buscable` texto normalizado con nombre, ASCII y alternos, `pais`, `region`, `lat`, `lon`, `poblacion`), `paises` (`codigo`, `nombre_es`, `nombre_en`).
- `geografia.normalizar(texto: str) -> str` (minúsculas, sin tildes, espacios simples).
- `geografia.cargar(directorio: Path) -> dict` → `{"aeropuertos": n, "lugares": n, "paises": n}`; no hace nada si ya están cargados con el mismo número de filas.

- [ ] **Paso 1:** con aprobación ya dada en el diseño, descargar a una carpeta temporal fuera del repositorio: OurAirports `airports.csv` y `countries.csv`, GeoNames `cities1000.zip` y `admin1CodesASCII.txt`. Filtrar aeropuertos a `iata_code` no vacío, `scheduled_service == "yes"` y tipo `large_airport` o `medium_airport` o `small_airport`; `grande = type == "large_airport"`. Nombres de país en español con Node: `new Intl.DisplayNames(["es"], {type: "region"}).of(codigo)`. Escribir los archivos de `datos/geografia/`. Esperado: unos 4.000 aeropuertos y unos 150.000 lugares; el `.gz` por debajo de 10 MB (si pasa, recortar alternos a los de 3 a 40 caracteres y quitar duplicados).
- [ ] **Paso 2: prueba que falla** `tests/test_geografia.py::test_carga_idempotente_del_subconjunto`: `cargar(tests/datos/geografia_mini)` dos veces deja el mismo conteo; `paises` tiene «Estados Unidos» para `US`.
- [ ] **Paso 3:** implementar tablas y `cargar`; la semilla carga `datos/geografia/` (en pruebas, `conftest.py` carga el subconjunto).
- [ ] **Paso 4:** verificación; medir que `make ejecutar` arranca y la carga completa en SQLite tarda menos de 60 s (si no, carga por lotes con `insertar_varios`).
- [ ] **Paso 5:** commit «Datos geográficos del mundo: aeropuertos, lugares y países», con atribución a GeoNames en `FUENTES.md`.

### Tarea 6: Búsqueda de lugares y aeropuertos cercanos

**Archivos:** `app/servicios/geografia.py`, crear `app/rutas/lugares.py`. Pruebas en `tests/test_geografia.py`.

**Interfaces:**
- `geografia.distancia_km(lat1, lon1, lat2, lon2) -> float` (haversine).
- `geografia.cercanos(lat: float, lon: float, radio_km: float | None = None, maximo: int | None = None) -> list[dict]` → `[{"iata", "nombre", "municipio", "km", "grande"}]` ordenados por distancia; por defecto toma radio y máximo de las reglas.
- `geografia.buscar(q: str, limite: int = 8) -> list[dict]` → cada resultado `{"tipo": "lugar" | "aeropuerto" | "pais", "id", "nombre", "region", "pais", "lat", "lon", "aeropuertos": [...], "aviso": str | None}`. Para un país, `aeropuertos` son sus `grande = 1` (hasta 6).
- `GET /lugares/buscar?q=&limite=8` (requiere sesión, categoría usuario) → JSON `{"resultados": [...]}`; `q` con menos de 2 caracteres → lista vacía.

- [ ] **Paso 1: pruebas que fallan** (con el subconjunto):
  - `test_moab_sugiere_sus_aeropuertos_cercanos`: primer resultado `Moab`, región `Utah`, país `Estados Unidos`, aeropuertos `["CNY", "GJT", "SLC"]` en ese orden con `km` creciente.
  - `test_homonimos_se_distinguen_por_pais`: «moab» también trae el de Jordania, después del de Utah.
  - `test_codigo_iata_y_pais`: «LIS» trae primero el aeropuerto de Lisboa; «portugal» trae el país con LIS y OPO; «lisboa» y «Lisboa» dan lo mismo.
  - `test_villa_de_leyva_propone_bogota`: BOG entre sus aeropuertos.
  - `test_lugar_aislado_lo_dice` (punto de atención 1): un lugar del subconjunto sin aeropuertos a 400 km trae `aeropuertos == []` y `aviso == "Sin aeropuertos con vuelos regulares a menos de 400 km. Busca un aeropuerto por nombre o código."`.
  - `test_la_ruta_exige_sesion_y_responde_rapido`: anónimo recibe 303/401; con sesión, 200 en menos de 300 ms con el subconjunto.
- [ ] **Paso 2:** fallan. **Paso 3:** implementar; la búsqueda por prefijo usa `buscable like :q || '%' or buscable like '% ' || :q || '%'` con índice en `buscable`, limitada y ordenada por población; los cercanos filtran primero por un recuadro de latitud y longitud y después por haversine en Python.
- [ ] **Paso 4:** verificación; probar a mano con los datos completos que «moab» responde en menos de 300 ms en SQLite y en PostgreSQL (`make entorno`). Commit «Búsqueda mundial de lugares y aeropuertos cercanos».

### Tarea 7: El formulario de cotización con el buscador

**Archivos:** `app/templates/viaje_nuevo.html` (más un archivo `app/static/buscador_lugares.js` cargado con el bloque de scripts de la plantilla), `app/rutas/cotizaciones.py` (`viaje_crear`), `app/db.py` (columnas en `solicitudes`), `datos/migracion.py`. Pruebas en `tests/test_cotizacion_mundial.py`.

**Interfaces:**
- Columnas nuevas en `solicitudes`: `origen_lugar` y `destino_lugar` (JSON: `nombre`, `region`, `pais`, `lat`, `lon`), `origen_aeropuertos` y `destino_aeropuertos` (códigos separados por coma, ordenados).
- `viaje_crear` acepta además `origen_aeropuertos: str` y `destino_aeropuertos: str` (códigos separados por coma) y `origen_lugar` y `destino_lugar` (JSON). Sin ellos, el comportamiento actual con `origen` y `destino` sigue igual (compatibilidad).
- `solicitudes.origen` y `solicitudes.destino` = aeropuerto marcado más cercano al lugar (o el primero).

- [ ] **Paso 1: pruebas que fallan:**
  - `test_cotizar_hacia_un_pueblo_guarda_lugar_y_aeropuertos`: POST con destino Moab y `destino_aeropuertos=CNY,GJT,SLC` guarda la lista ordenada, el lugar y `destino == "CNY"`.
  - `test_formulario_antiguo_sigue_funcionando`: POST con `origen=Miami (MIA)` y `destino=Las Vegas (LAS)` sin campos nuevos produce la misma solicitud que hoy.
  - `test_codigos_invalidos_se_rechazan`: `destino_aeropuertos=ZZZ` (no existe en `aeropuertos_mundo`) vuelve al formulario con el aviso de hoy.
- [ ] **Paso 2:** fallan. **Paso 3:** implementar. El campo muestra sugerencias mientras se escribe (pide `/lugares/buscar` con espera de 200 ms tras la última tecla, navegable con flechas y Enter, con `role="listbox"` y `aria-activedescendant`); al elegir, dibuja las casillas de aeropuertos con km y tiempo estimado; pie «Lugares: GeoNames (CC BY 4.0). Aeropuertos: OurAirports.».
- [ ] **Paso 4:** verificación y prueba a mano en el navegador (escritorio y celular). Commit «El formulario de cotización busca cualquier lugar del mundo».

### Tarea 8: Una búsqueda para varios aeropuertos

**Archivos:** `app/servicios/precios.py` (`buscar_vuelos`, `buscar_hoteles` sin cambios de firma), `app/rutas/cotizaciones.py`. Pruebas en `tests/test_cotizacion_mundial.py`.

**Interfaces:**
- `precios.buscar_vuelos(origen: str | list[str], destino: str | list[str], ida: str, regreso: str, solicitud_id: int | None = None)`: con listas, una consulta con `departure_id` y `arrival_id` unidos por coma; nombre de archivo `vuelos_{A-B}_{C-D-E}_{ida}_{regreso}.json` con los códigos ordenados y unidos por guion. Con una sola cadena, idéntico a hoy.
- La búsqueda de hotel usa `destino_lugar["nombre"]` si existe; si no, la ciudad del primer aeropuerto marcado.

- [ ] **Paso 1: pruebas que fallan:**
  - `test_varios_aeropuertos_una_sola_consulta`: con `httpx.get` simulado, cotizar Miami → Moab (3 aeropuertos) hace **una** llamada al buscador de vuelos con `arrival_id == "CNY,GJT,SLC"` y deja una fila en `consultas_buscador`.
  - `test_sin_clave_ni_respaldo_no_falla` (punto de atención 3): sin `SERPAPI_KEY` y sin archivo guardado, la cotización redirige a la comparación con «sin datos» y estado 303, nunca 500.
  - `test_la_respuesta_guardada_de_un_solo_codigo_sigue_valiendo`: MIA-LAS 18–21 nov usa el respaldo de siempre.
  - `test_parametros_estables_para_la_cache_del_proveedor`: `MIA` con `[GJT, CNY, SLC]` y con `[SLC, GJT, CNY]` envían exactamente los mismos parámetros (`arrival_id == "CNY,GJT,SLC"`) y nunca `no_cache`.
- [ ] **Paso 2:** fallan. **Paso 3:** implementar. **Paso 4:** verificación. Commit «Una búsqueda compara varios aeropuertos».

### Tarea 9: El traslado por carretera en el costo

**Archivos:** `app/servicios/costo.py`, `app/rutas/cotizaciones.py` (`_comparacion`, `viaje_decidir`), `app/servicios/viajes.py` (`presupuesto_de` reconoce los grupos `traslados` y `combustible`), `datos/semilla.py` (reglas nuevas), plantillas de la comparación y la ficha. Pruebas en `tests/test_cotizacion_mundial.py`.

**Interfaces:**
- Reglas nuevas (ámbito `supuesto`): `radio_aeropuertos_km=400`, `maximo_aeropuertos=4`, `factor_carretera=1.3`, `velocidad_carretera_kmh=70`, `traslado_minimo_km=30`, `traslado_usd_km=0.35`, `combustible_usd_km=0.12`.
- `costo.traslado(aeropuerto: dict | None, lugar: dict | None, con_carro: bool, cat: dict) -> dict | None` → `{"iata", "km_carretera", "horas", "valor", "concepto", "grupo"}`; `None` si falta el lugar o la distancia es menor que el mínimo. `concepto` = «Traslado por carretera desde GJT (141 km, unas 2 h)» o «Combustible y peajes desde GJT (…)».
- `costo.evaluar(...)` agrega las líneas de traslado de salida y de llegada (origen «supuesto») y descarta con «Con el traslado llega a las HH:MM, después de la hora límite.» comparando fecha y hora.

- [ ] **Paso 1: pruebas que fallan:**
  - `test_traslado_suma_y_cambia_el_orden`: con una respuesta simulada donde SLC es 120 USD más barato que CNY, la línea de traslado de SLC (unos 420 km por carretera × 0,35 × 2) hace que CNY quede primero.
  - `test_con_carro_solo_combustible`: con `carro_dia=60`, la línea es «Combustible y peajes…» a 0,12 USD/km y grupo `combustible`.
  - `test_bajo_30_km_no_hay_linea`: un aeropuerto a 20 km del lugar no agrega traslado.
  - `test_traslado_y_hora_limite_con_cambio_de_dia` (punto de atención 4): llegada 22:40 a un aeropuerto a 3 h y límite 16:00 del día siguiente no se descarta; límite 01:00 del día siguiente sí, con el motivo exacto.
  - `test_el_presupuesto_incluye_el_traslado`: al decidir, `presupuesto_detalle` tiene la línea con grupo `traslados` y el total la suma.
- [ ] **Paso 2:** fallan. **Paso 3:** implementar. **Paso 4:** verificación. Commit «El traslado por carretera cuenta en el costo y en la hora límite».

### Tarea 10: Tramos del vuelo al decidir

**Archivos:** `app/servicios/precios.py`, crear `app/servicios/monitoreo_vuelos.py` (tabla y registro de tramos), `app/rutas/cotizaciones.py` (`viaje_decidir`). Pruebas en `tests/test_monitoreo_vuelos.py`.

**Interfaces:**
- `precios.vuelo_regreso(vuelo_ida: dict, origenes: list[str], destinos: list[str], ida: str, regreso: str, solicitud_id: int | None = None) -> dict | None`: una consulta con `departure_token`; elige el regreso de menor precio; guarda la respuesta como las demás; `None` sin token, sin clave o si falla.
- Tabla `tramos_vuelo`: `viaje_id` (FK), `sentido` (`ida` | `regreso`), `orden`, `aerolinea`, `numero` (por ejemplo «IB 5634»), `fecha`, `desde`, `hasta`, `sale_programada`, `llega_programada`, `estado` (`programado` por defecto), `retraso_salida`, `retraso_llegada`, `terminal`, `puerta`, `llega_estimada`, `actualizado`, `consultas` (entero, 0), `ultimo_aviso` (JSON).
- `monitoreo_vuelos.registrar_tramos(viaje_id: int, vuelo_ida: dict, vuelo_regreso: dict | None) -> int` (idempotente: reemplaza los tramos del viaje).
- `_vuelo` en `precios.py` conserva por tramo: `aerolinea`, `numero`, `desde`, `hasta`, `sale`, `llega` (lista `tramos`).
- Al decidir, `solicitudes.origen` y `destino` pasan a `desde` del primer tramo y `hasta` del último.

- [ ] **Paso 1: pruebas que fallan:**
  - `test_decidir_registra_tramos_de_ida_y_regreso`: con respuestas simuladas, decidir deja 2 tramos de ida (con escala) y 1 de regreso con sus números, y gasta exactamente una consulta extra.
  - `test_sin_regreso_igual_se_decide`: si `vuelo_regreso` devuelve `None`, la decisión se guarda con solo los tramos de ida y un evento «regreso sin datos».
- [ ] **Paso 2:** fallan. **Paso 3:** implementar. **Paso 4:** verificación. Commit «La decisión registra los tramos del vuelo».

### Tarea 11: Estado del vuelo, tablero y avisos

**Archivos:** `app/servicios/precios.py` (`estado_vuelo`), `app/servicios/monitoreo_vuelos.py`, `app/rutas/viajes.py` (tablero y ruta de actualización), `app/templates/viajes_admin.html`, `datos/respaldo/estado_vuelo_IB5634_<fecha>.json`. Pruebas en `tests/test_monitoreo_vuelos.py`.

**Interfaces:**
- `precios.estado_vuelo(numero: str, fecha: str, solicitud_id: int | None = None) -> dict | None` → `{"estado", "retraso_salida", "retraso_llegada", "terminal_salida", "puerta_salida", "terminal_llegada", "puerta_llegada", "sale_estimada", "llega_estimada"}`; motor `google`, `q = f"Flight {numero}"`; registra en `consultas_buscador` con tipo `estado_vuelo`; `None` si la respuesta no trae el bloque del vuelo para esa fecha.
- `monitoreo_vuelos.consultar(tramo_id: int, ahora: datetime | None = None, forzar: bool = False) -> dict` → el tramo actualizado más `"consultado": bool` y `"motivo"` si no consultó («fuera de la ventana», «consultado hace menos de 30 min», «tope de 6 consultas»). `forzar` salta la caché, nunca el tope ni la ventana.
- `monitoreo_vuelos.del_dia(fecha: str) -> list[dict]` (tramos del día con el viaje y la persona).
- `monitoreo_vuelos.aviso(antes: dict, despues: dict) -> str | None` (puro): texto del aviso o `None`.
- `GET /admin/viajes/vuelos` (JSON para el tablero) y `POST /admin/vuelos/{tramo_id}/actualizar`.

- [ ] **Paso 1:** obtener una respuesta real con la clave de `.env` (una búsqueda) para un vuelo del día y guardarla en `datos/respaldo/`; confirmar los nombres de los campos y escribirlos en el docstring de `estado_vuelo`. Si no hay clave, construir el respaldo con la forma que documenta el proveedor y dejarlo dicho en el docstring.
- [ ] **Paso 2: pruebas que fallan:**
  - `test_ventana_cache_y_tope`: fuera de la ventana no consulta; dos llamadas en 10 minutos consultan una vez; la séptima en el día no consulta y dice «tope de 6 consultas».
  - `test_aviso_solo_cuando_cambia_algo`: `aviso` devuelve texto para retraso 0 → 20, `None` para 20 → 25, texto para 20 → 40, texto para cambio de puerta y para «cancelado»; nunca para la misma información repetida.
  - `test_retraso_avisa_una_vez_por_telegram`: con el bot simulado, dos consultas con el mismo retraso de 20 min envían un solo mensaje al titular.
  - `test_respuesta_sin_bloque_queda_sin_datos` (punto de atención 5): el tramo queda «sin datos», `consultas` aumenta y no hay aviso.
  - `test_tablero_muestra_el_estado_y_la_hora_limite`: `/admin/viajes` del día muestra estado, retraso, terminal y puerta, y marca «No llega a la grabación» si la llegada estimada más el traslado supera la hora límite.
- [ ] **Paso 3:** fallan. **Paso 4:** implementar; el tablero pide `/admin/viajes/vuelos` en el mismo ciclo de 15 s que ya existe; cada fila tiene «Actualizar ahora».
- [ ] **Paso 5:** verificación. Commit «Monitoreo del vuelo el día del viaje con avisos por Telegram».

### Tarea 12: Documentación y verificación final

**Archivos:** `README.md` (cotización mundial, cargos, monitoreo, atribución de GeoNames y OurAirports), `docs/datos.md` (tablas nuevas en el diagrama), `docs/kpis.md` (gasto por cargo, consultas `estado_vuelo`), `docs/arquitectura_objetivo.md` (sección de referencias que enlaza patrones de eShop con cada anillo).

- [ ] **Paso 1:** actualizar documentos en voz neutra.
- [ ] **Paso 2:** verificación completa (backend y web) y recorrido en `make entorno-web`:
  1. Una editora cotiza Miami → Moab.
  2. Compara CNY, GJT y SLC con traslado.
  3. Decide.
  4. Otra persona de administración aprueba.
  5. El tablero muestra los tramos con la respuesta de ejemplo.
  6. Llega un aviso simulado.
- [ ] **Paso 3:** commit «Documentación del buscador mundial, los cargos y el monitoreo». Sin push.
