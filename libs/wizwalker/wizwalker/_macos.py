"""macOS implementations of wizwalker's OS-boundary helpers.

On macOS the Wizard101 client runs as a Windows PE under Wine/CrossOver (x86-64
via Rosetta 2) and is reached by pid through the Mach VM backend (see the
zhol-backed ``pymem`` shim). There is no ``/proc`` and no ``xdotool``.

Process discovery uses ``ps``. The memory/hook path is pid-based, so a "window
handle" is modeled here as the **pid** — which is all the hook/read/RPC path (and
memory-only features such as freecam) needs. Real window geometry/focus
(CoreGraphics ``CGWindowList``) and pointer/key input (``CGEvent``) are a later
sub-stage; until then those helpers are safe no-ops so memory features work and
input-driven ones degrade gracefully rather than crash.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional

try:
    from loguru import logger
except Exception:  # pragma: no cover - logging is optional here
    class _Noop:
        def warning(self, *a, **k):
            pass

    logger = _Noop()

WIZARD_EXE = "WizardGraphicalClient.exe"
_PS_TIMEOUT = 5


# ---- process / instance ----
def get_wizard_pids() -> list:
    """Pids of running Wizard101 clients, via ``ps`` (no ``/proc`` on macOS)."""
    try:
        out = subprocess.run(
            ["ps", "-axww", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PS_TIMEOUT,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    needle = WIZARD_EXE.lower()
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        first, _, cmd = line.partition(" ")
        if first.isdigit() and needle in cmd.lower():
            pids.append(int(first))
    return pids


def pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours to signal
    except OSError:
        return False


def check_if_process_running(handle) -> bool:
    """`handle` is the pymem ``process_handle`` (a zhol.Process) or a pid."""
    pid = getattr(handle, "pid", None)
    if pid is None and isinstance(handle, int):
        pid = handle
    return pid_alive(pid) if pid is not None else False


# ---- windows ----
# The memory/hook path is pid-based, so on macOS the "handle" IS the pid. Real
# window geometry/focus is a later CoreGraphics sub-stage; these keep callers
# working for memory-only features.
def windows_for_pid(pid: int) -> list:
    return [pid] if pid_alive(pid) else []


def main_window_for_pid(pid: int) -> Optional[int]:
    return pid if pid_alive(pid) else None


def get_all_wizard_handles() -> list:
    return get_wizard_pids()


def pid_for_window(win: int) -> Optional[int]:
    return win


def get_pid_from_handle(handle: int) -> int:
    return handle or 0


def window_rect(win: int):
    # Window geometry not implemented yet on macOS (CoreGraphics sub-stage).
    return None


def get_foreground_window() -> Optional[int]:
    return None


def set_foreground_window(win: int) -> bool:
    return False


def get_window_title(handle: int, max_size: int = 100) -> str:
    return "Wizard101"


def set_window_title(handle: int, title: str):
    pass


# ---- input (CGEvent sub-stage; no-op for now) ----
_VK_TO_KEYSYM: dict = {}  # unused on macOS; kept for API parity

_warned_input = False


def _warn_input_once():
    global _warned_input
    if not _warned_input:
        _warned_input = True
        logger.warning(
            "macOS pointer/key input is not implemented yet; input-driven "
            "features (clicking, key sends) are no-ops. Memory features work."
        )


def keysym_for_vk(vk: int):
    return None


def send_key_to_window(win: int, vk: int):
    _warn_input_once()


def move_mouse_to_window(win: int, x: int, y: int):
    _warn_input_once()


def move_mouse_abs(x: int, y: int):
    _warn_input_once()


def focus_window(win: int):
    # No-op: bringing the game forward isn't needed for memory features.
    pass


def mouse_button(button: int, down: bool):
    _warn_input_once()


# ---- install path ----
def get_wiz_install(override: Optional[str]) -> Path:
    if override:
        return Path(override).absolute()
    env = os.environ.get("WIZLAUNCH_GAME_PATH")
    if env:
        return Path(env).absolute()
    candidates = [
        Path.home()
        / "Library/Application Support/Wizard101/Bottles/wizard101/drive_c"
        / "ProgramData/KingsIsle Entertainment/Wizard101",
        Path("/Applications/Wizard101"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise Exception("Wizard101 install not found (set WIZLAUNCH_GAME_PATH)")
