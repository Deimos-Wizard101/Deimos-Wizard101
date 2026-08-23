import asyncio
import ctypes
import ctypes.wintypes
import struct
from typing import Any, Tuple
from contextlib import suppress
import warnings

from loguru import logger

from .memory_reader import MemoryReader
from wizwalker.constants import kernel32


class MemoryHook(MemoryReader):
    def __init__(self, hook_handler, hook_cache = {}):
        super().__init__(hook_handler.process)
        self.hook_handler = hook_handler
        self._hook_cache = hook_cache
        self.jump_original_bytecode = None

        self.hook_address = None
        self.jump_address = None

        self.jump_bytecode = None
        self.hook_bytecode = None

        # so we can dealloc it on unhook
        self._allocated_addresses = []

    def _get_my_cache(self):
        if self._hook_cache is None:
            self._hook_cache = {type(self): {}}
        if type(self) not in self._hook_cache:
            self._hook_cache[type(self)] = {}
        return self._hook_cache[type(self)]
    
    def _is_cached(self, name):
        return name in self._get_my_cache()

    def _cache(self, name, value):
        self._get_my_cache()[name] = value

    def _get_cached(self, name):
        return self._get_my_cache()[name]

    async def alloc(self, size: int) -> int:
        """
        Allocate <size> bytes
        """
        addr = await self.allocate(size)
        self._allocated_addresses.append(addr)
        return addr

    async def prehook(self):
        """
        Called after bytecode is prepared and before written
        """
        pass

    async def posthook(self):
        """
        Called after bytecode is written
        """
        pass

    async def get_jump_address(self, pattern: bytes, module: str = None) -> int:
        """
        gets the address to write jump at
        """
        jump_address = await self.pattern_scan(pattern, module=module)
        return jump_address

    async def get_hook_address(self, size: int) -> int:
        return await self.alloc(size)

    async def get_jump_bytecode(self) -> bytes:
        """
        Gets the bytecode to write to the jump address
        """
        raise NotImplemented()

    async def get_hook_bytecode(self) -> bytes:
        """
        Gets the bytecord to write to the hook address
        """
        raise NotImplemented()

    async def get_pattern(self) -> Tuple[bytes, str]:
        raise NotImplemented()

    async def hook(self):
        """
        Writes jump_bytecode to jump address and hook bytecode to hook address
        """
        pattern, module = await self.get_pattern()

        self.jump_address = await self.get_jump_address(pattern, module=module)
        self.hook_address = await self.get_hook_address(50)

        logger.debug(f"Got hook address {self.hook_address} in {type(self)}")
        logger.debug(f"Got jump address {self.jump_address} in {type(self)}")

        self.hook_bytecode = await self.get_hook_bytecode()
        self.jump_bytecode = await self.get_jump_bytecode()

        logger.debug(f"Got hook bytecode {self.hook_bytecode} in {type(self)}")
        logger.debug(f"Got jump bytecode {self.jump_bytecode} in {type(self)}")

        self.jump_original_bytecode = await self.read_bytes(
            self.jump_address, len(self.jump_bytecode)
        )

        logger.debug(
            f"Got jump original bytecode {self.jump_original_bytecode} in {type(self)}"
        )

        await self.prehook()

        await self.write_bytes(self.hook_address, self.hook_bytecode)
        await self.write_bytes(self.jump_address, self.jump_bytecode)

        await self.posthook()

    async def unhook(self):
        """
        Deallocates hook memory and rewrites jump addr to it's original code,
        also called when a client is closed
        """
        logger.debug(
            f"Writing original bytecode {self.jump_original_bytecode} to {self.jump_address}"
        )
        await self.write_bytes(self.jump_address, self.jump_original_bytecode)
        for addr in self._allocated_addresses:
            await self.free(addr)


class AutoBotBaseHook(MemoryHook):
    """
    Subclass of MemoryHook that uses an autobot function for bytes so addresses aren't huge
    """

    async def alloc(self, size: int) -> int:
        # noinspection PyProtectedMember
        return await self.hook_handler._allocate_autobot_bytes(size)

    # TODO: tell handler those bytes are free now?
    async def unhook(self):
        logger.debug(
            f"Writing original bytecode {self.jump_original_bytecode} to {self.jump_address}"
        )
        await self.write_bytes(self.jump_address, self.jump_original_bytecode)


class SimpleHook(AutoBotBaseHook):
    """
    Simple hook for writing hooks that are simple ofc
    """

    pattern = None
    module = "WizardGraphicalClient.exe"
    instruction_length = 5
    exports = None
    noops = 0

    async def get_pattern(self):
        return self.pattern, self.module

    async def get_jump_bytecode(self) -> bytes:
        distance = self.hook_address - self.jump_address

        relitive_jump = distance - 5
        packed_relitive_jump = struct.pack("<i", relitive_jump)

        return b"\xE9" + packed_relitive_jump + (b"\x90" * self.noops)

    async def bytecode_generator(self, packed_exports):
        raise NotImplemented()

    async def get_hook_bytecode(self) -> bytes:
        packed_exports = []
        for export in self.exports:
            # addr = self.alloc(export[1])
            addr = self.hook_handler.process.allocate(export[1])
            setattr(self, export[0], addr)
            packed_addr = struct.pack("<Q", addr)
            packed_exports.append((export[0], packed_addr))

        bytecode = await self.bytecode_generator(packed_exports)

        return_addr = self.jump_address + self.instruction_length

        relitive_return_jump = return_addr - (self.hook_address + len(bytecode)) - 5
        packed_relitive_return_jump = struct.pack("<i", relitive_return_jump)

        bytecode += b"\xE9" + packed_relitive_return_jump

        return bytecode

    async def unhook(self):
        await super().unhook()
        for export in self.exports:
            if getattr(self, export[0], None):
                await self.free(getattr(self, export[0]))


