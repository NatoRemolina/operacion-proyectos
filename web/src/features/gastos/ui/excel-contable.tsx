"use client";

import { useState } from "react";
import type { Permiso } from "@/shared/domain/navegacion";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { CampoTexto } from "@/shared/ui/campo";
import { useUrlLibroContable } from "../application/gastos";
import { mesEnCurso, problemaDePeriodo, type PeriodoContable } from "../domain/gastos";

export const ID_PANEL_EXCEL = "panel-excel-contable";

const ALCANCE: Record<Permiso, string> = {
  admin: "Incluye todos los gastos.",
  gestor: "Incluye los tuyos y los de los proyectos que gestionas.",
  colaborador: "Solo tus gastos.",
};

/**
 * El Excel contable de un periodo: los gastos aprobados con su cuenta contable, listos para
 * contabilidad. Lo arma el servidor con el permiso de la sesión; aquí solo se elige el periodo.
 */
export function PanelExcelContable({ permiso }: { permiso: Permiso }) {
  const [periodo, setPeriodo] = useState<PeriodoContable>(() => mesEnCurso());
  const url = useUrlLibroContable(periodo);
  const problema = problemaDePeriodo(periodo);

  return (
    <section
      id={ID_PANEL_EXCEL}
      aria-labelledby="titulo-excel-contable"
      className="flex flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta"
    >
      <div>
        <h2 id="titulo-excel-contable" className="mb-1 text-lg font-bold">
          Excel contable
        </h2>
        <p className="max-w-prose text-texto-secundario">
          Los gastos aprobados del periodo, por la fecha del recibo, con su cuenta contable y un resumen por proyecto,
          cuenta y moneda. {ALCANCE[permiso]}
        </p>
      </div>
      <div className="grid gap-3 sm:max-w-md sm:grid-cols-2">
        <CampoTexto
          id="contable-desde"
          etiqueta="Desde"
          type="date"
          required
          value={periodo.desde}
          onChange={(e) => setPeriodo((p) => ({ ...p, desde: e.target.value }))}
        />
        <CampoTexto
          id="contable-hasta"
          etiqueta="Hasta"
          type="date"
          required
          value={periodo.hasta}
          error={problema}
          onChange={(e) => setPeriodo((p) => ({ ...p, hasta: e.target.value }))}
        />
      </div>
      {url ? (
        // Un enlace y no una petición: el navegador lo descarga con la sesión y el nombre que da el servidor.
        <a href={url} className={clasesBoton("primario", "self-start")}>
          Descargar Excel contable
        </a>
      ) : (
        <div className="flex flex-col items-start gap-2">
          <Boton disabled>Descargar Excel contable</Boton>
          {problema ? null : (
            <p className="text-sm text-texto-secundario">
              La descarga está disponible con la plataforma conectada; en el modo de demostración no hay libro contable.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
