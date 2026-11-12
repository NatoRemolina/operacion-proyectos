# Modelo de datos y regla de negocio

La base es relacional (PostgreSQL en la nube, SQLite en local, con el mismo código). El eje es el **viaje**: une la cotización con los gastos.

```
persona ──► cotización ──► decisión ──► VIAJE ──► gastos y evidencias
                                          ▲
                                 aprobación de administración
```

## Diagrama entidad-relación

```mermaid
erDiagram
  USUARIOS ||--|| VIAJEROS : "perfil operativo"
  CARGOS ||--o{ USUARIOS : "qué hace en la empresa"
  USUARIOS ||--o{ SESIONES : abre
  USUARIOS ||--o{ PROYECTO_MIEMBROS : gestiona
  PROYECTOS ||--o{ PROYECTO_MIEMBROS : tiene
  VIAJEROS ||--o{ MEMBRESIAS : tiene
  PROYECTOS ||--o{ SOLICITUDES : agrupa
  USUARIOS ||--o{ SOLICITUDES : cotiza
  VIAJEROS ||--o{ SOLICITUDES : "viaja en"
  SOLICITUDES ||--o{ OPCIONES : ofrece
  SOLICITUDES ||--o{ DECISIONES : recibe
  DECISIONES ||--o{ ELECCIONES : "opciones mostradas"
  SOLICITUDES ||--o| VIAJES : "se convierte en"
  DECISIONES ||--o{ VIAJES : "fija el presupuesto"
  USUARIOS ||--o{ VIAJES : "es titular"
  PROYECTOS ||--o{ VIAJES : agrupa
  VIAJES ||--o{ GASTOS : acumula
  VIAJES ||--o{ DOCUMENTOS : "evidencias"
  DOCUMENTOS ||--o{ GASTOS : origina
  USUARIOS ||--o{ GASTOS : reporta
  PROYECTOS ||--o{ GASTOS : imputa
  SOLICITUDES }o..o{ AEROPUERTOS_MUNDO : "aeropuertos marcados (códigos IATA en texto)"
  LUGARES }o..o{ AEROPUERTOS_MUNDO : "cercanos, por distancia"
  PAISES ||..o{ LUGARES : "código de país"
  USUARIOS ||--o{ VINCULOS_TELEGRAM : solicita
  GASTOS ||--o{ JUSTIFICACIONES : "para qué fue"
  USUARIOS ||--o{ JUSTIFICACIONES : escribe
  DOCUMENTOS ||--o| JUSTIFICACIONES : "nota de voz"
  USUARIOS {
    int id PK "se muestra como P-0007"
    text correo UK
    text rol "permiso: colaborador, gestor o admin"
    int cargo_id FK "opcional; no da permisos"
    bigint telegram_chat_id UK
    int viajero_id FK "toda cuenta tiene perfil de viajero"
  }
  CARGOS {
    int id PK
    text nombre UK "Pilotaje de dron, Edición de video..."
    int activo "un cargo asignado no se borra: se desactiva"
  }
  AEROPUERTOS_MUNDO {
    int id PK
    text iata UK "solo con servicio regular"
    text nombre
    text municipio
    text pais
    text region
    float lat
    float lon
    int grande "1 si suele tener más vuelos"
    text buscable "nombre y municipio sin tildes ni mayúsculas"
  }
  LUGARES {
    int id PK "el de GeoNames"
    text nombre
    text buscable "nombre y nombres alternativos normalizados"
    text pais
    text region
    float lat
    float lon
    int poblacion
  }
  PAISES {
    int id PK
    text codigo UK
    text nombre_es
    text nombre_en
  }
  AEROPUERTOS_GOOGLE {
    int id PK
    text iata UK
    text nombre
    text ciudad
    text kgmid
    text consulta "texto que lo trajo"
    text visto
  }
  CARGAS_DATOS {
    int id PK
    text fuente
    text archivo
    text url
    text huella "sha256 del archivo"
    int filas
    text resultado
    text momento
    text quien
  }
  SOLICITUDES {
    int id PK
    text origen "código del aeropuerto principal"
    text destino
    text origen_lugar "JSON: nombre, región, país, coordenadas"
    text destino_lugar
    text origen_aeropuertos "códigos marcados, ordenados, con coma"
    text destino_aeropuertos
  }
  VIAJES {
    int id PK "se muestra como V-2026-0012"
    int solicitud_id FK "único: una cotización, un viaje"
    int decision_id FK
    int usuario_id FK "titular"
    int proyecto_id FK
    text ida
    text regreso
    float presupuesto_usd
    text estado "pendiente_aprobacion, aprobado, rechazado, cerrado"
    int aprobado_por FK
  }
  GASTOS {
    int id PK
    int viaje_id FK
    int documento_id FK
    int proyecto_id FK
    int usuario_id FK
    float total_usd
    text estado
    text motivos "códigos de alerta"
  }
  JUSTIFICACIONES {
    int id PK
    int gasto_id FK
    int usuario_id FK "quien hizo el gasto o quien viaja"
    int documento_id FK "audio original, si lo hay"
    text tipo "texto o audio"
    text canal "web, celular, telegram, api"
    text texto "escrito o transcrito"
    text transcripcion "no_aplica, pendiente, hecha, fallida"
  }
  DOCUMENTOS {
    int id PK
    int viaje_id FK
    text tipo "soporte, audio o nota"
    text canal "web, celular, correo, telegram"
    text huella "sha256 del contenido"
  }
```

