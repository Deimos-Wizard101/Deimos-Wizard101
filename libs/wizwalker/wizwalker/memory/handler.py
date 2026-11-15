import asyncio
import os
import struct
import sys
from typing import Any
import warnings
import traceback

import pymem
import pymem.exception
import pymem.process
from loguru import logger


def _build_rpc_trampoline(done_addr: int, shell_addr: int, orig_bytes: bytes, ret_addr: int) -> bytes:
    """One-shot self-restoring trampoline for the Linux thread-hijack RPC.

    Reached by a jmp planted over ``orig_bytes`` at a per-frame game call site.
    It saves every volatile register and the flags, and if the done byte is still
    0 it 16-aligns the stack (matching a fresh thread's entry, as CreateRemoteThread
    gives) and calls ``shell_addr`` once, then marks done. Either way it restores
    the registers, re-runs the hijacked ``orig_bytes`` (so the game's own work still
    happens) and jumps back past them. Non-volatile registers are untouched and are
    preserved across the shellcode's calls by the x64 callee convention.
    """
    p = lambda a: struct.pack("<Q", a)
    guarded = (
        b"\x55\x48\x89\xE5\x48\x83\xE4\xF0"          # push rbp; mov rbp,rsp; and rsp,-16
        b"\x48\xB8" + p(shell_addr) + b"\xFF\xD0"    # mov rax,shell; call rax
        b"\x48\x89\xEC\x5D"                           # mov rsp,rbp; pop rbp
        b"\x48\xB8" + p(done_addr) + b"\xC6\x00\x01"  # mov rax,done; mov byte[rax],1
    )
    pre = (
        b"\x50\x51\x52\x41\x50\x41\x51\x41\x52\x41\x53\x9C"  # push rax,rcx,rdx,r8,r9,r10,r11; pushfq
        b"\x48\xB8" + p(done_addr) + b"\x80\x38\x00"          # mov rax,done; cmp byte[rax],0
        b"\x75" + bytes([len(guarded)])                      # jnz +len(guarded)  (skip the call)
    )
    post = (
        b"\x9D\x41\x5B\x41\x5A\x41\x59\x41\x58\x5A\x59\x58"  # popfq; pop r11,r10,r9,r8,rdx,rcx,rax
        + orig_bytes +
        b"\xFF\x25\x00\x00\x00\x00" + p(ret_addr)            # jmp qword[rip+0]; dq ret_addr
    )
    return pre + guarded + post

from wizwalker import HookAlreadyActivated, HookNotActive, HookNotReady
from .hooks import (
    ChatHook,
    ChatSendHook,
    ClientHook,
    MouselessCursorMoveHook,
    PlayerHook,
    PlayerStatHook,
    QuestHook,
    RootWindowHook,
    RenderContextHook,
    MovementTeleportHook,
    DropsToggleHook,
    DanceGameMovesHook,
    AhmarraAutoPuzzleHook,
    UpdateZoneCounterHook,
    ServerMoveSnapbackHook,
    MemoryHook
)
from .memory_reader import MemoryReader, Primitive


