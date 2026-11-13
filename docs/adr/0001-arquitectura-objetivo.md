# ADR 0001 · Arquitectura objetivo y migración por anillos

Estado: aceptada · Fecha: 12 de noviembre de 2026

## Contexto

La plataforma nació como una sola aplicación FastAPI con pantallas servidas por el backend, una sola base PostgreSQL (Supabase en la nube, SQLite en local) y un despliegue en una función de AWS Lambda. Resuelve los dos retos de la prueba (cotización de viajes y gastos por proyecto) sobre un eje común: el viaje.

El plan fullstack fija un objetivo distinto:

- una web Next.js con TypeScript que consume una API JSON versionada;
- un API Gateway delante;
- tres servicios por capacidad de negocio, con datos privados: **Organización y acceso**, **Viajes y presupuestos** (reto 1) y **Gastos y evidencias** (reto 2);
- comunicación por contratos HTTP y eventos durables.

El mapa de acoplamientos (`docs/arquitectura_objetivo.md`) muestra que hoy esos tres dominios comparten tablas, consultas y transacciones. Partir la aplicación de golpe obligaría a reescribir la lógica, la web y los datos a la vez, sin red de seguridad.

## Decisión

Migrar **por anillos, estrangulando la aplicación actual** en lugar de reescribirla. La aplicación actual sigue funcionando en cada paso; se le van sacando capacidades por el borde. Nunca hay dos escritores del mismo dato, y nada se llama «microservicio» mientras comparta tablas o despliegue.

| Anillo | Qué se construye | Fases del plan | Estado |
|---|---|---|---|
| 0 · Contrato y borde | API JSON v1 dentro de la aplicación actual; gateway local delante; errores uniformes, token CSRF, permisos por registro | F1, F2, M0, M1 parcial | En curso |
| 1 · Web nueva | Next.js consume solo la API v1; las pantallas actuales quedan de respaldo | F3 a F6 | En curso: cotizar y decidir, mis viajes y mis gastos, y la aprobación de viajes y la revisión de gastos de administración; el resto sigue en las pantallas actuales |
| 2 · Fronteras de datos | Esquemas privados (`org`, `viajes`, `gastos`) con un rol y una credencial por dominio; se cortan los cruces | M1 completa | Pendiente |
| 3 · Servicios reales | Gastos sale primero (base, migraciones, almacenamiento y proceso propios; outbox, inbox y saga de presupuesto); luego Viajes; queda Organización | M2, M3 | Pendiente |
| 4 · Nube | Gateway administrado, una función por servicio con su secreto, temas y colas, hospedaje de la web, dominio | F10 | Pendiente |

El orden lo justifica una sola razón: **el contrato y el gateway son lo único que permite mover después un servicio sin que la web se entere**. Separar datos antes de tener contrato obligaría a reescribir las pantallas dos veces.

### Datos: primero esquemas, después bases

La separación empieza con tres esquemas privados en el mismo PostgreSQL, cada uno con su rol y su credencial; un servicio no puede leer las tablas de otro (prueba MS-01 del plan). Cuando eso funcione y los cruces estén cortados, cada esquema se muda a su propia base. Mientras tanto se declara como **etapa de transición**: un esquema privado aísla el acceso, pero no la disponibilidad ni la restauración.

### Entorno local

`docker-compose.yml` levanta PostgreSQL, la aplicación, la web y un gateway Caddy. El gateway publica un solo origen (`127.0.0.1:8088`): `/api/v1/*` va a la API y el resto a la web. Es la misma forma que tendrá en la nube con un API Gateway administrado. El entorno local nunca lee `.env`, que apunta a la base real.

## Consecuencias

- La entrega del viernes 13 es la etapa de transición: una sola base, una sola aplicación, con contrato, gateway y web nueva funcionando en local. Se presenta así, sin llamarla microservicios.
- Mientras convivan las pantallas actuales y la web nueva, **toda regla vive en un servicio que ambas llaman**; la API v1 no copia lógica de las rutas de pantallas.
- El control del presupuesto es el corte más difícil: hoy Gastos decide sumando su propia tabla contra el límite de Viajes. En el anillo 3 pasa a un libro de reservas y consumos dueño de Viajes, coordinado con una saga.
- Las transacciones hoy se confirman sentencia a sentencia. Antes del anillo 3 hace falta una unidad de trabajo con transacción real (frente `integridad`).
- El dinero sigue en coma flotante; pasar a decimales exactos se hace antes de separar servicios.

## Decisiones abiertas

Se registrarán como ADR propios antes del anillo 4:

| Tema | Opciones a evaluar |
|---|---|
| Hospedaje de la web Next.js | **Resuelta en `docs/adr/0002-hospedaje-de-la-web.md`:** AWS, Lambda con la imagen de la web detrás de CloudFront, un solo origen con la API |
| Identidad entre servicios | Token firmado por el gateway con la identidad verificada; validación de la sesión en Organización por cada servicio |
| Relay del outbox y trabajador de extracción | Proceso propio con cola en PostgreSQL; cola administrada con consumidor por función |
| Ambiente previo a producción | Proyecto de base aislado y despliegue con datos de prueba |
| Costos y límites del proveedor | Varias bases o proyectos, conexiones del agrupador, respaldos de base y de archivos |

## Condición para revisar esta decisión

Si el volumen o el equipo no justifican tres servicios, el anillo 2 (esquemas privados con contratos) ya entrega la mayor parte del beneficio: límites claros entre dominios, sin la operación de varios despliegues.
