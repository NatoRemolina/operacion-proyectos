"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { JUSTIFICACION_MAXIMO } from "../domain/gastos";
import { CampoAreaTexto, CampoSelector } from "@/shared/ui/campo";
import { Alerta, InsigniaEstado } from "@/shared/ui/estado";
import { formatearTamano } from "@/shared/ui/formato";

export interface ArchivoElegido {
  nombre: string;
  tamano: number;
  esPdf: boolean;
  vistaPrevia: string | null;
}

export interface ErrorEnvio {
  titulo: string;
  detalle: string;
  /** Qué puede hacer la persona: entrar de nuevo, reintentar el mismo archivo o elegir otro. */
  accion: "entrar" | "reintentar" | "elegir";
  referencia?: string | null;
}

export interface OpcionViaje {
  id: number;
  codigo: string;
  ruta: string;
  fechas: string;
  estadoTexto: string;
  enCurso: boolean;
}

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

/** Un input de archivo oculto con su etiqueta visible como botón; el foco se ve en la etiqueta. */
function BotonArchivo({
  id,
  texto,
  variante,
  accept,
  capture,
  disabled,
  onElegir,
  className = "",
}: {
  id: string;
  texto: string;
  variante: "primario" | "secundario";
  accept: string;
  capture?: "environment";
  disabled: boolean;
  onElegir: (archivo: File | null) => void;
  className?: string;
}) {
  return (
    <div className={className}>
      <input
        id={id}
        type="file"
        accept={accept}
        capture={capture}
        disabled={disabled}
        className="peer sr-only"
        onChange={(e) => onElegir(e.target.files?.[0] ?? null)}
      />
      <label
        htmlFor={id}
        className={clasesBoton(
          variante,
          "w-full cursor-pointer peer-focus-visible:outline-3 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-marca peer-disabled:cursor-not-allowed peer-disabled:opacity-60",
        )}
      >
        {texto}
      </label>
    </div>
  );
}

function TarjetaViaje({
  viajes,
  cargandoViajes,
  viajeId,
  onCambiarViaje,
  enviando,
}: {
  viajes: readonly OpcionViaje[];
  cargandoViajes: boolean;
  viajeId: string;
  onCambiarViaje: (valor: string) => void;
  enviando: boolean;
}) {
  const [cambiando, setCambiando] = useState(false);
  const elegido = viajeId ? viajes.find((v) => String(v.id) === viajeId) : viajes.find((v) => v.enCurso);

  return (
    <section aria-labelledby="titulo-viaje-destino" className={TARJETA}>
      <h2 id="titulo-viaje-destino" className="sr-only">
        Viaje destino
      </h2>
      {cargandoViajes ? (
        <p className="text-texto-secundario">Cargando tus viajes…</p>
      ) : elegido ? (
        <>
          <InsigniaEstado tono="exito">{elegido.estadoTexto}</InsigniaEstado>
          <p className="mt-2 font-semibold">{elegido.ruta}</p>
          <p className="text-sm text-texto-secundario">
            {elegido.codigo} · {elegido.fechas}
          </p>
          {!viajeId ? (
            <p className="mt-1 text-sm text-texto-secundario">
              Asignado automáticamente: es tu viaje en curso.
            </p>
          ) : null}
        </>
      ) : (
        <p>
          <span className="font-semibold">Viaje automático.</span>{" "}
          <span className="text-texto-secundario">
            La plataforma asigna el viaje que corresponda; si no hay uno, administración lo revisa.
          </span>
        </p>
      )}

      {cambiando ? (
        <div className="mt-3">
          <CampoSelector
            id="viaje"
            etiqueta="Viaje"
            value={viajeId}
            onChange={(e) => onCambiarViaje(e.target.value)}
            disabled={enviando}
            autoFocus
          >
            <option value="">Automático (recomendado)</option>
            {viajes.map((viaje) => (
              <option key={viaje.id} value={String(viaje.id)}>
                {viaje.codigo} · {viaje.ruta} ({viaje.fechas})
              </option>
            ))}
          </CampoSelector>
        </div>
      ) : (
        <Boton
          variante="texto"
          className="mt-1"
          onClick={() => setCambiando(true)}
          disabled={enviando}
        >
          Cambiar viaje
        </Boton>
      )}
    </section>
  );
}

