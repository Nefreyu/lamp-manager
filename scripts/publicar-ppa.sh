#!/usr/bin/env bash
# Publica la versión actual de debian/changelog en el PPA para resolute y la copia a noble.
#
# Uso (desde la raíz del repositorio):
#   scripts/publicar-ppa.sh              comprueba, construye, sube, espera y copia a noble
#   scripts/publicar-ppa.sh --continuar  retoma la espera y la copia de una subida ya hecha
#   scripts/publicar-ppa.sh --simular    comprueba y construye sin firmar, sin subir nada

set -euo pipefail

PPA="ppa:nefreyu-99/lamp-manager"
PPA_URL="https://ppa.launchpadcontent.net/nefreyu-99/lamp-manager/ubuntu"
PACKAGE="lamp-manager"
SOURCE_SERIES="resolute"
COPY_SERIES="noble"
POLL_SECONDS=120
TIMEOUT_SECONDS=$((4 * 3600))

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
PARENT_DIR="$(dirname "$REPO_DIR")"
BUILDS_DIR="$PARENT_DIR/lamp-manager-builds"

mode="publicar"
case "${1:-}" in
    "") ;;
    --continuar) mode="continuar" ;;
    --simular) mode="simular" ;;
    *) echo "Opción desconocida: $1" >&2; echo "Uso: $0 [--continuar | --simular]" >&2; exit 2 ;;
esac

launchpad() { python3 "$SCRIPT_DIR/launchpad_ppa.py" "$@"; }

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

notify() {
    printf '\a'
    if command -v notify-send >/dev/null; then
        notify-send --icon=io.github.nefreyu.LampManager "LAMP Manager" "$1" || true
    fi
}

published_in() {
    local series="$1" version="$2"
    curl -fsSL "$PPA_URL/dists/$series/main/binary-amd64/Packages.gz?t=$(date +%s)" 2>/dev/null \
        | zcat 2>/dev/null \
        | awk -v pkg="$PACKAGE" -v ver="$version" '
            /^Package: / { name = $2 }
            /^Version: / { if (name == pkg && $2 == ver) found = 1 }
            END { exit !found }'
}

wait_until_published() {
    local series="$1" version="$2" start elapsed
    start=$(date +%s)
    while ! published_in "$series" "$version"; do
        elapsed=$(( $(date +%s) - start ))
        if (( elapsed >= TIMEOUT_SECONDS )); then
            echo
            notify "La $version no aparece en $series tras 4 horas"
            fail "La $version sigue sin publicarse en $series. Relanza con --continuar más tarde."
        fi
        printf '\r    Esperando a %s… %dh %02dmin' "$series" $((elapsed / 3600)) $((elapsed % 3600 / 60))
        sleep "$POLL_SECONDS"
    done
    printf '\r    Publicada en %s.%-30s\n' "$series" ""
}

cd "$REPO_DIR"
version="$(dpkg-parsechangelog -S Version)"
distribution="$(dpkg-parsechangelog -S Distribution)"

if [[ "$mode" != "continuar" ]]; then
    step "Comprobando la versión $version"
    problems=()

    branch="$(git branch --show-current)"
    [[ "$branch" == "main" ]] || problems+=("Estás en la rama '$branch'; las versiones se publican desde 'main'.")
    [[ -z "$(git status --porcelain)" ]] || problems+=("Hay cambios sin commitear.")
    if ! tag_commit="$(git rev-parse -q --verify "v$version^{commit}")"; then
        problems+=("No existe el tag v$version.")
    elif [[ "$tag_commit" != "$(git rev-parse HEAD)" ]]; then
        problems+=("El tag v$version no apunta al commit actual.")
    fi

    [[ "$distribution" == "$SOURCE_SERIES" ]] \
        || problems+=("La serie de debian/changelog es '$distribution' y debería ser '$SOURCE_SERIES'.")
    metainfo_version="$(grep -m1 -oP '<release version="\K[^"]+' data/io.github.nefreyu.LampManager.metainfo.xml || true)"
    [[ "$metainfo_version" == "$version" ]] \
        || problems+=("El metainfo tiene la versión '$metainfo_version' como última release.")
    man_version="$(awk -F'"' 'NR == 1 { print $4 }' data/lamp-manager.1)"
    [[ "$man_version" == "$version" ]] || problems+=("El manual (data/lamp-manager.1) tiene la versión '$man_version'.")

    set +e
    launchpad existe "$version"
    exists=$?
    set -e
    case $exists in
        0) problems+=("La versión $version ya se subió al PPA; Launchpad no deja reutilizarla.") ;;
        1) ;;
        *) problems+=("No se pudo consultar el PPA para saber si la versión $version ya existe.") ;;
    esac

    if ! .venv/bin/python -m pytest -q >/dev/null 2>&1; then
        problems+=("Fallan los tests (.venv/bin/python -m pytest -q).")
    fi

    if (( ${#problems[@]} > 0 )); then
        for p in "${problems[@]}"; do info "✗ $p"; done
        [[ "$mode" == "simular" ]] || fail "Corrige lo anterior antes de publicar."
        info "(simulación: se continúa igualmente)"
    else
        info "✓ Todo correcto"
    fi

    step "Construyendo el paquete fuente"
    if [[ "$mode" == "simular" ]]; then
        debuild -S -us -uc
    else
        debuild -S
    fi
    shopt -s nullglob
    generated=("$PARENT_DIR/${PACKAGE}_${version}".* "$PARENT_DIR/${PACKAGE}_${version}"_source.*)
    shopt -u nullglob
    for f in "${generated[@]}"; do info "$(basename "$f")"; done

    if [[ "$mode" == "simular" ]]; then
        rm -f -- "${generated[@]}"
        step "Simulación terminada: se han borrado los ficheros generados y no se ha subido nada"
        exit 0
    fi

    step "Subida al PPA"
    info "Versión $version para $SOURCE_SERIES en $PPA"
    read -r -p "    ¿Subir al PPA? [s/N] " answer
    [[ "$answer" =~ ^[sS]$ ]] || fail "Subida cancelada. Los ficheros siguen en $PARENT_DIR."
    dput "$PPA" "$PARENT_DIR/${PACKAGE}_${version}_source.changes"

    step "Guardando los ficheros en $BUILDS_DIR/$version"
    mkdir -p "$BUILDS_DIR/$version"
    shopt -s nullglob
    mv -- "$PARENT_DIR/${PACKAGE}_${version}".* "$PARENT_DIR/${PACKAGE}_${version}"_source.* "$BUILDS_DIR/$version/"
    shopt -u nullglob
fi

step "Esperando a que Launchpad publique la $version en $SOURCE_SERIES"
wait_until_published "$SOURCE_SERIES" "$version"
notify "La $version ya está publicada en $SOURCE_SERIES"

step "Copiando a $COPY_SERIES con los binarios ya compilados"
launchpad copiar "$version" "$SOURCE_SERIES" "$COPY_SERIES" || fail "No se pudo copiar a $COPY_SERIES. Relanza con --continuar."

step "Esperando a que Launchpad publique la $version en $COPY_SERIES"
wait_until_published "$COPY_SERIES" "$version"
notify "La $version ya está publicada en $SOURCE_SERIES y $COPY_SERIES"
step "Publicación terminada"