class PlayerHook(SimpleHook):
    pattern = rb"\xF2\x0F\x10\x40\x58\xF2"
    exports = [("player_struct", 8)]

    async def bytecode_generator(self, packed_exports):
        # We use ecx bc we want 4 bytes only
        bytecode = (
            b"\x51"  # push rcx
            b"\x8B\x88\x74\x04\x00\x00"  # mov ecx,[rax+474]
            # check if player
            b"\x83\xF9\x08"  # cmp ecx,08
            b"\x59"  # pop rcx
            b"\x0F\x85\x0A\x00\x00\x00"  # jne 10 down
            # mov(abs) [addr], rax
            b"\x48\xA3" + packed_exports[0][1] +
            # original code
            b"\xF2\x0F\x10\x40\x58"  # movsd xxmo,[rax+58]
        )
        return bytecode


class PlayerStatHook(SimpleHook):
    pattern = rb"\x2B\xD8\xB8....\x0F\x49\xC3\x48\x83\xC4\x20\x5B\xC3"
    instruction_length = 7
    exports = [("stat_addr", 8)]
    noops = 2

    async def bytecode_generator(self, packed_exports):
        # fmt: off
        bytecode = (
                b"\x50"  # push rax
                b"\x48\x89\xC8"  # mov rax, rcx
                b"\x48\xA3" + packed_exports[0][1] +  # mov qword ptr [stat_export], rax
                b"\x58"  # pop rax
                # original code
                b"\x2B\xD8"  # sub ebx, eax
                b"\xB8\x00\x00\x00\x00"  # mov eax, 0
        )
        # fmt: on
        return bytecode


class QuestHook(SimpleHook):
    pattern = rb"\xF3\x41\x0F\x10.\xFC\x0C\x00\x00\xF3\x0F\x11"
    exports = [("cord_struct", 4)]
    noops = 4

    async def bytecode_generator(self, packed_exports):
        # fmt: off
        bytecode = (
                b"\x50"  # push rax
                b"\x49\x8D\x87\xFC\x0C\x00\x00"  #lea rax,[r15+00000CFC]

                b"\x48\xA3" + packed_exports[0][1] +  # mov [export],rax
                b"\x58"  # pop rax
                b"\xF3\x41\x0F\x10\x87\xFC\x0C\x00\x00"  # original code 
        )
        # fmt: on
        return bytecode


class ClientHook(SimpleHook):
    pattern = (
        rb"\x18\x48......\x48\x8B\x7C\x24\x38\x48\x85\xFF\x74\x29\x8B\xC6\xF0\x0F\xC1\x47\x08\x83\xF8\x01\x75\x1D"
        rb"\x48\x8B\x07\x48\x8B\xCF\xFF\x50\x08\xF0\x0F\xC1\x77\x0C"
    )
    exports = [("current_client_addr", 8)]
    instruction_length = 7
    noops = 2

    # this is because the 18 byte at the start was tacked on
    async def get_jump_address(self, pattern: bytes, module: str = None) -> int:
        """
        gets the address to write jump at
        """
        jump_address = await self.pattern_scan(pattern, module=module)
        return jump_address + 1

    async def bytecode_generator(self, packed_exports):
        # fmt: off
        bytecode = (
                # We use rax bc we're using movabs
                b"\x50"  # push rax
                b"\x48\x8B\xC7"  # mov rax,rdi
                b"\x48\xA3" + packed_exports[0][1] +  # mov [current_client], rax
                b"\x58"  # pop rax
                b"\x48\x8B\x9B\xC0\x01\x00\x00"  # original instruction
        )
        # fmt: on

        return bytecode


class RootWindowHook(SimpleHook):
    pattern = rb".......\x48\x8B\x01.......\xFF\x50\x70\x84"
    instruction_length = 7
    noops = 2
    exports = [("current_root_window_addr", 8)]

    async def bytecode_generator(self, packed_exports):
        # fmt: off
        bytecode = (
            b"\x50"  # push rax
            b"\x49\x8B\x85\xD8\x00\x00\x00"  # mov rax,[r13+D8]
            b"\x48\xA3" + packed_exports[0][1] +  # mov [current_root_window_addr], rax
            b"\x58"  # pop rax
            b"\x49\x8B\x8D\xD8\x00\x00\x00"  # original instruction
        )
        # fmt: on

        return bytecode


class RenderContextHook(SimpleHook):
    pattern = rb"..................\xF3\x41\x0F\x10\x28\xF3\x0F\x10\x56\x04\x48\x63\xC1"
    instruction_length = 9
    noops = 4
    exports = [("current_render_context_addr", 8)]

    async def bytecode_generator(self, packed_exports):
        # fmt: off
        bytecode = (
            b"\x50"  # push rax
            b"\x48\x89\xd8"  # mov rax,rbx
            b"\x48\xA3" + packed_exports[0][1] +  # mov [current_ui_scale_addr],rax
            b"\x58"  # pop rax
            b"\xF3\x44\x0F\x10\x8B\x98\x00\x00\x00"  # original instruction
        )
        # fmt: on

        return bytecode


