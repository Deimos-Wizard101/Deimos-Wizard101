import asyncio
import ctypes
import ctypes.wintypes
from contextlib import suppress
from enum import IntFlag
from typing import Callable, Union

import janus

from wizwalker import HotkeyAlreadyRegistered
from wizwalker.constants import Keycode, user32


MAX_HOTKEY_ID = 0xBFFF


class _GlobalHotkeyIdentifierManager:
    def __init__(self):
        self.hotkey_id_list = []
        self.hotkey_lock = asyncio.Lock()

    async def get_id(self) -> int:
        # so an id isn't given out twice
        async with self.hotkey_lock:
            if (id_list_len := len(self.hotkey_id_list)) == MAX_HOTKEY_ID:
                raise RuntimeError(f"Max hotkey id of {MAX_HOTKEY_ID} reached")

            # all True
            if sum(self.hotkey_id_list) == id_list_len:
                self.hotkey_id_list.append(True)
                return id_list_len + 1

            # at least one False
            else:
                index = self.hotkey_id_list.index(False)
                self.hotkey_id_list[index] = True
                return index + 1

    async def free_id(self, hotkey_id: int):
        async with self.hotkey_lock:
            self.hotkey_id_list[hotkey_id - 1] = False

            # all False
            if sum(self.hotkey_id_list) == 0:
                self.hotkey_id_list = []


_hotkey_id_manager = _GlobalHotkeyIdentifierManager()


class _GlobalHotkeyMessageLoop:
    def __init__(self):
        self.messages = []
        self.message_loop_task = None
        self.connected_instances = 0
        self._message_loop_delay = 0.1

    async def check_for_message(self, keycode: int, modifiers: int) -> bool:
        if (keycode, modifiers) in self.messages:
            self.messages.remove((keycode, modifiers))
            return True

        return False

    async def message_loop(self):
        while True:
            # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-peekmessagew
            message = ctypes.wintypes.MSG()
            is_message = user32.PeekMessageW(
                ctypes.byref(message),
                None,
                0x311,
                0x314,
                1,
            )

            if is_message:
                # get lower 16 bits
                modifiers = message.lParam & 0b1111111111111111
                # get higher 16 bits
                keycode = message.lParam >> 16

                self.messages.append((keycode, modifiers))

                user32.DispatchMessageW(ctypes.byref(message))

            await asyncio.sleep(self._message_loop_delay)

    def connect(self):
        if not self.message_loop_task:
            self.message_loop_task = asyncio.create_task(self.message_loop())

        self.connected_instances += 1

    def disconnect(self):
        self.connected_instances -= 1

        if self.connected_instances == 0:
            if self.message_loop_task:
                with suppress(asyncio.CancelledError):
                    self.message_loop_task.cancel()

    def set_message_loop_delay(self, new_delay: float):
        self._message_loop_delay = new_delay


_hotkey_message_loop = _GlobalHotkeyMessageLoop()


class ModifierKeys(IntFlag):
    """
    Key modifiers
    """

    ALT = 0x1
    CTRL = 0x2
    NOREPEAT = 0x4000
    SHIFT = 0x4


# TODO: remove in 2.0
class Hotkey:
    """
    A hotkey to be listened to

    Args:
        keycode: Keycode to listen for
        callback: Coroutine to run when the key is pressed
        modifiers: Key modifiers to apply
    """

    def __init__(
        self,
        keycode: Keycode,
        callback: Callable,
        *,
        modifiers: Union[ModifierKeys, int] = 0,
    ):
        self.keycode = keycode
        self.modifiers = modifiers
        self.callback = callback


