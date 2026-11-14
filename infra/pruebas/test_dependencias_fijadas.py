"""B3: lo que entra en las imágenes es exactamente lo que se probó.

Toda imagen base, el adaptador de Lambda y las imágenes de docker compose van por digest (una etiqueta como
`3.12-slim` cambia de contenido sin aviso). Python se instala desde archivos de bloqueo con hashes, que cubren lo
que piden los requirements; Node, con `npm ci` sobre su package-lock."""
import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

RAIZ = Path(__file__).resolve().parents[2]
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
DOCKERFILES = ["Dockerfile", "web/Dockerfile", "analizador/Dockerfile"]
BLOQUEOS = [
    ("requirements.txt", "requirements.lock"),
    ("requirements-dev.txt", "requirements-dev.lock"),
    ("analizador/requirements.txt", "analizador/requirements.lock"),
    ("analizador/requirements-pruebas.txt", "analizador/requirements-pruebas.lock"),
]


def _leer(ruta: str) -> str:
    return (RAIZ / ruta).read_text(encoding="utf-8")


def imagenes_de(dockerfile: str) -> list[str]:
    """Las imágenes de fuera que usa un Dockerfile (FROM y COPY --from), con los ARG resueltos y sin sus propias etapas."""
    texto = _leer(dockerfile)
    args = dict(re.findall(r"^ARG (\w+)=(\S+)", texto, re.M))
    etapas = {e.lower() for e in re.findall(r"^FROM\s+\S+\s+AS\s+(\S+)", texto, re.M | re.I)}
    refs = re.findall(r"^FROM\s+(\S+)", texto, re.M) + re.findall(r"COPY\s+--from=(\S+)", texto)
    resueltas = [re.sub(r"\$\{(\w+)\}", lambda m: args.get(m.group(1), m.group(0)), r) for r in refs]
    return [r for r in resueltas if r.lower() not in etapas]


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_toda_imagen_de_fuera_va_por_digest(dockerfile):
    imagenes = imagenes_de(dockerfile)
    assert imagenes, f"{dockerfile} no usa ninguna imagen"
    sin_digest = [i for i in imagenes if not DIGEST.search(i)]
    assert not sin_digest, f"{dockerfile}: sin digest {sin_digest}"


def test_el_adaptador_de_lambda_va_por_digest_en_las_dos_imagenes():
    for dockerfile in ("Dockerfile", "web/Dockerfile"):
        adaptador = [i for i in imagenes_de(dockerfile) if "aws-lambda-adapter" in i]
        assert adaptador and all(DIGEST.search(i) for i in adaptador), dockerfile


def test_las_imagenes_de_docker_compose_van_por_digest():
    imagenes = re.findall(r"^\s+image:\s*(\S+)", _leer("docker-compose.yml"), re.M)
    assert imagenes
    assert all(DIGEST.search(i) for i in imagenes), imagenes


def test_la_imagen_de_reserva_de_cdk_va_por_digest():
    (imagen,) = re.findall(r'fromRegistry\("([^"]+)"\)', _leer("infra/lib/estaticos.ts"))
    assert DIGEST.search(imagen), imagen


def paquetes_del_bloqueo(ruta: str) -> dict[str, tuple[Version, int]]:
    """{nombre: (versión, hashes)} de un archivo de bloqueo."""
    paquetes: dict[str, tuple[Version, int]] = {}
    actual = None
    for linea in _leer(ruta).splitlines():
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;\\]+)", linea)
        if m:
            actual = m.group(1).lower().replace("_", "-")
            paquetes[actual] = (Version(m.group(2)), 0)
        elif actual and "--hash=sha256:" in linea:
            version, hashes = paquetes[actual]
            paquetes[actual] = (version, hashes + 1)
    return paquetes


def requisitos(ruta: str) -> list[Requirement]:
    salida = []
    for linea in _leer(ruta).splitlines():
        linea = linea.split("#", 1)[0].strip()
        if linea.startswith("-r "):
            salida += requisitos(str(Path(ruta).parent / linea[3:].strip()))
        elif linea:
            salida.append(Requirement(linea))
    return salida


@pytest.mark.parametrize(("origen", "bloqueo"), BLOQUEOS)
def test_cada_bloqueo_cubre_sus_requisitos_y_todo_lleva_hash(origen, bloqueo):
    paquetes = paquetes_del_bloqueo(bloqueo)
    for r in requisitos(origen):
        nombre = r.name.lower().replace("_", "-")
        assert nombre in paquetes, f"{bloqueo} no trae {r.name} (regenerar con make bloquear)"
        assert paquetes[nombre][0] in r.specifier, f"{bloqueo}: {r.name}=={paquetes[nombre][0]} no cumple {r.specifier}"
    sin_hash = [n for n, (_, hashes) in paquetes.items() if not hashes]
    assert not sin_hash, f"{bloqueo}: sin hash {sin_hash}"


def test_las_imagenes_la_integracion_y_la_instalacion_usan_el_bloqueo_con_hashes():
    assert re.search(r"pip install .*--require-hashes.* -r requirements\.lock", _leer("Dockerfile"))
    analizador = _leer("analizador/Dockerfile")
    assert re.search(r"pip install .*--require-hashes.* -r analizador/requirements\.lock", analizador)
    assert re.search(r"pip install .*--require-hashes.* -r analizador/requirements-pruebas\.lock", analizador)
    assert re.search(r"pip install .*--require-hashes.* -r requirements-dev\.lock", _leer(".github/workflows/pruebas.yml"))
    assert re.search(r"pip install .*--require-hashes.* -r requirements-dev\.lock", _leer("Makefile"))


def test_node_se_instala_con_npm_ci_sobre_su_package_lock():
    for carpeta in ("web", "infra"):
        assert (RAIZ / carpeta / "package-lock.json").is_file()
    assert "npm ci" in _leer("web/Dockerfile") and "npm install" not in _leer("web/Dockerfile")
    flujo = _leer(".github/workflows/pruebas.yml")
    assert "npm ci" in flujo and "npm install" not in flujo
