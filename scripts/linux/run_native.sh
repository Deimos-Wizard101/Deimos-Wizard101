#!/usr/bin/env bash
# Run Deimos natively on Linux (no Wine), against a Proton-hosted client.
#
# Runs under a nix-shell that puts the Qt/numpy/shapely native libs on
# LD_LIBRARY_PATH, NOT under steam-run: steam-run's user-namespace sandbox
# blocks reading the game client's /proc/<pid>/mem (cross-process), which the
# memory hooks need. nix-shell sets the env without sandboxing, so /proc works.
#
# Needs: native extensions (zhol/kinif/wizlaunch) in $PYDIR, the Python 3.13
# venv in $DVENV with Deimos' deps, and the game client already running.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
HOME_DIR="${DEIMOS_LINUX_HOME:-$HOME/.local/share/Deimos-linux}"
PYDIR="$HOME_DIR/py"
DVENV="$HOME_DIR/dvenv"

# Global hotkeys read the keyboard through evdev (/dev/input), which needs the
# 'input' group. If this login session predates being added to that group (e.g.
# added via `nixos-rebuild switch` without logging back in) but /etc/group now
# lists us, re-exec once under the group with `sg` so hotkeys work without a full
# re-login. A real re-login makes this branch a no-op. Not a member at all: warn
# and continue (the GUI and hooking still work; only global hotkeys are affected).
if [ -z "${_DEIMOS_INPUT_REEXEC:-}" ] && ! id -nG | tr ' ' '\n' | grep -qx input; then
    _members="$(getent group input 2>/dev/null | cut -d: -f4 || true)"
    case ",${_members}," in
        *",$(id -un),"*)
            export _DEIMOS_INPUT_REEXEC=1
            exec sg input -c "$(printf '%q ' bash "$REPO/scripts/linux/run_native.sh" "$@")"
            ;;
        *)
            echo "note: not in the 'input' group; global hotkeys won't fire (GUI/hooking still work)." >&2
            echo "      NixOS: users.users.$(id -un).extraGroups = [ \"input\" ]; then re-login." >&2
            ;;
    esac
fi

export PYTHONPATH="$REPO/src/linux_backend:$PYDIR:$REPO/libs/wizwalker:$REPO/libs/wizsprinter"
export WIZLAUNCH_GAME_PATH="${WIZLAUNCH_GAME_PATH:-$HOME/.local/share/Steam/steamapps/common/Wizard101}"

# Run Qt under X11/XWayland. The highlight overlay must share the game's window
# coordinate space and be an override-redirect, click-through X11 window; a native
# Wayland surface can't be positioned over another window or made click-through
# portably. xcb is already the default on X11 desktops, so this only matters on
# Wayland compositors, where it routes the GUI through XWayland (same space as the
# Proton client). Override by exporting QT_QPA_PLATFORM yourself.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

# The vault credential store is unlocked with a passphrase. On Windows wizlaunch
# pops a native OS credential dialog; Linux has none, so a GUI with no terminal
# cannot gather it and account loading would fail. Read it here — in the terminal
# that launched us — and hand it to Deimos via the environment. Press Enter to
# skip: Deimos still runs and can hook already-running clients; only the vault
# (saved-account list and launch-from-vault) stays locked until a passphrase is
# given. Skipped automatically when WIZLAUNCH_STORE_PASSPHRASE is already set.
CRED_STORE="${XDG_CONFIG_HOME:-$HOME/.config}/Deimos/credentials.bin"
if [ -f "$CRED_STORE" ] && [ -z "${WIZLAUNCH_STORE_PASSPHRASE:-}" ] && [ -t 0 ]; then
    read -rsp "Deimos vault passphrase (Enter to skip): " WIZLAUNCH_STORE_PASSPHRASE || true
    echo
    [ -n "$WIZLAUNCH_STORE_PASSPHRASE" ] && export WIZLAUNCH_STORE_PASSPHRASE
fi

cd "$REPO"
exec nix-shell "$REPO/scripts/linux/deimos-shell.nix" --run "exec '$DVENV/bin/python3' Deimos.py $*"
