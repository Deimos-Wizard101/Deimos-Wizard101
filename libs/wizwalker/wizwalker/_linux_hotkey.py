"""Linux global-hotkey backend (evdev), API-compatible with the Win32
:class:`HotkeyListener`.

Wayland (Hyprland here) deliberately refuses an application the global key grab
that ``RegisterHotKey`` relies on, so the Win32 path cannot be ported. Instead
this reads key events straight from the kernel via ``/dev/input`` (evdev), which
sees presses globally regardless of the compositor, and matches them against the
registered hotkeys in software.

Only the surface :class:`HotkeyListener` exposes is implemented, with identical
signatures, so callers (Deimos) are unchanged: the platform select in
``hotkey.py`` swaps this in for the Win32 class, nothing else.

Requires read access to the keyboard ``/dev/input/event*`` nodes, i.e. the
invoking user in the ``input`` group (or an equivalent udev/logind ACL). With no
readable keyboard the listener still starts and runs; it just never fires, and
says why once.
"""
import asyncio
import sys
from contextlib import suppress
from typing import Callable

from loguru import logger

from wizwalker.constants import Keycode
from wizwalker.hotkey import ModifierKeys


def _build_vk_to_evdev():
    """Map Win32 virtual-key codes (what :class:`Keycode` holds) to evdev key
    codes. Built once; missing keys simply can't be bound on Linux."""
    from evdev import ecodes

    m = {}
    # letters A-Z and digits 0-9 share their ASCII char with the evdev name
    for c in range(ord("A"), ord("Z") + 1):
        m[c] = getattr(ecodes, f"KEY_{chr(c)}")
    for c in range(ord("0"), ord("9") + 1):
        m[c] = getattr(ecodes, f"KEY_{chr(c)}")
    # function keys F1-F24
    for i in range(1, 25):
        name = f"KEY_F{i}"
        if hasattr(ecodes, name):
            m[111 + i] = getattr(ecodes, name)  # VK_F1 == 112
    # numeric pad 0-9 (VK_NUMPAD0 == 96)
    for i in range(10):
        m[96 + i] = getattr(ecodes, f"KEY_KP{i}")

    explicit = {
        8: ecodes.KEY_BACKSPACE, 9: ecodes.KEY_TAB, 13: ecodes.KEY_ENTER,
        19: ecodes.KEY_PAUSE, 20: ecodes.KEY_CAPSLOCK, 27: ecodes.KEY_ESC,
        32: ecodes.KEY_SPACE, 33: ecodes.KEY_PAGEUP, 34: ecodes.KEY_PAGEDOWN,
        35: ecodes.KEY_END, 36: ecodes.KEY_HOME, 37: ecodes.KEY_LEFT,
        38: ecodes.KEY_UP, 39: ecodes.KEY_RIGHT, 40: ecodes.KEY_DOWN,
        44: ecodes.KEY_SYSRQ, 45: ecodes.KEY_INSERT, 46: ecodes.KEY_DELETE,
        # generic modifiers resolve to the left-hand key
        16: ecodes.KEY_LEFTSHIFT, 17: ecodes.KEY_LEFTCTRL, 18: ecodes.KEY_LEFTALT,
        91: ecodes.KEY_LEFTMETA, 92: ecodes.KEY_RIGHTMETA, 93: ecodes.KEY_COMPOSE,
        106: ecodes.KEY_KPASTERISK, 107: ecodes.KEY_KPPLUS,
        109: ecodes.KEY_KPMINUS, 110: ecodes.KEY_KPDOT, 111: ecodes.KEY_KPSLASH,
        144: ecodes.KEY_NUMLOCK, 145: ecodes.KEY_SCROLLLOCK,
        160: ecodes.KEY_LEFTSHIFT, 161: ecodes.KEY_RIGHTSHIFT,
        162: ecodes.KEY_LEFTCTRL, 163: ecodes.KEY_RIGHTCTRL,
        164: ecodes.KEY_LEFTALT, 165: ecodes.KEY_RIGHTALT,
    }
    m.update(explicit)
    return m


