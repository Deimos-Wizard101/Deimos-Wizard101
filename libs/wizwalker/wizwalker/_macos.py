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
        cmd = cmd.strip()
        if not first.isdigit() or not cmd:
            continue
        # Key on argv[0]'s basename (like the Linux backend), not a substring of the
        # whole command line — otherwise a grep/editor/Deimos that merely mentions
        # the exe path would false-positive. Wine re-execs the client with the exe
        # name as argv[0] (the winetemp hard-link), so its basename matches.
        argv0 = cmd.split()[0]
        base = argv0.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if base.lower() == needle:
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


# ---- windows (CoreGraphics / Quartz) ----
# The memory/hook path is pid-based, so on macOS the "handle" IS the (Wine) pid.
# Window geometry/focus/input go through Quartz. The macOS NSWindow that Wine's Mac
# driver creates may be owned by a DIFFERENT macOS pid than the WizardGraphicalClient
# Wine pid (preloader/helper), so we resolve the game window by owner-pid first and
# fall back to a "Wizard101"-titled on-screen window, caching the resolution.
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


def _cg_window_list():
    import Quartz

    opts = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    return Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []


# pid (our Wine pid) -> the macOS owner pid of its game window, once resolved.
_WINDOW_OWNER_CACHE: dict = {}


def _find_game_window(win: int):
    """The CGWindowList entry for the game whose Wine pid is `win` (== handle).

    Matches the macOS window-owner pid first; else the largest on-screen window
    titled 'Wizard101'. Returns the window-info dict or None.
    """
    import Quartz  # noqa: F401

    try:
        wins = _cg_window_list()
    except Exception:
        return None

    owner = _WINDOW_OWNER_CACHE.get(win)
    want_pids = {owner} if owner else set()
    want_pids.add(win)

    best = None
    best_area = -1
    for w in wins:
        bounds = w.get("kCGWindowBounds")
        if not bounds:
            continue
        area = float(bounds.get("Width", 0)) * float(bounds.get("Height", 0))
        owner_pid = w.get("kCGWindowOwnerPID")
        name = w.get("kCGWindowName") or ""
        is_match = owner_pid in want_pids or ("Wizard101" in name and area > 10000)
        if is_match and area > best_area:
            best = w
            best_area = area
    if best is not None:
        _WINDOW_OWNER_CACHE[win] = best.get("kCGWindowOwnerPID")
    return best


def window_rect(win: int):
    """(X, Y, WIDTH, HEIGHT) of the game window in global screen coords, or None."""
    info = _find_game_window(win)
    if info is None:
        return None
    b = info.get("kCGWindowBounds")
    try:
        return (int(b["X"]), int(b["Y"]), int(b["Width"]), int(b["Height"]))
    except (KeyError, TypeError, ValueError):
        return None


def get_foreground_window() -> Optional[int]:
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return int(app.processIdentifier()) if app else None
    except Exception:
        return None


def set_foreground_window(win: int) -> bool:
    return focus_window(win)


def get_window_title(handle: int, max_size: int = 100) -> str:
    info = _find_game_window(handle)
    if info:
        name = info.get("kCGWindowName")
        if name:
            return str(name)
    return "Wizard101"


def set_window_title(handle: int, title: str):
    # Wine owns its NSWindow title; not settable from outside without Accessibility
    # scripting. No-op (title is cosmetic for our features).
    pass


# ---- input (Quartz CGEvent; real events to the game window) ----
# Win32 wizwalker clicks by writing the cursor into memory (mouseless hook) and
# posting WM_LBUTTONDOWN. On macOS there is no HWND; like the Linux XTEST path we
# drive the real pointer/keyboard through CoreGraphics so Wine's Mac driver turns
# the native event into the Win32 message the game processes. Needs Accessibility
# permission on the host (same as global hotkeys).
_VK_TO_KEYSYM: dict = {}  # unused on macOS; kept for API parity

_warned_input = False


def _warn_input_once(msg: str = None):
    global _warned_input
    if not _warned_input:
        _warned_input = True
        logger.warning(
            msg
            or (
                "macOS input via CGEvent failed (needs pyobjc-framework-Quartz and "
                "Accessibility permission for the launcher). Input features disabled."
            )
        )


def keysym_for_vk(vk: int):
    # On macOS we post hardware keycodes directly; expose the macOS keycode so
    # callers that gate on "is this key sendable" still work.
    from wizwalker._macos_hotkey import _build_vk_to_mac

    return _build_vk_to_mac().get(vk)


_post_access_checked = False


def _ensure_post_access():
    """Posting synthetic events on macOS needs Accessibility (post-event access).
    Preflight once and request it (registers the process in the TCC list + prompts);
    warn clearly if still denied."""
    global _post_access_checked
    if _post_access_checked:
        return
    _post_access_checked = True
    try:
        import Quartz

        if not bool(Quartz.CGPreflightPostEventAccess()):
            Quartz.CGRequestPostEventAccess()
            if not bool(Quartz.CGPreflightPostEventAccess()):
                _warn_input_once(
                    "macOS input sending needs ACCESSIBILITY permission. Enable the "
                    "launcher in System Settings > Privacy & Security > Accessibility, "
                    "then relaunch Deimos (re-grant after each launcher rebuild — "
                    "ad-hoc signing changes the binary identity). Memory features work "
                    "meanwhile."
                )
    except Exception:
        pass


