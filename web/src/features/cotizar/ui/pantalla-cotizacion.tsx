"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { CampoAreaTexto } from "@/shared/ui/campo";
import { Alerta } from "@/shared/ui/estado";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { formatearDinero, formatearRango } from "@/shared/ui/formato";
import { useCotizacion, useDecidir, useFormularioCotizacion } from "../application/cotizar";
import {
  MOTIVO_MINIMO,
  hora,
  problemaDeDecision,
  requiereMotivo,
  sinDatos,
  textoOrigenDato,
  tituloRuta,
  type Cotizacion,
  type OpcionVuelo,
} from "../domain/cotizar";
import { Horario, Leyenda, OpcionDeVuelo, nombreVuelo, pesoTotal } from "./opcion-vuelo";
import { EncabezadoPagina, EsqueletoDetalle, EstadoVacio, GIRO, Marca, PRESION } from "./piezas";


export function PantallaCotizacion({ id }: { id: number }) {
  const consulta = useCotizacion(id);
  const migas = [{ texto: "Cotizar viaje", href: "/cotizar" }, { texto: `Cotización ${id}` }];
  if (consulta.isPending) {
    return (
      <section className="flex flex-col gap-6">
        <EsqueletoDetalle texto="Cargando la cotización…" />
      </section>
    );
  }
  if (consulta.error) {
    return (
      <section aria-labelledby="titulo-cotizacion" className="flex flex-col gap-6">
        <EncabezadoPagina idTitulo="titulo-cotizacion" titulo={`Cotización ${id}`} migas={migas} />
        {consulta.error.tipo === "no_encontrado" ? (
          <EstadoVacio titulo="No encontramos esta cotización" accion={{ href: "/cotizar", texto: "Cotizar un viaje" }}>
            <p>Puede que el enlace esté incompleto o que la cotización sea de otra persona.</p>
          </EstadoVacio>
        ) : (
          <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
        )}
      </section>
    );
  }
  return consulta.data ? <VistaCotizacion c={consulta.data} migas={migas} /> : null;
}

function VistaCotizacion({ c, migas }: { c: Cotizacion; migas: { texto: string; href?: string }[] }) {
  const origen = textoOrigenDato(c.origen_dato);
  const vacia = sinDatos(c);
  return (
    <section aria-labelledby="titulo-cotizacion" className="flex flex-col gap-6">
      <EncabezadoPagina
        idTitulo="titulo-cotizacion"
        titulo={tituloRuta(c)}
        migas={migas}
        descripcion={
          <dl className="mt-1 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            <Dato nombre="Viaja" valor={c.viajero?.nombre ?? "Sin asignar"} />
            <Dato nombre="Proyecto" valor={c.proyecto?.nombre ?? "Sin proyecto"} />
            <Dato nombre="Fechas" valor={`${formatearRango(c.ida, c.regreso)} (${c.noches} ${c.noches === 1 ? "noche" : "noches"})`} />
            <Dato
              nombre="Aeropuertos"
              valor={`${c.origen.aeropuertos.join(", ")} → ${c.destino.aeropuertos.join(", ")}`}
            />
            {c.hora_limite ? <Dato nombre="Llegar antes de" valor={`${c.hora_limite} del día de ida`} /> : null}
          </dl>
        }
        accion={
          <div className="flex flex-wrap items-center gap-3">
            <Marca tono={origen.enVivo ? "exito" : "neutro"}>{origen.texto}</Marca>
            {!vacia ? (
              <Link href="/cotizar" className={clasesBoton("secundario", PRESION)}>
                Cotizar con otros datos
              </Link>
            ) : null}
          </div>
        }
      />

      {c.equipo.nivel !== "ok" ? (
        <Alerta tono={c.equipo.nivel === "bloqueo" ? "error" : "aviso"} titulo="Equipo">
          <p>{c.equipo.texto}</p>
        </Alerta>
      ) : null}
      {c.fallos.map((f) => (
        <Alerta key={f} tono="error" titulo="Falló una consulta en vivo">
          <p>{f}</p>
        </Alerta>
      ))}

      {vacia ? (
        <EstadoVacio titulo="Sin datos para esa combinación" accion={{ href: "/cotizar", texto: "Cotizar con otros datos" }}>
          <p>
            El buscador no trajo vuelos para estos aeropuertos y fechas. Prueba otras fechas o agrega aeropuertos cercanos.
            Sin conexión en vivo solo hay precios guardados, como Miami → Moab del 8 al 11 de diciembre de 2026.
          </p>
        </EstadoVacio>
      ) : (
        <Comparacion c={c} />
      )}
    </section>
  );
}

