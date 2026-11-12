"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useViajesParaRecibo } from "@/features/viajes/application/viajes";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { clasesBoton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { formatearRango } from "@/shared/ui/formato";
import { useEnvioRecibo } from "../application/gastos";
import { FormularioRecibo, type ArchivoElegido, type ErrorEnvio } from "./formulario-recibo";
import { ResultadoEnvio } from "./resultado-envio";

function describirError(error: ErrorDeAplicacion): ErrorEnvio {
  switch (error.tipo) {
    case "sesion_vencida":
      return {
        titulo: "Tu sesión venció",
        detalle: "El recibo no se guardó. Entra de nuevo y vuelve a enviarlo.",
        accion: "entrar",
      };
    case "demasiado_grande":
      return {
        titulo: "El archivo pesa más de 4,5 MB",
        detalle: "Elige un archivo más liviano o toma la foto de nuevo.",
        accion: "elegir",
      };
    case "tipo_no_admitido":
      return { titulo: "Ese archivo no se admite", detalle: error.message, accion: "elegir" };
    case "conflicto":
      return {
        titulo: "Ese envío ya se usó con otro archivo",
        detalle: "Vuelve a elegir el archivo para enviarlo como un recibo nuevo.",
        accion: "elegir",
      };
    case "validacion": {
      const campos = Object.values(error.campos);
      return {
        titulo: "Revisa los datos del envío",
        detalle: campos.length ? `${error.message} ${campos.join(". ")}.` : error.message,
        accion: "elegir",
        referencia: error.idPeticion,
      };
    }
    case "prohibido":
      return { titulo: "No puedes enviar este recibo", detalle: error.message, accion: "elegir" };
    case "en_curso":
      return {
        titulo: "Tu recibo todavía se está procesando",
        detalle: "Reintenta en unos segundos: se usa el mismo envío, así no se duplica.",
        accion: "reintentar",
      };
    default:
      return {
        titulo: "No se pudo enviar el recibo",
        detalle: `${error.message} Tu archivo sigue elegido: puedes reintentar sin que se duplique.`,
        accion: "reintentar",
        referencia: error.idPeticion,
      };
  }
}

/** Vista previa local del archivo; la URL anterior se libera al cambiarla y al salir. */
function useVistaPrevia() {
  const [url, setUrl] = useState<string | null>(null);
  const actual = useRef<string | null>(null);
  useEffect(
    () => () => {
      if (actual.current) URL.revokeObjectURL(actual.current);
    },
    [],
  );
  const mostrar = useCallback((archivo: File | null) => {
    if (actual.current) URL.revokeObjectURL(actual.current);
    const puede =
      archivo !== null && archivo.type.startsWith("image/") && typeof URL.createObjectURL === "function";
    actual.current = puede ? URL.createObjectURL(archivo) : null;
    setUrl(actual.current);
  }, []);
  return { url, mostrar };
}

export function PantallaNuevoGasto({ viajeInicial }: { viajeInicial?: number } = {}) {
  const envio = useEnvioRecibo();
  const viajes = useViajesParaRecibo();
  // Desde el detalle de un viaje se llega con ese viaje ya elegido.
  const inicial = viajeInicial ? String(viajeInicial) : "";
  const [viajeId, setViajeId] = useState(inicial);
  const [justificacion, setJustificacion] = useState("");
  const vistaPrevia = useVistaPrevia();

  const archivo: ArchivoElegido | null = envio.archivo
    ? {
        nombre: envio.archivo.name,
        tamano: envio.archivo.size,
        esPdf: envio.archivo.type === "application/pdf",
        vistaPrevia: vistaPrevia.url,
      }
    : null;

  const progreso = envio.enviando
    ? `Enviando «${envio.archivo?.name ?? "recibo"}». Estamos leyendo y validando el recibo; puede tardar unos segundos.`
    : envio.resultado
      ? `Recibo enviado. Estado: ${envio.resultado.estado_texto}.`
      : envio.archivo
        ? `Archivo elegido: ${envio.archivo.name}.`
        : "";

  return (
    <section aria-labelledby="titulo-nuevo" className="flex max-w-xl flex-col gap-4">
      <EncabezadoPagina
        idTitulo="titulo-nuevo"
        migas={[{ texto: "Gastos", href: "/gastos" }, { texto: "Cargar un gasto" }]}
        titulo="Cargar un gasto"
        descripcion="Guarda el soporte ahora. Confirma los datos después."
      />

      {/* Región viva única: anuncia elección, progreso y resultado sin mover el foco. */}
      <p role="status" aria-live="polite" className={envio.enviando ? "font-semibold text-marca" : "sr-only"}>
        {progreso}
      </p>

      {envio.resultado ? (
        <ResultadoEnvio
          gasto={envio.resultado}
          onEnviarOtro={() => {
            envio.reiniciar();
            vistaPrevia.mostrar(null);
            setViajeId(inicial);
            setJustificacion("");
          }}
        />
      ) : (
        <FormularioRecibo
          archivo={archivo}
          onElegirArchivo={(elegido) => {
            envio.elegirArchivo(elegido);
            vistaPrevia.mostrar(elegido);
          }}
          viajes={(viajes.data ?? []).map((v) => ({
            id: v.id,
            codigo: v.codigo,
            ruta: `${v.origen} → ${v.destino}`,
            fechas: formatearRango(v.ida, v.regreso),
            estadoTexto: v.estado_texto,
            enCurso: v.en_curso,
          }))}
          cargandoViajes={viajes.isPending}
          viajeId={viajeId}
          onCambiarViaje={setViajeId}
          justificacion={justificacion}
          onCambiarJustificacion={setJustificacion}
          onEnviar={() => envio.enviar(viajeId ? Number(viajeId) : null, justificacion)}
          enviando={envio.enviando}
          error={envio.error ? describirError(envio.error) : null}
        />
      )}

      <Link href="/gastos" className={clasesBoton("secundario", "w-full")}>
        Ver mis gastos
      </Link>
    </section>
  );
}