class MovementTeleportHook(SimpleHook):
    pattern = rb"\x57\x48\x83\xEC.\x48\x8B\x99...." \
              rb"\x48\x85\xDB\x74.\x4C\x8B\x43.\x48\x8B\x5B"\
              rb".\x48\x85\xDB\x74.\xF0\xFF\x43.\x4D\x85" \
              rb"\xC0\x74.\xF2\x0F\x10\x02\xF2\x41\x0F\x11\x40" \
              rb".\x8B\x42.\x41\x89\x40.\x41\xC6\x80."

    instruction_length = 5
    noops = 0
    # position vector = 12 + 1 for update bool + 8 for target object address
    exports = [("teleport_helper", 21)]

    _old_jes_bytes = None
    _old_collision_jes_bytes = None
    _collision_je_addrs = None
    _old_je_page_protection = None

    def _set_page_protection(self, address: int, protections: int, size: int = 24) -> int:
        old_protection = ctypes.wintypes.DWORD()
        target_address_passable = ctypes.c_uint64(address)

        result = kernel32.VirtualProtectEx(
            self.hook_handler.process.process_handle,
            target_address_passable,
            size,
            protections,
            ctypes.byref(old_protection),
        )

        if result == 0:
            raise RuntimeError(f"Movement teleport virtual protect returned 0 result={result}")

        return old_protection.value

    async def _wait_for_update_bool_unset_with_timeout(self):
        async def _inner():
            while True:
                should_update = await self.hook_handler.client._teleport_helper.should_update()

                if should_update is False:
                    return

                await asyncio.sleep(0.2)

        with suppress(asyncio.TimeoutError):
            return await asyncio.wait_for(_inner(), 5)

    async def prehook(self):
        jes = await self.hook_handler.client._get_je_instruction_forward_backwards()

        target_address = jes[0]

        inside_event_je_addr = await self.pattern_scan(
            rb"\x74.\xF3\x0F\x10\x55\xA8",
            module="WizardGraphicalClient.exe",
        )
        
        event_dispatch_je_addr = await self.pattern_scan(
            rb"\x74.\xF3\x0F\x10\x44\x24\x54\xF3\x0F",
            module="WizardGraphicalClient.exe",
        )

        old_inside_event_je_bytes = await self.read_bytes(inside_event_je_addr, 2)
        old_event_dispatch_je_addr = await self.read_bytes(event_dispatch_je_addr, 2)

        self._collision_je_addrs = (inside_event_je_addr, event_dispatch_je_addr)
        self._old_collision_jes_bytes = (old_inside_event_je_bytes, old_event_dispatch_je_addr)

        for addr in self._collision_je_addrs:
            await self.write_bytes(addr, b"\x90\x90")

        # 0x40 is read, write, execute
        self._old_je_page_protection = self._set_page_protection(target_address, 0x40)

    async def bytecode_generator(self, packed_exports):
        packed_should_update = bytearray(packed_exports[0][1])
        packed_should_update[0] += 12

        packed_z = bytearray(packed_exports[0][1])
        packed_z[0] += 8

        packed_target_addr = bytearray(packed_exports[0][1])
        packed_target_addr[0] += 13

        jes = await self.hook_handler.client._get_je_instruction_forward_backwards()

        jes_and_bytes = await self.hook_handler.read_bytes(jes[0], 8)
        jes_cmp_bytes = await self.hook_handler.read_bytes(jes[1], 8)

        self._old_jes_bytes = (jes_and_bytes, jes_cmp_bytes)

        packed_jes_and = struct.pack("<Q", jes[0])
        packed_jes_cmp = struct.pack("<Q", jes[1])

        # fmt: off
        bytecode = (
            b"\x50"  # push rax
            # b"\x48\x8B\x81\xA0\x01\x00\x00"  # mov rax,[rcx+1A0]
            # b"\x48\x85\xC0"  # test rax,rax
            b"\x48\xa1" + packed_target_addr +  # mov rax,[target_object_addr]
            b"\x48\x39\xC1"  # cmp rcx,rax
            b"\x58"  # pop rax
            b"\x0F\x84\x05\x00\x00\x00"  # je down 5 (local client object)
            b"\xE9\x6E\x00\x00\x00"  # jmp ( not local client object)
            b"\x50"  # push rax
            b"\xA0" + packed_should_update +  # mov al,[should_update_bool]
            b"\x84\xC0"  # test al,al (test if should_update is True)
            b"\x58"  # pop rax
            b"\x0F\x85\x05\x00\x00\x00"  # jne 5 (should_update is True)
            b"\xE9\x56\x00\x00\x00"  # jmp (should_update is False)
            b"\x50"  # push rax
            b"\x48\xA1" + packed_exports[0][1] +  # mov rax, [new_pos]
            b"\x48\x89\x02"  # mov[rdx], rax
            b"\xA1" + packed_z +  # mov eax, [7FF7E5541010]
            b"\x89\x42\x08"  # mov[rdx+08], eax
            b"\x48\xB8\x00\x00\x00\x00\x00\x00\x00\x00"  # mov rax,0000000000000000
            b"\xA2" + packed_should_update +  # mov [should_update_bool],al
            b"\x48\xB8" + jes_and_bytes +
            b"\x48\xA3" + packed_jes_and +
            b"\x48\xB8" + jes_cmp_bytes +
            b"\x48\xA3" + packed_jes_cmp +
            b"\x58" # pop rax
            b"\x57" # push rdi (original bytes)
            b"\x48\x83\xEC\x20" # sub rsp,20 (original bytes)
        )
        # fmt: on

        return bytecode

    async def hook(self):
        """
        Writes jump_bytecode to jump address and hook bytecode to hook address
        """
        pattern, module = await self.get_pattern()

        self.jump_address = await self.get_jump_address(pattern, module=module)
        self.hook_address = await self.get_hook_address(200)

        logger.debug(f"Got hook address {self.hook_address} in {type(self)}")
        logger.debug(f"Got jump address {self.jump_address} in {type(self)}")

        self.hook_bytecode = await self.get_hook_bytecode()
        self.jump_bytecode = await self.get_jump_bytecode()

        logger.debug(f"Got hook bytecode {self.hook_bytecode} in {type(self)}")
        logger.debug(f"Got jump bytecode {self.jump_bytecode} in {type(self)}")

        self.jump_original_bytecode = await self.read_bytes(
            self.jump_address, len(self.jump_bytecode)
        )

        logger.debug(
            f"Got jump original bytecode {self.jump_original_bytecode} in {type(self)}"
        )

        await self.prehook()

        await self.write_bytes(self.hook_address, self.hook_bytecode)
        await self.write_bytes(self.jump_address, self.jump_bytecode)

        await self.posthook()

    async def unhook(self):
        # with suppress(ExceptionalTimeout):
        #     await maybe_wait_for_value_with_timeout(
        #         self.hook_handler.client._teleport_helper.should_update,
        #         value=False,
        #         timeout=0.5,
        #     )

        # await wait_for_value(
        #     self.hook_handler.client._teleport_helper.should_update,
        #     False,
        #     ignore_errors=False,
        # )

        await self._wait_for_update_bool_unset_with_timeout()

        await super().unhook()

        if self._old_jes_bytes is None:
            return

        jes = await self.hook_handler.client._get_je_instruction_forward_backwards()

        for je, je_bytes in zip(jes, self._old_jes_bytes):
            await self.hook_handler.write_bytes(je, je_bytes)

        for addr, old_bytes in zip(self._collision_je_addrs, self._old_collision_jes_bytes):
            await self.write_bytes(addr, old_bytes)

        self._set_page_protection(jes[0], self._old_je_page_protection)


