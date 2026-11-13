"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { Boton } from "@/shared/ui/boton";
import { CampoSelector, CampoTexto } from "@/shared/ui/campo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle } from "@/shared/ui/esqueleto";
import { Alerta } from "@/shared/ui/estado";
import { formatearRango } from "@/shared/ui/formato";
import { useCotizar, useFormularioCotizacion } from "../application/cotizar";
import {
  BORRADOR_VACIO,
  borradorDeEjemplo,
  erroresDelServidor,
  pedidoDesdeBorrador,
  problemaDeAlcance,
  textoBusqueda,
  validarBorrador,
  type BorradorCotizacion,
  type CampoCotizacion,
  type ErroresBorrador,
  type FormularioCotizacion,
  type PedidoCotizacion,
} from "../domain/cotizar";
import { CampoLugar } from "./campo-lugar";

const CLAVE_BORRADOR = "cotizar-borrador";
const ORDEN: readonly CampoCotizacion[] = [
  "proyectoId", "viajeroId", "origen", "destino", "ida", "regreso", "horaLimite",
  "bateriasN", "bateriasWh", "probCambio", "carroDia",
];

function idCampo(campo: CampoCotizacion): string {
  return `cotizar-${campo}`;
}

/** Lo escrito se conserva en la pestaña: un error o una sesión vencida no lo borran. */
function leerBorrador(): BorradorCotizacion {
  if (typeof window === "undefined") return BORRADOR_VACIO;
  try {
    const guardado = window.sessionStorage.getItem(CLAVE_BORRADOR);
    return guardado ? { ...BORRADOR_VACIO, ...(JSON.parse(guardado) as Partial<BorradorCotizacion>) } : BORRADOR_VACIO;
  } catch {
    return BORRADOR_VACIO;
  }
}

/** Valores por omisión que dependen del formulario: viaja quien cotiza; si hay un solo proyecto, ese. */
function conOmisiones(b: BorradorCotizacion, f: FormularioCotizacion): BorradorCotizacion {
  return {
    ...b,
    viajeroId: b.viajeroId || (f.viajero_propio_id ? String(f.viajero_propio_id) : ""),
    proyectoId: b.proyectoId || (f.proyectos.length === 1 ? String(f.proyectos[0]!.id) : ""),
  };
}

export function PantallaCotizar() {
  const formulario = useFormularioCotizacion();
  return (
    <section aria-labelledby="titulo-cotizar" className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        idTitulo="titulo-cotizar"
        migas={[{ texto: "Operaciones" }, { texto: "Cotizar viaje" }]}
        titulo="Cotizar un viaje"
        descripcion="Escribe los lugares como en un buscador de vuelos: un país, una ciudad, un pueblo o el código de un aeropuerto. Se comparan los aeropuertos cercanos por el costo total esperado, no solo por el precio."
      />
      {formulario.isPending ? (
        <EsqueletoDetalle texto="Preparando el formulario…" />
      ) : formulario.error ? (
        <ErrorConsulta error={formulario.error} onReintentar={() => void formulario.refetch()} />
      ) : formulario.data ? (
        <FormularioCotizar datos={formulario.data} />
      ) : null}
    </section>
  );
}

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 md:p-6">
      {/* Flotante: la leyenda queda dentro de la tarjeta como su título, no montada sobre el borde. */}
      <legend className="float-left w-full text-lg font-bold">{titulo}</legend>
      {children}
    </fieldset>
  );
}

