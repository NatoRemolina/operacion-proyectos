"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";
import { estadoVisibleGasto, etiquetaCategoria, type GastoDetalle, type Justificacion } from "@/features/gastos/domain/gastos";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { CampoAreaTexto, CampoSelector, CampoTexto } from "@/shared/ui/campo";
import { DialogoConfirmacion } from "@/shared/ui/dialogo-confirmacion";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle } from "@/shared/ui/esqueleto";
import { Alerta } from "@/shared/ui/estado";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearDinero, formatearFecha, formatearInstante } from "@/shared/ui/formato";
import { Migas, type Miga } from "@/shared/ui/migas";
import { useAdministracionRepository, useDatosRevision, useRevisarGasto } from "../application/administracion";
import { problemaDeMotivo, type RevisionGasto as Revision } from "../domain/administracion";
import {
  cambiosDeRevision,
  formularioInicial,
  importeNormalizado,
  problemaDeMotivoExcepcion,
  type DatosRevision,
  type FormularioRevision,
  type LecturaOriginal,
  type SoporteRevision,
} from "../domain/revision";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

const TITULO_ERROR: Partial<Record<ErrorDeAplicacion["tipo"], string>> = {
  prohibido: "No puedes revisar este gasto",
  cambio_ajeno: "El gasto cambió mientras lo revisabas",
  validacion: "No se guardó la revisión",
};

const CANAL: Record<string, string> = { web: "Web", celular: "Celular", correo: "Correo", telegram: "Telegram" };

const HECHO: Record<"aprobar" | "excepcion" | "rechazar", string> = {
  aprobar: "Gasto aprobado.",
  excepcion: "Gasto aprobado con excepción: el motivo queda en la auditoría.",
  rechazar: "Gasto rechazado: la persona verá el motivo.",
};

function Fila({ termino, children }: { termino: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 border-b border-linea py-2 last:border-b-0">
      <dt className="text-texto-secundario">{termino}</dt>
      <dd className="text-right font-semibold tabular-nums">{children}</dd>
    </div>
  );
}

