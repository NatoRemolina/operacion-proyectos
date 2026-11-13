# ADR 0003 · El viaje como eje de los dos retos

Estado: aceptada · Fecha: 11 de noviembre de 2026 (registrada el 13 de noviembre) · Relacionada con el [ADR 0001](0001-arquitectura-objetivo.md)

## Contexto

La prueba plantea dos retos que el enunciado presenta por separado:

- **Reto 1, cotizar el viaje:** elegir vuelos y hoteles por su costo total (equipaje, cambios, fidelización), no por el precio más bajo, y reducir el tiempo de comparar.
- **Reto 2, recoger los gastos:** reunir soportes que llegan por canales y formatos distintos, organizarlos por proyecto y dar seguimiento sin trabajo manual.

Los dos describen el mismo objeto en dos momentos: el reto 1 decide **cuánto debería costar** un viaje y el reto 2 registra **cuánto costó**. El análisis inicial (`ANALISIS.md`, sección 4) recomendó una integración ligera, con el proyecto como punto de unión y la opción de recortarla si faltaba tiempo. La bitácora (`EXPLORACION.md`, puentes P.1 a P.3 y pregunta abierta 1) propuso además previsto frente a real por proyecto y la fidelización perdida detectada en los gastos.

Al diseñar la asignación automática del gasto apareció el límite del proyecto como unión: un proyecto tiene varios viajes y varias personas, así que un recibo que solo sabe su proyecto no se puede validar contra un presupuesto concreto, ni decir qué viaje no tiene soportes.

## Decisión

**Una sola plataforma con el viaje como eje:**

```
persona (P-0007) ─► cotización ─► decisión ─► VIAJE (V-2026-0012, presupuesto, estado) ─► gastos y evidencias
                                                  ▲
                                       aprobación de administración
```

- La decisión de la cotización **crea el viaje** con su código y su presupuesto (lo que se espera pagar), y administración lo aprueba.
- Cada gasto **se asigna solo al viaje** de la persona, por quién lo envía y las fechas (`viajes.resolver_para_gasto`), y se valida contra ese presupuesto.
- El proyecto agrupa viajes y gastos para comparar **previsto frente a real**, en cada viaje y en el tablero del proyecto.

La regla completa está en [`regla-de-negocio.md`](../regla-de-negocio.md) y el modelo de datos en [`datos.md`](../datos.md).

## Alternativas consideradas

| Alternativa | A favor | En contra | Resultado |
|---|---|---|---|
| **Dos herramientas sueltas**, una por reto | Menor riesgo; cada una se entiende y se entrega sola | Dos listas que alguien concilia a mano: a qué proyecto va cada recibo, si un gasto cabe en lo previsto, qué viaje no tiene soportes. Se pierde la historia más útil para Finanzas | Descartada |
| **Integración ligera con el proyecto como unión** (la recomendación inicial) | Poco diseño adicional; se puede recortar | Un gasto solo sabe su proyecto: no hay presupuesto concreto contra el cual validarlo ni forma de saber qué viaje no tiene soportes | Ampliada a la decisión |
| **El viaje como eje** | La asignación automática del gasto, el control del presupuesto y previsto frente a real salen de la misma relación | Una aplicación y una base compartidas por los dos retos, más acopladas que dos herramientas | **Elegida** |

## Consecuencias

- **La unión dejó de ser lo primero que se recorta:** la asignación automática y el control del presupuesto dependen de ella.
- **Todo gasto pertenece a un viaje.** Sin viaje, o con un viaje no aprobado o cerrado, el gasto se guarda igual y va a revisión con su motivo (`sin_viaje`, `viaje_no_aprobado`, `viaje_cerrado`).
- **Dos cifras distintas:** el costo total esperado ordena las opciones y el presupuesto es lo que se espera pagar. No coinciden y es correcto ([`regla-de-negocio.md`](../regla-de-negocio.md), sección 8).
- **Más acoplamiento:** los dos retos comparten tablas, consultas y transacciones. El control del presupuesto es el corte más difícil para separar servicios ([`arquitectura_objetivo.md`](../arquitectura_objetivo.md)). Por eso la plataforma se declara como etapa de transición y se migra por anillos ([ADR 0001](0001-arquitectura-objetivo.md)).
- **Concurrencia:** registrar, asignar viaje y aprobar un gasto se hacen con el viaje bloqueado (`db.transaccion`, `db.bloquear_viaje`), para que dos aprobaciones a la vez no gasten el mismo saldo.
- **Los datos del reto 2 informan al reto 1:** un hotel reservado por agencia avisa que no acumuló puntos (`sin_puntos`), y lo gastado frente a lo previsto alimenta los indicadores de presupuesto.

## Condición para revisar esta decisión

Si la empresa necesitara registrar gastos que no nacen de un viaje (por ejemplo, compras de un proyecto sin desplazamiento) en volumen, el eje tendría que admitir el proyecto como destino directo de un gasto, con su propia validación por fechas del proyecto.
