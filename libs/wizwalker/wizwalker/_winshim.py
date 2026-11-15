"""Linux stand-ins for the Win32 DLL objects wizwalker pulls from ``constants``.

wizwalker reaches the OS through ``ctypes.windll.{user32,kernel32,gdi32,ntdll}``.
On Linux those do not exist, so ``constants`` imports these objects instead.
Only the calls wizwalker actually makes are implemented; the memory path needs
very little (page-protection changes are inert because ``/proc`` writes ignore
protection), and window/input calls are routed to :mod:`src.linux_backend`.

Anything not yet implemented raises a clear error naming the symbol, so gaps
surface loudly rather than silently no-op.
"""


class _Stub:
    def __init__(self, name, impls):
        self._name = name
        self._impls = impls

    def __getattr__(self, item):
        impl = self._impls.get(item)
        if impl is not None:
            return impl
        raise NotImplementedError(
            f"{self._name}.{item} is not implemented on Linux (wizwalker Win32 shim)"
        )


# --- kernel32: page protection is a no-op; writes via /proc ignore it. ---
def _virtual_protect_ex(handle, address, size, new_protect, old_protect_ptr=None):
    # Report success and a benign previous protection.
    try:
        if old_protect_ptr is not None:
            old_protect_ptr._obj.value = 0  # byref(DWORD) -> set .value
    except Exception:
        pass
    return 1


def _get_exit_code_process(handle, exit_code_ptr):
    # Treat as still-running (STILL_ACTIVE = 259). Liveness is checked via /proc
    # by check_if_process_running, which is the authority.
    try:
        exit_code_ptr._obj.value = 259
    except Exception:
        pass
    return 1


def _get_system_directory_w(buffer, size):
    s = "C:\\windows\\system32"
    try:
        buffer.value = s
    except Exception:
        pass
    return len(s)


kernel32 = _Stub(
    "kernel32",
    {
        "VirtualProtectEx": _virtual_protect_ex,
        "GetExitCodeProcess": _get_exit_code_process,
        "GetSystemDirectoryW": _get_system_directory_w,
    },
)

# Global hotkeys are a Win32 message-loop feature (RegisterHotKey + PeekMessage).
# Stubbed as a successful no-op on Linux: the Deimos GUI still works, but global
# hotkeys do not fire. A real Linux path (X11 XGrabKey / evdev) is a follow-up.
def _register_hotkey(hwnd, hotkey_id, modifiers, vk):
    return 1


def _unregister_hotkey(hwnd, hotkey_id):
    return 1


def _peek_message(msg_ptr, hwnd, msg_min, msg_max, remove):
    return 0  # no messages → the listener loop idles


def _noop(*args, **kwargs):
    return 0


# GetClientRect fills a RECT with the window's client area (0, 0, width, height).
# hwnd is the X11 window id on Linux; query its size via xdotool, cached briefly
# so the per-frame world-to-screen projection doesn't spawn a process every frame
# (that flood was freezing the GUI).
import time as _time

_client_rect_cache = {}


def _get_client_rect(hwnd, rect_ptr):
    key = int(hwnd) if hwnd else 0
    now = _time.monotonic()
    hit = _client_rect_cache.get(key)
    if hit and now - hit[0] < 0.5:
        w, h = hit[1], hit[2]
    else:
        w = h = 0
        try:
            import subprocess
            out = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", str(key)],
                capture_output=True, text=True, timeout=2,
            ).stdout
            g = {k: int(v) for k, v in (ln.split("=", 1) for ln in out.splitlines() if "=" in ln)}
            w, h = g.get("WIDTH", 0), g.get("HEIGHT", 0)
        except Exception:
            pass
        _client_rect_cache[key] = (now, w, h)
    try:
        r = rect_ptr._obj  # byref(RECT) -> the RECT
        r.left = 0
        r.top = 0
        r.right = w
        r.bottom = h
    except Exception:
        pass
    return 1


# user32/gdi32/ntdll: window, input, and drawing. Window/input proper is handled
# by wizwalker._linux via xdotool; these cover the remaining direct calls.
user32 = _Stub(
    "user32",
    {
        "RegisterHotKey": _register_hotkey,
        "UnregisterHotKey": _unregister_hotkey,
        "PeekMessageW": _peek_message,
        "DispatchMessageW": _noop,
        "TranslateMessage": _noop,
        "GetClientRect": _get_client_rect,
    },
)
gdi32 = _Stub("gdi32", {})
ntdll = _Stub("ntdll", {})
