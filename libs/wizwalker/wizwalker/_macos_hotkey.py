"""macOS global-hotkey listener — no-op stub (Stage A).

Global hotkeys on macOS need a CGEventTap (and Accessibility/Input-Monitoring
permission), which is a later sub-stage. Until then this mirrors the
``_LinuxHotkeyListener`` interface as no-ops so the app runs; hotkey-driven
features should be triggered from the GUI instead. Memory features are unaffected.
"""
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


class _MacHotkeyListener:
    """No-op hotkey listener matching the Linux listener's surface."""

    def __init__(self, *, sleep_time: float = 0.1):
        self._sleep_time = sleep_time
        self._running = False
        self._warned = False

    def _warn_once(self):
        if not self._warned:
            self._warned = True
            logger.warning(
                "Global hotkeys are not implemented on macOS yet (CGEventTap "
                "sub-stage); trigger these actions from the GUI instead."
            )

    def is_running(self) -> bool:
        return self._running

    def start(self):
        self._running = True
        self._warn_once()

    async def stop(self):
        self._running = False

    async def add_hotkey(
        self,
        key: Keycode,
        callback: Callable,
        *,
        modifiers: ModifierKeys = 0,
    ):
        self._warn_once()

    async def remove_hotkey(self, key: Keycode, *, modifiers: ModifierKeys = 0):
        pass

    async def clear(self):
        pass

    @staticmethod
    async def set_global_message_loop_delay(delay: float):
        pass
