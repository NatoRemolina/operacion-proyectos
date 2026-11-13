"use client";

import { useState, type FormEvent } from "react";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { CampoTexto } from "@/shared/ui/campo";
import { Distintivo } from "@/shared/ui/distintivo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle } from "@/shared/ui/esqueleto";
import { Alerta } from "@/shared/ui/estado";
import { useCambiarMiClave, useDesvincularTelegram, useMiCuenta, useVincularTelegram } from "../application/cuenta";
import { problemasDeClave, type MiCuenta } from "../domain/cuenta";

const TARJETA = "flex flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

function MisDatos({ cuenta }: { cuenta: MiCuenta }) {
  const filas: [string, string][] = [
    ["Nombre", cuenta.persona.nombre],
    ["Código", cuenta.persona.codigo],
    ["Correo", cuenta.persona.correo],
    ["Permiso", cuenta.rol_texto],
    ["Cargo", cuenta.persona.cargo ?? "Sin cargo"],
  ];
  return (
    <section aria-labelledby="titulo-mis-datos" className={TARJETA}>
      <h2 id="titulo-mis-datos" className="text-lg font-bold">
        Mis datos
      </h2>
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-[auto_1fr]">
        {filas.map(([etiqueta, valor]) => (
          <div key={etiqueta} className="contents">
            <dt className="text-sm text-texto-secundario">{etiqueta}</dt>
            <dd className="font-semibold break-all">{valor}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm text-texto-secundario">
        El permiso dice qué puedes hacer en la plataforma; el cargo, qué haces en la empresa. Los cambia administración.
      </p>
    </section>
  );
}

function CambiarClave() {
  const cambiar = useCambiarMiClave();
  const { avisar } = useAvisos();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repetida, setRepetida] = useState("");
  const [problemas, setProblemas] = useState<{ nueva?: string; repetida?: string }>({});
  const delServidor = cambiar.error?.tipo === "validacion" ? cambiar.error.campos : {};
  const errorGeneral = cambiar.error && cambiar.error.tipo !== "validacion" ? cambiar.error : null;

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    const encontrados = problemasDeClave(actual, nueva, repetida);
    setProblemas(encontrados);
    if (Object.keys(encontrados).length) return;
    cambiar.mutate(
      { actual, nueva },
      {
        onSuccess: (r) => {
          setActual("");
          setNueva("");
          setRepetida("");
          avisar({ tono: "exito", texto: r.mensaje });
        },
      },
    );
  }

  return (
    <form aria-label="Cambiar mi contraseña" noValidate onSubmit={enviar} className={TARJETA}>
      <div>
        <h2 className="text-lg font-bold">Cambiar mi contraseña</h2>
        <p className="text-sm text-texto-secundario">
          Al cambiarla se cierran tus sesiones en otros equipos; en este sigues dentro.
        </p>
      </div>
      <div className="grid gap-3 sm:max-w-md">
        <CampoTexto
          id="clave-actual"
          etiqueta="Contraseña actual"
          type="password"
          autoComplete="current-password"
          required
          value={actual}
          error={delServidor.actual ?? null}
          onChange={(e) => setActual(e.target.value)}
        />
        <CampoTexto
          id="clave-nueva"
          etiqueta="Contraseña nueva"
          type="password"
          autoComplete="new-password"
          ayuda="10 caracteres o más, distinta de la actual."
          required
          value={nueva}
          error={problemas.nueva ?? delServidor.nueva ?? null}
          onChange={(e) => setNueva(e.target.value)}
        />
        <CampoTexto
          id="clave-repetida"
          etiqueta="Repite la contraseña nueva"
          type="password"
          autoComplete="new-password"
          required
          value={repetida}
          error={problemas.repetida ?? null}
          onChange={(e) => setRepetida(e.target.value)}
        />
      </div>
      {errorGeneral ? (
        <Alerta tono="error" titulo="No se cambió la contraseña" rol="alert">
          <p>{errorGeneral.message}</p>
        </Alerta>
      ) : null}
      <Boton type="submit" className="self-start" disabled={cambiar.isPending}>
        {cambiar.isPending ? "Cambiando…" : "Cambiar contraseña"}
      </Boton>
    </form>
  );
}

function Telegram({ cuenta }: { cuenta: MiCuenta }) {
  const vincular = useVincularTelegram();
  const desvincular = useDesvincularTelegram();
  const { avisar } = useAvisos();
  const { telegram } = cuenta;
  const vinculo = vincular.data;
  const error = vincular.error ?? desvincular.error;

  return (
    <section aria-labelledby="titulo-telegram" className={TARJETA}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="titulo-telegram" className="text-lg font-bold">
          Telegram
        </h2>
        <Distintivo tono={telegram.vinculado ? "exito" : "neutro"}>{telegram.vinculado ? "Chat vinculado" : "Sin vincular"}</Distintivo>
      </div>
      {!telegram.canal_activo ? (
        <p className="text-texto-secundario">
          El canal de Telegram no está configurado en esta instalación. Los gastos se cargan desde la plataforma, en «Gastos».
        </p>
      ) : telegram.vinculado ? (
        <p className="text-texto-secundario">
          Tu chat{telegram.usuario ? <> <strong className="text-texto">@{telegram.usuario}</strong></> : null} está vinculado: puedes
          enviar la foto de un recibo y queda en tu viaje.
        </p>
      ) : (
        <p className="text-texto-secundario">
          Vincula tu chat para registrar gastos con una foto, sin abrir la plataforma. El chat solo te identifica: tus permisos son
          los mismos de aquí.
        </p>
      )}

      {vinculo && !telegram.vinculado ? (
        <Alerta tono="exito" titulo="Listo para vincular" rol="status">
          <p>Abre este enlace desde el teléfono donde tienes Telegram. Vale {vinculo.minutos} minutos y sirve una sola vez.</p>
          {vinculo.enlace ? (
            <p className="mt-2">
              <a href={vinculo.enlace} target="_blank" rel="noopener noreferrer" className="font-semibold">
                Abrir el chat y vincular
              </a>
            </p>
          ) : null}
          <p className="mt-2 text-sm">
            O escribe en el chat del bot: <code className="break-all">/start {vinculo.codigo}</code>
          </p>
        </Alerta>
      ) : null}

      {error ? (
        <Alerta tono="error" titulo="No se pudo completar" rol="alert">
          <p>{error.message}</p>
        </Alerta>
      ) : null}

      {telegram.canal_activo && !telegram.vinculado ? (
        <Boton className="self-start" onClick={() => vincular.mutate()} disabled={vincular.isPending}>
          {vincular.isPending ? "Preparando…" : vinculo ? "Pedir otro enlace" : "Vincular Telegram"}
        </Boton>
      ) : null}
      {telegram.vinculado ? (
        <Boton
          variante="secundario"
          className="self-start"
          disabled={desvincular.isPending}
          onClick={() => desvincular.mutate(undefined, { onSuccess: () => avisar({ tono: "exito", texto: "Chat desvinculado." }) })}
        >
          {desvincular.isPending ? "Desvinculando…" : "Desvincular"}
        </Boton>
      ) : null}
    </section>
  );
}

export function PantallaMiCuenta() {
  const consulta = useMiCuenta();
  const cuenta = consulta.data;
  return (
    <div className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina migas={[{ texto: "Mi cuenta" }]} titulo="Mi cuenta" descripcion="Tus datos, tu contraseña y tu chat de Telegram." />
      {!cuenta ? (
        consulta.error ? (
          <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
        ) : (
          <EsqueletoDetalle texto="Cargando tu cuenta…" />
        )
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="flex flex-col gap-6">
            <MisDatos cuenta={cuenta} />
            <Telegram cuenta={cuenta} />
          </div>
          <CambiarClave />
        </div>
      )}
    </div>
  );
}