# TODO: remove in 2.0, make sure to also remove janus requirement
class Listener:
    """
    Hotkey listener

    Args:
        hotkeys: list of Hotkeys to be listened for
        loop: The event loop to use; defaults to current

    Examples:
        .. code-block:: py

                import asyncio

                from wizwalker import Hotkey, Keycode, Listener


                async def main():
                    async def callback():
                        print("a was pressed")

                    hotkey = Hotkey(Keycode.A, callback)
                    listener = Listener(hotkey)

                    listener.listen_forever()

                    # your program here
                    while True:
                        await asyncio.sleep(1)



                if __name__ == "__main__":
                    asyncio.run(main())
    """

    def __init__(self, *hotkeys: Hotkey):
        self.ready = False

        self._loop = asyncio.get_event_loop()
        self._hotkeys = hotkeys
        self._callbacks = {}
        self._queue = None
        self._message_task = None
        self._id_counter = 1
        self._closed = False

    def listen_forever(self) -> asyncio.Task:
        """
        return a task listening to events
        """
        return asyncio.create_task(self._listen_forever_loop())

    async def _listen_forever_loop(self):
        while True:
            await self.listen()

    async def listen(self):
        """
        Listen for one event
        """
        self._queue = janus.Queue()
        if self._message_task is None:
            self._message_task = self._loop.run_in_executor(None, self._add_and_listen)

        message = await self._queue.async_q.get()
        keycode, modifiers = message.split("|")
        keycode = int(keycode)
        modifiers = int(modifiers)

        # TODO: add to self._tasks and cancel in self.close
        self._loop.create_task(self._callbacks[(keycode, modifiers)]())

    # async for future proofing
    async def close(self):
        self._closed = True

    def _add_and_listen(self):
        if not self.ready:
            self._add_hotkeys()
        self.ready = True

        while True:
            # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-peekmessagew
            message = ctypes.wintypes.MSG()
            is_message = user32.PeekMessageW(
                ctypes.byref(message),
                None,
                0x311,
                0x314,
                1,
            )

            if is_message:
                modifiers = message.lParam & 0b1111111111111111
                keycode = message.lParam >> 16

                self._queue.sync_q.put(f"{keycode}|{modifiers}")

                user32.DispatchMessageW(ctypes.byref(message))

            else:
                if self._closed:
                    break

    def _add_hotkeys(self):
        for hotkey in self._hotkeys:
            if self._register_hotkey(hotkey.keycode.value, int(hotkey.modifiers)):
                # No repeat is not included in the return message
                no_norepeat = hotkey.modifiers & ~ModifierKeys.NOREPEAT
                self._callbacks[(hotkey.keycode.value, no_norepeat)] = hotkey.callback

            else:
                raise HotkeyAlreadyRegistered(
                    f"{hotkey.keycode} with modifers {hotkey.modifiers}"
                )

    def _register_hotkey(self, keycode: int, modifiers: int = 0) -> bool:
        res = user32.RegisterHotKey(None, self._id_counter, modifiers, keycode)
        self._id_counter += 1

        return res != 0


