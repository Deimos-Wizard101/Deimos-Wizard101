"""Linux window control and input injection for Proton-hosted game clients.

The Windows build drives each client by HWND: window geometry via GetWindowRect,
input via PostMessage/SendMessage to that specific window. Under Proton the
clients are XWayland windows, so the same per-window model is reachable through
X11 (xdotool): find the window by pid, read/activate its geometry, and inject
keys with XTEST while it holds focus.

Verified on Hyprland (wlroots + XWayland): window lookup, geometry, activate,
and key injection all land on the specific client window.

Limitation vs. Windows: X11 input is delivered to the *focused* window, so
driving several clients at once serialises (focus each in turn) rather than
posting to each unfocused window as SendMessage does. A future per-window path
would write the game's input state through memory (zhol) instead.
"""
import subprocess
from typing import Optional


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout.strip()


def windows_for_pid(pid: int) -> list[int]:
    """X11 window ids owned by `pid` that are real top-levels (named, sized)."""
    out = _run(["xdotool", "search", "--pid", str(pid)])
    wins = []
    for line in out.splitlines():
        if not line.strip().isdigit():
            continue
        win = int(line)
        name = _run(["xdotool", "getwindowname", str(win)])
        geo = window_geometry(win)
        # Skip IME/helper windows (unnamed or 1x1).
        if name and geo and geo[2] > 1 and geo[3] > 1:
            wins.append(win)
    return wins


def main_window_for_pid(pid: int) -> Optional[int]:
    """The largest real window of `pid` — the game view."""
    wins = windows_for_pid(pid)
    if not wins:
        return None
    return max(wins, key=lambda w: (lambda g: g[2] * g[3] if g else 0)(window_geometry(w)))


def window_geometry(win: int) -> Optional[tuple[int, int, int, int]]:
    """(x, y, w, h) of a window, or None."""
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


def pid_for_window(win: int) -> Optional[int]:
    out = _run(["xdotool", "getwindowpid", str(win)])
    return int(out) if out.isdigit() else None


def activate(win: int) -> None:
    """Raise and focus a window."""
    subprocess.run(["xdotool", "windowactivate", str(win)], check=False)


def send_key(win: int, key: str) -> None:
    """Inject a key (xdotool keysym, e.g. 'Escape', 'w', 'F1') to `win`.

    The window is focused first; the key is delivered via XTEST to the focused
    window (synthetic XSendEvent is ignored by the game).
    """
    activate(win)
    subprocess.run(["xdotool", "key", "--clearmodifiers", key], check=False)


def type_text(win: int, text: str) -> None:
    activate(win)
    subprocess.run(["xdotool", "type", "--clearmodifiers", text], check=False)
