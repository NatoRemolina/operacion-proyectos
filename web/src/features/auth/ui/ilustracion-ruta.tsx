import { useId } from "react";

/*
 * Ilustración de la portada: la ruta Miami → Moab del caso de ejemplo del repositorio sobre una carta como la de
 * los mapas de Estados Unidos (proyección cónica: meridianos que convergen hacia el norte y paralelos curvos), con
 * curvas de nivel en la zona de cañones de Moab. La geometría se calcula aquí, sin imágenes. Encima, el viaje que
 * nace de esa ruta y un recibo del ejemplo que se lee, queda aprobado y hace avanzar la ejecución del viaje.
 * Es decorativa: el texto de la portada dice lo mismo y los lectores de pantalla la omiten.
 */

const ANCHO = 640;
const ALTO = 360;
const CONO = 0.6; // cuánto convergen los meridianos
const PX_POR_GRADO = 9;
const LON_CENTRAL = -96;
const RADIO_MOAB = 900;
const MOAB = { lat: 38.76, lon: -109.75 }; // aeropuerto de Canyonlands (CNY), el más cercano a Moab
const MIAMI = { lat: 25.79, lon: -80.29 }; // MIA

const angulo = (lon: number) => ((lon - LON_CENTRAL) * CONO * Math.PI) / 180;
const VERTICE_Y = 120 - RADIO_MOAB * Math.cos(angulo(MOAB.lon));

function proyectar(lat: number, lon: number) {
  const radio = RADIO_MOAB + (MOAB.lat - lat) * PX_POR_GRADO;
  return { x: ANCHO / 2 + radio * Math.sin(angulo(lon)), y: VERTICE_Y + radio * Math.cos(angulo(lon)) };
}

const n = (valor: number) => Number(valor.toFixed(1));
const linea = (puntos: { x: number; y: number }[]) => "M" + puntos.map((p) => `${n(p.x)} ${n(p.y)}`).join(" L");
const dentro = (p: { x: number; y: number }) => p.x > -24 && p.x < ANCHO + 24 && p.y > -24 && p.y < ALTO + 24;

function graticula(): string {
  const trazos: string[] = [];
  for (let lat = 15; lat <= 55; lat += 5) {
    const puntos = [];
    for (let lon = -140; lon <= -50; lon += 2.5) puntos.push(proyectar(lat, lon));
    const visibles = puntos.filter(dentro);
    if (visibles.length > 1) trazos.push(linea(visibles));
  }
  for (let lon = -135; lon <= -55; lon += 5) trazos.push(linea([proyectar(58, lon), proyectar(12, lon)]));
  return trazos.join(" ");
}

/** Curvas de nivel alrededor de Moab: anillos irregulares, siempre iguales (sin azar, para que coincidan al hidratar). */
function curvasDeNivel(centro: { x: number; y: number }): string {
  const curvas: string[] = [];
  for (let k = 1; k <= 6; k++) {
    const puntos = [];
    for (let i = 0; i < 40; i++) {
      const t = (2 * Math.PI * i) / 40;
      const r = 11 * k * (1 + 0.16 * Math.sin(3 * t + k * 0.7) + 0.09 * Math.sin(5 * t - k) + 0.05 * Math.sin(7 * t + 2 * k));
      puntos.push({ x: centro.x + r * Math.cos(t) * 1.35, y: centro.y + r * Math.sin(t) });
    }
    curvas.push(linea(puntos) + "Z");
  }
  return curvas.join(" ");
}

const CNY = proyectar(MOAB.lat, MOAB.lon);
const MIA = proyectar(MIAMI.lat, MIAMI.lon);
const GRATICULA = graticula();
const CURVAS = curvasDeNivel({ x: CNY.x + 26, y: CNY.y + 14 });

/** La ruta se curva hacia el norte, como un círculo máximo en esta proyección. */
const RUTA = (() => {
  const medio = { x: (MIA.x + CNY.x) / 2, y: (MIA.y + CNY.y) / 2 };
  const largo = Math.hypot(CNY.x - MIA.x, CNY.y - MIA.y);
  const control = { x: medio.x - ((CNY.y - MIA.y) / largo) * 72, y: medio.y + ((CNY.x - MIA.x) / largo) * 72 };
  return `M${n(MIA.x)} ${n(MIA.y)} Q${n(control.x)} ${n(control.y)} ${n(CNY.x)} ${n(CNY.y)}`;
})();

const posicion = (p: { x: number; y: number }) => ({ left: `${(p.x / ANCHO) * 100}%`, top: `${(p.y / ALTO) * 100}%` });

function Mapa() {
  const mascara = `ruta-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="portada-mapa absolute inset-0 size-full" fill="none">
      <defs>
        {/* La ruta punteada se descubre con un trazo continuo que se dibuja (animación en globals.css). */}
        <mask id={mascara} maskUnits="userSpaceOnUse" x="0" y="0" width={ANCHO} height={ALTO}>
          <path d={RUTA} pathLength={1} className="portada-trazo" stroke="#ffffff" strokeWidth="10" strokeLinecap="round" />
        </mask>
      </defs>
      <path d={GRATICULA} stroke="var(--carta-linea)" strokeWidth="1" />
      <path d={CURVAS} stroke="var(--carta-relieve)" strokeWidth="1" strokeLinejoin="round" />
      <path d={RUTA} stroke="var(--marca)" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="6 7" mask={`url(#${mascara})`} />
      <circle cx={MIA.x} cy={MIA.y} r="5.5" fill="var(--grafito)" stroke="var(--superficie)" strokeWidth="2.5" />
      <circle cx={CNY.x} cy={CNY.y} r="9" stroke="var(--marca)" strokeWidth="2" className="portada-ping" />
      <circle cx={CNY.x} cy={CNY.y} r="6" fill="var(--marca)" stroke="var(--superficie)" strokeWidth="2.5" className="portada-llegada" />
    </svg>
  );
}