function FormularioCotizar({ datos }: { datos: FormularioCotizacion }) {
  const router = useRouter();
  const cotizar = useCotizar();
  const [borrador, setBorrador] = useState<BorradorCotizacion>(leerBorrador);
  const [tocados, setTocados] = useState<ReadonlySet<CampoCotizacion>>(new Set());
  const [intentado, setIntentado] = useState(false);
  const [delServidor, setDelServidor] = useState<ErroresBorrador>({});
  const [pedido, setPedido] = useState<PedidoCotizacion | null>(null);
  const origenRef = useRef<HTMLInputElement>(null);
  const destinoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(CLAVE_BORRADOR, JSON.stringify(borrador));
    } catch {
      // Sin almacenamiento disponible, lo escrito dura lo que la pantalla.
    }
  }, [borrador]);

  const efectivo = conOmisiones(borrador, datos);
  const alcance = problemaDeAlcance(efectivo, datos);
  const propios: ErroresBorrador = { ...validarBorrador(efectivo), ...(alcance ? { proyectoId: alcance } : {}) };
  const paraOtra = Boolean(efectivo.viajeroId) && efectivo.viajeroId !== String(datos.viajero_propio_id ?? "");
  const visibles: ErroresBorrador = { ...delServidor };
  for (const campo of ORDEN) {
    if (propios[campo] && (intentado || tocados.has(campo))) visibles[campo] = propios[campo];
  }
  const buscando = cotizar.isPending;

  function cambiar<K extends keyof BorradorCotizacion>(campo: K, valor: BorradorCotizacion[K]) {
    setBorrador((b) => ({ ...b, [campo]: valor }));
    if (campo in delServidor) {
      setDelServidor((d) => {
        const copia = { ...d };
        delete copia[campo as CampoCotizacion];
        return copia;
      });
    }
  }

  function tocar(campo: CampoCotizacion) {
    setTocados((t) => new Set(t).add(campo));
  }

  function enfocar(campo: CampoCotizacion) {
    if (campo === "origen") origenRef.current?.focus();
    else if (campo === "destino") destinoRef.current?.focus();
    else document.getElementById(idCampo(campo))?.focus();
  }

  function enviar(e?: FormEvent) {
    e?.preventDefault();
    if (buscando) return;
    setIntentado(true);
    const primero = ORDEN.find((c) => propios[c]);
    if (primero) {
      enfocar(primero);
      return;
    }
    const nuevo = pedidoDesdeBorrador(efectivo, datos.viajero_propio_id);
    setPedido(nuevo);
    setDelServidor({});
    cotizar.mutate(nuevo, {
      onSuccess: (c) => router.push(`/cotizar/${c.id}`),
      onError: (error) => {
        if (error.tipo !== "validacion") return;
        const campos = erroresDelServidor(error.campos);
        setDelServidor(campos);
        const primeroServidor = ORDEN.find((c) => campos[c]);
        if (primeroServidor) enfocar(primeroServidor);
      },
    });
  }

  const propio = datos.viajeros.find((v) => v.soy_yo);
  const comun = (campo: CampoCotizacion) => ({
    id: idCampo(campo),
    error: visibles[campo] ?? null,
    onBlur: () => tocar(campo),
  });

  return (
    <form noValidate onSubmit={enviar} className="flex flex-col gap-6 md:gap-8" aria-busy={buscando}>
      {!datos.precios_en_vivo ? (
        <Alerta tono="info" titulo="El buscador en vivo no está conectado" rol="status">
          <p>
            Solo hay precios guardados, como Miami → Moab del 8 al 11 de diciembre de 2026. Otras rutas mostrarán «sin
            datos».
          </p>
        </Alerta>
      ) : null}
      <p className="flex flex-wrap items-baseline gap-x-2">
        <Boton
          variante="texto"
          className="-ml-1"
          onClick={() => {
            setBorrador((b) => {
              const ejemplo = borradorDeEjemplo(conOmisiones(b, datos));
              return { ...ejemplo, proyectoId: ejemplo.proyectoId || String(datos.proyectos[0]?.id ?? "") };
            });
            setDelServidor({});
          }}
        >
          Usar el caso de ejemplo
        </Boton>
        <span className="text-sm text-texto-secundario">(Miami → Moab, comparando CNY, GJT y SLC)</span>
      </p>

      <Seccion titulo="Quién y para qué">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <CampoSelector
            {...comun("proyectoId")}
            etiqueta="Proyecto"
            value={efectivo.proyectoId}
            onChange={(e) => cambiar("proyectoId", e.target.value)}
          >
            <option value="" disabled>
              Elige un proyecto
            </option>
            {datos.proyectos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
                {p.ciudad ? ` · ${p.ciudad}` : ""}
                {p.inicio && p.fin ? ` · ${formatearRango(p.inicio, p.fin)}` : ""}
                {paraOtra && !p.para_otra_persona ? " (solo para ti)" : ""}
              </option>
            ))}
          </CampoSelector>
          {datos.elige_viajero ? (
            <CampoSelector
              {...comun("viajeroId")}
              etiqueta="Quién viaja"
              ayuda="Por omisión, tú. Puedes cotizar para otra persona del equipo."
              value={efectivo.viajeroId}
              onChange={(e) => cambiar("viajeroId", e.target.value)}
            >
              <option value="" disabled>
                Elige quién viaja
              </option>
              {datos.viajeros.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.nombre}
                  {v.soy_yo ? " (tú)" : v.base ? ` · ${v.base}` : ""}
                </option>
              ))}
            </CampoSelector>
          ) : (
            <div className="flex flex-col gap-1">
              <span className="font-semibold">Quién viaja</span>
              {propio ? (
                <p className="flex min-h-11 items-center">{`${propio.nombre} (tú)`}</p>
              ) : (
                <p id={idCampo("viajeroId")} className="text-sm font-semibold text-error">
                  Tu cuenta no tiene perfil de viajero. Pide a administración que lo cree.
                </p>
              )}
            </div>
          )}
        </div>
      </Seccion>

      <Seccion titulo="Ruta y fechas">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <CampoLugar
            id={idCampo("origen")}
            etiqueta="Origen"
            lado="origen"
            valor={efectivo.origen}
            onCambio={(v) => cambiar("origen", v)}
            error={visibles.origen ?? null}
            entradaRef={origenRef}
            onSalir={() => tocar("origen")}
          />
          <CampoLugar
            id={idCampo("destino")}
            etiqueta="Destino"
            lado="destino"
            valor={efectivo.destino}
            onCambio={(v) => cambiar("destino", v)}
            error={visibles.destino ?? null}
            entradaRef={destinoRef}
            onSalir={() => tocar("destino")}
          />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <CampoTexto {...comun("ida")} etiqueta="Ida" type="date" value={efectivo.ida} onChange={(e) => cambiar("ida", e.target.value)} />
          <CampoTexto
            {...comun("regreso")}
            etiqueta="Regreso"
            type="date"
            min={efectivo.ida || undefined}
            value={efectivo.regreso}
            onChange={(e) => cambiar("regreso", e.target.value)}
          />
          <CampoTexto
            {...comun("horaLimite")}
            etiqueta="Llegar antes de (opcional)"
            ayuda="Hora en el destino el día de ida. Descarta los vuelos que llegan tarde."
            type="time"
            value={efectivo.horaLimite}
            onChange={(e) => cambiar("horaLimite", e.target.value)}
          />
        </div>
        <CampoTexto
          id="cotizar-ciudadHotel"
          etiqueta="Ciudad del hotel (opcional)"
          ayuda="Vacío: se buscan hoteles en el lugar de destino."
          value={efectivo.ciudadHotel}
          maxLength={80}
          onChange={(e) => cambiar("ciudadHotel", e.target.value)}
        />
      </Seccion>

      <Seccion titulo="Equipo y supuestos">
        {/* Dos columnas: con cuatro, las etiquetas largas se parten y los campos quedan a distinta altura. */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <CampoTexto {...comun("bateriasN")} etiqueta="Baterías de repuesto" inputMode="numeric" value={efectivo.bateriasN}
            onChange={(e) => cambiar("bateriasN", e.target.value)} />
          <CampoTexto {...comun("bateriasWh")} etiqueta="Capacidad de cada batería (Wh)" inputMode="decimal" value={efectivo.bateriasWh}
            onChange={(e) => cambiar("bateriasWh", e.target.value)} />
          <CampoTexto {...comun("probCambio")} etiqueta="Probabilidad de cambio de fecha (%)" inputMode="numeric" value={efectivo.probCambio}
            onChange={(e) => cambiar("probCambio", e.target.value)} />
          <CampoTexto {...comun("carroDia")} etiqueta="Carro de alquiler por día (USD)" ayuda="0 si no hay carro." inputMode="decimal"
            value={efectivo.carroDia} onChange={(e) => cambiar("carroDia", e.target.value)} />
        </div>
        <label className="flex min-h-11 items-center gap-3 font-semibold">
          <input
            type="checkbox"
            className="size-5 accent-marca"
            checked={efectivo.maleta}
            onChange={(e) => cambiar("maleta", e.target.checked)}
          />
          Lleva maleta facturada
        </label>
      </Seccion>

      <ResultadoEnvio
        error={cotizar.error}
        tieneCampos={Object.keys(delServidor).length > 0}
        onReintentar={() => enviar()}
      />

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Boton type="submit" disabled={buscando}>
            {buscando ? "Buscando…" : "Buscar y comparar"}
          </Boton>
          {!buscando ? (
            <p className="text-sm text-texto-secundario">
              Una ruta nueva usa dos consultas al buscador (vuelos y hoteles) y tarda unos segundos.
            </p>
          ) : null}
        </div>
        {buscando && pedido ? <ProgresoBusqueda pedido={pedido} enVivo={datos.precios_en_vivo} /> : null}
      </div>
    </form>
  );
}

