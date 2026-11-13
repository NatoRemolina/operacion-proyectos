import { useId } from "react";

/*
 * Ilustración de la portada: las rutas que salen de Medellín hacia Miami, Nueva York, San Francisco y Los Ángeles,
 * sobre una carta con Colombia y los 48 estados contiguos de Estados Unidos. Los contornos están simplificados a mano
 * a partir de coordenadas reales y se proyectan aquí, sin imágenes ni datos externos. Encima, el viaje a Los Ángeles
 * que nace de la ruta principal y el recibo del hotel, que se lee, queda aprobado y hace avanzar la ejecución.
 * Es decorativa: el texto de la portada dice lo mismo y los lectores de pantalla la omiten.
 */

type Punto = { x: number; y: number };
type Coordenada = readonly [latitud: number, longitud: number];

const ANCHO = 640;
const ALTO = 360;

/** Estados Unidos contiguo, en el sentido de las agujas del reloj desde el cabo Flattery (80 puntos). */
const EEUU: readonly Coordenada[] = [
  [48.38, -124.72], [49.0, -123.03], [49.0, -95.15], [48.6, -93.4], [48.0, -89.6], [46.5, -84.5], [45.2, -82.5],
  [43.0, -82.42], [42.3, -83.1], [41.75, -82.6], [42.85, -78.95], [43.6, -77.5], [44.1, -76.4], [45.0, -74.75],
  [45.0, -71.5], [46.4, -70.05], [47.46, -69.22], [47.07, -67.79], [45.6, -67.78], [44.82, -66.95], [43.75, -70.0],
  [42.6, -70.62], [41.75, -70.52], [42.05, -70.2], [41.67, -69.95], [41.5, -71.3], [41.07, -71.86], [40.58, -73.75],
  [40.45, -74.0], [39.35, -74.43], [38.93, -74.92], [37.12, -75.95], [35.22, -75.53], [34.6, -76.5], [33.85, -77.96],
  [32.75, -79.85], [30.3, -81.4], [28.45, -80.55], [25.77, -80.13], [25.12, -81.05], [25.9, -81.7], [27.75, -82.75],
  [29.9, -83.65], [29.68, -85.35], [30.35, -86.5], [30.25, -88.05], [30.2, -89.6], [29.0, -89.2], [29.2, -90.1],
  [29.7, -93.85], [29.35, -94.75], [28.45, -96.4], [27.7, -97.15], [25.96, -97.15], [27.5, -99.5], [29.35, -100.9],
  [29.8, -101.5], [28.97, -103.25], [29.55, -104.38], [31.75, -106.5], [31.78, -108.21], [31.33, -108.21],
  [31.33, -111.07], [32.49, -114.81], [32.53, -117.12], [33.45, -117.7], [33.75, -118.4], [34.03, -118.8],
  [34.4, -119.7], [34.45, -120.47], [35.65, -121.25], [36.3, -121.9], [36.95, -122.05], [37.8, -122.52],
  [38.0, -123.0], [38.95, -123.74], [40.44, -124.41], [42.84, -124.56], [46.25, -124.05], [47.9, -124.65],
];

/** Colombia, en el sentido de las agujas del reloj desde Punta Gallinas (49 puntos). */
const COLOMBIA: readonly Coordenada[] = [
  [12.46, -71.67], [12.08, -71.12], [11.85, -71.32], [11.1, -72.25], [10.0, -72.95], [9.1, -73.35], [8.4, -72.6],
  [7.9, -72.45], [7.1, -72.2], [7.05, -70.8], [6.95, -70.1], [6.1, -69.4], [6.2, -67.5], [4.0, -67.8], [2.6, -67.6],
  [1.22, -66.85], [1.0, -67.5], [1.15, -69.0], [0.6, -69.2], [-0.2, -69.6], [-1.4, -69.45], [-4.22, -69.94],
  [-3.8, -70.6], [-2.4, -71.0], [-1.6, -73.0], [-0.95, -74.0], [-0.12, -75.25], [0.35, -76.4], [0.85, -77.65],
  [1.45, -78.85], [1.6, -79.0], [2.5, -78.2], [3.85, -77.2], [5.5, -77.55], [6.6, -77.45], [7.2, -77.9], [7.9, -77.3],
  [8.68, -77.37], [8.5, -77.25], [7.95, -76.85], [8.6, -76.88], [9.0, -76.2], [9.45, -75.7], [10.4, -75.55],
  [11.0, -74.9], [11.25, -74.2], [11.25, -73.5], [11.55, -72.9], [12.2, -72.15],
];

