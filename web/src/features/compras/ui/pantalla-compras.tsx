"use client";

import { useId, useState, type FormEvent } from "react";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { CampoAreaTexto, CampoTexto } from "@/shared/ui/campo";
import { Distintivo } from "@/shared/ui/distintivo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle, EsqueletoLista } from "@/shared/ui/esqueleto";
import { Alerta } from "@/shared/ui/estado";
import { EstadoVacio } from "@/shared/ui/estado-vacio";
import { formatearDinero, formatearInstante } from "@/shared/ui/formato";
import {
  useAnalizarCompra,
  useCambiarEstado,
  useCompra,
  useCompras,
  useRegistrarCompra,
} from "../application/compras";
import {
  DESTINO_CLIC,
  ETIQUETA_ACCION,
  MOTIVO_MINIMO,
  accionesPosibles,
  bloqueoSeComprara,
  requiereMotivo,
  validarRegistro,
  type AccionCompra,
  type Compra,
  type CompraDetalle,
  type EstadoCompra,
  type RegistroCompra,
} from "../domain/compras";

const TONO: Readonly<Record<EstadoCompra, "neutro" | "aviso" | "exito" | "marca">> = {
  solicitada: "aviso",
  en_analisis: "marca",
  se_comprara: "exito",
  no_se_comprara: "neutro",
  comprada: "exito",
  cancelada: "neutro",
};

/** Bandeja de compras de administración: las solicitudes que nacen al decidir, su análisis, la decisión y el registro. */
export function PantallaCompras() {
  const compras = useCompras();
  const [elegida, setElegida] = useState<number | null>(null);
  return (
    <section aria-labelledby="titulo-compras" className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        idTitulo="titulo-compras"
        titulo="Compras"
        descripcion="Las solicitudes de compra del tiquete que nacen al decidir una cotización. Nadie decide la compra de su propio viaje."
      />
      {compras.isPending ? (
        <EsqueletoLista texto="Cargando las compras…" />
      ) : compras.error ? (
        <ErrorConsulta error={compras.error} onReintentar={() => void compras.refetch()} />
      ) : !compras.data?.length ? (
        <EstadoVacio titulo="No hay solicitudes de compra">
          <p>Aparecen aquí cuando alguien decide una cotización.</p>
        </EstadoVacio>
      ) : (
        <ListaCompras compras={compras.data} elegida={elegida} onElegir={setElegida} />
      )}
      {elegida !== null ? <DetalleCompra key={elegida} id={elegida} /> : null}
    </section>
  );
}