function Lugar({ codigo, nombre, lado }: { codigo: string; nombre: string; lado: "izquierda" | "centro" }) {
  return (
    <span className={`flex flex-col leading-tight ${lado === "izquierda" ? "items-end text-right" : "items-center text-center"}`}>
      <span className="text-sm font-extrabold tracking-wide text-texto">{codigo}</span>
      <span className="text-xs text-texto-secundario">{nombre}</span>
    </span>
  );
}

function TarjetaViaje() {
  return (
    <div className="portada-aparece rounded-2xl bg-grafito p-3.5 text-sobre-grafito shadow-flotante [animation-delay:1.35s] @lg:p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold tabular-nums text-sobre-grafito-suave">V-2026-0012</span>
        <span className="rounded-md bg-sobre-grafito/10 px-2 py-0.5 text-xs font-semibold text-cian-claro">Aprobado</span>
      </div>
      <p className="mt-1.5 font-bold leading-snug @lg:mt-2 @lg:text-xl">Miami → Moab</p>
      <p className="hidden text-xs text-sobre-grafito-suave @lg:block">Producción inmobiliaria · 8 – 11 dic 2026</p>
      <div className="mt-3 flex items-baseline gap-3 text-xs @lg:mt-4 @lg:justify-between">
        <span className="hidden text-sobre-grafito-suave @lg:inline">Gastado</span>
        <span className="tabular-nums text-sobre-grafito-suave">
          <span className="inline-grid font-bold text-sobre-grafito">
            <span className="portada-cifra-antes col-start-1 row-start-1">USD 69,95</span>
            <span className="portada-cifra-despues col-start-1 row-start-1">USD 352,27</span>
          </span>{" "}
          de USD 1.153,00
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-sobre-grafito/20">
        <div className="portada-ejecucion h-full w-[31%] rounded-full bg-cian-claro" />
      </div>
    </div>
  );
}

function Recibo() {
  const fila = "flex justify-between gap-2";
  return (
    <div className="portada-aparece relative [animation-delay:1.8s]">
      <div className="portada-sombra-recibo">
        <div className="portada-recibo relative overflow-hidden bg-superficie px-3.5 pb-5 pt-3.5 font-mono text-[0.6875rem] leading-[1.6] text-texto">
          <p className="portada-campo relative font-bold [animation-delay:2.35s]">DESERT SKY HOTEL</p>
          <p className="portada-campo relative [animation-delay:2.55s]">DEC 11 2026 · 11:02</p>
          <hr className="my-2 border-dashed border-borde-campo" />
          <p className={fila}>
            <span>ROOM 3N</span>
            <span className="tabular-nums">249.00</span>
          </p>
          <p className={fila}>
            <span>TAX</span>
            <span className="tabular-nums">33.32</span>
          </p>
          <p className={`portada-campo relative mt-1 font-bold [animation-delay:2.75s] ${fila}`}>
            <span>TOTAL USD</span>
            <span className="tabular-nums">282.32</span>
          </p>
          <span className="portada-lectura pointer-events-none absolute inset-0" />
        </div>
      </div>
      <p className="portada-sello absolute -bottom-3 -right-2 rounded-md border-2 border-exito bg-superficie px-2 py-0.5 text-xs font-extrabold text-exito shadow-tarjeta">
        Aprobado automático
      </p>
    </div>
  );
}

export function IlustracionRuta() {
  // La disposición depende del ancho de la propia ilustración (consulta de contenedor), no de la pantalla: en la
  // columna de escritorio puede ser tan angosta como en una tableta.
  return (
    <div aria-hidden="true" className="portada-ilustracion @container relative mb-8 select-none @lg:mb-0">
      <div className="relative aspect-[16/9]">
        <Mapa />
        <span className="absolute -translate-x-[calc(100%+0.75rem)] -translate-y-1/2" style={posicion(CNY)}>
          <Lugar codigo="CNY" nombre="Moab, Utah" lado="izquierda" />
        </span>
        <span className="absolute -translate-x-1/2 translate-y-2.5" style={posicion(MIA)}>
          <Lugar codigo="MIA" nombre="Miami" lado="centro" />
        </span>
        {/* Las tarjetas flotan en las zonas que la ruta no cruza, sin tapar los aeropuertos. Si la ilustración
            es angosta, solo va el viaje, compacto, abajo a la izquierda. */}
        <div className="absolute left-0 top-[58%] w-[68%] @lg:bottom-0 @lg:top-auto @lg:w-[min(19rem,52%)]">
          <TarjetaViaje />
        </div>
        <div className="absolute right-[1%] top-0 hidden w-[11.5rem] @lg:block">
          <Recibo />
        </div>
      </div>
    </div>
  );
}