/*
 * Proyección cónica equidistante (paralelos de referencia 20° y 45° N, meridiano central 95° O), la que da a los
 * mapas de Estados Unidos su frontera norte curva. El mar entre Colombia y la costa del golfo se comprime para que
 * Colombia quepa debajo sin un hueco vacío; por eso la cuadrícula no dibuja el paralelo 20° N.
 */
const RAD = Math.PI / 180;
const REFERENCIA_SUR = 20 * RAD;
const REFERENCIA_NORTE = 45 * RAD;
const CONO = (Math.cos(REFERENCIA_SUR) - Math.cos(REFERENCIA_NORTE)) / (REFERENCIA_NORTE - REFERENCIA_SUR);
const VERTICE = Math.cos(REFERENCIA_SUR) / CONO + REFERENCIA_SUR;
const LON_CENTRAL = -95;
const CARIBE = { desde: 14, hasta: 24, factor: 0.2 };

function comprimir(lat: number): number {
  if (lat <= CARIBE.desde) return lat;
  if (lat >= CARIBE.hasta) return lat - (CARIBE.hasta - CARIBE.desde) * (1 - CARIBE.factor);
  return CARIBE.desde + (lat - CARIBE.desde) * CARIBE.factor;
}

function conica([lat, lon]: Coordenada): Punto {
  const radio = VERTICE - comprimir(lat) * RAD;
  const angulo = CONO * (lon - LON_CENTRAL) * RAD;
  return { x: radio * Math.sin(angulo), y: radio * Math.cos(angulo) };
}

/** Recuadro del lienzo que ocupan los dos países; lo demás queda libre para las tarjetas y las etiquetas. */
const RECUADRO = { izquierda: 104, arriba: 14, alto: 334 };
const CRUDOS = [...EEUU, ...COLOMBIA].map(conica);
const MIN_X = Math.min(...CRUDOS.map((p) => p.x));
const MIN_Y = Math.min(...CRUDOS.map((p) => p.y));
const ESCALA = RECUADRO.alto / (Math.max(...CRUDOS.map((p) => p.y)) - MIN_Y);

function proyectar(coordenada: Coordenada): Punto {
  const p = conica(coordenada);
  return { x: RECUADRO.izquierda + (p.x - MIN_X) * ESCALA, y: RECUADRO.arriba + (p.y - MIN_Y) * ESCALA };
}

const n = (valor: number) => Number(valor.toFixed(1));
const linea = (puntos: Punto[]) => "M" + puntos.map((p) => `${n(p.x)} ${n(p.y)}`).join(" L");
const contorno = (coordenadas: readonly Coordenada[]) => linea(coordenadas.map(proyectar)) + "Z";

function graticula(): string {
  const trazos: string[] = [];
  for (const lat of [-10, 0, 10, 30, 40, 50]) {
    const puntos = [];
    for (let lon = -140; lon <= -50; lon += 2.5) puntos.push(proyectar([lat, lon]));
    trazos.push(linea(puntos));
  }
  for (let lon = -130; lon <= -60; lon += 10) trazos.push(linea([proyectar([58, lon]), proyectar([-12, lon])]));
  return trazos.join(" ");
}

const GRATICULA = graticula();
const TRAZO_EEUU = contorno(EEUU);
const TRAZO_COLOMBIA = contorno(COLOMBIA);

