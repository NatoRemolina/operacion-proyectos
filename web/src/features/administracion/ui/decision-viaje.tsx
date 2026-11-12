"use client";

import { useState } from "react";
import type { ViajeResumen } from "@/features/viajes/domain/viajes";
import { usePermiso } from "@/shared/application/identidad";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { CampoAreaTexto } from "@/shared/ui/campo";
import { DialogoConfirmacion } from "@/shared/ui/dialogo-confirmacion";
import { Alerta } from "@/shared/ui/estado";
import { useCambiarEstadoViaje } from "../application/administracion";
import { problemaDeMotivo, type CambioEstadoViaje } from "../domain/administracion";

const TITULO_ERROR: Partial<Record<ErrorDeAplicacion["tipo"], string>> = {
  autoaprobacion: "Este presupuesto lo aprueba otra persona",
  estado_invalido: "El viaje ya cambió de estado",
  prohibido: "No tienes permiso para decidir este viaje",
};

/**
 * Aprobar o rechazar el presupuesto de un viaje pendiente. Solo administración ve los botones y
 * nunca sobre un viaje propio. Rechazar pide el motivo; si el precio del vuelo cambió, aprobar
 * se convierte en «Confirmar precio y aprobar».
 */
export function DecisionViaje({ viaje }: { viaje: ViajeResumen }) {
  const permiso = usePermiso();
  const mutacion = useCambiarEstadoViaje();
  const { avisar } = useAvisos();
  const [precioNuevo, setPrecioNuevo] = useState<string | null>(null);
  const [rechazando, setRechazando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [errorMotivo, setErrorMotivo] = useState<string | null>(null);
  const [error, setError] = useState<ErrorDeAplicacion | null>(null);

  if (permiso !== "admin") {
    return <p className="text-texto-secundario">Esperando la aprobación de administración.</p>;
  }
  if (viaje.propio) {
    return <p className="text-texto-secundario">Es tu viaje: lo aprueba otra persona de administración.</p>;
  }

  const cambioDePrecio = precioNuevo ?? viaje.precio_por_confirmar ?? null;
  const enviando = mutacion.isPending;
  const accionEnCurso = mutacion.variables?.cambio.accion;

  function decidir(cambio: CambioEstadoViaje) {
    setError(null);
    mutacion.mutate(
      { id: viaje.id, cambio },
      {
        onSuccess: (resultado) => {
          setRechazando(false);
          setMotivo("");
          avisar({ tono: "exito", texto: resultado.mensaje });
        },
        onError: (e) => {
          if (e.tipo === "precio_por_confirmar") setPrecioNuevo(e.campos.precio ?? e.message);
          else if (e.tipo === "validacion" && e.campos.motivo) setErrorMotivo(e.campos.motivo);
          else {
            setRechazando(false);
            setError(e);
          }
        },
      },
    );
  }

  function rechazar() {
    const problema = problemaDeMotivo(motivo);
    setErrorMotivo(problema);
    if (!problema) decidir({ accion: "rechazar", motivo: motivo.trim() });
  }

  return (
    <div className="flex flex-col gap-3">
      {cambioDePrecio ? (
        <Alerta tono="aviso" titulo="El precio del vuelo cambió">
          <p>{cambioDePrecio}.</p>
          <p className="mt-1">Si lo confirmas, el presupuesto pasa al precio nuevo.</p>
        </Alerta>
      ) : null}
      {error ? (
        <Alerta tono="error" rol="alert" titulo={TITULO_ERROR[error.tipo] ?? "No se pudo decidir el viaje"}>
          <p>{error.message}</p>
        </Alerta>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Boton
          onClick={() => decidir({ accion: "aprobar", confirmarPrecio: Boolean(cambioDePrecio) })}
          disabled={enviando}
        >
          {enviando && accionEnCurso === "aprobar"
            ? "Aprobando…"
            : cambioDePrecio
              ? "Confirmar precio y aprobar"
              : "Aprobar presupuesto"}
        </Boton>
        <Boton variante="secundario" onClick={() => setRechazando(true)} disabled={enviando}>
          Rechazar
        </Boton>
      </div>
      <DialogoConfirmacion
        abierto={rechazando}
        titulo={`Rechazar el presupuesto de ${viaje.codigo}`}
        efecto={`El viaje queda rechazado y ${viaje.titular?.nombre ?? "quien viaja"} verá el motivo. Se puede reabrir después.`}
        confirmar="Rechazar presupuesto"
        peligro
        enviando={enviando}
        onConfirmar={rechazar}
        onCancelar={() => {
          setRechazando(false);
          setErrorMotivo(null);
        }}
      >
        <CampoAreaTexto
          id={`motivo-rechazo-${viaje.id}`}
          etiqueta="Motivo del rechazo"
          ayuda="La persona lo verá en su viaje."
          value={motivo}
          maxLength={300}
          onChange={(e) => setMotivo(e.target.value)}
          onBlur={() => motivo && setErrorMotivo(problemaDeMotivo(motivo))}
          error={errorMotivo}
        />
      </DialogoConfirmacion>
    </div>
  );
}
