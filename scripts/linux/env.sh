# Shared discovery for scripts/linux/*. Sourced, not executed.
#
# Deimos is a Windows program (wizwalker drives the game through Win32 memory and
# window APIs), so on Linux it runs under the same Proton prefix as the game.
# Locations are detected the way wizlaunch's Linux launcher detects them and
# honor the same WIZLAUNCH_* overrides:
#
#   WIZLAUNCH_PROTON     Proton build (directory or `proton` script)
#   WIZLAUNCH_PREFIX     Wine prefix shared by the clients and Deimos
#   WIZLAUNCH_GAME_PATH  Wizard101 install (the directory holding Bin/)
#   DEIMOS_LINUX_HOME    where the Windows Python, prefix and logs live
#   DEIMOS_WIN_PYTHON    python.exe inside that prefix

DEIMOS_LINUX_HOME="${DEIMOS_LINUX_HOME:-$HOME/.local/share/Deimos-linux}"

STEAM_ROOT="${STEAM_COMPAT_CLIENT_INSTALL_PATH:-}"
if [ -z "$STEAM_ROOT" ]; then
    for d in "$HOME/.local/share/Steam" "$HOME/.steam/root" "$HOME/.steam/steam"; do
        if [ -d "$d" ]; then STEAM_ROOT=$d; break; fi
    done
fi
if [ -z "$STEAM_ROOT" ]; then
    echo "could not locate the Steam install; set STEAM_COMPAT_CLIENT_INSTALL_PATH" >&2
    exit 1
fi

PROTON="${WIZLAUNCH_PROTON:-$STEAM_ROOT/steamapps/common/Proton - Experimental}"
if [ -d "$PROTON" ]; then PROTON="$PROTON/proton"; fi
if [ ! -x "$PROTON" ]; then
    echo "no Proton runner at $PROTON; install Proton Experimental or set WIZLAUNCH_PROTON" >&2
    exit 1
fi

PREFIX="${WIZLAUNCH_PREFIX:-$DEIMOS_LINUX_HOME/prefix}"
GAME_PATH="${WIZLAUNCH_GAME_PATH:-$STEAM_ROOT/steamapps/common/Wizard101}"
WIN_PYTHON="${DEIMOS_WIN_PYTHON:-$DEIMOS_LINUX_HOME/python/python.exe}"
WIN_SITE_PACKAGES="$(dirname "$WIN_PYTHON")/Lib/site-packages"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$DEIMOS_LINUX_HOME/logs"

export PROTON
export STEAM_COMPAT_DATA_PATH="$PREFIX"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT"
# Xalia's gamepad overlay steals focus from freshly launched clients.
export PROTON_USE_XALIA="${PROTON_USE_XALIA:-0}"
# Proton sends child stdout/stderr to /dev/null unless PROTON_LOG is set; any
# value other than "1" is also appended to WINEDEBUG, so "-all" gives the file
# without Wine's own debug spew.
export PROTON_LOG="${PROTON_LOG:--all}"
export PROTON_LOG_DIR="${PROTON_LOG_DIR:-$LOG_DIR}"

# Host path -> path Wine sees through its Z: drive.
winpath() {
    printf 'Z:%s' "$(realpath -m "$1" | tr / '\\')"
}

# Run a Windows program in the prefix.
proton_run() {
    "$PROTON" run "$@"
}

# steam-run mounts a private tmpfs on /tmp, and that is where wineserver keeps
# its socket. Two separate steam-run invocations therefore end up with two
# wineservers on one prefix, and processes in one cannot see windows or memory
# of the other. Anything that must share a Wine session re-executes itself once
# inside a single sandbox.
enter_sandbox() {
    if [ -z "${DEIMOS_IN_SANDBOX:-}" ]; then
        if ! command -v steam-run >/dev/null; then
            echo "steam-run not found; Proton's binaries need the FHS environment it provides" >&2
            exit 1
        fi
        exec steam-run env DEIMOS_IN_SANDBOX=1 "$0" "$@"
    fi
}