# noinspection PyUnresolvedReferences
class HookHandler(MemoryReader):
    """
    Manages hooks
    """

    AUTOBOT_PATTERN = (
        rb"\x48\x8B\xC4\x55\x41\x54\x41\x55\x41\x56\x41\x57......."
        rb"\x48......\x48.......\x48\x89\x58\x10\x48\x89"
        rb"\x70\x18\x48\x89\x78\x20.......\x48\x33\xC4....."
        rb"..\x4C\x8B\xE9.......\x80......\x0F"
    )
    # rounded down
    AUTOBOT_SIZE = 3900

    def __init__(self, process: pymem.Pymem, client):
        super().__init__(process)

        self.client = client

        self._autobot_address = None
        self._autobot_lock = None
        self._original_autobot_bytes = b""
        self._autobot_pos = 0

        # Linux thread-hijack RPC (start_thread): a cached writable done-flag.
        self._rpc_done = None

        # Inline value-capture hooks (a jump patched over game .text that writes a
        # captured pointer to scratch each frame) do NOT fire under Rosetta on
        # macOS: a cross-process write to already-translated x86 code is ignored by
        # Rosetta's self-modifying-code detection. So those hooks are unsupported on
        # macOS — memory reads and the pointer-redirect RPC (start_thread → camera/
        # freecam) still work. This capability keeps the platform split BELOW
        # wizwalker's API: callers use activate_hooks identically everywhere.
        self._supports_inline_hooks = sys.platform != "darwin"
        self._warned_no_inline_hooks = False

        # TODO: Is this signature correct?
        self._active_hooks: dict[type, MemoryHook] = {}
        self._base_addrs = {}

        self._hook_cache = {}
        self._dance_moves_transtable = str.maketrans("abcd", "WDSA")

    async def _get_open_autobot_address(self, size: int) -> int:
        if self._autobot_pos + size > self.AUTOBOT_SIZE:
            raise RuntimeError("Somehow went over autobot size")

        addr = self._autobot_address + self._autobot_pos
        self._autobot_pos += size

        logger.debug(
            f"Allocating autobot address {addr}; autobot position is now {self._autobot_pos}"
        )
        return addr

    async def _get_autobot_address(self):
        from wizwalker import PatternFailed

        try:
            addr = await self.pattern_scan(
                self.AUTOBOT_PATTERN, module="WizardGraphicalClient.exe"
            )
        except PatternFailed:
            addr = None

        # A prior session that exited uncleanly (SIGKILL/crash) can leave the
        # autobot zeroed, so the in-memory pattern no longer matches. The region
        # is real .text present in the module on disk, so recover it from there and
        # carry on — no client restart needed. Linux only; Windows wizwalker keeps
        # its original behavior.
        if addr is None and sys.platform != "win32":
            addr = await self._heal_autobot_from_disk()

        if addr is None:
            raise RuntimeError("Pattern scan failed for autobot pattern")

        self._autobot_address = addr

    def _autobot_from_disk(self):
        """``(rva, pristine_bytes)`` for the autobot in the on-disk module, or None.

        The autobot's bytes are RIP/register-relative .text with no base
        relocations in the matched span, so the on-disk bytes equal the loaded
        ones regardless of load base.
        """
        try:
            import regex
            import pefile
            from wizwalker import utils

            exe = utils.get_wiz_install() / "Bin" / "WizardGraphicalClient.exe"
            data = exe.read_bytes()
            match = regex.search(self.AUTOBOT_PATTERN, data, regex.DOTALL)
            if match is None:
                return None
            file_off = match.start()
            rva = pefile.PE(str(exe), fast_load=True).get_rva_from_offset(file_off)
            return rva, data[file_off:file_off + self.AUTOBOT_SIZE]
        except Exception as exc:
            logger.opt(exception=exc).debug("Autobot disk lookup failed")
            return None

    async def _heal_autobot_from_disk(self):
        """Rewrite a zeroed/corrupt autobot from the on-disk module, returning its
        address, or None if the module or pattern can't be resolved."""
        found = self._autobot_from_disk()
        if found is None:
            return None
        rva, pristine = found
        module = pymem.process.module_from_name(
            self.process.process_handle, "WizardGraphicalClient.exe"
        )
        if module is None:
            return None
        addr = module.lpBaseOfDll + rva
        logger.warning(
            "Autobot not found in memory; restoring it from the on-disk module "
            "(a previous session likely exited without cleaning up). Recovering in place."
        )
        await self.write_bytes(addr, pristine)
        return addr

    # noinspection PyTypeChecker
    async def _prepare_autobot(self):
        if self._autobot_address is None:
            await self._get_autobot_address()

            # Save the whole region we are about to zero, not just the pattern:
            # the autobot spans real code (only a fraction of AUTOBOT_SIZE is
            # padding), so a pattern-length restore leaves the rest zeroed and
            # corrupts the target's .text once unhooked. Restoring the full span
            # returns the client to a pristine state after close().
            self._original_autobot_bytes = await self.read_bytes(
                self._autobot_address, self.AUTOBOT_SIZE
            )
            logger.debug(
                f"Got original bytes {self._original_autobot_bytes} from autobot"
            )
            await self.write_bytes(self._autobot_address, b"\x00" * self.AUTOBOT_SIZE)

    async def _rewrite_autobot(self):
        if self._autobot_address is not None:
            compare_bytes = await self.read_bytes(
                self._autobot_address, self.AUTOBOT_SIZE
            )
            # Give some time for execution point to leave hooks
            await asyncio.sleep(0.5)

            # Only write if the original isn't already back in place
            if compare_bytes != self._original_autobot_bytes:
                logger.debug(
                    f"Rewriting bytes {self._original_autobot_bytes} to autobot"
                )
                await self.write_bytes(
                    self._autobot_address, self._original_autobot_bytes
                )

    async def _allocate_autobot_bytes(self, size: int) -> int:
        address = await self._get_open_autobot_address(size)

        return address

    # Reserve the tail of the autobot as reusable scratch for the RPC trampoline +
    # shellcode, so repeated calls don't bump-exhaust the autobot.
    RPC_SCRATCH = 512

    async def start_thread(self, address: int):
        """Run the shellcode at ``address`` once in the target.

        On Windows this is CreateRemoteThread (the base implementation). Linux has
        no such call, so execute via a one-shot thread hijack: copy the shellcode
        into executable memory (the autobot, since ``allocate`` hands out writable,
        non-executable data memory on Linux), plant a self-restoring trampoline at a
        per-frame game call site that runs it once, wait for it, and restore. Same
        signature, so callers (e.g. camera freecam) are unchanged.
        """
        if sys.platform == "win32":
            return await super().start_thread(address)

        size = self.process.allocation_size(address)
        if size is None:
            raise RuntimeError(
                "start_thread on Linux needs the shellcode length; allocate it via "
                "process.allocate so its size is tracked"
            )
        shellcode = await self.read_bytes(address, size)

        # Linux one-shot RPC via thread-hijack. Default: zhol's native
        # rpc_via_hijack (the mechanism lives in the library now, drop-safe and
        # reusable; validated against a live client). Set DEIMOS_ZHOL_RPC=0 to fall
        # back to the in-Python path below.
        if os.environ.get("DEIMOS_ZHOL_RPC", "1") != "0":
            # zhol executes the shellcode + trampoline from a code cave (the done
            # byte stays in its writable data cave). Hand it the autobot's reserved
            # RPC scratch as that code cave: executable .text, within rel32 of the
            # hijack site, and large enough — Wizard101's own .text padding isn't.
            await self._check_for_autobot()
            scratch = self._autobot_address + self.AUTOBOT_SIZE - self.RPC_SCRATCH
            self.process.process_handle.register_cave(scratch, self.RPC_SCRATCH)
            mua = await self.client._get_movement_update_address()
            ran = await self.run_in_executor(
                self.process.process_handle.rpc_via_hijack,
                mua, shellcode, 10, 0, 2000,
            )
            if not ran:
                logger.warning(
                    "start_thread (zhol rpc_via_hijack): shellcode did not run within timeout"
                )
            return

        await self._check_for_autobot()
        scratch = self._autobot_address + self.AUTOBOT_SIZE - self.RPC_SCRATCH
        if scratch < self._autobot_address + self._autobot_pos:
            raise RuntimeError("autobot too full for RPC scratch")
        shell_addr = scratch
        tramp_addr = (shell_addr + len(shellcode) + 15) & ~15

        if self._rpc_done is None:
            self._rpc_done = self.process.allocate(8)
        done = self._rpc_done

        # Hijack the per-frame movement-update call site (always present, main
        # thread, clean stack). Whatever is there now (possibly NOPed by a freecam
        # movement patch) is captured and re-run by the trampoline, then restored.
        mua = await self.client._get_movement_update_address()
        orig = await self.read_bytes(mua, 10)
        tramp = _build_rpc_trampoline(done, shell_addr, orig, mua + 10)
        if (tramp_addr - shell_addr) + len(tramp) > self.RPC_SCRATCH:
            raise RuntimeError("RPC shellcode + trampoline exceed scratch")

        await self.write_bytes(done, b"\x00" * 8)
        await self.write_bytes(shell_addr, shellcode)
        await self.write_bytes(tramp_addr, tramp)

        rel = tramp_addr - (mua + 5)
        hijack = b"\xE9" + struct.pack("<i", rel) + b"\x90" * 5
        try:
            await self.write_bytes(mua, hijack)
            for _ in range(400):  # up to ~2s at 5 ms
                await asyncio.sleep(0.005)
                if (await self.read_bytes(done, 1))[0] == 1:
                    break
            else:
                logger.warning("start_thread: shellcode did not run within timeout")
        finally:
            await self.write_bytes(mua, orig)

    async def close(self):
        for hook in self._active_hooks.values():
            await hook.unhook()

        await self._rewrite_autobot()

        self._active_hooks = {}
        self._autobot_pos = 0
        self._autobot_address = None
        self._base_addrs = {}

    async def _check_for_autobot(self):
        if self._autobot_lock is None:
            self._autobot_lock = asyncio.Lock()

        # this is so it isn't prepared more than once at the same time
        async with self._autobot_lock:
            await self._prepare_autobot()

    def _check_if_hook_active(self, hook_type) -> bool:
        return hook_type in self._active_hooks

    def _get_hook_by_type(self, hook_type) -> MemoryHook:
        return self._active_hooks.get(hook_type, None)

    async def _read_hook_base_addr(self, addr_name: str, hook_name: str):
        addr = self._base_addrs.get(addr_name)
        if addr is None:
            raise HookNotActive(hook_name)

        try:
            return await self.read_typed(addr, Primitive.int64)
        except pymem.exception.MemoryReadError:
            raise HookNotReady(hook_name)

    # wait for an addr to be set and not 0
    async def _wait_for_value(self, address: int, timeout: int = None):
        async def _wait_for_value_task():
            while True:
                try:
                    value = await self.read_typed(address, Primitive.int64)
                    logger.debug(
                        f"Waiting for address {hex(address)}; got value {value}"
                    )
                except pymem.exception.MemoryReadError:
                    pass
                else:
                    if value != 0:
                        logger.debug(f"Address {hex(address)} is set")
                        break
                    else:
                        logger.debug(f"Address {hex(address)} is not set yet; sleeping")
                        await asyncio.sleep(0.5)

        try:
            await asyncio.wait_for(_wait_for_value_task(), timeout)
        except TimeoutError:
            # TODO: replace error
            raise TimeoutError("Hook value took too long")

    # TODO: make this faster
    async def activate_all_hooks(
        self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """
        Activate all hooks but mouseless

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        # macOS/Rosetta: inline value-capture hooks can't fire (and installing them
        # would also fail the rel32 reach to a fresh page), so skip them and don't
        # wait — otherwise `_wait_for_value` blocks forever on a value that is never
        # written. Memory reads and camera/RPC features don't need these hooks.
        if not self._supports_inline_hooks:
            if not self._warned_no_inline_hooks:
                self._warned_no_inline_hooks = True
                logger.warning(
                    "Inline value-capture hooks are unsupported on macOS (Rosetta); "
                    "skipping them. Memory reads and camera/RPC features still work; "
                    "hook-dependent reads (player/stats/quest) are unavailable here."
                )
            return

        await self.activate_player_hook(wait_for_ready=False)
        # quest hook is not written if the quest arrow is off
        await self.activate_quest_hook()
        await self.activate_player_stat_hook(wait_for_ready=False)
        await self.activate_client_hook(wait_for_ready=False)
        await self.activate_root_window_hook(wait_for_ready=False)
        await self.activate_render_context_hook(wait_for_ready=False)
        await self.activate_movement_teleport_hook(wait_for_ready=False)
        await self.activate_drops_toggle_hook(wait_for_ready=False)
        await self.activate_auto_puzzle_hook(wait_for_ready=False)
        await self.activate_update_zone_counter_hook(wait_for_ready=False)
        await self.activate_server_move_snapback_hook(wait_for_ready=False)

        if wait_for_ready:
            wait_tasks = []
            for atter_name in [
                "player_struct",
                "player_stat_struct",
                "current_client",
                "current_root_window",
                "current_render_context",
            ]:
                value = self._base_addrs[atter_name]
                wait_tasks.append(
                    asyncio.create_task(self._wait_for_value(value, timeout))
                )

            await asyncio.gather(*wait_tasks)

    async def activate_player_hook(
        self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """
        Activate player hook

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        if self._check_if_hook_active(PlayerHook):
            raise HookAlreadyActivated("Player")

        await self._check_for_autobot()

        player_hook = PlayerHook(self)
        await player_hook.hook()

        self._active_hooks[PlayerHook] = player_hook
        self._base_addrs["player_struct"] = player_hook.player_struct

        if wait_for_ready:
            await self._wait_for_value(player_hook.player_struct, timeout)

    async def deactivate_player_hook(self):
        """
        Deactivate player hook
        """
        if not self._check_if_hook_active(PlayerHook):
            raise HookNotActive("Player")

        hook = self._active_hooks.pop(PlayerHook)
        await hook.unhook()

        del self._base_addrs["player_struct"]

    async def read_current_player_base(self) -> int:
        """
        Read player base address

        Returns:
            The player base address
        """
        return await self._read_hook_base_addr("player_struct", "Player")

    async def activate_quest_hook(
        self, *, wait_for_ready: bool = False, timeout: float = None
    ):
        """
        Activate quest hook

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        if self._check_if_hook_active(QuestHook):
            raise HookAlreadyActivated("Quest")

        await self._check_for_autobot()

        quest_hook = QuestHook(self)
        await quest_hook.hook()

        self._active_hooks[QuestHook] = quest_hook
        self._base_addrs["quest_struct"] = quest_hook.cord_struct

        if wait_for_ready:
            await self._wait_for_value(quest_hook.cord_struct, timeout)

    async def deactivate_quest_hook(self):
        """
        Deactivate quest hook
        """
        if not self._check_if_hook_active(QuestHook):
            raise HookNotActive("Quest")

        hook = self._active_hooks.pop(QuestHook)
        await hook.unhook()

        del self._base_addrs["quest_struct"]

    async def read_current_quest_base(self) -> int:
        """
        Read quest base address

        Returns:
            The quest base address
        """
        return await self._read_hook_base_addr("quest_struct", "Quest")

    async def activate_player_stat_hook(
        self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """
        Activate player stat hook

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        if self._check_if_hook_active(PlayerStatHook):
            raise HookAlreadyActivated("Player stat")

        await self._check_for_autobot()

        player_stat_hook = PlayerStatHook(self)
        await player_stat_hook.hook()

        self._active_hooks[PlayerStatHook] = player_stat_hook
        self._base_addrs["player_stat_struct"] = player_stat_hook.stat_addr

        if wait_for_ready:
            await self._wait_for_value(player_stat_hook.stat_addr, timeout)

    async def deactivate_player_stat_hook(self):
        """
        Deactivate player stat hook
        """
        if not self._check_if_hook_active(PlayerStatHook):
            raise HookNotActive("Player stat")

        hook = self._active_hooks.pop(PlayerStatHook)
        await hook.unhook()

        del self._base_addrs["player_stat_struct"]

    async def read_current_player_stat_base(self) -> int:
        """
        Read player stat base address

        Returns:
            The player stat base address
        """
        return await self._read_hook_base_addr("player_stat_struct", "Player stat")

    async def activate_client_hook(
        self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """
        Activate client hook

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        if self._check_if_hook_active(ClientHook):
            raise HookAlreadyActivated("Client")

        await self._check_for_autobot()

        client_hook = ClientHook(self)
        await client_hook.hook()

        self._active_hooks[ClientHook] = client_hook
        self._base_addrs["current_client"] = client_hook.current_client_addr

        if wait_for_ready:
            await self._wait_for_value(client_hook.current_client_addr, timeout)

    async def deactivate_client_hook(self):
        """
        Deactivate client hook
        """
        if not self._check_if_hook_active(ClientHook):
            raise HookNotActive("Client")

        hook = self._active_hooks.pop(ClientHook)
        await hook.unhook()

        del self._base_addrs["current_client"]

    async def read_current_client_base(self) -> int:
        """
        Read cureent client base address

        Returns:
            The current client base address
        """
        return await self._read_hook_base_addr("current_client", "Client")

    async def activate_root_window_hook(
        self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """
        Activate root window hook

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        if self._check_if_hook_active(RootWindowHook):
            raise HookAlreadyActivated("Root window")

        await self._check_for_autobot()

        root_window_hook = RootWindowHook(self)
        await root_window_hook.hook()

        self._active_hooks[RootWindowHook] = root_window_hook
        self._base_addrs[
            "current_root_window"
        ] = root_window_hook.current_root_window_addr

        if wait_for_ready:
            await self._wait_for_value(
                root_window_hook.current_root_window_addr, timeout
            )

    async def deactivate_root_window_hook(self):
        """
        Deactivate root window hook
        """
        if not self._check_if_hook_active(RootWindowHook):
            raise HookNotActive("Root window")

        hook = self._active_hooks.pop(RootWindowHook)
        await hook.unhook()

        del self._base_addrs["current_root_window"]

    async def read_current_root_window_base(self) -> int:
        """
        Read current root window base address

        Returns:
            The current root window base address
        """
        return await self._read_hook_base_addr("current_root_window", "Root window")

    async def activate_render_context_hook(
        self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """
        Activate render context hook

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        if self._check_if_hook_active(RenderContextHook):
            raise HookAlreadyActivated("Render context")

        await self._check_for_autobot()

        render_context_hook = RenderContextHook(self)
        await render_context_hook.hook()

        self._active_hooks[RenderContextHook] = render_context_hook
        self._base_addrs[
            "current_render_context"
        ] = render_context_hook.current_render_context_addr

        if wait_for_ready:
            await self._wait_for_value(
                render_context_hook.current_render_context_addr, timeout
            )

    async def deactivate_render_context_hook(self):
        """
        Deactivate render context hook
        """
        if not self._check_if_hook_active(RenderContextHook):
            raise HookNotActive("Render context")

        hook = self._active_hooks.pop(RenderContextHook)
        await hook.unhook()

        del self._base_addrs["current_render_context"]

    async def read_current_render_context_base(self) -> int:
        """
        Read current render context base address

        Returns:
            The current render context base address
        """
        return await self._read_hook_base_addr(
            "current_render_context", "Render context"
        )

    async def activate_movement_teleport_hook(
            self, *, wait_for_ready: bool = False, timeout: float = None
    ):
        """
        Activate movement teleport hook

        wait_for_ready is useless for this hook

        Keyword Args:
            wait_for_ready: Wait for hook values to be written
            timeout: How long to wait for hook values to be written (None for no timeout)
        """
        if self._check_if_hook_active(MovementTeleportHook):
            raise HookAlreadyActivated("Movement teleport")

        await self._check_for_autobot()

        movement_teleport_hook = MovementTeleportHook(self)
        await movement_teleport_hook.hook()

        self._active_hooks[MovementTeleportHook] = movement_teleport_hook
        self._base_addrs[
            "teleport_helper"
        ] = movement_teleport_hook.teleport_helper

    async def deactivate_movement_teleport_hook(self):
        """
        Deactivate movement teleport hook
        """
        if not self._check_if_hook_active(MovementTeleportHook):
            raise HookNotActive("Movement teleport")

        hook = self._active_hooks.pop(MovementTeleportHook)
        await hook.unhook()

        del self._base_addrs["teleport_helper"]

    async def read_teleport_helper(self) -> int:
        """
        Read teleport helper base address

        Returns:
            The teleport helper base address
        """
        addr = self._base_addrs.get("teleport_helper")
        if addr is None:
            raise HookNotActive("Movement teleport")

        return addr

    async def activate_drops_toggle_hook(
        self, *, wait_for_ready: bool = False, timeout: float = None
    ):
        
        if self._check_if_hook_active(DropsToggleHook):
            raise HookAlreadyActivated("Drops toggle")

        await self._check_for_autobot()

        drops_toggle_hook = DropsToggleHook(self)
        await drops_toggle_hook.hook()

        self._active_hooks[DropsToggleHook] = drops_toggle_hook
        self._base_addrs["disable_drops_bool"] = drops_toggle_hook.disable_drops_bool

    async def deactivate_drops_toggle_hook(self):

        if not self._check_if_hook_active(DropsToggleHook):
            raise HookNotActive("Drops toggle")

        drops_toggle_hook = self._active_hooks.pop(DropsToggleHook)
        await drops_toggle_hook.unhook()

        del self._base_addrs["disable_drops_bool"]

    async def read_disable_drops_bool(self) -> int:
        addr = self._base_addrs.get("disable_drops_bool")

        if addr is None:
            raise HookNotActive("Drops toggle")

        return addr

    async def activate_auto_puzzle_hook(
        self, *, wait_for_ready: bool = False, timeout: float = None
    ):

        if self._check_if_hook_active(AhmarraAutoPuzzleHook):
            raise HookAlreadyActivated("Auto puzzle")

        await self._check_for_autobot()

        auto_puzzle_hook = AhmarraAutoPuzzleHook(self)
        await auto_puzzle_hook.hook()

        self._active_hooks[AhmarraAutoPuzzleHook] = auto_puzzle_hook
        self._base_addrs["auto_puzzle_bool"] = auto_puzzle_hook.auto_puzzle_bool

    async def deactivate_auto_puzzle_hook(self):

        if not self._check_if_hook_active(AhmarraAutoPuzzleHook):
            raise HookNotActive("Auto puzzle")

        auto_puzzle_hook = self._active_hooks.pop(AhmarraAutoPuzzleHook)
        await auto_puzzle_hook.unhook()

        del self._base_addrs["auto_puzzle_bool"]

    async def read_auto_puzzle_bool(self) -> int:
        addr = self._base_addrs.get("auto_puzzle_bool")

        if addr is None:
            raise HookNotActive("Auto puzzle")

        return addr

    async def activate_update_zone_counter_hook(
        self, *, wait_for_ready: bool = False, timeout: float = None
    ):

        if self._check_if_hook_active(UpdateZoneCounterHook):
            raise HookAlreadyActivated("Update Zone Counter")

        await self._check_for_autobot()

        update_zone_counter_hook = UpdateZoneCounterHook(self)
        await update_zone_counter_hook.hook()

        self._active_hooks[UpdateZoneCounterHook] = update_zone_counter_hook
        self._base_addrs["server_teleport_snapback_bool"] = update_zone_counter_hook.server_teleport_snapback_bool
    
    async def deactivate_update_zone_counter_hook(self):

        if not self._check_if_hook_active(UpdateZoneCounterHook):
            raise HookNotActive("Update Zone Counter")

        update_zone_counter_hook = self._active_hooks.pop(UpdateZoneCounterHook)
        await update_zone_counter_hook.unhook()

        del self._base_addrs["server_teleport_snapback_bool"]

    async def read_server_teleport_snapback_bool(self) -> int:
        addr = self._base_addrs.get("server_teleport_snapback_bool")

        if addr is None:
            raise HookNotActive("Update Zone Counter")

        return addr

    async def activate_server_move_snapback_hook(
        self, *, wait_for_ready: bool = False, timeout: float = None
    ):

        if self._check_if_hook_active(ServerMoveSnapbackHook):
            raise HookAlreadyActivated("Server move snapback")

        await self._check_for_autobot()

        server_move_snapback_hook = ServerMoveSnapbackHook(self)
        await server_move_snapback_hook.hook()

        self._active_hooks[ServerMoveSnapbackHook] = server_move_snapback_hook
        self._base_addrs["server_move_snapback_bool"] = server_move_snapback_hook.server_move_snapback_bool

    async def deactivate_server_move_snapback_hook(self):

        if not self._check_if_hook_active(ServerMoveSnapbackHook):
            raise HookNotActive("Server move snapback")

        server_move_snapback_hook = self._active_hooks.pop(ServerMoveSnapbackHook)
        await server_move_snapback_hook.unhook()

        del self._base_addrs["server_move_snapback_bool"]

    async def read_server_move_snapback_bool(self) -> int:
        addr = self._base_addrs.get("server_move_snapback_bool")

        if addr is None:
            raise HookNotActive("Server move snapback")

        return addr

    async def activate_dance_game_moves_hook(
        self, *, wait_for_ready: bool = False, timeout: float = None
    ):
        if self._check_if_hook_active(DanceGameMovesHook):
            raise HookAlreadyActivated("DanceGameMovesHook")

        await self._check_for_autobot()

        dance_game_hook = DanceGameMovesHook(self)
        await dance_game_hook.hook()

        self._active_hooks[DanceGameMovesHook] = dance_game_hook
        #self._active_hooks.append(dance_game_hook)
        self._base_addrs["dance_game_moves"] = dance_game_hook.dance_game_moves

        if wait_for_ready:
            await self._wait_for_value(dance_game_hook.dance_game_moves, timeout)

    async def deactivate_dance_game_moves_hook(self):
        if not self._check_if_hook_active(DanceGameMovesHook):
            raise HookNotActive("DanceGameMovesHook")

        dance_game_hook = self._get_hook_by_type(DanceGameMovesHook)
        #self._active_hooks.remove(dance_game_hook)
        del self._active_hooks[DanceGameMovesHook]
        await dance_game_hook.unhook()

        del self._base_addrs["dance_game_moves"]

    async def attempt_activate_dance_hook(self, sleep_time: float = 0.1):
        # Attempts to activate dance hook, in a try block in case it's already off for this client
        if not self.client.dance_hook_status:
            try:
                await self.activate_dance_game_moves_hook()
            except:
                logger.debug("failed to activate dance hook")
                logger.debug(traceback.print_exc())
                pass

            self.client.dance_hook_status = True
        await asyncio.sleep(sleep_time)

    async def attempt_deactivate_dance_hook(self, sleep_time: float = 0.1):
        # Attempts to deactivate dance hook, in a try block in case it's already off for this client
        if self.client.dance_hook_status:
            try:
                await self.deactivate_dance_game_moves_hook()
            except:
                pass

            self.client.dance_hook_status = False
        await asyncio.sleep(sleep_time)

    async def read_current_dance_game_moves(self) -> str:
        try:
            addr = self._base_addrs["dance_game_moves"]
        except KeyError:
            raise HookNotActive("DanceGameMovesHook")

        try:
            moves = await self.read_bytes(addr, 8)
        except pymem.exception.MemoryReadError:
            raise HookNotReady("DanceGameMovesHook")
        return moves.partition(b"\0")[0].decode().translate(self._dance_moves_transtable)

    # nothing to wait for in this hook
    async def activate_mouseless_cursor_hook(self):
        """
        Activate mouseless cursor hook
        """
        if self._check_if_hook_active(MouselessCursorMoveHook):
            raise HookAlreadyActivated("Mouseless cursor")

        await self._check_for_autobot()

        mouseless_cursor_hook = MouselessCursorMoveHook(self, self._hook_cache)
        await mouseless_cursor_hook.hook()

        self._active_hooks[MouselessCursorMoveHook] = mouseless_cursor_hook
        self._base_addrs["mouse_position"] = mouseless_cursor_hook.mouse_pos_addr

        await self.write_mouse_position(0, 0)

    async def deactivate_mouseless_cursor_hook(self):
        """
        Deactivate mouseless cursor hook
        """
        if not self._check_if_hook_active(MouselessCursorMoveHook):
            raise HookNotActive("Mouseless cursor")

        hook = self._active_hooks.pop(MouselessCursorMoveHook)
        await hook.unhook()

        del self._base_addrs["mouse_position"]

    # TODO: 2.0 switch this to a helper object like movement teleport and quest
    async def write_mouse_position(self, x: int, y: int):
        """
        Write mouse position to memory

        Args:
            x: x position of mouse
            y: y position of mouse
        """
        addr = self._base_addrs.get("mouse_position")
        if addr is None:
            raise HookNotActive("Mouseless cursor")

        packed_position = struct.pack("<ii", x, y)

        await self.write_bytes(addr, packed_position)

    async def activate_chat_hook(
        self, *, wait_for_ready: bool = True, timeout: float = None
    ):
        """Activate the chat hook to capture incoming directed chat messages.

        The hook fires on every incoming MSG_DirectedChat, extracting the
        sender's GID and message text to persistent export buffers.

        Keyword Args:
            wait_for_ready: Wait for the first message to arrive
            timeout: How long to wait (None for no timeout)
        """
        if self._check_if_hook_active(ChatHook):
            raise HookAlreadyActivated("Chat")

        await self._check_for_autobot()

        chat_hook = ChatHook(self)
        await chat_hook.hook()

        self._active_hooks[ChatHook] = chat_hook
        self._base_addrs["chat_owner"] = chat_hook.chat_owner_addr
        self._base_addrs["recv_source_gid"] = chat_hook.recv_source_gid
        self._base_addrs["recv_message_buf"] = chat_hook.recv_message_buf
        self._base_addrs["recv_message_len"] = chat_hook.recv_message_len
        self._base_addrs["recv_counter"] = chat_hook.recv_counter

        if wait_for_ready:
            await self._wait_for_value(chat_hook.recv_counter, timeout)

    async def deactivate_chat_hook(self):
        """Deactivate the chat hook."""
        if not self._check_if_hook_active(ChatHook):
            raise HookNotActive("Chat")

        hook = self._active_hooks.pop(ChatHook)
        await hook.unhook()

        del self._base_addrs["chat_owner"]
        del self._base_addrs["recv_source_gid"]
        del self._base_addrs["recv_message_buf"]
        del self._base_addrs["recv_message_len"]
        del self._base_addrs["recv_counter"]

    async def read_chat_owner_base(self) -> int:
        """Read the chat owner (chat module) base address.

        Returns:
            The chat module base address
        """
        return await self._read_hook_base_addr("chat_owner", "Chat")

    async def activate_chat_send_hook(self):
        """Activate the chat send hook on the main game loop.

        This hooks the game's main loop so that send_msg() executes
        on the main thread where chat operations are safe.
        """
        if self._check_if_hook_active(ChatSendHook):
            raise HookAlreadyActivated("Chat send")

        await self._check_for_autobot()

        hook = ChatSendHook(self)
        await hook.hook()

        self._active_hooks[ChatSendHook] = hook
        self._base_addrs["send_trigger"] = hook.send_trigger
        self._base_addrs["send_struct"] = hook.send_struct
        self._base_addrs["buddy_trigger"] = hook.buddy_trigger
        self._base_addrs["buddy_obj"] = hook.buddy_obj

    async def deactivate_chat_send_hook(self):
        """Deactivate the chat send hook."""
        if not self._check_if_hook_active(ChatSendHook):
            raise HookNotActive("Chat send")

        hook = self._active_hooks.pop(ChatSendHook)
        await hook.unhook()

        del self._base_addrs["send_trigger"]
        del self._base_addrs["send_struct"]
        del self._base_addrs["buddy_trigger"]
        del self._base_addrs["buddy_obj"]