/** Aeropuertos por sus coordenadas reales; redondeados como los trazos, para que el servidor y el navegador coincidan. */
const aeropuerto = (coordenada: Coordenada) => {
  const p = proyectar(coordenada);
  return { x: n(p.x), y: n(p.y) };
};
const CIUDADES = {
  MDE: { nombre: "Medellín", punto: aeropuerto([6.25, -75.56]) },
  LAX: { nombre: "Los Ángeles", punto: aeropuerto([33.94, -118.41]) },
  SFO: { nombre: "San Francisco", punto: aeropuerto([37.62, -122.38]) },
  JFK: { nombre: "Nueva York", punto: aeropuerto([40.64, -73.78]) },
  MIA: { nombre: "Miami", punto: aeropuerto([25.79, -80.29]) },
} as const;

type Destino = "MIA" | "JFK" | "SFO" | "LAX";

/*
 * Las rutas salen de Medellín una tras otra y la principal, a Los Ángeles, llega de última. Cada arco se curva hacia
 * un lado distinto (fracción de su largo; positiva, a la derecha del sentido del vuelo) para que se abran en abanico
 * sin pasar por encima de Miami, que queda en el camino de las rutas al oeste.
 */
const RUTAS: { destino: Destino; curva: number; inicio: number; duracion: number }[] = [
  { destino: "MIA", curva: -0.3, inicio: 0.1, duracion: 0.35 },
  { destino: "JFK", curva: 0.22, inicio: 0.3, duracion: 0.45 },
  { destino: "SFO", curva: 0.14, inicio: 0.5, duracion: 0.55 },
  { destino: "LAX", curva: 0.06, inicio: 0.7, duracion: 0.65 },
];

function arco(destino: Destino, curva: number): string {
  const a = CIUDADES.MDE.punto;
  const b = CIUDADES[destino].punto;
  const largo = Math.hypot(b.x - a.x, b.y - a.y);
  const desvio = curva * largo;
  const control = {
    x: (a.x + b.x) / 2 - ((b.y - a.y) / largo) * desvio,
    y: (a.y + b.y) / 2 + ((b.x - a.x) / largo) * desvio,
  };
  return `M${n(a.x)} ${n(a.y)} Q${n(control.x)} ${n(control.y)} ${n(b.x)} ${n(b.y)}`;
}

const TRAZOS_RUTAS = RUTAS.map((ruta) => ({ ...ruta, d: arco(ruta.destino, ruta.curva) }));
const fin = (destino: Destino) => {
  const ruta = RUTAS.find((r) => r.destino === destino)!;
  return ruta.inicio + ruta.duracion;
};

