import Link from "next/link";

export interface Miga {
  texto: string;
  href?: string;
}

/** Dónde está la persona. La última miga es la página actual. */
export function Migas({ items }: { items: readonly Miga[] }) {
  return (
    <nav aria-label="Migas de pan" className="text-sm text-texto-secundario">
      <ol className="flex flex-wrap items-center gap-x-2">
        {items.map((miga, i) => {
          const ultima = i === items.length - 1;
          return (
            <li key={`${miga.texto}-${i}`} className="flex items-center gap-x-2">
              {miga.href && !ultima ? (
                <Link href={miga.href} className="inline-flex min-h-11 items-center">
                  {miga.texto}
                </Link>
              ) : (
                <span aria-current={ultima ? "page" : undefined} className={ultima ? "font-semibold text-texto" : ""}>
                  {miga.texto}
                </span>
              )}
              {ultima ? null : <span aria-hidden="true">/</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