Tablas de registro, sin claves foráneas a propósito (un hecho se conserva aunque cambie lo demás): `eventos`, `errores`, `llamadas_modelo`, `telegram_mensajes`, `busquedas`, `observaciones`, `historial_ruta`, `consultas_buscador` y `cargas_datos`.

Datos de referencia del buscador mundial: `aeropuertos_mundo`, `lugares` y `paises` se cargan de los archivos de `datos/geografia/` (OurAirports y GeoNames, ver el README) y no tienen claves foráneas: un viaje guarda los códigos y el lugar elegido como texto, de modo que sigue siendo legible aunque los datos se actualicen. `aeropuertos_google` guarda los aeropuertos que solo conoce el autocompletado de Google, para poder elegirlos aunque no estén en los datos locales. `cargas_datos` deja una fila por archivo en cada carga, también si no cambió nada.

`consultas_buscador` guarda además las consultas de autocompletado con `tipo = 'autocompletado'` (la respuesta completa queda en `busquedas`, con clave `autocompletado_<texto>`). Solo las que gastaron una búsqueda (`en vivo` o `fallida`) cuentan contra los topes; las servidas de lo guardado no se registran porque serían una por pulsación.

## Identificadores

| Qué | Cómo se ve | De dónde sale |
|---|---|---|
| Persona | `P-0007` | Identificador de la fila en `usuarios` |
| Viaje | `V-2026-0012` | Año de creación e identificador de la fila en `viajes` |

Se calculan a partir de la clave primaria, así que no pueden repetirse ni quedar desfasados.

## Reglas y dónde se hacen cumplir