class DropsToggleHook(SimpleHook):
    pattern = rb"\x4C\x8B\xDC\x48\x83\xEC\x68\x48\x8B\x05...." \
              rb"\x48\x33\xC4\x48\x89\x44\x24.\x48\x8D\x05...."

    instruction_length = 7
    exports = [("disable_drops_bool", 1)]
    noops = 2

    async def bytecode_generator(self, packed_exports):
        return (
            b"\x50" # push rax
            b"\xA0" + packed_exports[0][1] + # mov al,[disable_drops_bool]
            b"\x84\xC0" # test al,al
            b"\x58" # pop rax
            b"\x0F\x84\x04\x00\x00\x00" # je down 4
            b"\x48\x31\xC0" # xor rax,rax
            b"\xC3" # ret
            b"\x4C\x8B\xDC" # mov r11,rsp (original bytes)
            b"\x48\x83\xEC\x68" # sub rsp,68 (original bytes)
        )


# TODO: fix this hacky class
class User32GetClassInfoBaseHook(AutoBotBaseHook):
    """
    Subclass of MemoryHook that uses the user32.GetClassInfoExA for bytes so addresses arent huge
    """

    AUTOBOT_PATTERN = (
        rb"\x48\x89\x5C\x24\x20\x55\x56\x57\x41\x54\x41\x55\x41\x56\x41\x57........"
        rb"\x48......\x48\x8B\x05.+\x48\x33\xC4.+\x48\x8B\xDA\x4C"
    )
    # rounded down
    AUTOBOT_SIZE = 1200
    
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._hooked_instances = 0
        # How far into the function we are
        self._autobot_bytes_offset = 0 
        self._autobot_addr = None
        self._autobot_original_bytes = None

    async def alloc(self, size: int) -> int:
        if self._autobot_addr is None:
            addr = await self.get_address_from_symbol("user32.dll", "GetClassInfoExA")
            # this is so all instances have the address
            self._autobot_addr = addr

        if self._autobot_bytes_offset + size > self.AUTOBOT_SIZE:
            raise RuntimeError(
                "Somehow used the entirety of the GetClassInfoExA function"
            )

        if self._autobot_original_bytes is None:
            self._autobot_original_bytes = await self.read_bytes(
                self._autobot_addr, self.AUTOBOT_SIZE
            )
            # this is so instructions don't collide
            await self.write_bytes(self._autobot_addr, b"\x00" * self.AUTOBOT_SIZE)

        addr = self._autobot_addr + self._autobot_bytes_offset
        self._autobot_bytes_offset += size

        return addr

    async def hook(self) -> Any:
        self._hooked_instances += 1
        return await super().hook()

    async def unhook(self):
        self._hooked_instances -= 1
        await self.write_bytes(self.jump_address, self.jump_original_bytecode)

        if self._hooked_instances == 0:
            await self.write_bytes(self._autobot_addr, self._autobot_original_bytes)
            self._autobot_bytes_offset = 0


