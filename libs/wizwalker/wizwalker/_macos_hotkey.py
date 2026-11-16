"""macOS global-hotkey listener backed by a Quartz ``CGEventTap``.

API-compatible with the Win32 ``HotkeyListener`` and the Linux evdev listener.
Needs the host process to be granted **Accessibility** (or Input Monitoring)
permission in System Settings > Privacy & Security; without it the OS refuses to
create the tap and we fall back to a warning (GUI buttons still work). Requires
``pyobjc-framework-Quartz`` (``pip install pyobjc-framework-Quartz``).

The event tap runs its own CFRunLoop on a dedicated daemon thread (CFRunLoopRun
blocks); the tap callback maps the macOS key code to a Win32 VK + the modifier
flags and dispatches the registered coroutine onto the asyncio loop captured at
``start`` via ``call_soon_threadsafe`` — exactly the (vk, modifiers) -> callback
semantics the other backends use.
"""
import asyncio
import threading
from contextlib import suppress
from typing import Callable

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Noop:
        def warning(self, *a, **k):
            pass

    logger = _Noop()

from wizwalker.constants import Keycode
from wizwalker.hotkey import ModifierKeys


_VK_TO_MAC = None
_MAC_TO_VK = None


def _build_vk_to_mac():
    """Win32 virtual-key code (what :class:`Keycode` holds) -> macOS virtual key
    code (Carbon ``kVK_*``). Mirrors the Linux VK->evdev table."""
    m = {}
    letters = {
        "A": 0, "B": 11, "C": 8, "D": 2, "E": 14, "F": 3, "G": 5, "H": 4,
        "I": 34, "J": 38, "K": 40, "L": 37, "M": 46, "N": 45, "O": 31, "P": 35,
        "Q": 12, "R": 15, "S": 1, "T": 17, "U": 32, "V": 9, "W": 13, "X": 7,
        "Y": 16, "Z": 6,
    }
    for ch, kc in letters.items():
        m[ord(ch)] = kc
    digits = {"0": 29, "1": 18, "2": 19, "3": 20, "4": 21,
              "5": 23, "6": 22, "7": 26, "8": 28, "9": 25}
    for ch, kc in digits.items():
        m[ord(ch)] = kc
    # F1..F20 (VK_F1 == 112)
    fkeys = [122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111,
             105, 107, 113, 106, 64, 79, 80, 90]
    for i, kc in enumerate(fkeys):
        m[112 + i] = kc
    # numpad 0..9 (VK_NUMPAD0 == 96)
    numpad = [82, 83, 84, 85, 86, 87, 88, 89, 91, 92]
    for i, kc in enumerate(numpad):
        m[96 + i] = kc
    explicit = {
        8: 51,    # backspace -> Delete
        9: 48,    # tab
        13: 36,   # enter -> Return
        27: 53,   # escape
        32: 49,   # space
        33: 116,  # page up
        34: 121,  # page down
        35: 119,  # end
        36: 115,  # home
        37: 123,  # left
        38: 126,  # up
        39: 124,  # right
        40: 125,  # down
        45: 114,  # insert -> Help
        46: 117,  # delete -> ForwardDelete
        106: 67,  # numpad *
        107: 69,  # numpad +
        109: 78,  # numpad -
        110: 65,  # numpad .
        111: 75,  # numpad /
        # modifiers: generic + sided -> macOS left/right keycodes
        16: 56, 160: 56, 161: 60,   # shift
        17: 59, 162: 59, 163: 62,   # control
        18: 58, 164: 58, 165: 61,   # alt / option
    }
    m.update(explicit)
    return m


def _build_mac_to_vk():
    global _VK_TO_MAC
    if _VK_TO_MAC is None:
        _VK_TO_MAC = _build_vk_to_mac()
    mac_to_vk = {}
    for vk, kc in _VK_TO_MAC.items():
        mac_to_vk.setdefault(kc, vk)  # first VK wins (canonical)
    return mac_to_vk