function ListaCompras({
  compras,
  elegida,
  onElegir,
}: {
  compras: readonly Compra[];
  elegida: number | null;
  onElegir: (id: number) => void;
}) {
  const celda = "flex gap-2 py-1 md:table-cell md:py-2 md:pr-3 before:shrink-0 before:font-semibold " +
    "before:text-texto-secundario before:content-[attr(data-titulo)] md:before:content-none";
  return (
    <table className="w-full text-sm [overflow-wrap:anywhere]">
      <caption className="sr-only">Solicitudes de compra</caption>
      <thead className="sr-only md:not-sr-only">
        <tr className="text-left text-texto-secundario">
          <th scope="col" className="py-1 pr-3 font-semibold">Viaje</th>
          <th scope="col" className="py-1 pr-3 font-semibold">Estado</th>
          <th scope="col" className="py-1 pr-3 font-semibold">Solicitó</th>
          <th scope="col" className="py-1 pr-3 text-right font-semibold">Cotizado</th>
          <th scope="col" className="py-1 font-semibold"><span className="sr-only">Abrir</span></th>
        </tr>
      </thead>
      <tbody>
        {compras.map((c) => (
          <tr key={c.id} className={`block border-t border-linea py-2 md:table-row md:py-0 ${elegida === c.id ? "bg-marca-suave" : ""}`}>
            <th scope="row" data-titulo="Viaje:" className={`${celda} text-left font-semibold`}>{c.viaje.codigo}</th>
            <td data-titulo="Estado:" className={celda}><Distintivo tono={TONO[c.estado]}>{c.estado_texto}</Distintivo></td>
            <td data-titulo="Solicitó:" className={celda}>{c.solicitada_por ?? "—"}</td>
            <td data-titulo="Cotizado:" className={`${celda} tabular-nums md:text-right`}>{formatearDinero(c.precio_cotizado_usd)}</td>
            <td className="py-1 md:table-cell md:py-2">
              <Boton variante="texto" aria-label={`Abrir la compra del viaje ${c.viaje.codigo}`} onClick={() => onElegir(c.id)}>
                Abrir
              </Boton>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DetalleCompra({ id }: { id: number }) {
  const compra = useCompra(id);
  if (compra.isPending) return <EsqueletoDetalle texto="Cargando la compra…" />;
  if (compra.error) return <ErrorConsulta error={compra.error} onReintentar={() => void compra.refetch()} />;
  return compra.data ? <Detalle c={compra.data} /> : null;
}

function Detalle({ c }: { c: CompraDetalle }) {
  const titulo = useId();
  const v = c.vuelo;
  return (
    <section aria-labelledby={titulo} className="flex flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 md:p-6">
      <h2 id={titulo} className="text-xl font-bold tracking-tight">Compra del viaje {c.viaje.codigo}</h2>
      <p className="flex flex-wrap items-center gap-2">
        <Distintivo tono={TONO[c.estado]}>{c.estado_texto}</Distintivo>
        <span className="text-sm text-texto-secundario">
          Viaje {c.viaje.estado === "aprobado" ? "aprobado" : "sin aprobar"} · presupuesto {formatearDinero(c.viaje.presupuesto_usd)}
          {c.solicitada_por ? ` · la solicitó ${c.solicitada_por}` : ""}
        </span>
      </p>
      {c.motivo ? <p className="text-sm">Motivo: {c.motivo}</p> : null}
      {v ? (
        <div className="flex flex-col gap-1">
          <p className="font-semibold">{[v.aerolinea, v.numeros.join(" + ")].filter(Boolean).join(" ")}</p>
          <p className="text-sm text-texto-secundario">
            {v.sale ? `Sale ${v.sale}` : ""}{v.llega ? ` · llega ${v.llega}` : ""} · cotizado {formatearDinero(c.precio_cotizado_usd)}
          </p>
          <p className="flex flex-wrap gap-3">
            {v.vendedor_url ? (
              <a href={v.vendedor_url} target="_blank" rel="noopener noreferrer" className={clasesBoton("secundario")}
                aria-label="Comprar en la página oficial del vendedor, se abre en otra pestaña">
                Comprar en la página oficial <span aria-hidden="true">↗</span>
              </a>
            ) : null}
            {v.fuente_url ? (
              <a href={v.fuente_url} target="_blank" rel="noopener noreferrer" className={clasesBoton("texto")}
                aria-label="Ver el vuelo en Google Flights, se abre en otra pestaña">
                Ver en Google Flights <span aria-hidden="true">↗</span>
              </a>
            ) : null}
          </p>
        </div>
      ) : null}
      {c.frente_presupuesto ? (
        <Alerta tono={Number(c.frente_presupuesto.diferencia_usd ?? 0) > 0 ? "aviso" : "exito"} titulo={`Comprada a ${c.vendedor} · ${c.localizador}`}>
          <p>
            Pagado {formatearDinero(c.precio_pagado_usd)} · cotizado {formatearDinero(c.frente_presupuesto.cotizado_usd)} · diferencia{" "}
            {formatearDinero(c.frente_presupuesto.diferencia_usd)} · presupuesto del viaje {formatearDinero(c.frente_presupuesto.presupuesto_usd)}
          </p>
        </Alerta>
      ) : null}
      <Acciones c={c} />
      {c.estado === "se_comprara" ? <Registro c={c} /> : null}
      <Analisis c={c} />
      <div className="flex flex-col gap-1">
        <h3 className="font-semibold">Clics a las fuentes</h3>
        {c.clics.length ? (
          <ul className="flex flex-col gap-1 text-sm">
            {c.clics.map((k, i) => (
              <li key={`${k.momento}-${i}`}>
                {DESTINO_CLIC[k.destino]} · {k.dominio ?? "—"} · {k.usuario ?? "—"}
                {k.momento ? ` · ${formatearInstante(k.momento)}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-texto-secundario">Nadie abrió todavía las fuentes de este vuelo.</p>
        )}
      </div>
    </section>
  );
}

function Acciones({ c }: { c: CompraDetalle }) {
  const cambiar = useCambiarEstado(c);
  const [motivo, setMotivo] = useState("");
  const [faltaMotivo, setFaltaMotivo] = useState(false);
  const acciones = accionesPosibles(c);
  if (!acciones.length) return null;
  const bloqueo = bloqueoSeComprara(c);
  function hacer(accion: AccionCompra) {
    if (requiereMotivo(accion) && motivo.trim().length < MOTIVO_MINIMO) {
      setFaltaMotivo(true);
      document.getElementById(`motivo-compra-${c.id}`)?.focus();
      return;
    }
    setFaltaMotivo(false);
    cambiar.mutate({ accion, motivo: motivo.trim() });
  }
  return (
    <div className="flex flex-col gap-3">
      <CampoAreaTexto
        id={`motivo-compra-${c.id}`}
        etiqueta="Motivo"
        ayuda="Obligatorio para no comprar o cancelar. La persona que viaja lo verá."
        error={faltaMotivo ? `Escribe el motivo (${MOTIVO_MINIMO} caracteres o más).` : cambiar.error?.campos?.motivo ?? null}
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        rows={2}
        maxLength={300}
      />
      <div className="flex flex-wrap gap-2">
        {acciones.map((a) => (
          <Boton
            key={a}
            variante={a === "se_comprara" ? "primario" : a === "en_analisis" ? "secundario" : "peligro"}
            disabled={cambiar.isPending || (a === "se_comprara" && Boolean(bloqueo))}
            aria-describedby={a === "se_comprara" && bloqueo ? `bloqueo-compra-${c.id}` : undefined}
            onClick={() => hacer(a)}
          >
            {ETIQUETA_ACCION[a]}
          </Boton>
        ))}
      </div>
      {acciones.includes("se_comprara") && bloqueo ? (
        <p id={`bloqueo-compra-${c.id}`} className="text-sm text-texto-secundario">
          {bloqueo} «Se va a comprar» se habilita cuando se apruebe.
        </p>
      ) : null}
      {cambiar.error && cambiar.error.tipo !== "validacion" ? (
        <Alerta tono="error" titulo="No se guardó el cambio" rol="alert">
          <p>{cambiar.error.message}</p>
        </Alerta>
      ) : null}
    </div>
  );
}

function Registro({ c }: { c: CompraDetalle }) {
  const registrar = useRegistrarCompra(c);
  const [r, setR] = useState<RegistroCompra>({ localizador: "", precio_pagado: "", vendedor: "" });
  const [intentado, setIntentado] = useState(false);
  const locales = intentado ? validarRegistro(r) : {};
  const delServidor = registrar.error?.campos ?? {};
  function enviar(e: FormEvent) {
    e.preventDefault();
    setIntentado(true);
    if (Object.keys(validarRegistro(r)).length) return;
    registrar.mutate({ ...r, localizador: r.localizador.trim().toUpperCase(), precio_pagado: r.precio_pagado.trim() });
  }
  const campo = (clave: keyof RegistroCompra) => ({
    value: r[clave],
    onChange: (e: { target: { value: string } }) => setR({ ...r, [clave]: e.target.value }),
    error: locales[clave] ?? delServidor[clave] ?? null,
  });
  return (
    <form noValidate onSubmit={enviar} aria-label="Registrar la compra" className="flex flex-col gap-3 border-t border-linea pt-3">
      <h3 className="font-semibold">Registrar la compra</h3>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <CampoTexto id={`localizador-${c.id}`} etiqueta="Localizador" autoComplete="off" {...campo("localizador")} />
        <CampoTexto id={`pagado-${c.id}`} etiqueta="Precio pagado (USD)" inputMode="decimal" {...campo("precio_pagado")} />
        <CampoTexto id={`vendedor-${c.id}`} etiqueta="Vendedor" {...campo("vendedor")} />
      </div>
      <div>
        <Boton type="submit" disabled={registrar.isPending}>Registrar la compra</Boton>
      </div>
      {registrar.error && registrar.error.tipo !== "validacion" ? (
        <Alerta tono="error" titulo="No se registró la compra" rol="alert">
          <p>{registrar.error.message}</p>
        </Alerta>
      ) : null}
    </form>
  );
}

function Analisis({ c }: { c: CompraDetalle }) {
  const analizar = useAnalizarCompra(c.id);
  const a = c.analisis;
  return (
    <div className="flex flex-col gap-2 border-t border-linea pt-3">
      <h3 className="font-semibold">Página del vuelo en Google Flights</h3>
      <p role="status" className="text-sm">
        {analizar.isPending
          ? "Leyendo la página del vuelo…"
          : !a
            ? "Todavía no se leyó."
            : a.estado === "listo"
              ? `Leída${a.leido ? ` el ${formatearInstante(a.leido)}` : ""}.`
              : `No se pudo leer: ${a.motivo ?? "sin motivo"}`}
      </p>
      {a?.aviso_precio ? <p className="text-sm">{a.aviso_precio}</p> : null}
      {a?.captura_url ? (
        <a href={a.captura_url} target="_blank" rel="noopener noreferrer" className="self-start text-sm underline underline-offset-3">
          Ver la captura
        </a>
      ) : null}
      <div>
        <Boton variante="secundario" disabled={analizar.isPending} onClick={() => analizar.mutate()}>
          Leer la página del vuelo
        </Boton>
      </div>
    </div>
  );
}
