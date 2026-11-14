#!/usr/bin/env bash
# Run Deimos natively on Linux (no Wine), against a Proton-hosted client.
#
# Needs: the native extensions (zhol/kinif/wizlaunch) in $PYDIR, the Python 3.13
# venv in $DVENV with Deimos' deps, and the game client already running. Runs
# under steam-run for the FHS libraries the pip wheels (Qt/numpy/shapely) need,
# with xdotool on PATH for window/input.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HOME_DIR="${DEIMOS_LINUX_HOME:-$HOME/.local/share/Deimos-linux}"
PYDIR="$HOME_DIR/py"
DVENV="$HOME_DIR/dvenv"

export PYTHONPATH="$REPO/src/linux_backend:$PYDIR:$REPO/libs/wizwalker:$REPO/libs/wizsprinter"
export WIZLAUNCH_GAME_PATH="${WIZLAUNCH_GAME_PATH:-$HOME/.local/share/Steam/steamapps/common/Wizard101}"
# xdotool for the window/input layer:
XDOTOOL_BIN="$(nix-build '<nixpkgs>' -A xdotool --no-out-link 2>/dev/null)/bin"
export PATH="$XDOTOOL_BIN:$PATH"

cd "$REPO"
exec steam-run "$DVENV/bin/python3" Deimos.py "$@"