function Dato({ nombre, valor }: { nombre: string; valor: string }) {
  return (
    <div className="flex gap-2">
      <dt className="shrink-0 whitespace-nowrap text-texto-secundario">{nombre}:</dt>
      <dd className="font-semibold">{valor}</dd>
    </div>
  );
}

/** El camino común primero: la recomendada frente a la más barata, con la razón. Lo demás, debajo. */
function Resumen({ c }: { c: Cotizacion }) {
  const todas = [...c.vuelos, ...c.descartados];
  const recomendada = todas.find((v) => v.id === c.recomendada_id);
  const barata = todas.find((v) => v.id === c.mas_barata_id);
  const [verPorque, setVerPorque] = useState(false);
  if (!recomendada) {
    return (
      <Alerta tono="aviso" titulo="Ningún vuelo cumple" rol="status">
        <p>
          Todos los vuelos encontrados se descartaron por la hora límite o el equipo. Puedes elegir uno abajo, con su razón a
          la vista, contando por qué; o <Link href="/cotizar">cotizar con otros datos</Link>.
        </p>
      </Alerta>
    );
  }
  return (
    <section aria-labelledby="titulo-resumen" className="flex flex-col gap-3">
      <h2 id="titulo-resumen" className="text-xl font-bold tracking-tight">
        La recomendación
      </h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <TarjetaResumen titulo="Recomendada por costo total" vuelo={recomendada} destacada />
        {barata && barata.id !== recomendada.id ? (
          <TarjetaResumen titulo="La más barata del buscador" vuelo={barata} />
        ) : null}
      </div>
      {c.aviso ? (
        <div className="rounded-tarjeta border-l-4 border-marca bg-marca-suave p-4">
          <p className="font-bold">Lo más barato no es lo mejor</p>
          <p className="mt-1">{c.aviso}</p>
        </div>
      ) : null}
      <div>
        <button
          type="button"
          aria-expanded={verPorque}
          onClick={() => setVerPorque((v) => !v)}
          className={`inline-flex min-h-11 items-center px-1 font-semibold text-marca underline underline-offset-3 hover:text-marca-oscura ${PRESION}`}
        >
          {verPorque ? "Ocultar el análisis" : "Por qué se recomienda"}
        </button>
        {verPorque ? <p className="mt-2 max-w-prose whitespace-pre-line text-texto-secundario">{c.recomendacion}</p> : null}
      </div>
    </section>
  );
}

function TarjetaResumen({ titulo, vuelo, destacada = false }: { titulo: string; vuelo: OpcionVuelo; destacada?: boolean }) {
  return (
    <div className={`flex flex-col gap-1 rounded-tarjeta border bg-superficie p-4 ${destacada ? "border-2 border-exito" : "border-linea"}`}>
      <p className="text-sm font-semibold text-texto-secundario">{titulo}</p>
      <p className="font-bold">{nombreVuelo(vuelo)}</p>
      <p className="text-sm">
        <Horario vuelo={vuelo} />
      </p>
      <p className="mt-1 flex flex-wrap items-baseline gap-x-3">
        <span className="text-2xl font-extrabold tracking-tight tabular-nums">{formatearDinero(vuelo.costo_total_usd)}</span>
        <span className="text-sm text-texto-secundario">costo total esperado</span>
      </p>
      <p className="text-sm text-texto-secundario">Precio del buscador: {formatearDinero(vuelo.precio_usd)}</p>
    </div>
  );
}

