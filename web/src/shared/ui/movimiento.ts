/*
 * Movimiento del sistema. Solo se animan transformaciones y opacidad; con movimiento reducido, lo que lleva
 * `se-mueve` no se desplaza ni escala (ver globals.css).
 */

/** Respuesta inmediata al presionar: escala 0,97 en 100 ms. */
export const PRESIONAR = "se-mueve transition-transform duration-100 ease-out active:scale-97 disabled:active:scale-100";

/**
 * Flechas que giran al abrir: solo se anima `rotate`. Con movimiento reducido el giro se conserva (indica el
 * estado) pero sin animación.
 */
export const GIRO = "inline-block transition-[rotate] duration-150 ease-out motion-reduce:transition-none";