export function FormularioRecibo({
  archivo,
  onElegirArchivo,
  viajes,
  cargandoViajes,
  viajeId,
  onCambiarViaje,
  justificacion,
  onCambiarJustificacion,
  onEnviar,
  enviando,
  error,
}: {
  archivo: ArchivoElegido | null;
  onElegirArchivo: (archivo: File | null) => void;
  viajes: readonly OpcionViaje[];
  cargandoViajes: boolean;
  viajeId: string;
  onCambiarViaje: (valor: string) => void;
  justificacion: string;
  onCambiarJustificacion: (valor: string) => void;
  onEnviar: () => void;
  enviando: boolean;
  error: ErrorEnvio | null;
}) {
  function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    onEnviar();
  }

  return (
    <form onSubmit={enviar} className="flex flex-col gap-4">
      <TarjetaViaje
        viajes={viajes}
        cargandoViajes={cargandoViajes}
        viajeId={viajeId}
        onCambiarViaje={onCambiarViaje}
        enviando={enviando}
      />

      <section aria-labelledby="titulo-soporte" className={`${TARJETA} border-marca`}>
        <h2 id="titulo-soporte" className="font-bold">
          Agrega tu soporte
        </h2>
        <p id="ayuda-soporte" className="mt-1 text-sm text-texto-secundario">
          Foto o PDF · Hasta 4,5 MB
        </p>
        <div className="mt-3 flex flex-col gap-3">
          <BotonArchivo
            id="foto-recibo"
            texto={archivo ? "Tomar otra foto" : "Tomar foto"}
            variante={archivo ? "secundario" : "primario"}
            accept="image/*"
            capture="environment"
            disabled={enviando}
            onElegir={onElegirArchivo}
            className="hidden pointer-coarse:block"
          />
          <BotonArchivo
            id="archivo-recibo"
            texto={archivo ? "Elegir otro archivo" : "Elegir archivo"}
            variante="secundario"
            accept="image/*,application/pdf"
            disabled={enviando}
            onElegir={onElegirArchivo}
          />
        </div>

        {archivo ? (
          <figure className="mt-4 flex flex-col gap-2 border-t border-linea pt-4 sm:flex-row sm:items-center">
            {archivo.vistaPrevia && !archivo.esPdf ? (
              // Vista previa local (blob:), no pasa por el optimizador de imágenes.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={archivo.vistaPrevia}
                alt="Vista previa del recibo elegido"
                className="max-h-64 w-auto max-w-full self-start rounded-md border border-linea object-contain"
              />
            ) : (
              <div
                aria-hidden="true"
                className="flex h-24 w-20 items-center justify-center rounded-md border border-linea bg-neutro-suave font-bold text-neutro"
              >
                {archivo.esPdf ? "PDF" : "IMG"}
              </div>
            )}
            <figcaption className="text-sm">
              <span className="font-semibold">{archivo.nombre}</span>
              <br />
              <span className="text-texto-secundario">
                {archivo.esPdf ? "Documento PDF" : "Imagen"} · {formatearTamano(archivo.tamano)}
              </span>
            </figcaption>
          </figure>
        ) : null}
      </section>

      <section aria-labelledby="titulo-para-que" className={TARJETA}>
        <h2 id="titulo-para-que" className="sr-only">
          Para qué fue el gasto
        </h2>
        <CampoAreaTexto
          id="justificacion"
          etiqueta="¿Para qué fue este gasto?"
          ayuda="Opcional, pero ayuda a quien revisa. También puedes contarlo después desde el detalle del gasto o con una nota de voz por Telegram."
          placeholder="Por ejemplo: taxi del hotel al set con el equipo del dron"
          maxLength={JUSTIFICACION_MAXIMO}
          value={justificacion}
          onChange={(e) => onCambiarJustificacion(e.target.value)}
          disabled={enviando}
        />
      </section>

      {error ? (
        <Alerta tono={error.accion === "entrar" ? "aviso" : "error"} titulo={error.titulo} rol="alert">
          <p>{error.detalle}</p>
          {error.accion === "entrar" ? (
            <p className="mt-2">
              <Link href="/entrar?volver=%2Fgastos%2Fnuevo">Entrar de nuevo</Link>
            </p>
          ) : null}
          {error.referencia ? (
            <p className="mt-1 text-sm text-texto-secundario">Referencia: {error.referencia}</p>
          ) : null}
        </Alerta>
      ) : null}

      {archivo ? (
        <Boton type="submit" disabled={enviando} className="w-full">
          {enviando
            ? "Enviando…"
            : error?.accion === "reintentar"
              ? "Reintentar envío"
              : "Enviar recibo"}
        </Boton>
      ) : null}

      <p className="text-sm text-texto-secundario">
        Tu soporte quedará asociado al viaje. Si algo no se puede leer, administración lo revisa.
      </p>
    </form>
  );
}