/** Lo que pasó al enviar, en lenguaje claro según el tipo de error. */
function ResultadoEnvio({
  error,
  tieneCampos,
  onReintentar,
}: {
  error: ErrorDeAplicacion | null;
  tieneCampos: boolean;
  onReintentar: () => void;
}) {
  if (!error) return null;
  if (error.tipo === "validacion") {
    return (
      <Alerta tono="error" titulo="Revisa los datos marcados" rol="alert">
        <p>{tieneCampos ? "Cada campo dice qué corregir. Lo que escribiste se conserva." : error.message}</p>
      </Alerta>
    );
  }
  if (error.tipo === "sesion_vencida") {
    return (
      <Alerta tono="aviso" titulo="Tu sesión venció" rol="alert">
        <p>
          <Link href="/entrar?volver=%2Fcotizar">Entra de nuevo</Link>: al volver, lo que escribiste sigue aquí.
        </p>
      </Alerta>
    );
  }
  const textos: Partial<Record<ErrorDeAplicacion["tipo"], string>> = {
    demasiados_intentos:
      "Llegaste al tope de cotizaciones nuevas de hoy. Retoma una de las que ya tienes o pide a administración que amplíe el tope.",
    conflicto: "Esa cotización todavía se está buscando. Espera un momento y vuelve a intentarlo.",
    prohibido: "Tu cuenta no puede cotizar para esa persona. Cotiza para ti o pide ayuda a gestión.",
  };
  return (
    <Alerta tono="error" titulo="No se pudo cotizar" rol="alert">
      <p>{textos[error.tipo] ?? error.message}</p>
      {error.idPeticion ? <p className="mt-1 text-sm text-texto-secundario">Referencia: {error.idPeticion}</p> : null}
      {error.tipo === "red" || error.tipo === "servidor" ? (
        <Boton variante="secundario" className="mt-3" onClick={onReintentar}>
          Reintentar
        </Boton>
      ) : null}
    </Alerta>
  );
}