class HotkeyListener:
    """
    Examples:
        .. code-block:: py

                import asyncio

                from wizwalker import Keycode, HotkeyListener, ModifierKeys


                async def main():
                    listener = HotkeyListener()

                    async def callback():
                        print("a was pressed; removing it")
                        await listener.remove_hotkey(Keycode.A, modifiers=ModifierKeys.NOREPEAT)

                    await listener.add_hotkey(Keycode.A, callback, modifiers=ModifierKeys.NOREPEAT)

                    listener.start()

                    try:
                        # your program here
                        while True:
                            await asyncio.sleep(1)

                    finally:
                        await listener.stop()


                if __name__ == "__main__":
                    asyncio.run(main())
    """

    def __init__(self, *, sleep_time: float = 0.1):
        self.sleep_time = sleep_time

        self._hotkeys = {}
        self._callbacks = {}
        self._callback_tasks = []

        self._message_loop_task = None

    @property
    def is_running(self) -> bool:
        """
        If this hotkey listener is running
        """
        return self._message_loop_task is not None

    # TODO: 2.0: make async
    def start(self):
        """
        Start the listener
        """
        if self._message_loop_task:
            raise ValueError("This listener has already been started")

        _hotkey_message_loop.connect()

        self._message_loop_task = asyncio.create_task(self._message_loop())

        # this is because making this method async would be breaking
        loop = asyncio.get_event_loop()

        for keycode, modifiers in self._hotkeys:
            loop.create_task(self._register_hotkey(keycode, modifiers))

    async def stop(self):
        """
        Stop the listener
        """
        _hotkey_message_loop.disconnect()

        for hotkey_id in self._hotkeys.values():
            res = user32.UnregisterHotKey(None, hotkey_id)

            if res != 0:
                await _hotkey_id_manager.free_id(hotkey_id)

        with suppress(asyncio.CancelledError):
            if self._message_loop_task:
                self._message_loop_task.cancel()
                self._message_loop_task = None

            for task in self._callback_tasks:
                task.cancel()

    async def add_hotkey(
        self, key: Keycode, callback: Callable, *, modifiers: ModifierKeys = 0
    ):
        """
        Add a hotkey to listen for

        Args:
            key: The keycode to use
            callback: The hotkey callback
            modifiers: The hotkey modifer keys
        """
        if await self._register_hotkey(key.value, int(modifiers)):
            # No repeat is not included in the return message
            no_norepeat = modifiers & ~ModifierKeys.NOREPEAT
            self._callbacks[(key.value, no_norepeat)] = callback

        else:
            raise ValueError(f"{key} with modifers {modifiers} already registered")

    async def remove_hotkey(self, key: Keycode, *, modifiers: ModifierKeys = 0):
        """
        Remove a hotkey from this listener

        Args:
            key: The keycode of the hotkey to stop listening to
            modifiers: Modifers of the hotkey to stop listening to
        """
        if self._hotkeys.get((key.value, modifiers)) is None:
            raise ValueError(
                f"No hotkey registered for key {key} with modifiers {modifiers}"
            )

        if not await self._unregister_hotkey(key.value, int(modifiers)):
            raise ValueError(
                f"Unregistering hotkey failure for key {key} with modifiers {modifiers}"
            )

        del self._hotkeys[(key.value, modifiers)]

    @staticmethod
    async def set_global_message_loop_delay(delay: float):
        """
        Set the global message loop delay

        Args:
            delay: The message loop delay
        """
        _hotkey_message_loop.set_message_loop_delay(delay)

    # async so it isn't a breaking change later
    async def clear(self):
        """
        Remove all hotkeys from this listener
        """
        for hotkey_id in self._hotkeys.values():
            res = user32.UnregisterHotKey(None, hotkey_id)

            if res != 0:
                await _hotkey_id_manager.free_id(hotkey_id)

        self._callbacks = {}
        self._hotkeys = {}

    async def _message_loop(self):
        while True:
            for keycode, modifiers in self._callbacks.keys():
                if await _hotkey_message_loop.check_for_message(keycode, modifiers):
                    await self._handle_hotkey(keycode, modifiers)

            await asyncio.sleep(self.sleep_time)

    async def _handle_hotkey(self, keycode: int, modifiers: int):
        self._callback_tasks.append(
            asyncio.create_task(self._callbacks[(keycode, modifiers)]())
        )

    async def _register_hotkey(self, keycode: int, modifiers: int = 0) -> bool:
        hotkey_id = await _hotkey_id_manager.get_id()
        # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey
        res = user32.RegisterHotKey(None, hotkey_id, modifiers, keycode)

        success = res != 0

        if success:
            self._hotkeys[(keycode, modifiers)] = hotkey_id

        else:
            await _hotkey_id_manager.free_id(hotkey_id)

        return success

    async def _unregister_hotkey(self, keycode: int, modifiers: int = 0):
        hotkey_id = self._hotkeys[(keycode, modifiers)]

        # https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-unregisterhotkey
        res = user32.UnregisterHotKey(None, hotkey_id)

        success = res != 0

        if success:
            await _hotkey_id_manager.free_id(hotkey_id)

        return success