function Mapa() {
  const base = `ruta-${useId().replace(/:/g, "")}`;
  const lax = CIUDADES.LAX.punto;
  const mde = CIUDADES.MDE.punto;
  return (
    <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="absolute inset-0 size-full" fill="none">
      <defs>
        {/* Cada ruta punteada se descubre con un trazo continuo que se dibuja (animación en globals.css). */}
        {TRAZOS_RUTAS.map((ruta) => (
          <mask key={ruta.destino} id={`${base}-${ruta.destino}`} maskUnits="userSpaceOnUse" x="0" y="0" width={ANCHO} height={ALTO}>
            <path
              d={ruta.d}
              pathLength={1}
              className="portada-trazo"
              style={{ animationDelay: `${ruta.inicio}s`, animationDuration: `${ruta.duracion}s` }}
              stroke="#ffffff"
              strokeWidth="10"
              strokeLinecap="round"
            />
          </mask>
        ))}
      </defs>
      <path d={GRATICULA} stroke="var(--carta-linea)" strokeWidth="1" />
      <path d={TRAZO_EEUU} fill="var(--carta-tierra)" stroke="var(--carta-costa)" strokeWidth="1" strokeLinejoin="round" />
      <path d={TRAZO_COLOMBIA} fill="var(--carta-origen)" stroke="var(--carta-costa-origen)" strokeWidth="1.25" strokeLinejoin="round" />
      {TRAZOS_RUTAS.map((ruta) =>
        ruta.destino === "LAX" ? (
          <path key={ruta.destino} d={ruta.d} stroke="var(--marca)" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="6 7" mask={`url(#${base}-${ruta.destino})`} />
        ) : (
          <path key={ruta.destino} d={ruta.d} stroke="var(--carta-ruta)" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="4 5" mask={`url(#${base}-${ruta.destino})`} />
        ),
      )}
      {(["MIA", "JFK", "SFO"] as const).map((destino) => (
        <circle
          key={destino}
          cx={CIUDADES[destino].punto.x}
          cy={CIUDADES[destino].punto.y}
          r="3.5"
          fill="var(--superficie)"
          stroke="var(--marca)"
          strokeWidth="2"
          className="portada-llegada"
          style={{ animationDelay: `${fin(destino) - 0.05}s` }}
        />
      ))}
      <circle cx={lax.x} cy={lax.y} r="9" stroke="var(--marca)" strokeWidth="2" className="portada-ping" style={{ animationDelay: `${fin("LAX") + 0.05}s` }} />
      <circle
        cx={lax.x}
        cy={lax.y}
        r="6"
        fill="var(--marca)"
        stroke="var(--superficie)"
        strokeWidth="2.5"
        className="portada-llegada"
        style={{ animationDelay: `${fin("LAX") - 0.05}s` }}
      />
      <circle cx={mde.x} cy={mde.y} r="6" fill="var(--grafito)" stroke="var(--superficie)" strokeWidth="2.5" />
    </svg>
  );
}

const posicion = (p: Punto) => ({ left: `${(p.x / ANCHO) * 100}%`, top: `${(p.y / ALTO) * 100}%` });

/** Hacia dónde sale la etiqueta respecto del punto, para no pisar las rutas ni la otra ciudad. */
const LADOS = {
  oeste: "-translate-x-[calc(100%+0.5rem)] -translate-y-1/2 items-end text-right @lg:-translate-x-[calc(100%+0.625rem)]",
  este: "translate-x-2 -translate-y-1/2 items-start text-left @lg:translate-x-2.5",
  noroeste: "-translate-x-[calc(100%+0.375rem)] -translate-y-[calc(100%+0.125rem)] items-end text-right",
  suroeste: "-translate-x-[calc(100%+0.5rem)] translate-y-1.5 items-end text-right",
} as const;

function Ciudad({ codigo, lado }: { codigo: keyof typeof CIUDADES; lado: keyof typeof LADOS }) {
  const ciudad = CIUDADES[codigo];
  return (
    <span className={`portada-etiqueta absolute flex flex-col leading-tight ${LADOS[lado]}`} style={posicion(ciudad.punto)}>
      <span className="text-[0.6875rem] font-extrabold tracking-wide text-texto @lg:text-sm">{codigo}</span>
      <span className="hidden whitespace-nowrap text-xs text-texto-secundario @lg:block">{ciudad.nombre}</span>
    </span>
  );
}