function Comparacion({ c }: { c: Cotizacion }) {
  const decidida = Boolean(c.decision && c.viaje);
  const [cambiando, setCambiando] = useState(false);
  const [recien, setRecien] = useState(false);
  const elegible = c.puede_decidir && (!decidida || cambiando) && !recien;
  const maximo = Math.max(1, ...[...c.vuelos, ...c.descartados].map(pesoTotal));

  return (
    <>
      {decidida && c.viaje && c.decision ? (
        <DecisionGuardada
          c={c}
          recien={recien}
          puedeCambiar={c.puede_decidir && !cambiando}
          onCambiar={() => {
            setRecien(false);
            setCambiando(true);
          }}
        />
      ) : null}
      {c.bloqueo ? (
        <Alerta tono="aviso" titulo="La decisión ya no se puede cambiar" rol="status">
          <p>{c.bloqueo}</p>
        </Alerta>
      ) : !c.puede_decidir ? (
        <Alerta tono="neutro" titulo="Solo lectura" rol="status">
          <p>Esta cotización la decide quien viaja, quien la creó o administración.</p>
        </Alerta>
      ) : null}
      <Resumen c={c} />
      <FormularioDecision
        c={c}
        elegible={elegible}
        maximo={maximo}
        onDecidida={() => {
          setCambiando(false);
          setRecien(true);
        }}
      />
    </>
  );
}

function DecisionGuardada({
  c,
  recien,
  puedeCambiar,
  onCambiar,
}: {
  c: Cotizacion;
  recien: boolean;
  puedeCambiar: boolean;
  onCambiar: () => void;
}) {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (recien) titulo.current?.focus();
  }, [recien]);
  const viaje = c.viaje!;
  const d = c.decision!;
  const vuelo = [...c.vuelos, ...c.descartados].find((v) => v.id === d.vuelo_id);
  const hotel = c.hoteles.find((h) => h.id === d.hotel_id);
  const pendiente = viaje.estado === "pendiente_aprobacion";
  return (
    <section
      aria-labelledby="titulo-decision-guardada"
      className={`flex flex-col gap-3 rounded-tarjeta border-l-4 p-4 md:p-6 ${pendiente ? "border-aviso bg-aviso-suave" : "border-exito bg-exito-suave"}`}
    >
      <h2 id="titulo-decision-guardada" ref={titulo} tabIndex={-1} className="text-xl font-bold tracking-tight focus:outline-none">
        {recien ? (
          `Viaje ${viaje.codigo} creado, pendiente de aprobación`
        ) : (
          <>
            Decisión guardada en el viaje <span className="select-all">{viaje.codigo}</span>
          </>
        )}
      </h2>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <Dato nombre="Estado del viaje" valor={viaje.estado_texto} />
        <Dato nombre="Presupuesto para aprobar" valor={formatearDinero(viaje.presupuesto_usd)} />
        {vuelo ? <Dato nombre="Vuelo elegido" valor={`${nombreVuelo(vuelo)} (${hora(vuelo.sale)})`} /> : null}
        <Dato nombre="Hotel" valor={hotel?.nombre ?? "Sin hotel en esta decisión"} />
        {d.motivo ? <Dato nombre="Por qué" valor={d.motivo} /> : null}
      </dl>
      {d.aviso ? (
        <p className="text-sm font-semibold text-aviso">
          <span aria-hidden="true">! </span>
          {d.aviso}
        </p>
      ) : null}
      <p className="text-sm">
        {pendiente
          ? "Administración revisa el presupuesto. Cuando lo apruebe, podrás cargar los gastos del viaje."
          : viaje.estado === "aprobado"
            ? "El presupuesto está aprobado: ya puedes cargar los gastos del viaje."
            : `Estado: ${viaje.estado_texto}.`}
      </p>
      <div className="flex flex-wrap gap-3">
        <Link href="/viajes" className={clasesBoton("primario", PRESION)}>
          Ver mis viajes
        </Link>
        <Link href="/cotizar" className={clasesBoton("secundario", PRESION)}>
          Cotizar otro viaje
        </Link>
        {puedeCambiar ? (
          <Boton variante="texto" className={PRESION} onClick={onCambiar}>
            Cambiar la decisión
          </Boton>
        ) : null}
      </div>
    </section>
  );
}

