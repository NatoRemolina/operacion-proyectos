/** Bloques grises mientras llegan los datos: la pantalla nunca queda en blanco. */
function Bloque({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-md bg-neutro-suave ${className}`} />;
}

export function EsqueletoLista({ texto = "Cargando…", filas = 4 }: { texto?: string; filas?: number }) {
  return (
    <div role="status" className="flex flex-col gap-3 rounded-tarjeta border border-linea bg-superficie p-4">
      <span className="sr-only">{texto}</span>
      {Array.from({ length: filas }, (_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Bloque className="h-4 flex-1" />
          <Bloque className="h-4 w-24" />
        </div>
      ))}
    </div>
  );
}

export function EsqueletoIndicadores({ cantidad = 4 }: { cantidad?: number }) {
  return (
    <div aria-hidden="true" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: cantidad }, (_, i) => (
        <div key={i} className="flex flex-col gap-2 rounded-tarjeta border border-linea bg-superficie p-4">
          <Bloque className="h-3 w-2/3" />
          <Bloque className="h-7 w-1/2" />
          <Bloque className="h-3 w-3/4" />
        </div>
      ))}
    </div>
  );
}

export function EsqueletoDetalle({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <div role="status" className="flex flex-col gap-4">
      <span className="sr-only">{texto}</span>
      <Bloque className="h-8 w-1/2" />
      <div className="flex flex-col gap-3 rounded-tarjeta border border-linea bg-superficie p-4">
        {Array.from({ length: 5 }, (_, i) => (
          <Bloque key={i} className="h-4 w-full" />
        ))}
      </div>
    </div>
  );
}