class MouselessCursorMoveHook(User32GetClassInfoBaseHook):
    def __init__(self, memory_handler, hook_cache = {}):
        super().__init__(memory_handler, hook_cache=hook_cache)
        self.mouse_pos_addr = None

        self.toggle_bool_addrs = ()
        self.set_cursor_pos = None

    async def hook(self):
        """
        Writes jump_bytecode to jump address and hook bytecode to hook address
        """
        self._hooked_instances += 1

        self.jump_address = await self.get_jump_address()
        self.hook_address = await self.get_hook_address(50)

        logger.debug(f"Got hook address {self.hook_address} in {type(self)}")
        logger.debug(f"Got jump address {self.jump_address} in {type(self)}")

        self.hook_bytecode = await self.get_hook_bytecode()
        self.jump_bytecode = await self.get_jump_bytecode()

        logger.debug(f"Got hook bytecode {self.hook_bytecode} in {type(self)}")
        logger.debug(f"Got jump bytecode {self.jump_bytecode} in {type(self)}")

        self.jump_original_bytecode = await self.read_bytes(
            self.jump_address, len(self.jump_bytecode)
        )

        logger.debug(
            f"Got jump original bytecode {self.jump_original_bytecode} in {type(self)}"
        )

        await self.prehook()

        await self.write_bytes(self.hook_address, self.hook_bytecode)
        await self.write_bytes(self.jump_address, self.jump_bytecode)

        await self.posthook()

    async def posthook(self):
        bool_one_address = None
        if not self._is_cached("bool_one_address"):
            if a := await self.pattern_scan(
                rb"\x00\xFF\x50\x18\x66\xC7", module="WizardGraphicalClient.exe"
            ):
                self._cache("bool_one_address", a)
                bool_one_address = a
        else:
            bool_one_address = self._get_cached("bool_one_address")

        bool_two_address = None
        if not self._is_cached("bool_two_address"):
            if a := await self.pattern_scan(
                rb"\xC6\x86...\x00\x00\x33\xFF\x89",
                module="WizardGraphicalClient.exe",
            ):
                self._cache("bool_two_address", a)
                bool_two_address = a
        else:
            bool_two_address = self._get_cached("bool_two_address")

        if bool_one_address is None or bool_two_address is None:
            raise RuntimeError("toogle bool address pattern failed")

        # bool is 6 away from pattern target
        bool_two_address += 6

        self.toggle_bool_addrs = (bool_one_address, bool_two_address)

        await self.write_bytes(bool_one_address, b"\x01")
        await self.write_bytes(bool_two_address, b"\x01")

        set_cursor_pos = None
        if not self._is_cached("SetCursorPos"):
            if a := await self.get_address_from_symbol("user32.dll", "SetCursorPos"):
                self._cache("SetCursorPos", a)
                set_cursor_pos = a
        else:
            set_cursor_pos = self._get_cached("SetCursorPos")
        self.set_cursor_pos = (set_cursor_pos, await self.read_bytes(set_cursor_pos, 6))

        # ret + 5 noops
        await self.write_bytes(set_cursor_pos, b"\xC3" + (b"\x90" * 5))

    async def set_mouse_pos_addr(self):
        if not self._is_cached("mouse_pos_addr"):
            self.mouse_pos_addr = await self.allocate(8)
            self._cache("mouse_pos_addr", self.mouse_pos_addr)
        else:
            self.mouse_pos_addr = self._get_cached("mouse_pos_addr")

    async def get_jump_address(self) -> int:
        """
        gets the address to write jump at
        """
        if not self._is_cached("GetCursorPos"):
            if a := await self.get_address_from_symbol("user32.dll", "GetCursorPos"):
                self._cache("GetCursorPos", a)
                return a
        else:
            return self._get_cached("GetCursorPos")

    async def get_jump_bytecode(self) -> bytes:
        # distance = end - start
        distance = self.hook_address - self.jump_address
        relitive_jump = distance - 5  # size of this line
        packed_relitive_jump = struct.pack("<i", relitive_jump)
        return b"\xE9" + packed_relitive_jump

    async def get_hook_bytecode(self) -> bytes:
        await self.set_mouse_pos_addr()
        packed_mouse_pos_addr = struct.pack("<Q", self.mouse_pos_addr)

        # fmt: off
        bytecode = (
                b"\x50"  # push rax
                b"\x48\xA1" + packed_mouse_pos_addr +  # mov rax, mouse_pos
                b"\x48\x89\x01"  # mov [rcx], rax
                b"\x58"  # pop rax
                b"\xC3"  # ret
        )
        # fmt: on

        return bytecode

    async def unhook(self):
        await super().unhook()
        for bool_addr in self.toggle_bool_addrs:
            await self.write_bytes(bool_addr, b"\x00")

        if self.set_cursor_pos:
            set_cursor_pos, set_cursor_pos_bytes = self.set_cursor_pos
            await self.write_bytes(set_cursor_pos, set_cursor_pos_bytes)