/** Qué está haciendo la búsqueda, paso a paso. Una búsqueda en vivo tarda unos segundos. */
function ProgresoBusqueda({ pedido, enVivo }: { pedido: PedidoCotizacion; enVivo: boolean }) {
  const [paso, setPaso] = useState(0);
  useEffect(() => {
    const temporizadores = [setTimeout(() => setPaso(1), 3000), setTimeout(() => setPaso(2), 7000)];
    return () => temporizadores.forEach(clearTimeout);
  }, []);
  const hotel = pedido.ciudad_hotel || pedido.destino.lugar?.nombre || pedido.destino.texto;
  const pasos = [
    textoBusqueda(pedido),
    `Buscando hoteles en ${hotel}…`,
    "Calculando el costo total esperado de cada vuelo…",
  ];
  return (
    <div role="status" className="rounded-tarjeta border border-marca bg-marca-suave p-4">
      <ol className="flex flex-col gap-1">
        {pasos.slice(0, paso + 1).map((texto, i) => (
          <li key={texto} className={i === paso ? "font-bold text-texto" : "text-texto-secundario"}>
            <span aria-hidden="true">{i === paso ? "• " : "✓ "}</span>
            <span>{texto}</span>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-sm text-texto-secundario">
        {enVivo
          ? "Si la ruta ya se buscó antes, se usan los precios guardados y no se gasta otra consulta."
          : "Sin conexión en vivo: se usan los precios guardados."}
      </p>
    </div>
  );
}