| Regla | En la base | En el código |
|---|---|---|
| Una cotización produce un solo viaje | Índice único en `viajes.solicitud_id` | `viajes.crear_desde_decision` |
| El viaje pertenece a quien viaja | Clave foránea `viajes.usuario_id` | `viajes.titular_de` |
| El presupuesto es lo que se espera pagar: compras de la decisión más viáticos por día | — | `viajes.presupuesto_de` |
| Estados válidos del viaje | Restricción `ck_viajes_estado` | `viajes.TRANSICIONES` |
| Solo administración aprueba, rechaza, reabre o cierra | — | `viajes.cambiar_estado`, `acceso.nivel` |
| Con el presupuesto aprobado la decisión no cambia sin reabrir | — | `viajes.bloquea_decision` |
| Todo gasto pertenece a un viaje aprobado; si no, se guarda y va a revisión | Clave foránea `gastos.viaje_id` | `validacion.revisar`: `sin_viaje`, `viaje_no_aprobado`, `viaje_cerrado`, `fuera_del_viaje`, `presupuesto_superado` |
| A qué viaje va un gasto | — | `viajes.resolver_para_gasto`: el indicado, el fijado, el que está en curso, el próximo aprobado |
| Permisos válidos: `colaborador`, `gestor`, `admin` | Restricción `ck_usuarios_rol` | `acceso.ROLES` |
| El cargo no da permisos; es opcional | `usuarios.cargo_id`, clave foránea a `cargos` | `acceso.asignar_cargo` |
| Nombre de cargo único; un cargo con personas asignadas no se borra, se desactiva | `cargos.nombre` único | `acceso.crear_cargo`, `acceso.cambiar_cargo` |
| Toda cuenta tiene perfil de viajero | `usuarios.viajero_id` | `acceso.crear_usuario`, `acceso.crear_perfil_viajero` |
| Nadie aprueba ni rechaza su propio presupuesto, ni revisa sus propios gastos; el intento queda en la bitácora | — | `viajes.cambiar_estado`, `viajes.impedir_autoaprobacion` |
| El traslado por carretera suma al costo, a la hora límite y al presupuesto; a menos de `traslado_minimo_km` no se suma | — | `costo.traslado` |
| Un código de aeropuerto marcado debe existir en los datos locales o en `aeropuertos_google` | — | `geografia.aeropuertos_conocidos` |
| El autocompletado de Google respeta `tope_autocompletado_mes` y `tope_autocompletado_persona_dia` | — | `geografia._tope_alcanzado` |
| Cada carga de datos de referencia deja su registro | Tabla `cargas_datos` | `geografia` (carga desde `datos/geografia/`) |
| Un chat de Telegram, una cuenta | Índice único en `usuarios.telegram_chat_id` | `telegram.vincular` |
| Una entrega de Telegram se procesa una vez | `telegram_mensajes.update_id` único | `telegram.procesar` |
| Nada apunta a algo que no existe | Claves foráneas en todo el núcleo | `datos/migracion.py` las crea y limpia referencias huérfanas |

## Quién ve qué

El permiso (`usuarios.rol`) decide qué se puede hacer. El cargo (`cargos`) dice qué hace la persona en la empresa, aparece en su ficha y en la analítica, y no cambia lo que ve ni lo que puede.

| Permiso | Ve | Puede |
|---|---|---|
| Colaborador (antes piloto) | Sus cotizaciones, viajes, gastos y evidencias | Cotizar, decidir sus viajes, cargar gastos (web, celular, Telegram) |
| Gestor de proyecto | Lo suyo y todo lo de los proyectos que gestiona | Lo mismo que el colaborador sobre lo suyo; lo ajeno, solo lectura |
| Administrador | Todo | Aprobar presupuestos, revisar gastos, administrar cuentas y cargos, monitorear. No aprueba lo propio |

Todas las cuentas viajan: cotizan, reciben viajes a su nombre y reportan gastos.

## Migración

`python -m datos.semilla` crea lo que falte y ejecuta `datos/migracion.py`, que se puede repetir sin efecto: renombra el permiso antiguo (`piloto` pasa a `colaborador` con el cargo «Pilotaje de dron»), siembra los cinco cargos iniciales en una tabla vacía, crea el perfil de viajero de las cuentas que no lo tienen, crea los viajes de las decisiones que ya existían, enlaza los gastos cuyo viaje es inequívoco, vacía referencias huérfanas, añade claves foráneas, restricciones e índices, activa la seguridad por filas y retira los permisos de los roles públicos.

## Telegram

1. Crear el bot con BotFather y poner su clave en `.env` como `TELEGRAM_BOT_TOKEN`.
2. `python -m datos.telegram_webhook --preparar` anota el nombre del bot y genera el secreto.
3. Publicar la plataforma con esas variables en el secreto de la nube.
4. `python -m datos.telegram_webhook https://<dirección-pública>` registra la entrada.
5. Cada persona abre «Mi cuenta» → «Vincular Telegram».

Sin esas variables el canal queda apagado y lo demás funciona igual.