class ChatHook(SimpleHook):
    """Captures incoming directed chat message data.

    Binary RE source: FUN_1416dbb30 (r794925) — MSG_DirectedChat handler.

    Hooks AFTER the handler has extracted all DML fields, at the point
    where GetWideString just returned the Message wstring pointer in RAX
    and SourceID is already stored at [RBP-0x80].

    Hook point: func+0x379 (LEA RCX,[RBP-0x8], 4 bytes)
    At this point:
      RAX = pointer to std::wstring (Message from GetWideString)
      [RBP-0x80] = SourceID (GID, 8 bytes)
      RSI = chat owner object (saved from RCX at func entry)

    The hook copies SourceID and Message text to persistent exports
    and increments a counter so Python can detect new messages.

    Pattern: uses the function prologue (same as before) to find the
    function, then hooks at func+0x379 instead of func+0x00.
    """
    pattern = (
        rb"\x48\x89\x5C\x24\x18"           # MOV [RSP+18h], RBX
        rb"\x48\x89\x74\x24\x20"           # MOV [RSP+20h], RSI
        rb"\x55\x57\x41\x56"               # PUSH RBP / PUSH RDI / PUSH R14
        rb"\x48\x8D\xAC\x24\x40\xFF\xFF\xFF"  # LEA RBP, [RSP-0C0h]
        rb"\x48\x81\xEC\xC0\x01\x00\x00"   # SUB RSP, 1C0h
        rb"\x48\x8B\x05...."               # MOV RAX, [rip+??] (cookie)
        rb"\x48\x33\xC4"                    # XOR RAX, RSP
        rb"\x48\x89\x85\xB0\x00\x00\x00"   # MOV [RBP+0B0h], RAX
        rb"\x48\x8B\xFA"                    # MOV RDI, RDX
        rb"\x48\x8B\xF1"                    # MOV RSI, RCX
        rb"\x45\x33\xF6"                    # XOR R14D, R14D
    )
    exports = [
        ("chat_owner_addr", 8),        # persistent: chat owner (RSI)
        ("recv_source_gid", 8),        # sender's GID
        ("recv_message_buf", 160),     # message text (UTF-16LE, 80 wchars max)
        ("recv_message_len", 8),       # wchar count
        ("recv_counter", 8),           # increments on each message
    ]
    # Hook at func+0x379: LEA RCX,[RBP-0x8] (4 bytes) + CMP RCX,RAX (3 bytes)
    # Both instructions must be replaced because a JMP is 5 bytes and
    # the LEA is only 4 — the 5th byte would corrupt the CMP.
    _HOOK_OFFSET = 0x379
    instruction_length = 7   # 4 (LEA) + 3 (CMP) = 7 bytes
    noops = 2                # 7 - 5 = 2 padding NOPs

    # The prologue pattern returns ~10 results from the pattern scan.
    # Of those ~10 results, only the DirectedChat handler has
    # MOV dword ptr [RBP-10h], 9 at func+0x7E. So we override
    # get_jump_address to probe each match and find the correct one.
    _DISAMBIG_OFFSET = 0x7E
    _DISAMBIG_BYTES = b"\xC7\x45\xF0\x09\x00\x00\x00"

    async def get_jump_address(self, pattern: bytes, module: str = None) -> int:
        candidates = await self.pattern_scan(
            pattern, module=module, return_multiple=True
        )
        if isinstance(candidates, int):
            candidates = [candidates]

        for addr in candidates:
            probe = await self.read_bytes(
                addr + self._DISAMBIG_OFFSET, len(self._DISAMBIG_BYTES)
            )
            if probe == self._DISAMBIG_BYTES:
                # Hook at func+0x379, not at the prologue
                return addr + self._HOOK_OFFSET

        from wizwalker import PatternFailed
        raise PatternFailed(
            f"ChatHook: pattern matched {len(candidates)} functions but none "
            f"had type=9 marker at offset +{self._DISAMBIG_OFFSET:#x}"
        )

    async def hook(self):
        """Override to allocate enough space for the extraction bytecode."""
        pattern, module = await self.get_pattern()

        self.jump_address = await self.get_jump_address(pattern, module=module)
        self.hook_address = await self.get_hook_address(200)

        logger.debug(f"Got hook address {self.hook_address} in {type(self)}")
        logger.debug(f"Got jump address {self.jump_address} in {type(self)}")

        self.hook_bytecode = await self.get_hook_bytecode()
        self.jump_bytecode = await self.get_jump_bytecode()

        self.jump_original_bytecode = await self.read_bytes(
            self.jump_address, len(self.jump_bytecode)
        )

        await self.prehook()
        await self.write_bytes(self.hook_address, self.hook_bytecode)
        await self.write_bytes(self.jump_address, self.jump_bytecode)
        await self.posthook()

    async def bytecode_generator(self, packed_exports):
        chat_owner  = packed_exports[0][1]
        source_gid  = packed_exports[1][1]
        message_buf = packed_exports[2][1]
        message_len = packed_exports[3][1]
        counter     = packed_exports[4][1]

        # At hook point (func+0x379), register state:
        #   RAX = wstring pointer (Message from GetWideString)
        #   [RBP-0x80] = SourceID GID (8 bytes)
        #   RSI = chat owner (saved from param_1 at func entry)

        # fmt: off
        preamble = (
            # Save volatile registers
            b"\x51"                              # push rcx
            b"\x52"                              # push rdx
            b"\x41\x50"                          # push r8
            b"\x41\x51"                          # push r9

            # RAX = wstring ptr from GetWideString

            # Save chat owner (RSI → export)
            b"\x50"                              # push rax
            b"\x48\x89\xF0"                      # mov rax, rsi
            b"\x48\xA3" + chat_owner +           # mov [chat_owner], rax
            b"\x58"                              # pop rax

            # Copy SourceID ([RBP-0x80] → export)
            b"\x50"                              # push rax
            b"\x48\x8B\x45\x80"                 # mov rax, [rbp-0x80]
            b"\x48\xA3" + source_gid +           # mov [recv_source_gid], rax
            b"\x58"                              # pop rax

            # Save message length ([rax+0x10] → export)
            b"\x50"                              # push rax
            b"\x48\x8B\x40\x10"                 # mov rax, [rax+0x10]
            b"\x48\xA3" + message_len +          # mov [recv_message_len], rax
            b"\x58"                              # pop rax

            # Get wstring data pointer into RDX
            b"\x48\x8B\xD0"                      # mov rdx, rax (inline)
            b"\x48\x83\x78\x18\x08"             # cmp [rax+0x18], 8
            b"\x72\x03"                          # jb .copy
            b"\x48\x8B\x10"                      # mov rdx, [rax] (heap)
        )

        # Copy 160 bytes (20 x 8-byte chunks) from RDX to export
        # Use R8 as dest, R9 as counter, RCX as temp value
        copy_loop = (
            b"\x49\xB8" + message_buf +          # mov r8, &message_buf
            b"\x41\xB9\x14\x00\x00\x00"         # mov r9d, 20 (iterations)
            # .loop:
            b"\x48\x8B\x0A"                      # mov rcx, [rdx]
            b"\x49\x89\x08"                      # mov [r8], rcx
            b"\x48\x83\xC2\x08"                 # add rdx, 8
            b"\x49\x83\xC0\x08"                 # add r8, 8
            b"\x41\xFF\xC9"                      # dec r9d
            b"\x75\xED"                          # jnz .loop (-19 bytes back)
        )

        # Increment message counter
        inc_counter = (
            b"\x50"                              # push rax
            b"\x48\xA1" + counter +              # mov rax, [recv_counter]
            b"\x48\xFF\xC0"                      # inc rax
            b"\x48\xA3" + counter +              # mov [recv_counter], rax
            b"\x58"                              # pop rax
        )

        # Restore registers
        restore = (
            b"\x41\x59"                          # pop r9
            b"\x41\x58"                          # pop r8
            b"\x5A"                              # pop rdx
            b"\x59"                              # pop rcx
        )

        # Original instructions: LEA RCX,[RBP-0x8] (4) + CMP RCX,RAX (3) = 7 bytes
        original = await self.read_bytes(self.jump_address, 7)

        bytecode = preamble + copy_loop + inc_counter + restore + original
        # fmt: on

        return bytecode