/** La foto del recibo. Si no se puede mostrar, se ofrece abrirla aparte. */
function ImagenRecibo({ url, comercio }: { url: string; comercio: string }) {
  const [noSeMuestra, setNoSeMuestra] = useState(false);
  if (noSeMuestra) {
    return (
      <p>
        No se puede mostrar aquí: puede ser un PDF o un correo, o el archivo no está disponible.{" "}
        <a href={url} target="_blank" rel="noopener noreferrer">
          Abrir el recibo original en otra pestaña
        </a>
      </p>
    );
  }
  return (
    <figure className="flex flex-col gap-2">
      {/* El original lo sirve la API aislado; no pasa por el optimizador de imágenes. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={`Recibo original de ${comercio}`}
        onError={() => setNoSeMuestra(true)}
        className="max-h-160 w-full rounded-md border border-linea bg-neutro-suave object-contain"
      />
      <figcaption>
        <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center">
          Abrir en tamaño completo
        </a>
      </figcaption>
    </figure>
  );
}

/** El recibo tal como llegó: imagen o PDF al lado; un correo o una confirmación HTML, para descargar. */
function SoporteOriginal({ soporte, url, comercio }: { soporte: SoporteRevision; url: string | null; comercio: string }) {
  if (!url) return <p className="text-texto-secundario">El original no está disponible en esta fuente de datos.</p>;
  if (soporte.forma === "imagen") return <ImagenRecibo url={url} comercio={comercio} />;
  if (soporte.forma === "pdf") {
    return (
      <div className="flex flex-col gap-2">
        <iframe src={url} title={`Recibo original de ${comercio} (PDF)`} className="h-160 w-full rounded-md border border-linea bg-neutro-suave" />
        <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center">
          Abrir el PDF en otra pestaña
        </a>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-texto-secundario">
        Llegó como correo o como confirmación en HTML. Se guardó sin código ni enlaces activos, y no se muestra aquí: descárgalo para leerlo.
      </p>
      <a href={url} download className={clasesBoton("secundario", "self-start")}>
        Descargar el recibo original{soporte.nombre ? ` (${soporte.nombre})` : ""}
      </a>
    </div>
  );
}

function TextoJustificacion({ j }: { j: Justificacion }) {
  if (j.texto) return <p>{j.texto}</p>;
  if (j.tipo !== "audio") return null;
  const estado =
    j.transcripcion === "pendiente"
      ? "Transcripción pendiente: escucha la nota."
      : j.transcripcion === "fallida"
        ? "No se pudo transcribir: escucha la nota."
        : "Nota de voz sin transcribir.";
  return <p className="text-texto-secundario">{estado}</p>;
}

function Justificaciones({ gasto, urlAudio }: { gasto: GastoDetalle; urlAudio: (jid: number) => string | null }) {
  if (!gasto.justificaciones.length) return <p className="text-texto-secundario">No dejó una justificación.</p>;
  return (
    <ul className="flex flex-col gap-3">
      {gasto.justificaciones.map((j) => {
        const url = j.tipo === "audio" ? urlAudio(j.id) : null;
        return (
          <li key={j.id} className="flex flex-col gap-1 border-b border-linea pb-3 last:border-b-0 last:pb-0">
            <p className="text-sm text-texto-secundario">
              {j.tipo === "audio" ? "Nota de voz" : "Por escrito"} · {CANAL[j.canal] ?? j.canal} · {formatearInstante(j.creado)}
            </p>
            {url ? (
              <audio controls preload="none" src={url} aria-label="Nota de voz de la persona" className="w-full max-w-md">
                <a href={url}>Descargar la nota de voz</a>
              </audio>
            ) : null}
            <TextoJustificacion j={j} />
          </li>
        );
      })}
    </ul>
  );
}

function LecturaDelRecibo({ lectura }: { lectura: LecturaOriginal | null }) {
  if (!lectura) {
    return <p className="text-texto-secundario">La lectura del recibo falló o no se guardó: completa los datos a mano.</p>;
  }
  return (
    <>
      <dl>
        <Fila termino="Comercio">{lectura.comercio ?? "Sin leer"}</Fila>
        <Fila termino="Fecha">{formatearFecha(lectura.fecha)}</Fila>
        <Fila termino="Categoría">{etiquetaCategoria(lectura.categoria)}</Fila>
        <Fila termino="Subtotal">{formatearDinero(lectura.subtotal, lectura.moneda)}</Fila>
        <Fila termino="Impuesto">{formatearDinero(lectura.impuesto, lectura.moneda)}</Fila>
        <Fila termino="Propina">{lectura.propina === null ? "Sin propina" : formatearDinero(lectura.propina, lectura.moneda)}</Fila>
        <Fila termino="Total">{formatearDinero(lectura.total, lectura.moneda)}</Fila>
        <Fila termino="Confianza de la lectura">
          {lectura.confianza === null ? "Sin dato" : `${Math.round(lectura.confianza * 100)} %`}
        </Fila>
      </dl>
      {lectura.dudas.length ? (
        <p className="mt-2 text-sm text-texto-secundario">La lectura no estaba segura de: {lectura.dudas.join(", ")}.</p>
      ) : null}
    </>
  );
}

type CampoTextual = Exclude<keyof FormularioRevision, "categoria" | "viaje">;

/** «Se leyó: …» cuando la lectura original no coincide con lo que hay guardado. */
function seLeyo(lectura: LecturaOriginal | null, campo: CampoTextual, actual: string): string | undefined {
  if (!lectura) return undefined;
  const original = lectura[campo];
  if (original === null || original === "") return undefined;
  const esImporte = ["subtotal", "impuesto", "propina", "total"].includes(campo);
  const comparable = esImporte ? importeNormalizado(actual) : { valor: actual.trim() };
  return "valor" in comparable && comparable.valor === original ? undefined : `Se leyó: ${original}`;
}

const CAMPOS: readonly { campo: CampoTextual; etiqueta: string; tipo?: string; decimal?: boolean; max?: number }[] = [
  { campo: "comercio", etiqueta: "Comercio", max: 200 },
  { campo: "fecha", etiqueta: "Fecha", tipo: "date" },
  { campo: "moneda", etiqueta: "Moneda", max: 3 },
  { campo: "subtotal", etiqueta: "Subtotal", decimal: true },
  { campo: "impuesto", etiqueta: "Impuesto", decimal: true },
  { campo: "propina", etiqueta: "Propina", decimal: true },
  { campo: "total", etiqueta: "Total", decimal: true },
  { campo: "metodo_pago", etiqueta: "Método de pago", max: 200 },
  { campo: "canal_reserva", etiqueta: "Canal de reserva", max: 200 },
];

/**
 * Revisión completa de administración: el recibo al lado, la lectura original, los datos para
 * corregir, el viaje, lo que contó la persona y la decisión. Tras decidir, pasa al siguiente gasto
 * en revisión. Las reglas (versión, nadie revisa lo suyo, motivos) las aplica el servidor.
 */
export function RevisionGasto({ gasto, urlOriginal, migas }: { gasto: GastoDetalle; urlOriginal: string | null; migas: readonly Miga[] }) {
  const consulta = useDatosRevision(gasto.id);
  // Lo que debe sobrevivir cuando el formulario se vuelve a cargar con la versión nueva del gasto.
  const [sigueEnRevision, setSigueEnRevision] = useState(false);
  const [error, setError] = useState<ErrorDeAplicacion | null>(null);
  const [motivo, setMotivo] = useState("");
  const [motivoExcepcion, setMotivoExcepcion] = useState("");
  const datos = consulta.data;
  if (!datos) {
    return (
      <div className="flex flex-col gap-4">
        <Migas items={migas} />
        {consulta.error ? (
          <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
        ) : (
          <EsqueletoDetalle texto="Cargando la revisión…" />
        )}
      </div>
    );
  }
  return (
    <RevisionCompleta
      // Con cada versión nueva el formulario parte de lo guardado; mientras la ficha y los datos de revisión no son
      // de la misma versión, no se envía nada (se editaría algo viejo).
      key={`${gasto.version ?? 0}-${datos.version}`}
      gasto={gasto}
      datos={datos}
      actualizando={datos.version !== (gasto.version ?? 0)}
      urlOriginal={urlOriginal}
      migas={migas}
      persistente={{ sigueEnRevision, setSigueEnRevision, error, setError, motivo, setMotivo, motivoExcepcion, setMotivoExcepcion }}
    />
  );
}

interface EstadoPersistente {
  readonly sigueEnRevision: boolean;
  readonly setSigueEnRevision: (valor: boolean) => void;
  readonly error: ErrorDeAplicacion | null;
  readonly setError: (valor: ErrorDeAplicacion | null) => void;
  readonly motivo: string;
  readonly setMotivo: (valor: string) => void;
  readonly motivoExcepcion: string;
  readonly setMotivoExcepcion: (valor: string) => void;
}

function RevisionCompleta({
  gasto,
  datos,
  actualizando,
  urlOriginal,
  migas,
  persistente,
}: {
  gasto: GastoDetalle;
  datos: DatosRevision;
  actualizando: boolean;
  urlOriginal: string | null;
  migas: readonly Miga[];
  persistente: EstadoPersistente;
}) {
  const router = useRouter();
  const { avisar } = useAvisos();
  const repositorio = useAdministracionRepository();
  const revision = useRevisarGasto(gasto.id);
  const [inicial] = useState(() => formularioInicial(gasto, datos));
  const [formulario, setFormulario] = useState(inicial);
  const [erroresCampos, setErroresCampos] = useState<Readonly<Record<string, string>>>({});
  const [dialogo, setDialogo] = useState<"rechazar" | "excepcion" | null>(null);
  const [errorMotivo, setErrorMotivo] = useState<string | null>(null);
  const { sigueEnRevision, setSigueEnRevision, error, setError, motivo, setMotivo, motivoExcepcion, setMotivoExcepcion } = persistente;
  const comercio = gasto.comercio ?? "gasto sin comercio leído";
  const version = gasto.version ?? 0;
  const ocupado = revision.isPending || actualizando;

  const viajes = datos.viajes.some((v) => String(v.id) === inicial.viaje) || !gasto.viaje
    ? datos.viajes
    : [{ id: gasto.viaje.id, codigo: gasto.viaje.codigo, estado_texto: "", titular: null, ida: null }, ...datos.viajes];
  const categorias = datos.categorias.some((c) => c.clave === inicial.categoria) || !inicial.categoria
    ? datos.categorias
    : [{ clave: inicial.categoria, nombre: etiquetaCategoria(inicial.categoria) }, ...datos.categorias];

  function cambiar(campo: keyof FormularioRevision, valor: string) {
    setFormulario((f) => ({ ...f, [campo]: valor }));
    if (erroresCampos[campo]) setErroresCampos((previos) => Object.fromEntries(Object.entries(previos).filter(([c]) => c !== campo)));
  }

  function enviar(accion: Revision["accion"], texto = "") {
    setError(null);
    setSigueEnRevision(false);
    const cambios = cambiosDeRevision(formulario, inicial);
    const conCambios = accion !== "rechazar";
    if (conCambios && Object.keys(cambios.errores).length) {
      setErroresCampos(cambios.errores);
      setDialogo(null);
      avisar({ tono: "aviso", texto: "Revisa los datos marcados: no se envió nada." });
      return;
    }
    const hayCampos = conCambios && Object.keys(cambios.campos).length > 0;
    const hayViaje = conCambios && cambios.viajeId !== undefined;
    if (accion === "guardar" && !hayCampos && !hayViaje) {
      avisar({ tono: "info", texto: "No hay correcciones que guardar." });
      return;
    }
    const cuerpo: Revision = {
      version,
      accion,
      ...(accion === "rechazar" || accion === "excepcion" ? { motivo: texto.trim() } : {}),
      ...(hayCampos ? { campos: cambios.campos } : {}),
      ...(hayViaje ? { viajeId: cambios.viajeId } : {}),
    };
    revision.mutate(cuerpo, {
      onSuccess: ({ gasto: revisado, siguiente }) => {
        setDialogo(null);
        if (accion === "guardar") {
          avisar({ tono: "exito", texto: "Correcciones guardadas. El gasto sigue en revisión." });
          return;
        }
        // Aprobar vuelve a pasar las reglas: si no pasan, el gasto sigue en revisión y no se aprobó.
        if (revisado.estado === "revision") {
          setSigueEnRevision(true);
          avisar({ tono: "aviso", texto: "No se aprobó: el gasto sigue en revisión." });
          return;
        }
        setMotivo("");
        setMotivoExcepcion("");
        const hecho = HECHO[accion];
        if (siguiente) {
          avisar({ tono: "exito", texto: `${hecho} Sigue el siguiente en revisión.` });
          router.push(`/gastos/${siguiente.id}`);
        } else {
          avisar({ tono: "exito", texto: `${hecho} No quedan gastos en revisión.` });
        }
      },
      onError: (e) => {
        if (e.tipo === "validacion" && e.campos.motivo && dialogo) {
          setErrorMotivo(e.campos.motivo);
          return;
        }
        if (e.tipo === "validacion" && Object.keys(e.campos).length) setErroresCampos(e.campos);
        setDialogo(null);
        setError(e);
        // Si el gasto ya no está en revisión, esta vista se cierra al recargar: el aviso queda.
        if (e.tipo === "cambio_ajeno") {
          avisar({ tono: "aviso", texto: "Otra persona cambió este gasto mientras lo revisabas: cargamos lo último." });
        }
      },
    });
  }

  function guardar(evento: FormEvent) {
    evento.preventDefault();
    enviar("guardar");
  }

  function confirmarDialogo() {
    const texto = dialogo === "rechazar" ? motivo : motivoExcepcion;
    const problema = dialogo === "rechazar" ? problemaDeMotivo(texto) : problemaDeMotivoExcepcion(texto);
    setErrorMotivo(problema);
    if (!problema && dialogo) enviar(dialogo, texto);
  }

  function abrir(cual: "rechazar" | "excepcion") {
    setErrorMotivo(null);
    setDialogo(cual);
  }

  const enDialogo = dialogo === "rechazar" ? motivo : motivoExcepcion;
  const validarMotivo = dialogo === "rechazar" ? problemaDeMotivo : problemaDeMotivoExcepcion;

  return (
    <div className="flex flex-col gap-6 md:gap-8">
      <header className="flex flex-col gap-1">
        <Migas items={migas} />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-extrabold">Revisar: {gasto.comercio ?? "Gasto sin comercio leído"}</h1>
              <EtiquetaEstado estado={estadoVisibleGasto(gasto.estado)} texto={gasto.estado_texto} />
            </div>
            <p className="text-texto-secundario">
              Recibido {formatearInstante(gasto.creado)} · {gasto.viaje?.codigo ?? "sin viaje asignado"}
            </p>
          </div>
          {/* La decisión, visible sin desplazarse: una sola acción principal. Aprobar incluye las correcciones. */}
          <div className="flex flex-wrap gap-2">
            <Boton variante="secundario" onClick={() => abrir("rechazar")} disabled={ocupado}>
              Rechazar
            </Boton>
            <Boton onClick={() => enviar("aprobar")} disabled={ocupado}>
              {ocupado && revision.variables?.accion === "aprobar" ? "Aprobando…" : "Aprobar gasto"}
            </Boton>
          </div>
        </div>
      </header>

      {sigueEnRevision ? (
        <Alerta tono="aviso" rol="alert" titulo="No se aprobó: las reglas todavía no lo dejan pasar">
          <p>
            Mira «Por qué va a revisión». Corrige los datos abajo y vuelve a aprobar, o usa «Aprobar con excepción» si el gasto es legítimo.
          </p>
        </Alerta>
      ) : null}
      {error ? (
        <Alerta tono={error.tipo === "cambio_ajeno" ? "aviso" : "error"} rol="alert" titulo={TITULO_ERROR[error.tipo] ?? "No se pudo guardar la revisión"}>
          <p>
            {error.tipo === "prohibido" ? "Si el gasto es tuyo, lo revisa otra persona de administración." : error.message}
          </p>
        </Alerta>
      ) : null}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
        <section aria-labelledby="titulo-recibo" className={`${TARJETA} flex flex-col gap-3`}>
          <h2 id="titulo-recibo" className="text-lg font-bold">
            Recibo original
          </h2>
          {gasto.correo ? (
            <dl>
              <Fila termino="Remitente">{gasto.correo.remitente ?? "Sin remitente leído"}</Fila>
              <Fila termino="Asunto">{gasto.correo.asunto ?? "Sin asunto"}</Fila>
            </dl>
          ) : null}
          {datos.soporte ? (
            <SoporteOriginal soporte={datos.soporte} url={urlOriginal} comercio={comercio} />
          ) : (
            <p className="text-texto-secundario">Este gasto no tiene un archivo original guardado.</p>
          )}
        </section>

        <div className="flex min-w-0 flex-col gap-4">
          <section aria-labelledby="titulo-motivos" className={`${TARJETA} flex flex-col gap-2`}>
            <h2 id="titulo-motivos" className="text-lg font-bold">
              Por qué va a revisión
            </h2>
            {gasto.alertas.length ? (
              <ul className="flex flex-col gap-2">
                {gasto.alertas.map((alerta) => (
                  <li key={alerta} className="rounded-lg border-l-4 border-aviso bg-aviso-suave p-3">
                    <span aria-hidden="true" className="font-bold text-aviso">
                      !{" "}
                    </span>
                    {alerta}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-texto-secundario">Las reglas no dejaron una alerta escrita: revisa los datos leídos.</p>
            )}
          </section>

          <section aria-labelledby="titulo-contado" className={TARJETA}>
            <h2 id="titulo-contado" className="mb-1 text-lg font-bold">
              Lo que contó la persona
            </h2>
            <Justificaciones gasto={gasto} urlAudio={(jid) => repositorio.urlAudioJustificacion(gasto.id, jid)} />
          </section>

          <section aria-labelledby="titulo-leido" className={TARJETA}>
            <h2 id="titulo-leido" className="mb-1 text-lg font-bold">
              Lo que leímos del recibo
            </h2>
            <LecturaDelRecibo lectura={datos.lectura_original} />
          </section>

          <section aria-labelledby="titulo-corregir" className={TARJETA}>
            <h2 id="titulo-corregir" className="mb-1 text-lg font-bold">
              Corregir los datos
            </h2>
            <p className="mb-3 text-sm text-texto-secundario">
              Lo que cambies aquí se guarda con «Guardar correcciones» y también al aprobar. Lo que no cambies se conserva.
            </p>
            {actualizando ? (
              <p role="status" className="mb-3 text-sm font-semibold text-texto-secundario">
                Actualizando los datos del gasto…
              </p>
            ) : null}
            <form onSubmit={guardar} noValidate className="flex flex-col gap-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {CAMPOS.map(({ campo, etiqueta, tipo, decimal, max }) => (
                  <CampoTexto
                    key={campo}
                    id={`revision-${campo}`}
                    etiqueta={etiqueta}
                    type={tipo ?? "text"}
                    inputMode={decimal ? "decimal" : undefined}
                    maxLength={max}
                    autoComplete="off"
                    value={formulario[campo]}
                    onChange={(e) => cambiar(campo, e.target.value)}
                    ayuda={seLeyo(datos.lectura_original, campo, inicial[campo])}
                    error={erroresCampos[campo]}
                  />
                ))}
                <CampoSelector
                  id="revision-categoria"
                  etiqueta="Categoría"
                  value={formulario.categoria}
                  onChange={(e) => cambiar("categoria", e.target.value)}
                  error={erroresCampos.categoria}
                >
                  {inicial.categoria ? null : <option value="">Por confirmar</option>}
                  {categorias.map((c) => (
                    <option key={c.clave} value={c.clave}>
                      {c.nombre}
                    </option>
                  ))}
                </CampoSelector>
                <CampoSelector
                  id="revision-viaje"
                  etiqueta="Viaje"
                  ayuda="El viaje define el proyecto y quién viaja; el saldo se vuelve a revisar al aprobar."
                  value={formulario.viaje}
                  onChange={(e) => cambiar("viaje", e.target.value)}
                >
                  <option value="">Sin viaje</option>
                  {viajes.map((v) => (
                    <option key={v.id} value={String(v.id)}>
                      {[v.codigo, v.titular, v.ida, v.estado_texto].filter(Boolean).join(" · ")}
                    </option>
                  ))}
                </CampoSelector>
              </div>
              <div className="flex flex-wrap gap-2">
                <Boton type="submit" variante="secundario" disabled={ocupado}>
                  {ocupado && revision.variables?.accion === "guardar" ? "Guardando…" : "Guardar correcciones"}
                </Boton>
                <Boton variante="secundario" onClick={() => abrir("excepcion")} disabled={ocupado}>
                  Aprobar con excepción
                </Boton>
              </div>
            </form>
          </section>
        </div>
      </div>

      <DialogoConfirmacion
        abierto={dialogo !== null}
        titulo={
          dialogo === "excepcion"
            ? "Aprobar con excepción"
            : gasto.comercio
              ? `Rechazar el gasto de ${gasto.comercio}`
              : "Rechazar este gasto"
        }
        efecto={
          dialogo === "excepcion"
            ? "Para un gasto legítimo que las reglas no dejan pasar (por ejemplo, dos peajes iguales el mismo día). Se aprueba con las correcciones que hayas hecho y el motivo queda en la auditoría."
            : "El gasto no cuenta para el presupuesto y la persona verá el motivo en su lista de gastos."
        }
        confirmar={dialogo === "excepcion" ? "Aprobar con excepción" : "Rechazar gasto"}
        peligro={dialogo === "rechazar"}
        enviando={ocupado}
        onConfirmar={confirmarDialogo}
        onCancelar={() => {
          setDialogo(null);
          setErrorMotivo(null);
        }}
      >
        <CampoAreaTexto
          key={dialogo ?? "cerrado"}
          id={`motivo-${dialogo ?? "gasto"}-${gasto.id}`}
          etiqueta={dialogo === "excepcion" ? "Motivo de la excepción" : "Motivo del rechazo"}
          ayuda={dialogo === "excepcion" ? "Queda en la auditoría del gasto." : "Escríbelo para la persona: lo verá tal cual."}
          value={enDialogo}
          maxLength={500}
          onChange={(e) => {
            (dialogo === "excepcion" ? setMotivoExcepcion : setMotivo)(e.target.value);
            // Si ya se mostró el aviso, se revisa al escribir: así no cambia el alto del diálogo justo al pulsar.
            if (errorMotivo) setErrorMotivo(validarMotivo(e.target.value));
          }}
          onBlur={() => enDialogo && setErrorMotivo(validarMotivo(enDialogo))}
          error={errorMotivo}
        />
      </DialogoConfirmacion>
    </div>
  );
}