class _LinuxHotkeyListener:
    """evdev-backed, API-compatible with the Win32 ``HotkeyListener``."""

    def __init__(self, *, sleep_time: float = 0.1):
        self.sleep_time = sleep_time  # accepted for parity; evdev is event-driven

        # (vk, modifiers_without_norepeat) -> callback
        self._callbacks = {}
        # (vk, modifiers) -> True, the registration registry (parity with Win32)
        self._hotkeys = {}
        self._callback_tasks = []

        self._devices = []
        self._read_tasks = []
        self._mods_down = set()  # evdev codes of held modifier keys
        self._running = False

        self._vk_to_evdev = None
        self._evdev_to_vk = None
        self._mod_codes = None  # evdev code -> ModifierKeys bit

    @property
    def is_running(self) -> bool:
        return self._running

    def _ensure_maps(self):
        if self._vk_to_evdev is not None:
            return
        from evdev import ecodes

        self._vk_to_evdev = _build_vk_to_evdev()
        self._evdev_to_vk = {}
        for vk, code in self._vk_to_evdev.items():
            # first VK wins so a code maps back to its canonical key
            self._evdev_to_vk.setdefault(code, vk)
        self._mod_codes = {
            ecodes.KEY_LEFTCTRL: ModifierKeys.CTRL, ecodes.KEY_RIGHTCTRL: ModifierKeys.CTRL,
            ecodes.KEY_LEFTSHIFT: ModifierKeys.SHIFT, ecodes.KEY_RIGHTSHIFT: ModifierKeys.SHIFT,
            ecodes.KEY_LEFTALT: ModifierKeys.ALT, ecodes.KEY_RIGHTALT: ModifierKeys.ALT,
        }

    # ---- lifecycle ----
    def start(self):
        if self._running:
            raise ValueError("This listener has already been started")
        self._ensure_maps()
        self._running = True
        self._open_devices()
        for dev in self._devices:
            self._read_tasks.append(asyncio.create_task(self._read_loop(dev)))

    async def stop(self):
        self._running = False
        for t in self._read_tasks:
            t.cancel()
        self._read_tasks = []
        for dev in self._devices:
            with suppress(Exception):
                dev.close()
        self._devices = []
        for t in self._callback_tasks:
            t.cancel()
        self._callback_tasks = []
        self._mods_down.clear()

    # ---- registration (software-side; no OS call) ----
    async def add_hotkey(
        self, key: Keycode, callback: Callable, *, modifiers: ModifierKeys = 0
    ):
        self._ensure_maps()
        if key.value not in self._vk_to_evdev:
            logger.warning(f"Hotkey key {key} has no evdev mapping on Linux; ignored")
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
        # No shared Win32 message loop on Linux; nothing to tune.
        return None

    # ---- evdev plumbing ----
    def _open_devices(self):
        import evdev
        from evdev import ecodes

        opened = 0
        denied = 0
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
            except PermissionError:
                denied += 1
                continue
            except Exception:
                continue
            keys = dev.capabilities().get(ecodes.EV_KEY, [])
            # a real keyboard reports the letter keys
            if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                self._devices.append(dev)
                opened += 1
            else:
                with suppress(Exception):
                    dev.close()
        if opened == 0:
            if denied:
                logger.warning(
                    "Global hotkeys: no readable keyboard devices "
                    f"({denied} denied by permissions). Add your user to the 'input' "
                    "group (NixOS: users.users.<you>.extraGroups = [ \"input\" ]), then "
                    "rebuild and re-login. GUI buttons still work meanwhile."
                )
            else:
                logger.warning("Global hotkeys: no keyboard /dev/input devices found")

    async def _read_loop(self, dev):
        from evdev import ecodes

        try:
            async for event in dev.async_read_loop():
                if event.type != ecodes.EV_KEY:
                    continue
                code, value = event.code, event.value
                mod_bit = self._mod_codes.get(code)
                if mod_bit is not None:
                    if value == 0:
                        self._mods_down.discard(code)
                    else:
                        self._mods_down.add(code)
                    continue
                # fire on key-down only (matches NOREPEAT; avoids auto-repeat spam)
                if value != 1:
                    continue
                vk = self._evdev_to_vk.get(code)
                if vk is None:
                    continue
                mods = 0
                for c in self._mods_down:
                    mods |= int(self._mod_codes[c])
                callback = self._callbacks.get((vk, mods))
                if callback is not None:
                    self._callback_tasks.append(asyncio.create_task(callback()))
        except asyncio.CancelledError:
            raise
        except OSError:
            # device went away (unplugged / VT switch); drop it quietly
            with suppress(Exception):
                dev.close()
