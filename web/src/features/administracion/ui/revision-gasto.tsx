"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { estadoVisibleGasto, type GastoDetalle } from "@/features/gastos/domain/gastos";
import { usePlataforma } from "@/shared/application/plataforma";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { CampoAreaTexto } from "@/shared/ui/campo";
import { DialogoConfirmacion } from "@/shared/ui/dialogo-confirmacion";
import { Alerta } from "@/shared/ui/estado";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearDinero, formatearFecha, formatearInstante } from "@/shared/ui/formato";
import { Migas, type Miga } from "@/shared/ui/migas";
import { useRevisarGasto } from "../application/administracion";
import { problemaDeMotivo } from "../domain/administracion";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

const TITULO_ERROR: Partial<Record<ErrorDeAplicacion["tipo"], string>> = {
  prohibido: "No puedes revisar este gasto",
  cambio_ajeno: "El gasto cambió mientras lo revisabas",
};

function Fila({ termino, children }: { termino: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 border-b border-linea py-2 last:border-b-0">
      <dt className="text-texto-secundario">{termino}</dt>
      <dd className="text-right font-semibold tabular-nums">{children}</dd>
    </div>
  );
}

/** El recibo tal como llegó. Si no es una imagen (PDF o correo), se ofrece abrirlo aparte. */
function ImagenRecibo({ url, comercio }: { url: string | null; comercio: string }) {
  const [noSeMuestra, setNoSeMuestra] = useState(false);
  if (!url) return <p className="text-texto-secundario">El original no está disponible en esta fuente de datos.</p>;
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

/**
 * Revisión de administración (diseño de Figma 03): el recibo junto a lo leído, por qué va a
 * revisión en lenguaje claro y la decisión. Tras decidir, pasa al siguiente gasto en revisión.
 */
export function RevisionGasto({ gasto, urlOriginal, migas }: { gasto: GastoDetalle; urlOriginal: string | null; migas: readonly Miga[] }) {
  const router = useRouter();
  const { avisar } = useAvisos();
  const revision = useRevisarGasto(gasto.id);
  const [rechazando, setRechazando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [errorMotivo, setErrorMotivo] = useState<string | null>(null);
  const [error, setError] = useState<ErrorDeAplicacion | null>(null);
  const [sigueEnRevision, setSigueEnRevision] = useState(false);
  const plataforma = usePlataforma();
  const comercio = gasto.comercio ?? "gasto sin comercio leído";
  const version = gasto.version ?? 0;

  function decidir(accion: "aprobar" | "rechazar") {
    setError(null);
    setSigueEnRevision(false);
    const cuerpo = accion === "aprobar" ? { version, accion } : { version, accion, motivo: motivo.trim() };
    revision.mutate(cuerpo, {
      onSuccess: ({ gasto: revisado, siguiente }) => {
        setRechazando(false);
        // Aprobar vuelve a pasar las reglas: si no pasan, el gasto sigue en revisión y no se aprobó.
        if (revisado.estado === "revision") {
          setSigueEnRevision(true);
          avisar({ tono: "aviso", texto: "No se aprobó: el gasto sigue en revisión." });
          return;
        }
        setMotivo("");
        const hecho = accion === "aprobar" ? "Gasto aprobado." : "Gasto rechazado: la persona verá el motivo.";
        if (siguiente) {
          avisar({ tono: "exito", texto: `${hecho} Sigue el siguiente en revisión.` });
          router.push(`/gastos/${siguiente.id}`);
        } else {
          avisar({ tono: "exito", texto: `${hecho} No quedan gastos en revisión.` });
        }
      },
      onError: (e) => {
        if (e.tipo === "validacion" && e.campos.motivo) {
          setErrorMotivo(e.campos.motivo);
          return;
        }
        setRechazando(false);
        setError(e);
        // Si el gasto ya no está en revisión, esta vista se cierra al recargar: el aviso queda.
        if (e.tipo === "cambio_ajeno") {
          avisar({ tono: "aviso", texto: "Otra persona cambió este gasto mientras lo revisabas: cargamos lo último." });
        }
      },
    });
  }

  function rechazar() {
    const problema = problemaDeMotivo(motivo);
    setErrorMotivo(problema);
    if (!problema) decidir("rechazar");
  }

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
          {/* La decisión, visible sin desplazarse: una sola acción principal. */}
          <div className="flex flex-wrap gap-2">
            <Boton variante="secundario" onClick={() => setRechazando(true)} disabled={revision.isPending}>
              Rechazar
            </Boton>
            <Boton onClick={() => decidir("aprobar")} disabled={revision.isPending}>
              {revision.isPending && revision.variables?.accion === "aprobar" ? "Aprobando…" : "Aprobar gasto"}
            </Boton>
          </div>
        </div>
      </header>

      {sigueEnRevision ? (
        <Alerta tono="aviso" rol="alert" titulo="No se aprobó: las reglas todavía no lo dejan pasar">
          <p>Mira «Por qué va a revisión». Para corregir los datos o aprobarlo con una excepción justificada:</p>
          {plataforma ? (
            <p className="mt-2">
              <a href={`${plataforma}/gastos/${gasto.id}`}>Abrir la revisión completa de este gasto</a>
            </p>
          ) : (
            <p className="mt-1">usa la revisión completa de la plataforma actual.</p>
          )}
        </Alerta>
      ) : null}
      {error ? (
        <Alerta tono={error.tipo === "cambio_ajeno" ? "aviso" : "error"} rol="alert" titulo={TITULO_ERROR[error.tipo] ?? "No se pudo guardar la revisión"}>
          <p>
            {error.tipo === "prohibido"
              ? "Si el gasto es tuyo, lo revisa otra persona de administración."
              : error.message}
          </p>
        </Alerta>
      ) : null}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
        <section aria-labelledby="titulo-recibo" className={`${TARJETA} flex flex-col gap-3`}>
          <h2 id="titulo-recibo" className="text-lg font-bold">
            Recibo original
          </h2>
          {gasto.documento_id === null ? (
            <p className="text-texto-secundario">Este gasto no tiene un archivo original guardado.</p>
          ) : (
            <ImagenRecibo url={urlOriginal} comercio={comercio} />
          )}
        </section>

        <div className="flex flex-col gap-4">
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
            {gasto.justificaciones.length ? (
              <ul className="flex flex-col gap-2">
                {gasto.justificaciones.map((j) => (
                  <li key={j.id}>{j.texto ?? "Nota de voz sin transcribir."}</li>
                ))}
              </ul>
            ) : (
              <p className="text-texto-secundario">No dejó una justificación.</p>
            )}
          </section>

          <section aria-labelledby="titulo-leido" className={TARJETA}>
            <h2 id="titulo-leido" className="mb-1 text-lg font-bold">
              Lo que leímos del recibo
            </h2>
            <dl>
              <Fila termino="Fecha">{formatearFecha(gasto.fecha)}</Fila>
              <Fila termino="Categoría">{gasto.categoria ?? "Por confirmar"}</Fila>
              <Fila termino="Subtotal">{formatearDinero(gasto.subtotal, gasto.moneda)}</Fila>
              <Fila termino="Impuesto">{formatearDinero(gasto.impuesto, gasto.moneda)}</Fila>
              <Fila termino="Propina">{gasto.propina === null ? "Sin propina" : formatearDinero(gasto.propina, gasto.moneda)}</Fila>
              <Fila termino="Total">{formatearDinero(gasto.total, gasto.moneda)}</Fila>
              {gasto.moneda && gasto.moneda !== "USD" ? (
                <Fila termino="Total en dólares">{formatearDinero(gasto.total_usd, "USD")}</Fila>
              ) : null}
              <Fila termino="Confianza de la lectura">
                {gasto.lectura.confianza === null ? "Sin dato" : `${Math.round(gasto.lectura.confianza * 100)} %`}
              </Fila>
            </dl>
          </section>

        </div>
      </div>

      <DialogoConfirmacion
        abierto={rechazando}
        titulo={gasto.comercio ? `Rechazar el gasto de ${gasto.comercio}` : "Rechazar este gasto"}
        efecto="El gasto no cuenta para el presupuesto y la persona verá el motivo en su lista de gastos."
        confirmar="Rechazar gasto"
        peligro
        enviando={revision.isPending}
        onConfirmar={rechazar}
        onCancelar={() => {
          setRechazando(false);
          setErrorMotivo(null);
        }}
      >
        <CampoAreaTexto
          id={`motivo-gasto-${gasto.id}`}
          etiqueta="Motivo del rechazo"
          ayuda="Escríbelo para la persona: lo verá tal cual."
          value={motivo}
          maxLength={500}
          onChange={(e) => {
            setMotivo(e.target.value);
            // Si ya se mostró el aviso, se revisa al escribir: así no cambia el alto del diálogo justo al pulsar.
            if (errorMotivo) setErrorMotivo(problemaDeMotivo(e.target.value));
          }}
          onBlur={() => motivo && setErrorMotivo(problemaDeMotivo(motivo))}
          error={errorMotivo}
        />
      </DialogoConfirmacion>
    </div>
  );
}
