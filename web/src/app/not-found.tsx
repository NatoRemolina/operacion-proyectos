import Link from "next/link";

export default function NoEncontrada() {
  return (
    <main id="contenido" className="mx-auto w-full max-w-contenido px-4 py-10">
      <h1 className="text-2xl font-extrabold">Esta página no existe</h1>
      <p className="mt-2">
        Revisa la dirección o <Link href="/viajes">vuelve a tus viajes</Link>.
      </p>
    </main>
  );
}