class ChatSendHook(SimpleHook):
    """Main-thread action hook for social operations.

    Hooks the game's main loop at the shutdown_signal check:
      CMP [RDI+0x211B8], BL  (RDI = GameClient)

    This runs every frame on the main game thread. Each iteration
    the hook checks trigger flags. When Python sets a trigger, the
    hook calls the corresponding game function on the main thread
    where UI updates and game state access are safe.

    Supported actions:
      send_trigger=1  -> call send_directed_chat(GameClient, &send_struct)
      buddy_trigger=1 -> call buddy_request_add(&buddy_obj)

    Python writes data to the export buffer, sets the trigger to 1,
    then polls until the hook clears it back to 0 (action complete).

    Current chat limitation: messages must be <=7 wchars (SSO inline).
    """
    # Pattern: shutdown_signal CMP in the main game loop, followed
    # by JZ (loop back), CALL, and CMP EAX,0x64 (return check).
    # The displacement in the CMP and the JZ offset are wildcarded
    # for patch survivability.
    pattern = (
        rb"\x38\x9F....\x74.\xE8....\x83\xF8\x64\x0F\x8F"
    )
    instruction_length = 6  # CMP [RDI+offset], BL = 6 bytes
    noops = 0
    exports = [
        ("send_trigger", 1),      # chat: 1 = send requested, 0 = idle
        ("send_struct", 0x28),    # chat: DirectedChatRequest (40 bytes)
        ("buddy_trigger", 1),     # buddy: 1 = add requested, 0 = idle
        ("buddy_obj", 0xE8),      # buddy: fake object, GID at +0xE0
    ]

    # --- Send directed chat function ---
    _SEND_PATTERN = (
        rb"\x48\x89\x5C\x24\x18"
        rb"\x55\x56\x57"
        rb"\x48\x8D\xAC\x24\x30\xFF\xFF\xFF"
        rb"\x48\x81\xEC\xD0\x01\x00\x00"
        rb"\x48\x8B\x05...."
        rb"\x48\x33\xC4"
        rb"\x48\x89\x85\xC0\x00\x00\x00"
        rb"\x48\x8B\xDA"
        rb"\x48\x8B\xF9"
    )
    _SEND_DISAMBIG_OFFSET = 0x33
    _SEND_DISAMBIG_BYTES = b"\x48\x83\xC2\x20"

    # --- Buddy add function: FUN_141710e10 ---
    # This is the clean buddy add that takes (BuddyListManager, target_gid).
    # The key differentiator from FUN_1412536b0 (dialog callback) is
    # MOV [RSP+20h], RDX at func+0x1E — it saves param_2 (the GID).
    # FUN_1412536b0 doesn't have this instruction because it only
    # takes one parameter.
    _BUDDY_PATTERN = (
        rb"\x48\x81\xEC\xA0\x00\x00\x00"       # SUB RSP, 0xA0
        rb"\x48\x8B\x05...."                   # MOV RAX, [cookie]
        rb"\x48\x33\xC4"                        # XOR RAX, RSP
        rb"\x48\x89\x84\x24\x90\x00\x00\x00"  # MOV [RSP+90h], RAX
        rb"\x48\x8B\xD9"                        # MOV RBX, RCX
        rb"\x48\x89\x54\x24\x20"               # MOV [RSP+20h], RDX (saves param_2)
        rb"\xBA\x10\x00\x00\x00"               # MOV EDX, 0x10
        rb"\x48\x8D\x4C\x24\x30"               # LEA RCX, [RSP+30h]
    )
    # MOVUPS at func+0x72 loads "MSG_BUDDYREQUESTADD". Pattern starts
    # at func+2 (skips PUSH RBX), so disambig offset is 0x72 - 2.
    _BUDDY_DISAMBIG_OFFSET = 0x70
    _BUDDY_DISAMBIG_BYTES = b"\x0F\x10\x05"

    async def _resolve_send_func(self) -> int:
        """Resolve FUN_1416e5ac0 via pattern scan + disambiguation."""
        candidates = await self.pattern_scan(
            self._SEND_PATTERN,
            module="WizardGraphicalClient.exe",
            return_multiple=True,
        )
        if isinstance(candidates, int):
            candidates = [candidates]

        for addr in candidates:
            probe = await self.read_bytes(
                addr + self._SEND_DISAMBIG_OFFSET,
                len(self._SEND_DISAMBIG_BYTES),
            )
            if probe == self._SEND_DISAMBIG_BYTES:
                return addr

        from wizwalker import PatternFailed
        raise PatternFailed(
            f"ChatSendHook: send function pattern matched "
            f"{len(candidates)} but none had ADD RDX,0x20"
        )

    async def _resolve_buddy_add_func(self) -> int:
        """Resolve FUN_141710e10 via pattern scan + string verification.

        Multiple buddy functions (Add, Drop, etc.) share the same prologue
        and all have MOVUPS at the same offset. We disambiguate by reading
        the RIP-relative target of the MOVUPS and verifying it points to
        the "MSG_BUDDYREQUESTADD" string (starts with 'M','S','G','_','B',
        'U','D','D','Y','R','E','Q','U','E','S','T','A','D','D').
        """
        candidates = await self.pattern_scan(
            self._BUDDY_PATTERN,
            module="WizardGraphicalClient.exe",
            return_multiple=True,
        )
        if isinstance(candidates, int):
            candidates = [candidates]

        for addr in candidates:
            probe = await self.read_bytes(
                addr + self._BUDDY_DISAMBIG_OFFSET,
                len(self._BUDDY_DISAMBIG_BYTES),
            )
            if probe != self._BUDDY_DISAMBIG_BYTES:
                continue

            # Read the RIP-relative offset from the MOVUPS instruction.
            # MOVUPS XMM0,[rip+disp32] = 0F 10 05 <disp32> (7 bytes)
            movups_addr = addr + self._BUDDY_DISAMBIG_OFFSET
            disp32_bytes = await self.read_bytes(movups_addr + 3, 4)
            disp32 = struct.unpack("<i", disp32_bytes)[0]
            string_addr = (movups_addr + 7) + disp32

            # Verify it's "MSG_BUDDYREQUESTADD" (not DROP, ACCEPT, etc.)
            string_bytes = await self.read_bytes(string_addr, 19)
            if string_bytes == b"MSG_BUDDYREQUESTADD":
                return addr - 2  # pattern starts at func+2

        from wizwalker import PatternFailed
        raise PatternFailed(
            f"ChatSendHook: buddy add pattern matched "
            f"{len(candidates)} but none loaded MSG_BUDDYREQUESTADD"
        )

    async def hook(self):
        """Override to allocate enough space for the larger bytecode."""
        pattern, module = await self.get_pattern()

        self.jump_address = await self.get_jump_address(pattern, module=module)
        self.hook_address = await self.get_hook_address(300)

        logger.debug(f"Got hook address {self.hook_address} in {type(self)}")
        logger.debug(f"Got jump address {self.jump_address} in {type(self)}")

        self.hook_bytecode = await self.get_hook_bytecode()
        self.jump_bytecode = await self.get_jump_bytecode()

        self.jump_original_bytecode = await self.read_bytes(
            self.jump_address, len(self.jump_bytecode)
        )

        await self.prehook()
        await self.write_bytes(self.hook_address, self.hook_bytecode)
        await self.write_bytes(self.jump_address, self.jump_bytecode)
        await self.posthook()

    def _build_action_block(self, trigger_addr, save_restore, call_setup, clear_trigger):
        """Build a check-trigger + call + clear block with jz skip."""
        # Check trigger
        check = (
            b"\x50"                              # push rax
            b"\xA0" + trigger_addr +             # movabs al, [trigger]
            b"\x84\xC0"                          # test al, al
            b"\x58"                              # pop rax
            b"\x0F\x84" + b"\x00\x00\x00\x00"   # jz skip (patch below)
        )
        body = save_restore + call_setup + clear_trigger
        # Patch jz: skip over body
        jz_offset = 13  # position of 0F 84 in check block
        rel32 = len(body)
        patched = bytearray(check)
        struct.pack_into("<i", patched, jz_offset + 2, rel32)
        return bytes(patched) + body

    def _save_restore_regs(self, call_bytes, trigger_addr):
        """Wrap a call with register save/restore and trigger clear."""
        save = (
            b"\x50"                              # push rax
            b"\x51"                              # push rcx
            b"\x52"                              # push rdx
            b"\x41\x50"                          # push r8
            b"\x41\x51"                          # push r9
            b"\x41\x52"                          # push r10
            b"\x41\x53"                          # push r11
            b"\x48\x81\xEC\x28\x00\x00\x00"     # sub rsp, 0x28
        )
        restore = (
            b"\x48\x81\xC4\x28\x00\x00\x00"     # add rsp, 0x28
            b"\x41\x5B"                          # pop r11
            b"\x41\x5A"                          # pop r10
            b"\x41\x59"                          # pop r9
            b"\x41\x58"                          # pop r8
            b"\x5A"                              # pop rdx
            b"\x59"                              # pop rcx
            b"\x58"                              # pop rax
        )
        clear = (
            b"\x50"                              # push rax
            b"\x30\xC0"                          # xor al, al
            b"\xA2" + trigger_addr +             # movabs [trigger], al
            b"\x58"                              # pop rax
        )
        return save + call_bytes + restore, clear

    async def bytecode_generator(self, packed_exports):
        send_func = await self._resolve_send_func()
        buddy_func = await self._resolve_buddy_add_func()

        send_trigger = packed_exports[0][1]
        send_struct  = packed_exports[1][1]
        buddy_trigger = packed_exports[2][1]
        buddy_obj    = packed_exports[3][1]

        original_cmp = await self.read_bytes(self.jump_address, 6)

        q = lambda v: struct.pack("<Q", v)

        # --- Action 1: send directed chat ---
        chat_call = (
            b"\x48\x89\xF9" +                   # mov rcx, rdi (GameClient)
            b"\x48\xBA" + send_struct +          # movabs rdx, &send_struct
            b"\x48\xB8" + q(send_func) +         # movabs rax, send_func
            b"\xFF\xD0"                          # call rax
        )
        chat_body, chat_clear = self._save_restore_regs(chat_call, send_trigger)
        chat_block = self._build_action_block(
            send_trigger, chat_body, b"", chat_clear
        )

        # --- Action 2: buddy add ---
        # FUN_141710e10(BuddyListManager, target_gid_value)
        #   param_1 needs [+0x18] = GameClient pointer
        #   param_2 = raw GID value (not a pointer)
        # We use buddy_obj as a fake BuddyListManager, writing RDI
        # (GameClient from the game loop) into [buddy_obj+0x18] at
        # call time. The target GID was written by Python at +0xE0.
        buddy_call = (
            b"\x48\xB9" + buddy_obj +           # movabs rcx, &buddy_obj
            b"\x48\x89\x79\x18" +               # mov [rcx+0x18], rdi  (GameClient)
            b"\x48\x8B\x91\xE0\x00\x00\x00" +   # mov rdx, [rcx+0xE0]  (target GID)
            b"\x48\xB8" + q(buddy_func) +        # movabs rax, buddy_func
            b"\xFF\xD0"                          # call rax
        )
        buddy_body, buddy_clear = self._save_restore_regs(buddy_call, buddy_trigger)
        buddy_block = self._build_action_block(
            buddy_trigger, buddy_body, b"", buddy_clear
        )

        bytecode = chat_block + buddy_block + original_cmp
        return bytecode
