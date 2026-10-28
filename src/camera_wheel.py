"""Per-camera wheel limits, leaving wheel speed and follow-camera code intact."""

import asyncio
import ctypes
import struct

from wizwalker.constants import kernel32
from wizwalker.memory.hooks import MemoryHook


MODULE = "WizardGraphicalClient.exe"
# Check both clamp paths and their return points before patching.
PATTERN = (
    rb"\x80\xbe\xe8\x01\x00\x00\x00\x75\x65"
    rb"\xf3\x0f\x10\x05....\x0f\x2f\xc1\x76\x24"
    rb"\x48\x8d\x05....\x0f\x2f\x0d....\x48\x0f\x47\xc1\xeb\x17"
    rb"\x48\x8b\xae\x08\x01\x00\x00\xf0\xff\x43\x08\xe9...."
    rb"\x48\x8d\x05....\xf3\x0f\x10\x10\xf3\x0f\x11\x11"
    rb"\xf3\x0f\x10\x8e\x44\x01\x00\x00\x0f\x28\xc1\xf3\x0f\x58\xc2"
    rb"\xf3\x0f\x11\x86\x48\x01\x00\x00\xf3\x0f\x5c\xd1"
    rb"\xf3\x0f\x11\x96\x4c\x01\x00\x00\xeb\x27"
    rb"\xf3\x0f\x10\x86\x48\x01\x00\x00\x0f\x2f\xc1\x76\x16"
    rb"\x48\x8d\x05....\x0f\x2f\x0d....\x48\x0f\x47\xc1"
    rb"\xf3\x0f\x10\x00\xf3\x0f\x11\x01"
)
ORIGINAL = bytes.fromhex("80 be e8 01 00 00 00")


def jump(source, target):
    return b"\xe9" + struct.pack("<i", target - source - 5)


def build_code(address, site, config_pointer):
    """Clamp wheel input, then resume the original follow-range calculation.

    rsi = camera, rcx = distance target, config = {camera:u64, min:f32, max:f32}.
    """
    code = bytearray(b"\x50\x48\xa1" + struct.pack("<Q", config_pointer))  # save rax; load record
    code += b"\x48\x85\xc0"  # test rax,rax
    no_config = len(code)
    code += b"\x74\x00"
    code += b"\x48\x3b\x30"  # cmp rsi,[rax]
    wrong_camera = len(code)
    code += b"\x75\x00"
    code += bytes.fromhex("f3 0f 5f 48 08 f3 0f 5d 48 0c f3 0f 11 09")
    code += b"\x58"  # pop rax
    code += ORIGINAL  # preserve the game's alternate-camera flag
    alternate = len(code)
    code += b"\x0f\x85" + struct.pack("<i", site + 0x95 - (address + alternate + 6))
    code += b"\x48\x89\xc8"  # mov rax,rcx (source of bounded distance)
    code += jump(address + len(code), site + 0x41)
    fallback = len(code)
    code += b"\x58" + ORIGINAL
    code += jump(address + len(code), site + len(ORIGINAL))
    for branch in (no_config, wrong_camera):
        code[branch + 1] = fallback - branch - 2
    return bytes(code)


class CameraWheelHook(MemoryHook):
    def __init__(self, handler):
        super().__init__(handler)
        self._lock = asyncio.Lock()
        self._records = []
        self._config_pointer = None
        self._patch = None
        self.bounds = None
        self.camera_address = None

    async def _write_code(self, address, data):
        await self.write_bytes(address, data)
        if not kernel32.FlushInstructionCache(self.process.process_handle, ctypes.c_void_p(address), len(data)):
            raise OSError("Could not flush camera-wheel instruction cache")
        if await self.read_bytes(address, len(data)) != data:
            raise RuntimeError("Camera-wheel code verification failed")

    async def configure(self, camera_address, minimum, maximum):
        async with self._lock:
            if self.camera_address == camera_address and self.bounds == (minimum, maximum):
                return
            if self._patch is None:
                self.jump_address = await self.pattern_scan(PATTERN, module=MODULE)
                await self.hook_handler._check_for_autobot()
                self.hook_address = await self.hook_handler._allocate_autobot_bytes(128)
                # Aligned pointer, kept in the client's managed codecave.
                self._config_pointer = (self.hook_address + 119) & ~7
                await self.write_bytes(self._config_pointer, b"\0" * 8)
                code = build_code(self.hook_address, self.jump_address, self._config_pointer)
                if len(code) > self._config_pointer - self.hook_address:
                    raise RuntimeError("Camera-wheel hook exceeds allocation")
                await self._write_code(self.hook_address, code)
                patch = jump(self.jump_address, self.hook_address) + b"\x90\x90"
                if await self.read_bytes(self.jump_address, 7) != ORIGINAL:
                    raise RuntimeError("Camera-wheel instructions changed during installation")
                # Track the patch before writing so a failed write remains recoverable.
                self._patch = patch
                try:
                    await self._write_code(self.jump_address, patch)
                except BaseException:
                    await self._restore_code()
                    raise
            record = await self.allocate(16)
            self._records.append(record)
            await self.write_bytes(record, struct.pack("<Qff", camera_address, minimum, maximum))
            # Publish a complete record; keep old records alive for in-flight wheel events.
            await self.write_bytes(self._config_pointer, struct.pack("<Q", record))
            self.camera_address = camera_address
            self.bounds = (minimum, maximum)

    async def _restore_code(self):
        if self._patch is None:
            return
        current = await self.read_bytes(self.jump_address, 7)
        if any(c not in (o, p) for c, o, p in zip(current, ORIGINAL, self._patch)):
            raise RuntimeError("Camera-wheel code changed externally; refusing to overwrite it")
        await self._write_code(self.jump_address, ORIGINAL)
        self._patch = None

    async def unhook(self):
        async with self._lock:
            if self._config_pointer is not None:
                await self.write_bytes(self._config_pointer, b"\0" * 8)
            await self._restore_code()
            # Match WizWalker's grace period for in-flight hook execution.
            await asyncio.sleep(0.5)
            for record in self._records[:]:
                await self.free(record)
                self._records.remove(record)
            self.bounds = self.camera_address = None


async def wheel_bounds(camera):
    hook = camera.hook_handler._active_hooks.get(CameraWheelHook)
    if hook and hook.bounds and hook.camera_address == await camera.read_base_address():
        return hook.bounds
    return None


async def configure_wheel(camera, minimum, maximum):
    handler = camera.hook_handler
    hook = handler._active_hooks.get(CameraWheelHook)
    if hook is None:
        hook = CameraWheelHook(handler)
        handler._active_hooks[CameraWheelHook] = hook
    await hook.configure(await camera.read_base_address(), minimum, maximum)