function TarjetaViaje() {
  return (
    <div className="portada-aparece rounded-2xl bg-grafito p-3.5 text-sobre-grafito shadow-flotante [animation-delay:1.35s] @xl:p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold tabular-nums text-sobre-grafito-suave">V-2026-0031</span>
        <span className="rounded-md bg-sobre-grafito/10 px-2 py-0.5 text-xs font-semibold text-cian-claro">Aprobado</span>
      </div>
      <p className="mt-1.5 font-bold leading-snug @lg:text-lg">Medellín → Los&nbsp;Ángeles</p>
      <p className="hidden text-xs text-sobre-grafito-suave @xl:block">Residencial Malibú · 8 – 11 dic 2026</p>
      <div className="mt-3 flex items-baseline gap-3 text-xs @xl:justify-between">
        <span className="hidden text-sobre-grafito-suave @xl:inline">Gastado</span>
        <span className="tabular-nums text-sobre-grafito-suave">
          <span className="inline-grid font-bold text-sobre-grafito @xl:justify-items-end">
            <span className="portada-cifra-antes col-start-1 row-start-1">USD&nbsp;891,40</span>
            <span className="portada-cifra-despues col-start-1 row-start-1">USD&nbsp;1.582,13</span>
          </span>{" "}
          de USD&nbsp;2.150,00
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-sobre-grafito/20">
        <div className="portada-ejecucion h-full w-[74%] rounded-full bg-cian-claro" />
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
          <p className="portada-campo relative font-bold [animation-delay:2.35s]">MARINA PALMS HOTEL</p>
          <p>LOS ANGELES, CA</p>
          <p className="portada-campo relative [animation-delay:2.55s]">DEC 11 2026 · 11:02</p>
          <hr className="my-2 border-dashed border-borde-campo" />
          <p className={fila}>
            <span>ROOM 3N</span>
            <span className="tabular-nums">597.00</span>
          </p>
          <p className={fila}>
            <span>TAX</span>
            <span className="tabular-nums">93.73</span>
          </p>
          <p className={`portada-campo relative mt-1 font-bold [animation-delay:2.75s] ${fila}`}>
            <span>TOTAL USD</span>
            <span className="tabular-nums">690.73</span>
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

/*
 * Lienzo de 640 × 360 con el mapa y las etiquetas. Si la ilustración es angosta, el recuadro muestra solo la zona de
 * los dos países (x de 62 a 554 y de 6 a 354): el mapa se ve más grande y las etiquetas no pisan las rutas.
 */
const LIENZO = "absolute left-[-12.6%] top-[-1.72%] aspect-[16/9] w-[130.08%] @lg:left-0 @lg:top-0 @lg:w-full";

export function IlustracionRuta() {
  // La disposición depende del ancho de la propia ilustración (consulta de contenedor), no de la pantalla: en la
  // columna de escritorio puede ser tan angosta como en una tableta.
  return (
    <div aria-hidden="true" className="portada-ilustracion @container relative mb-8 select-none @lg:mb-0">
      <div className="relative aspect-[492/348] @lg:aspect-[16/9]">
        {/* La carta se desvanece hacia los bordes del recuadro; las etiquetas, encima, no. */}
        <div className="portada-mapa absolute inset-0 overflow-hidden">
          <div className={LIENZO}>
            <Mapa />
          </div>
        </div>
        {/* Recortado al recuadro: el lienzo ampliado no debe ensanchar la página. */}
        <div className="absolute inset-0 overflow-hidden">
          <div className={LIENZO}>
            <Ciudad codigo="SFO" lado="noroeste" />
            <Ciudad codigo="LAX" lado="suroeste" />
            <Ciudad codigo="JFK" lado="oeste" />
            <Ciudad codigo="MIA" lado="este" />
            <Ciudad codigo="MDE" lado="este" />
          </div>
        </div>
        {/* Con espacio, el recibo flota sobre el Atlántico, al este de la costa, sin tapar aeropuertos ni rutas. */}
        <div className="absolute right-0 top-[2%] hidden w-[9.75rem] @lg:block @xl:w-[10.5rem]">
          <Recibo />
        </div>
      </div>
      {/* El viaje va abajo a la izquierda, sobre el Pacífico, bajo las rutas al oeste. Si la ilustración es
          angosta, va compacto y monta solo sobre el borde inferior del mapa, sin llegar a Colombia. */}
      <div className="relative -mt-[11%] w-[70%] @lg:absolute @lg:bottom-0 @lg:left-0 @lg:mt-0 @lg:w-[min(16rem,48%)] @xl:-bottom-2 @xl:w-[min(18rem,48%)]">
        <TarjetaViaje />
      </div>
    </div>
  );
}
