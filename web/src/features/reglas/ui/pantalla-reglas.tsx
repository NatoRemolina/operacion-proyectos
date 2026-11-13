"use client";

import { useId, useState, type FormEvent } from "react";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { InsigniaEstado, type Tono } from "@/shared/ui/estado";
import { formatearFecha } from "@/shared/ui/formato";
import { useCatalogoReglas, useEditarRegla } from "../application/reglas";
import { esFuenteEnlace, problemaDeValor, valorParaEnviar, type Membresia, type Regla } from "../domain/reglas";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";
const MIGAS = [{ texto: "Administración" }, { texto: "Reglas y supuestos" }];

/** Oficial o del buscador: verificada; secundaria: de otra fuente; lo demás, por confirmar. */
function tonoConfianza(confianza: string | null): Tono {
  if (confianza === "oficial" || confianza === "buscador") return "exito";
  return confianza === "secundaria" ? "info" : "aviso";
}

function coincide(regla: Regla, busqueda: string): boolean {
  if (!busqueda) return true;
  const texto = [regla.clave, regla.entidad, regla.tarifa, regla.valor, regla.nota].join(" ").toLowerCase();
  return busqueda
    .toLowerCase()
    .split(/\s+/)
    .every((palabra) => texto.includes(palabra));
}

function FilaRegla({ regla }: { regla: Regla }) {
  const id = useId();
  const { avisar } = useAvisos();
  const edicion = useEditarRegla();
  const [valor, setValor] = useState(regla.valor);
  const [error, setError] = useState<string | null>(null);

  function guardar(evento: FormEvent) {
    evento.preventDefault();
    const problema = problemaDeValor(regla, valor);
    setError(problema);
    if (problema) return;
    const enviar = valorParaEnviar(regla, valor);
    if (enviar === regla.valor) {
      avisar({ tono: "info", texto: `Sin cambios en ${regla.clave}.` });
      return;
    }
    edicion.mutate(
      { id: regla.id, valor: enviar },
      {
        onSuccess: (guardada) => {
          setValor(guardada.valor);
          avisar({ tono: "exito", texto: `Regla guardada: ${guardada.clave}.` });
        },
        onError: (e) => {
          if (e.tipo === "validacion" && e.campos.valor) setError(e.campos.valor);
          else avisar({ tono: "error", texto: `No se guardó ${regla.clave}: ${e.message}` });
        },
      },
    );
  }

  const aplica = [regla.entidad, regla.tarifa ? `(${regla.tarifa})` : ""].filter(Boolean).join(" ");
  return (
    <li id={`r${regla.id}`} className="flex flex-col gap-3 border-b border-linea py-4 last:border-b-0 md:grid md:grid-cols-[minmax(0,1fr)_18rem] md:gap-6">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="break-all font-mono font-semibold">{regla.clave}</p>
          {regla.confianza ? <InsigniaEstado tono={tonoConfianza(regla.confianza)}>{regla.confianza}</InsigniaEstado> : null}
        </div>
        {aplica ? <p className="text-sm text-texto-secundario">Aplica a: {aplica}</p> : null}
        {regla.nota ? <p>{regla.nota}</p> : null}
        <p className="text-sm text-texto-secundario">
          {esFuenteEnlace(regla.fuente) ? (
            <a href={regla.fuente!} target="_blank" rel="noopener noreferrer">
              Fuente (se abre en otra pestaña)
            </a>
          ) : (
            <span className="break-words">Fuente: {regla.fuente || "sin fuente escrita"}</span>
          )}
          {regla.verificado ? ` · Verificado el ${formatearFecha(regla.verificado)}` : null}
        </p>
      </div>
      <form onSubmit={guardar} noValidate className="flex flex-col gap-1">
        <label htmlFor={id} className="font-semibold">
          Valor<span className="sr-only"> de {regla.clave}</span>
        </label>
        <div className="flex gap-2">
          <input
            id={id}
            value={valor}
            maxLength={500}
            inputMode={regla.numerica ? "decimal" : undefined}
            autoComplete="off"
            onChange={(e) => {
              setValor(e.target.value);
              if (error) setError(null);
            }}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `${id}-error` : `${id}-tipo`}
            className="block min-h-11 w-full min-w-0 rounded-lg border border-borde-campo bg-superficie px-3 py-2 text-base text-texto aria-invalid:border-2 aria-invalid:border-error"
          />
          <Boton
            type="submit"
            variante="secundario"
            className="shrink-0 whitespace-nowrap"
            disabled={edicion.isPending}
            aria-label={`Guardar ${regla.clave}`}
          >
            {edicion.isPending ? "Guardando…" : "Guardar"}
          </Boton>
        </div>
        {error ? (
          <p id={`${id}-error`} className="text-sm font-semibold text-error">
            <span aria-hidden="true">✕ </span>
            {error}
          </p>
        ) : (
          <p id={`${id}-tipo`} className="text-sm text-texto-secundario">
            {regla.numerica ? "Un número (se acepta la coma decimal)." : "Texto."}
          </p>
        )}
      </form>
    </li>
  );
}

