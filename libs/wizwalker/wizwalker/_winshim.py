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

# user32/gdi32/ntdll: window, input, and drawing. Implemented lazily as the
# Linux window/input layer is wired in; until then these raise if touched.
user32 = _Stub("user32", {})
gdi32 = _Stub("gdi32", {})
ntdll = _Stub("ntdll", {})