class _MacHotkeyListener:
    """CGEventTap-backed hotkey listener matching the Win32/Linux surface."""

    def __init__(self, *, sleep_time: float = 0.1):
        self.sleep_time = sleep_time  # accepted for parity; the tap is event-driven

        self._callbacks = {}  # (vk, modifiers_without_norepeat) -> callback
        self._hotkeys = {}    # (vk, modifiers) -> True (registration registry)
        self._callback_tasks = []

        self._running = False
        self._loop = None
        self._thread = None
        self._tap = None
        self._runloop = None
        self._warned_perm = False

    @property
    def is_running(self) -> bool:
        return self._running

    # ---- lifecycle ----
    def start(self):
        if self._running:
            raise ValueError("This listener has already been started")
        _build_mac_to_vk()  # warm the maps
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.get_event_loop()
        self._running = True
        self._thread = threading.Thread(target=self._run_tap, name="mac-hotkeys", daemon=True)
        self._thread.start()

    def _run_tap(self):
        try:
            import Quartz
        except Exception:
            logger.warning(
                "Global hotkeys need pyobjc (pip install pyobjc-framework-Quartz); "
                "disabled. GUI buttons still work."
            )
            self._running = False
            return

        # Keyboard LISTENING on macOS is gated by Input Monitoring (kTCCServiceListenEvent),
        # NOT Accessibility. CGEventTapCreate SUCCEEDS without it but then silently
        # delivers no key events — so a "tap is None" check never fires. Preflight the
        # permission, request it (registers this process in the TCC list and prompts),
        # and warn based on the preflight result.
        try:
            granted = bool(Quartz.CGPreflightListenEventAccess())
            if not granted:
                Quartz.CGRequestListenEventAccess()  # prompt / register
                granted = bool(Quartz.CGPreflightListenEventAccess())
        except Exception:
            granted = True  # older pyobjc without these APIs; assume usable
        if not granted and not self._warned_perm:
            self._warned_perm = True
            logger.warning(
                "Global hotkeys need INPUT MONITORING permission. Enable it for the "
                "launcher in System Settings > Privacy & Security > Input Monitoring "
                "(and Accessibility, for input sending), then relaunch Deimos. NOTE: "
                "re-grant after each launcher rebuild — ad-hoc signing changes the "
                "binary's identity and macOS silently drops the grant. GUI keys still "
                "work meanwhile."
            )

        mac_to_vk = _build_mac_to_vk()
        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
        )

        def _callback(proxy, type_, event, refcon):
            try:
                # Re-enable if the OS disabled the tap (slow callback / user input).
                if type_ in (
                    Quartz.kCGEventTapDisabledByTimeout,
                    Quartz.kCGEventTapDisabledByUserInput,
                ):
                    if self._tap is not None:
                        Quartz.CGEventTapEnable(self._tap, True)
                    return event
                if type_ != Quartz.kCGEventKeyDown:
                    return event
                # skip auto-repeat so a held key fires once (NOREPEAT semantics)
                if Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventAutorepeat
                ):
                    return event
                keycode = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode
                )
                vk = mac_to_vk.get(int(keycode))
                if vk is None:
                    return event
                flags = Quartz.CGEventGetFlags(event)
                mods = 0
                # Accept EITHER physical Control OR Command as CTRL: Qt on macOS
                # reports Command as Qt::ControlModifier, so the GUI's rebind capture
                # records Command as "CTRL" — honoring both keys here means a Ctrl
                # binding fires whichever the user reaches for.
                if flags & (
                    Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskCommand
                ):
                    mods |= int(ModifierKeys.CTRL)
                if flags & Quartz.kCGEventFlagMaskShift:
                    mods |= int(ModifierKeys.SHIFT)
                if flags & Quartz.kCGEventFlagMaskAlternate:
                    mods |= int(ModifierKeys.ALT)
                cb = self._callbacks.get((vk, mods))
                if cb is not None and self._loop is not None:
                    self._loop.call_soon_threadsafe(self._dispatch, cb)
            except Exception:  # never let a callback error kill the tap
                pass
            return event

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            _callback,
            None,
        )
        if not tap:
            if not self._warned_perm:
                self._warned_perm = True
                logger.warning(
                    "Global hotkeys: the OS refused the event tap. Grant this app "
                    "Accessibility permission in System Settings > Privacy & Security "
                    "> Accessibility (and relaunch). GUI buttons work meanwhile."
                )
            self._running = False
            return

        self._tap = tap
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._runloop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._runloop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        Quartz.CFRunLoopRun()  # blocks on this thread until CFRunLoopStop

    def _dispatch(self, cb):
        # runs on the asyncio loop thread
        task = asyncio.ensure_future(cb())
        self._callback_tasks.append(task)
        task.add_done_callback(
            lambda t: self._callback_tasks.remove(t) if t in self._callback_tasks else None
        )

    async def stop(self):
        self._running = False
        if self._tap is not None:
            with suppress(Exception):
                import Quartz

                Quartz.CGEventTapEnable(self._tap, False)
        if self._runloop is not None:
            with suppress(Exception):
                import Quartz

                Quartz.CFRunLoopStop(self._runloop)
        self._tap = None
        self._runloop = None
        for t in self._callback_tasks:
            t.cancel()
        self._callback_tasks = []

    # ---- registration (software-side; no OS call) ----
    async def add_hotkey(
        self, key: Keycode, callback: Callable, *, modifiers: ModifierKeys = 0
    ):
        mac_to_vk = _build_mac_to_vk()
        if key.value not in mac_to_vk.values():
            logger.warning(f"Hotkey key {key} has no macOS mapping; ignored")
            return
        no_norepeat = int(modifiers) & ~int(ModifierKeys.NOREPEAT)
        ckey = (key.value, no_norepeat)
        if ckey in self._callbacks:
            raise ValueError(f"{key} with modifers {modifiers} already registered")
        self._callbacks[ckey] = callback
        self._hotkeys[(key.value, int(modifiers))] = True

    async def remove_hotkey(self, key: Keycode, *, modifiers: ModifierKeys = 0):
        if self._hotkeys.get((key.value, int(modifiers))) is None:
            raise ValueError(
                f"No hotkey registered for key {key} with modifiers {modifiers}"
            )
        del self._hotkeys[(key.value, int(modifiers))]
        self._callbacks.pop((key.value, int(modifiers) & ~int(ModifierKeys.NOREPEAT)), None)

    async def clear(self):
        self._callbacks = {}
        self._hotkeys = {}

    @staticmethod
    async def set_global_message_loop_delay(delay: float):
        # No shared Win32 message loop on macOS; nothing to tune.
        return None