function Membresias({ membresias }: { membresias: readonly Membresia[] }) {
  return (
    <section aria-labelledby="titulo-membresias" className={TARJETA}>
      <h2 id="titulo-membresias" className="text-xl font-bold">
        Membresías de fidelización
      </h2>
      <p className="mb-3 text-sm text-texto-secundario">
        Solo lectura. Dos niveles: la cuenta de la empresa acumula aparte de la membresía personal de quien viaja. En los
        programas de hotel, «Aplica en» es el programa. Las marcadas «Dato de ejemplo» son inventadas para la demostración.
      </p>
      {membresias.length ? (
        <ul className="flex flex-col">
          {membresias.map((m) => (
            <li key={m.id} className="flex flex-col gap-1 border-b border-linea py-3 last:border-b-0 sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-4">
              <span className="flex flex-wrap items-center gap-2 font-semibold">
                {m.titular}
                {m.ejemplo ? <InsigniaEstado tono="aviso">Dato de ejemplo</InsigniaEstado> : null}
              </span>
              <span>{m.programa ?? "Sin programa"}</span>
              <span className="text-texto-secundario">Aplica en: {m.entidad ?? "—"}</span>
              <span className="text-texto-secundario">Estatus: {m.estatus || "—"}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-texto-secundario">No hay membresías registradas.</p>
      )}
    </section>
  );
}

/** Catálogo de reglas y supuestos, agrupado por ámbito, con la edición de cada valor. Solo administración. */
export function PantallaReglas() {
  const consulta = useCatalogoReglas();
  const [busqueda, setBusqueda] = useState("");
  const catalogo = consulta.data;
  const descripcion =
    "Lo que ningún buscador entrega. Cada regla tiene fuente, nivel de confianza y fecha de verificación, y se edita sin tocar el código.";

  if (!catalogo) {
    return (
      <div className="flex flex-col gap-6">
        <EncabezadoPagina migas={MIGAS} titulo="Reglas y supuestos" descripcion={descripcion} />
        {consulta.error ? (
          <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
        ) : (
          <EsqueletoLista texto="Cargando las reglas…" />
        )}
      </div>
    );
  }

  const termino = busqueda.trim();
  const grupos = catalogo.grupos
    .map((g) => ({ ...g, visibles: g.reglas.filter((r) => coincide(r, termino)) }))
    .filter((g) => g.visibles.length);

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina migas={MIGAS} titulo="Reglas y supuestos" descripcion={descripcion} />
      <div className="flex flex-col gap-3">
        <div className="flex max-w-md flex-col gap-1">
          <label htmlFor="buscar-regla" className="font-semibold">
            Buscar una regla
          </label>
          <input
            id="buscar-regla"
            type="search"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Por ejemplo: equipaje, tolerancia, Hilton"
            className="block min-h-11 w-full rounded-lg border border-borde-campo bg-superficie px-3 py-2 text-base text-texto placeholder:text-texto-secundario"
          />
        </div>
        {grupos.length ? (
          <nav aria-label="Ámbitos de las reglas">
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              {grupos.map((g) => (
                <li key={g.clave}>
                  <a href={`#grupo-${g.clave}`} className="inline-flex min-h-11 items-center">
                    {g.titulo} ({g.visibles.length})
                  </a>
                </li>
              ))}
              <li>
                <a href="#titulo-membresias" className="inline-flex min-h-11 items-center">
                  Membresías ({catalogo.membresias.length})
                </a>
              </li>
            </ul>
          </nav>
        ) : (
          <p role="status" className="text-texto-secundario">
            Ninguna regla coincide con la búsqueda.
          </p>
        )}
      </div>

      {grupos.map((g) => (
        <section key={g.clave} id={`grupo-${g.clave}`} aria-labelledby={`titulo-grupo-${g.clave}`} className={`${TARJETA} scroll-mt-4`}>
          <h2 id={`titulo-grupo-${g.clave}`} className="text-xl font-bold">
            {g.titulo} <span className="text-base font-normal text-texto-secundario">({g.visibles.length})</span>
          </h2>
          <ul className="flex flex-col">
            {g.visibles.map((r) => (
              <FilaRegla key={`${r.id}-${r.valor}`} regla={r} />
            ))}
          </ul>
        </section>
      ))}

      <Membresias membresias={catalogo.membresias} />
    </div>
  );
}