function FormularioDecision({
  c,
  elegible,
  maximo,
  onDecidida,
}: {
  c: Cotizacion;
  elegible: boolean;
  maximo: number;
  onDecidida: () => void;
}) {
  const decidir = useDecidir(c.id);
  const formulario = useFormularioCotizacion();
  const clave = `${CLAVE_DECISION}${c.id}`;
  const [inicial] = useState(() => leerDecision(clave));
  const [vueloId, setVueloId] = useState<number | null>(inicial.vueloId);
  const [hotelId, setHotelId] = useState<number | null>(inicial.hotelId);
  const [motivo, setMotivo] = useState(inicial.motivo);
  const [razones, setRazones] = useState<string[]>(inicial.razones);
  useEffect(() => {
    guardarDecision(clave, { vueloId, hotelId, motivo, razones });
  }, [clave, vueloId, hotelId, motivo, razones]);
  const [intentado, setIntentado] = useState(false);
  const [verDescartados, setVerDescartados] = useState(false);
  const nombreGrupo = useId();
  const errorVueloId = useId();
  const problema = intentado ? problemaDeDecision(c, vueloId, motivo) : null;
  const delServidor = decidir.error?.tipo === "validacion" ? decidir.error.campos : {};
  const errorVuelo = problema?.campo === "vuelo" ? problema.mensaje : delServidor.vuelo_id ?? null;
  const errorMotivo = problema?.campo === "motivo" ? problema.mensaje : delServidor.motivo ?? null;
  const conMotivo = requiereMotivo(c, vueloId);
  const elegido = [...c.vuelos, ...c.descartados].find((v) => v.id === vueloId);
  // Sin vuelos que cumplan no hay callejón: se elige entre los descartados, con su razón a la vista y el porqué
  const soloDescartados = c.vuelos.length === 0;
  const opciones = soloDescartados ? c.descartados : c.vuelos;

  function enviar(e: FormEvent) {
    e.preventDefault();
    setIntentado(true);
    const falta = problemaDeDecision(c, vueloId, motivo);
    if (falta || vueloId === null) {
      if (falta?.campo === "motivo") document.getElementById("decision-motivo")?.focus();
      else document.querySelector<HTMLInputElement>(`input[name="${nombreGrupo}"]`)?.focus();
      return;
    }
    decidir.decidir({ vuelo_id: vueloId, hotel_id: hotelId, motivo: motivo.trim(), razones }, () => {
      setIntentado(false);
      borrarDecision(clave);
      onDecidida();
    });
  }

  return (
    <form noValidate onSubmit={enviar} className="flex flex-col gap-6">
      <fieldset className="flex min-w-0 flex-col gap-3" aria-describedby={errorVuelo ? errorVueloId : undefined}>
        <legend className="mb-1 text-xl font-bold tracking-tight">
          {soloDescartados ? "Vuelos descartados" : "Vuelos por costo total esperado"}
        </legend>
        <p className="text-sm text-texto-secundario">
          {soloDescartados
            ? "Ninguno cumple. Si eliges uno, explica abajo el motivo."
            : "Del menor al mayor costo total: precio + equipaje + riesgo de cambio − millas + traslado."}
          {elegible ? " Ninguno viene marcado: la elección es tuya." : ""}
        </p>
        <Leyenda />
        {errorVuelo ? (
          <p id={errorVueloId} role="alert" className="text-sm font-semibold text-error">
            <span aria-hidden="true">✕ </span>
            {errorVuelo}
          </p>
        ) : null}
        <div className="flex flex-col gap-3">
          {opciones.map((v) => (
            <OpcionDeVuelo
              key={v.id}
              vuelo={v}
              maximo={maximo}
              elegible={elegible}
              elegido={v.id === vueloId}
              onElegir={() => setVueloId(v.id)}
              nombreGrupo={nombreGrupo}
            />
          ))}
        </div>
      </fieldset>

      {c.descartados.length && !soloDescartados ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold tracking-tight">
            <button
              type="button"
              aria-expanded={verDescartados}
              onClick={() => setVerDescartados((v) => !v)}
              className={`inline-flex min-h-11 items-center gap-2 text-left ${PRESION}`}
            >
              <span aria-hidden="true" className={`${GIRO} ${verDescartados ? "rotate-90" : ""}`}>
                ›
              </span>
              <span>{`Vuelos descartados (${c.descartados.length})`}</span>
            </button>
          </h2>
          {verDescartados ? (
            <ul className="flex flex-col gap-2">
              {c.descartados.map((v) => (
                <li key={v.id} className="flex flex-col gap-1 rounded-tarjeta border border-linea bg-superficie p-3 sm:flex-row sm:items-center sm:justify-between">
                  <span>
                    <span className="font-semibold">{nombreVuelo(v)}</span>{" "}
                    <span className="text-sm">
                      <Horario vuelo={v} />
                    </span>
                  </span>
                  <span className="text-sm text-error">{v.descartada}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      <Hoteles c={c} elegible={elegible} hotelId={hotelId} onElegir={setHotelId} />

      {elegible ? (
        <section aria-labelledby="titulo-decidir" className="flex flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 md:p-6">
          <h2 id="titulo-decidir" className="text-xl font-bold tracking-tight">
            Tu decisión
          </h2>
          <p aria-live="polite" className="text-sm">
            {elegido
              ? elegido.recomendada
                ? `Elegiste ${nombreVuelo(elegido)}, la recomendada.`
                : `Elegiste ${nombreVuelo(elegido)}, que no es la recomendada: explica abajo por qué la eliges.`
              : "Elige un vuelo de la lista."}
          </p>
          {formulario.data?.razones.length ? (
            <fieldset className="flex min-w-0 flex-col gap-2">
              <legend className="font-semibold">Razones (opcional)</legend>
              <div className="flex flex-wrap gap-x-5 gap-y-1">
                {formulario.data.razones.map((r) => (
                  <label key={r.clave} className="flex min-h-11 items-center gap-2">
                    <input
                      type="checkbox"
                      className="size-5 accent-marca"
                      checked={razones.includes(r.clave)}
                      onChange={(e) =>
                        setRazones((rs) => (e.target.checked ? [...rs, r.clave] : rs.filter((x) => x !== r.clave)))
                      }
                    />
                    {r.texto}
                  </label>
                ))}
              </div>
            </fieldset>
          ) : null}
          <CampoAreaTexto
            id="decision-motivo"
            etiqueta={conMotivo ? "Por qué eliges este vuelo (obligatorio)" : "Por qué eliges este vuelo (opcional)"}
            ayuda={`Obligatorio si no es la recomendada (${MOTIVO_MINIMO} caracteres o más). Es el dato que más ayuda a mejorar las recomendaciones.`}
            required={conMotivo}
            maxLength={300}
            value={motivo}
            error={errorMotivo}
            onChange={(e) => setMotivo(e.target.value)}
          />
          <p className="text-sm text-texto-secundario">
            Al guardar nace el viaje con su presupuesto (vuelo, equipaje, hotel, carro y viáticos por día) y pasa a
            aprobación de administración. El riesgo de cambio y las millas solo sirven para comparar.
          </p>
          <ErrorDecision error={decidir.error} id={c.id} />
          <div>
            <Boton type="submit" disabled={decidir.isPending} className={PRESION}>
              {decidir.isPending ? "Guardando…" : "Guardar decisión y enviar a aprobación"}
            </Boton>
          </div>
        </section>
      ) : null}
    </form>
  );
}

const CLAVE_DECISION = "cotizar-decision-";

interface BorradorDecision {
  vueloId: number | null;
  hotelId: number | null;
  motivo: string;
  razones: string[];
}

/** Lo escrito en la decisión se conserva en la pestaña: si la sesión vence, al volver sigue ahí. Se borra al decidir. */
function leerDecision(clave: string): BorradorDecision {
  const vacio: BorradorDecision = { vueloId: null, hotelId: null, motivo: "", razones: [] };
  if (typeof window === "undefined") return vacio;
  try {
    const guardado = window.sessionStorage.getItem(clave);
    return guardado ? { ...vacio, ...(JSON.parse(guardado) as Partial<BorradorDecision>) } : vacio;
  } catch {
    return vacio;
  }
}

function guardarDecision(clave: string, borrador: BorradorDecision) {
  try {
    window.sessionStorage.setItem(clave, JSON.stringify(borrador));
  } catch {
    // Sin almacenamiento disponible, lo escrito dura lo que la pantalla.
  }
}

function borrarDecision(clave: string) {
  try {
    window.sessionStorage.removeItem(clave);
  } catch {
    // Nada que borrar.
  }
}

function Hoteles({
  c,
  elegible,
  hotelId,
  onElegir,
}: {
  c: Cotizacion;
  elegible: boolean;
  hotelId: number | null;
  onElegir: (id: number | null) => void;
}) {
  const nombre = useId();
  if (!c.hoteles.length) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-xl font-bold tracking-tight">Hotel</h2>
        <p className="text-texto-secundario">
          No hay hoteles para este lugar y fechas{c.ciudad_hotel ? ` (${c.ciudad_hotel})` : ""}. Puedes guardar la decisión
          solo con el vuelo.
        </p>
      </section>
    );
  }
  const filas = c.hoteles.map((h) => ({
    h,
    texto: (
      <span className="flex flex-1 flex-wrap items-baseline justify-between gap-x-4">
        <span>
          <span className="font-semibold">{h.nombre}</span>
          {h.clase ? <span className="text-texto-secundario"> · {h.clase} estrellas</span> : null}
          {h.calificacion ? <span className="text-texto-secundario"> · calificación {h.calificacion.toFixed(1)}</span> : null}
          {h.programa ? <span className="block text-sm text-texto-secundario">{h.programa}, solo con reserva directa</span> : null}
        </span>
        <span className="tabular-nums">
          <span className="font-bold">{formatearDinero(h.total_usd)}</span>{" "}
          <span className="text-sm text-texto-secundario">{c.noches} noches</span>
        </span>
      </span>
    ),
  }));
  if (!elegible) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-xl font-bold tracking-tight">Hoteles</h2>
        <ul className="flex flex-col gap-2">
          {filas.map(({ h, texto }) => (
            <li key={h.id} className="flex rounded-tarjeta border border-linea bg-superficie p-3">
              {texto}
            </li>
          ))}
        </ul>
      </section>
    );
  }
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="mb-1 text-xl font-bold tracking-tight">Hotel (opcional)</legend>
      <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-tarjeta border border-linea bg-superficie p-3">
        <input type="radio" name={nombre} className="size-5 accent-marca" checked={hotelId === null} onChange={() => onElegir(null)} />
        Sin hotel
      </label>
      {filas.map(({ h, texto }) => (
        <label
          key={h.id}
          className={`flex cursor-pointer items-center gap-3 rounded-tarjeta border bg-superficie p-3 ${hotelId === h.id ? "border-2 border-marca" : "border-linea"}`}
        >
          <input type="radio" name={nombre} className="size-5 shrink-0 accent-marca" checked={hotelId === h.id} onChange={() => onElegir(h.id)} />
          {texto}
        </label>
      ))}
    </fieldset>
  );
}

function ErrorDecision({ error, id }: { error: ErrorDeAplicacion | null; id: number }) {
  if (!error || error.tipo === "validacion") return null;
  if (error.tipo === "conflicto") {
    return (
      <Alerta tono="aviso" titulo="La decisión ya no se puede cambiar" rol="alert">
        <p>El viaje ya tiene el presupuesto aprobado o está cerrado. Para cambiarla, administración debe reabrirlo.</p>
      </Alerta>
    );
  }
  if (error.tipo === "sesion_vencida") {
    return (
      <Alerta tono="aviso" titulo="Tu sesión venció" rol="alert">
        <p>
          <Link href={`/entrar?volver=${encodeURIComponent(`/cotizar/${id}`)}`}>Entra de nuevo</Link>: volverás a esta
          cotización para guardar la decisión.
        </p>
      </Alerta>
    );
  }
  return (
    <Alerta tono="error" titulo="No se pudo guardar la decisión" rol="alert">
      <p>{error.tipo === "prohibido" ? "Esta cotización la decide quien viaja, quien la creó o administración." : error.message}</p>
      {error.idPeticion ? <p className="mt-1 text-sm text-texto-secundario">Referencia: {error.idPeticion}</p> : null}
    </Alerta>
  );
}
