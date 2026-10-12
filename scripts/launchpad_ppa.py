#!/usr/bin/env python3
"""Consultas y copias en el PPA de lamp-manager a través de la API de Launchpad.

  existe <versión>                      sale con 0 si la versión se subió alguna vez al PPA
  copiar <versión> <origen> <destino>   copia la versión entre series reutilizando los binarios
"""
import argparse
import logging
import sys

from launchpadlib.launchpad import Launchpad
from lazr.restfulclient.errors import HTTPError

log = logging.getLogger("launchpad_ppa")

PPA_OWNER = "nefreyu-99"
PPA_NAME = "lamp-manager"
PACKAGE = "lamp-manager"
APP_NAME = "lamp-manager-publicar"


def _ppa(anonymous: bool):
    if anonymous:
        lp = Launchpad.login_anonymously(APP_NAME, "production", version="devel")
    else:
        # La primera vez abre el navegador para autorizar el acceso; después usa el llavero
        lp = Launchpad.login_with(APP_NAME, "production", version="devel")
    return lp, lp.people[PPA_OWNER].getPPAByName(name=PPA_NAME)


def version_exists(version: str) -> bool:
    _, ppa = _ppa(anonymous=True)
    sources = ppa.getPublishedSources(source_name=PACKAGE, version=version, exact_match=True)
    return len(sources) > 0


def copy_package(version: str, from_series: str, to_series: str) -> None:
    lp, ppa = _ppa(anonymous=False)
    target = lp.distributions["ubuntu"].getSeries(name_or_version=to_series)
    already = ppa.getPublishedSources(
        source_name=PACKAGE, version=version, exact_match=True, distro_series=target,
    )
    if len(already) > 0:
        log.info("La versión %s ya está en %s (%s); no se copia otra vez",
                 version, to_series, already[0].status)
        return
    ppa.copyPackage(
        source_name=PACKAGE,
        version=version,
        from_archive=ppa,
        from_series=from_series,
        to_series=to_series,
        to_pocket="Release",
        include_binaries=True,
    )
    log.info("Copia de %s de %s a %s solicitada", version, from_series, to_series)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    exists_cmd = sub.add_parser("existe")
    exists_cmd.add_argument("version")
    copy_cmd = sub.add_parser("copiar")
    copy_cmd.add_argument("version")
    copy_cmd.add_argument("from_series")
    copy_cmd.add_argument("to_series")
    args = parser.parse_args()

    try:
        if args.command == "existe":
            return 0 if version_exists(args.version) else 1
        copy_package(args.version, args.from_series, args.to_series)
        return 0
    except HTTPError as e:
        log.error("Launchpad respondió con un error: %s", e.content.decode(errors="replace") if e.content else e)
    except Exception as e:
        log.error("No se pudo completar la operación en Launchpad: %s", e)
    return 2


if __name__ == "__main__":
    sys.exit(main())