def _post(event):
    import Quartz

    _ensure_post_access()
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


_event_source = None
_event_source_tried = False


def _source():
    """One cached CGEventSource. Events created with a NULL source carry no HID/
    keyboard metadata and Wine's winemac.drv drops them (proven: keys only moved the
    character once a real HIDSystemState source was passed). Mouse events worked with
    None too, but we use the same source for consistency."""
    global _event_source, _event_source_tried
    if not _event_source_tried:
        _event_source_tried = True
        try:
            import Quartz

            _event_source = Quartz.CGEventSourceCreate(
                Quartz.kCGEventSourceStateHIDSystemState
            )
        except Exception:
            _event_source = None
    return _event_source


def _focus_with_settle(win: int):
    """Focus the game only if it isn't already frontmost; give it a brief moment to
    become the key window so the first key event isn't dropped."""
    try:
        from AppKit import NSWorkspace

        info = _find_game_window(win)
        owner = info.get("kCGWindowOwnerPID") if info else _WINDOW_OWNER_CACHE.get(win, win)
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is not None and int(front.processIdentifier()) == int(owner):
            return  # already focused; no activate, no settle
    except Exception:
        pass
    if focus_window(win):
        import time

        time.sleep(0.2)


def focus_window(win: int) -> bool:
    """Bring the game app to the foreground so it receives pointer/key events.
    Returns True if the activation call was issued."""
    info = _find_game_window(win)
    owner = info.get("kCGWindowOwnerPID") if info else _WINDOW_OWNER_CACHE.get(win, win)
    try:
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps

        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(owner))
        if app is not None:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True
    except Exception as e:
        _warn_input_once(f"macOS focus_window failed: {e}")
    return False


def send_keydown_to_window(win: int, vk: int):
    """Press (and hold) a key. Focuses the game first so it receives the event."""
    mac_kc = keysym_for_vk(vk)
    if mac_kc is None:
        return
    try:
        import Quartz

        _focus_with_settle(win)
        _post(Quartz.CGEventCreateKeyboardEvent(_source(), int(mac_kc), True))
    except Exception as e:
        _warn_input_once(f"macOS keydown failed: {e}")


def send_keyup_to_window(win: int, vk: int):
    """Release a key previously pressed with ``send_keydown_to_window``."""
    mac_kc = keysym_for_vk(vk)
    if mac_kc is None:
        return
    try:
        import Quartz

        _post(Quartz.CGEventCreateKeyboardEvent(_source(), int(mac_kc), False))
    except Exception as e:
        _warn_input_once(f"macOS keyup failed: {e}")


def send_key_to_window(win: int, vk: int):
    """Tap a key (down then up)."""
    send_keydown_to_window(win, vk)
    send_keyup_to_window(win, vk)


def move_mouse_to_window(win: int, x: int, y: int):
    """Move the pointer to (x, y) relative to the window's top-left (client area)."""
    rect = window_rect(win)
    if rect is None:
        return
    move_mouse_abs(rect[0] + int(x), rect[1] + int(y))


def move_mouse_abs(x: int, y: int):
    """Move the pointer to absolute global screen (x, y)."""
    try:
        import Quartz

        pt = Quartz.CGPointMake(float(x), float(y))
        Quartz.CGWarpMouseCursorPosition(pt)
        ev = Quartz.CGEventCreateMouseEvent(
            _source(), Quartz.kCGEventMouseMoved, pt, Quartz.kCGMouseButtonLeft
        )
        _post(ev)
    except Exception as e:
        _warn_input_once(f"macOS move_mouse failed: {e}")


def mouse_button(button: int, down: bool):
    """Press/release a mouse button at the current pointer position. 1=left,
    2=middle, 3=right (xdotool numbering, for cross-platform callers)."""
    try:
        import Quartz
        from Quartz import CGEventGetLocation, CGEventCreate

        pos = CGEventGetLocation(CGEventCreate(None))
        if button == 3:
            etype = Quartz.kCGEventRightMouseDown if down else Quartz.kCGEventRightMouseUp
            cg_btn = Quartz.kCGMouseButtonRight
        elif button == 2:
            etype = Quartz.kCGEventOtherMouseDown if down else Quartz.kCGEventOtherMouseUp
            cg_btn = Quartz.kCGMouseButtonCenter
        else:
            etype = Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp
            cg_btn = Quartz.kCGMouseButtonLeft
        ev = Quartz.CGEventCreateMouseEvent(_source(), etype, pos, cg_btn)
        _post(ev)
    except Exception as e:
        _warn_input_once(f"macOS mouse_button failed: {e}")


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
