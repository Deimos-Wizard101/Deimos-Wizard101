"""Linux implementations of wizwalker's OS-boundary helpers.

On Linux wizwalker runs natively against a Proton-hosted client. A "window
handle" here is an X11 window id (the clients are XWayland windows); a process
is reached by pid through ``/proc`` (see the zhol-backed ``pymem`` shim). Window
geometry, focus, and key input go through ``xdotool``.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional

WIZARD_EXE = "WizardGraphicalClient.exe"


# xdotool talks to the X server, which can briefly stall (compositor hiccup,
# workspace switch under XWayland). These calls run synchronously inside the
# backend's asyncio loop, so a call that never returns freezes the whole backend
# (hooks stop, the app won't close) even though the Qt GUI thread stays alive.
# A timeout turns any such stall into a recoverable no-op instead of a hang.
_XDOTOOL_TIMEOUT = 5


def _run(args) -> str:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=False, timeout=_XDOTOOL_TIMEOUT
        ).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _run_nowait(args):
    """Fire-and-forget xdotool call that can't block the caller forever."""
    try:
        subprocess.run(args, check=False, timeout=_XDOTOOL_TIMEOUT)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# ---- process / instance ----
def get_wizard_pids() -> list:
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                argv0 = f.read().split(b"\x00", 1)[0]
        except OSError:
            continue
        base = argv0.rsplit(b"/", 1)[-1].rsplit(b"\\", 1)[-1]
        if base.lower() == WIZARD_EXE.lower().encode():
            pids.append(int(entry))
    return pids


def pid_alive(pid: int) -> bool:
    return os.path.isdir(f"/proc/{pid}")


def check_if_process_running(handle) -> bool:
    """`handle` is the pymem ``process_handle`` (a zhol.Process) or a pid/window."""
    pid = getattr(handle, "pid", None)
    if pid is None and isinstance(handle, int):
        pid = pid_for_window(handle) or handle
    return pid_alive(pid) if pid is not None else False


# ---- windows (xdotool) ----
def windows_for_pid(pid: int) -> list:
    out = _run(["xdotool", "search", "--pid", str(pid)])
    wins = []
    for line in out.splitlines():
        if not line.strip().isdigit():
            continue
        win = int(line)
        geo = window_rect(win)
        name = _run(["xdotool", "getwindowname", str(win)])
        if name and geo and geo[2] > 1 and geo[3] > 1:
            wins.append(win)
    return wins


def main_window_for_pid(pid: int) -> Optional[int]:
    wins = windows_for_pid(pid)
    if not wins:
        return None
    return max(wins, key=lambda w: (lambda g: g[2] * g[3] if g else 0)(window_rect(w)))


def get_all_wizard_handles() -> list:
    handles = []
    for pid in get_wizard_pids():
        win = main_window_for_pid(pid)
        if win is not None:
            handles.append(win)
    return handles


def pid_for_window(win: int) -> Optional[int]:
    out = _run(["xdotool", "getwindowpid", str(win)])
    return int(out) if out.isdigit() else None


def get_pid_from_handle(handle: int) -> int:
    return pid_for_window(handle) or 0


def window_rect(win: int):
    out = _run(["xdotool", "getwindowgeometry", "--shell", str(win)])
    vals = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k] = v
    try:
        return (int(vals["X"]), int(vals["Y"]), int(vals["WIDTH"]), int(vals["HEIGHT"]))
    except (KeyError, ValueError):
        return None


def get_foreground_window() -> Optional[int]:
    out = _run(["xdotool", "getactivewindow"])
    return int(out) if out.isdigit() else None


def set_foreground_window(win: int) -> bool:
    _run_nowait(["xdotool", "windowactivate", str(win)])
    return True


def get_window_title(handle: int, max_size: int = 100) -> str:
    return _run(["xdotool", "getwindowname", str(handle)])


def set_window_title(handle: int, title: str):
    _run_nowait(["xdotool", "set_window", "--name", title, str(handle)])


# ---- input (xdotool; delivered to the focused window via XTEST) ----
# Windows virtual-key code -> xdotool keysym for the keys wizwalker sends.
_VK_TO_KEYSYM = {
    8: "BackSpace", 9: "Tab", 13: "Return", 27: "Escape", 32: "space",
    37: "Left", 38: "Up", 39: "Right", 40: "Down", 46: "Delete",
    **{i: chr(i) for i in range(48, 58)},          # 0-9
    **{i: chr(i).lower() for i in range(65, 91)},  # A-Z -> a-z
    **{111 + i: f"F{i}" for i in range(1, 13)},     # F1..F12 (112..123)
}


def keysym_for_vk(vk: int) -> Optional[str]:
    return _VK_TO_KEYSYM.get(vk)


def send_key_to_window(win: int, vk: int):
    keysym = keysym_for_vk(vk)
    if keysym is None:
        return
    _run_nowait(["xdotool", "windowactivate", str(win)])
    _run_nowait(["xdotool", "key", "--clearmodifiers", keysym])


# ---- mouse (xdotool; real pointer events to the XWayland game window) ----
# Win32 wizwalker clicks by writing the cursor into memory (mouseless hook) and
# sending WM_LBUTTONDOWN to the HWND. On Linux there's no HWND and no way to post
# a Win32 message in, so instead drive the real pointer over the game's X11 window
# and send a genuine button event the window actually processes.
def move_mouse_to_window(win: int, x: int, y: int):
    """Move the pointer to (x, y) relative to the window's top-left (client area)."""
    # `--` so negative coords (used to park the cursor off-client) aren't parsed
    # as options.
    _run_nowait(
        ["xdotool", "mousemove", "--window", str(win), "--", str(int(x)), str(int(y))]
    )


def move_mouse_abs(x: int, y: int):
    """Move the pointer to absolute screen (x, y)."""
    _run_nowait(["xdotool", "mousemove", "--", str(int(x)), str(int(y))])


def focus_window(win: int):
    """Bring a window to the foreground so it receives pointer events."""
    _run_nowait(["xdotool", "windowactivate", str(win)])


def mouse_button(button: int, down: bool):
    """Press (down=True) or release a mouse button: 1=left, 3=right."""
    _run_nowait(
        ["xdotool", "mousedown" if down else "mouseup", str(int(button))]
    )


# ---- install path ----
def get_wiz_install(override: Optional[str]) -> Path:
    if override:
        return Path(override).absolute()
    env = os.environ.get("WIZLAUNCH_GAME_PATH")
    if env:
        return Path(env).absolute()
    steam = Path.home() / ".local/share/Steam/steamapps/common/Wizard101"
    if steam.exists():
        return steam
    raise Exception("Wizard101 install not found (set WIZLAUNCH_GAME_PATH)")
