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


def _run(args) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()
    except FileNotFoundError:
        return ""


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
    subprocess.run(["xdotool", "windowactivate", str(win)], check=False)
    return True


def get_window_title(handle: int, max_size: int = 100) -> str:
    return _run(["xdotool", "getwindowname", str(handle)])


def set_window_title(handle: int, title: str):
    subprocess.run(["xdotool", "set_window", "--name", title, str(handle)], check=False)


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
    subprocess.run(["xdotool", "windowactivate", str(win)], check=False)
    subprocess.run(["xdotool", "key", "--clearmodifiers", keysym], check=False)


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
