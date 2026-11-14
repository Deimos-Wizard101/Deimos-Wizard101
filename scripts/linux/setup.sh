#!/usr/bin/env bash
# One-time (and idempotent) bootstrap for running Deimos from source on Linux.
#
#   scripts/linux/setup.sh
#
# Builds, in order:
#   1. a Proton prefix shared by the game clients and Deimos
#   2. a Windows CPython (the python.org NuGet build) inside DEIMOS_LINUX_HOME
#   3. Deimos' dependencies via pip, plus wizwalker/wizsprinter as editable installs
#   4. the two pyo3 extensions (wizlaunch, kinif) cross-compiled with mingw-w64
#
# Requirements on the host: steam-run, curl, nix-shell (for unzip and the
# mingw-w64 toolchain), rustup with the x86_64-pc-windows-gnu target.
# Afterwards: scripts/linux/run.sh
set -euo pipefail
source "$(dirname "$0")/env.sh"

PY_VERSION="${DEIMOS_WIN_PYTHON_VERSION:-3.13.17}"
PY_DIR="$(dirname "$WIN_PYTHON")"
mkdir -p "$PREFIX" "$LOG_DIR"

step() { printf '\n==> %s\n' "$*"; }

# ---- 2. Windows Python (host side: download + unpack) ----
if [ ! -f "$WIN_PYTHON" ]; then
    step "Fetching Windows CPython $PY_VERSION"
    tmp="$(mktemp -d)"
    curl -sSL -o "$tmp/python.nupkg" "https://www.nuget.org/api/v2/package/python/$PY_VERSION"
    nix-shell -p unzip --run "unzip -q '$tmp/python.nupkg' -d '$tmp/pkg'"
    rm -rf "$PY_DIR"
    mv "$tmp/pkg/tools" "$PY_DIR"
    rm -rf "$tmp"
fi

# ---- 4. pyo3 extensions (host side: cross-compile) ----
# pyo3-build-config's own build script insists on a host interpreter even when
# cross-compiling, hence python3 in the shell. Rust's windows-gnu std links
# winpthreads, which nixpkgs ships as a separate cross package.
step "Cross-compiling wizlaunch and kinif for x86_64-pc-windows-gnu"
if command -v rustup >/dev/null; then
    rustup target add x86_64-pc-windows-gnu >/dev/null
fi
pthreads="$(nix-build '<nixpkgs>' -A pkgsCross.mingwW64.windows.pthreads --no-out-link)"
nix-shell -p pkgsCross.mingwW64.stdenv.cc python3 --run "
    set -e
    export PYO3_CROSS_PYTHON_VERSION='${PY_VERSION%.*}'
    export CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=x86_64-w64-mingw32-gcc
    export CARGO_TARGET_X86_64_PC_WINDOWS_GNU_RUSTFLAGS='-L native=$pthreads/lib'
    for crate in libs/wizlaunch libs/kinif; do
        (cd '$REPO'/\$crate && cargo build --release --lib --quiet \
            --target x86_64-pc-windows-gnu --features pyo3/generate-import-lib)
    done
"

# ---- 1 + 3. Everything that runs inside the prefix ----
# A single steam-run session so the sequence below shares one wineserver.
step "Initialising prefix and installing Python packages (pip log: $LOG_DIR/pip.log)"
export DEIMOS_SETUP_PY_VERSION="$PY_VERSION"
steam-run bash -s <<INNER
set -euo pipefail
source '$REPO/scripts/linux/env.sh'
pip_log="\$(winpath "$LOG_DIR/pip.log")"
pip() {
    proton_run "$WIN_PYTHON" -m pip "\$@" --disable-pip-version-check --no-input \
        --progress-bar off --log "\$pip_log"
}

proton_run cmd /c ver
proton_run "$WIN_PYTHON" -m ensurepip --default-pip

# Mirrors pyproject.toml plus the workspace libs' own requirements. Deviations:
#  - PyQt6 is held at 6.6.1: from 6.7 the Windows Qt build imports icuuc.dll,
#    the ICU that ships with Windows 10 1903+ and that Wine does not provide.
#  - memobj pins pefile==2021.9.3 (sdist only) and regex<2025; the project's
#    uv config overrides pefile, so memobj and wiztype go in without deps.
pip install --only-binary=:all: \
    "PyQt6==6.6.1" "PyQt6-Qt6==6.6.1" \
    "loguru>=0.7.2" "pypresence>=4.3.0" "pyperclip>=1.9.0" "pywin32>=306" \
    "cryptography>=42.0.0" "pyyaml>=6.0.1" "requests>=2.32.3" "thefuzz>=0.22.1" \
    "numpy>=2.4.6" "shapely>=2.1.2" "katsuba>=0.4.0" "keystone-engine>=0.9.2" \
    "aiofiles>=23.2.1" "pymem==1.13.1" "appdirs>=1.4.4" "click>=8.1.7" \
    "click-default-group>=1.2.4" "janus>=1.0.0" "pefile>=2024.8.26" \
    "regex>=2024.11.6,<2025" "lark>=1.1.9" "iced-x86>=1.21.0"
pip install --only-binary=:all: --no-deps "memobj==0.14.1" "wiztype>=0.1.12"
pip install -e "\$(winpath '$REPO/libs/wizwalker')" -e "\$(winpath '$REPO/libs/wizsprinter')"
INNER

cp "$REPO/libs/wizlaunch/target/x86_64-pc-windows-gnu/release/wizlaunch.dll" "$WIN_SITE_PACKAGES/wizlaunch.pyd"
cp "$REPO/libs/wizlaunch/wizlaunch.pyi" "$WIN_SITE_PACKAGES/"
cp "$REPO/libs/kinif/target/x86_64-pc-windows-gnu/release/kinif.dll" "$WIN_SITE_PACKAGES/kinif.pyd"

step "Done. Launch with: scripts/linux/run.sh --clients 1"
