"use client";

import { useState } from "react";
import type { ViajeResumen } from "@/features/viajes/domain/viajes";
import { usePermiso } from "@/shared/application/identidad";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { DialogoConfirmacion } from "@/shared/ui/dialogo-confirmacion";
import { Alerta } from "@/shared/ui/estado";
import { useCambiarEstadoViaje } from "../application/administracion";
import type { AccionViaje } from "../domain/administracion";

/** Reabrir y cerrar un viaje: solo administración. Cerrar pide confirmación con su efecto. */
export function AccionesViaje({ viaje }: { viaje: ViajeResumen }) {
  const permiso = usePermiso();
  const mutacion = useCambiarEstadoViaje();
  const { avisar } = useAvisos();
  const [cerrando, setCerrando] = useState(false);
  const [error, setError] = useState<ErrorDeAplicacion | null>(null);
  if (permiso !== "admin" || viaje.estado === "pendiente_aprobacion") return null;

  function hacer(accion: AccionViaje) {
    setError(null);
    mutacion.mutate(
      { id: viaje.id, cambio: { accion } },
      {
        onSuccess: (r) => {
          setCerrando(false);
          avisar({ tono: "exito", texto: r.mensaje });
        },
        onError: (e) => {
          setCerrando(false);
          setError(e);
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <Alerta tono="error" rol="alert" titulo="No se pudo cambiar el viaje">
          <p>{error.message}</p>
        </Alerta>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {viaje.estado === "aprobado" ? (
          <Boton variante="secundario" onClick={() => setCerrando(true)} disabled={mutacion.isPending}>
            Cerrar viaje
          </Boton>
        ) : null}
        <Boton variante="secundario" onClick={() => hacer("reabrir")} disabled={mutacion.isPending}>
          {mutacion.isPending && mutacion.variables?.cambio.accion === "reabrir" ? "Reabriendo…" : "Reabrir para decidir de nuevo"}
        </Boton>
      </div>
      <DialogoConfirmacion
        abierto={cerrando}
        titulo={`Cerrar el viaje ${viaje.codigo}`}
        efecto="El viaje deja de recibir gastos y queda como cerrado en los reportes. Solo administración puede reabrirlo."
        confirmar="Cerrar viaje"
        peligro
        enviando={mutacion.isPending}
        onConfirmar={() => hacer("cerrar")}
        onCancelar={() => setCerrando(false)}
      />
    </div>
  );
}
