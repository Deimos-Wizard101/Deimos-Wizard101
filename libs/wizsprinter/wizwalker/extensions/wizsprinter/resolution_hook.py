"""In-process resolution forcing via WizWalker-style asm hooks.

Cross-process tools can resize the window and write the camera frustum, but they
CANNOT force the D3D backbuffer to a chosen size (that requires intercepting the
game's mode-set call and rewriting its width/height registers). This module does
that from inside the game process using WizWalker's hook framework, so Deimos can
force an arbitrary, crisp render resolution.

Two pattern-scanned asm hooks (build/ASLR-resilient):

* SetModeResHook — the engine's "set video mode" function:
      setMode(this /*rcx*/, width /*edx*/, height /*r8d*/, flags /*r9d*/, hwnd)
  When our control block's `enabled` flag is set, we overwrite edx/r8d with the
  forced width/height, so the device is (re)created at exactly that size.

* VideoManagerHook — the per-frame "process pending video-mode change" function.
  Its `this` (rcx) is the video manager, whose byte at +0x2229b is a pending-change
  flag the engine polls each frame. We capture that `this` pointer to an export so
  we can set the flag and trigger the apply on demand.

To force WxH: write {enabled, width, height} to the control block, then set the
manager's pending byte. The engine runs its own full apply on the game thread
(release -> setMode -> Reset); setMode's args come out as our WxH. Aspect (the 3D
projection) is corrected separately via the CamView frustum (see Deimos client
resizing) since it derives from the frustum, not the backbuffer.
"""
import struct

from wizwalker.memory.hooks import SimpleHook
from wizwalker.memory.memory_reader import Primitive

# Video-manager field offsets (this build of WizardGraphicalClient.exe).
MGR_PENDING_FLAG_OFF = 0x2229B  # byte: non-zero => apply pending video mode


class SetModeResHook(SimpleHook):
    """Override setMode's width (edx) / height (r8d) with a forced size."""

    # mov [rsp+8],rbx ; mov [rsp+20],r9d ; mov [rsp+18],r8d ; mov [rsp+10],edx ;
    # push rbp/rsi/rdi/r12/r13/r14/r15 ; sub rsp,0xB0
    pattern = (
        rb"\x48\x89\x5C\x24\x08\x44\x89\x4C\x24\x20\x44\x89\x44\x24\x18"
        rb"\x89\x54\x24\x10\x55\x56\x57\x41\x54\x41\x55\x41\x56\x41\x57"
        rb"\x48\x81\xEC\xB0\x00\x00\x00"
    )
    instruction_length = 5  # mov qword [rsp+8], rbx
    # control block: u32 enabled, u32 width, u32 height
    exports = [("control_block", 12)]

    async def bytecode_generator(self, packed_exports):
        ctrl = packed_exports[0][1]  # packed 8-byte address of control_block
        return (
            b"\x48\xB8" + ctrl          # mov rax, control_block
            + b"\x83\x38\x00"           # cmp dword [rax], 0     (enabled?)
            + b"\x74\x07"               # je +7  -> skip the two movs
            + b"\x8B\x50\x04"           # mov edx, [rax+4]       (forced width)
            + b"\x44\x8B\x40\x08"       # mov r8d, [rax+8]       (forced height)
            # ---- original overwritten instruction ----
            + b"\x48\x89\x5C\x24\x08"   # mov [rsp+8], rbx
        )


class VideoManagerHook(SimpleHook):
    """Capture the video-manager `this` (rcx) at the per-frame mode checker.

    The function was recompiled in a client update (2026-06) — new prologue, but
    same semantics: rcx = manager at entry, and it still polls the pending byte at
    +0x2229b. We anchor on the full prologue (frame setup + xmm spills + stack
    canary load) up to `mov rbx, rcx`; the rip-relative __security_cookie load's
    displacement is build-variable, so it is wildcarded.
    """

    # mov rax,rsp ; mov [rax+10],rbx ; mov [rax+18],rsi ; push rbp/rdi/r14 ;
    # lea rbp,[rax-0x78] ; sub rsp,0x160 ; movaps xmm6/7/8 ;
    # mov rax,[rip+cookie(wildcard)] ; xor rax,rsp ; mov [rbp+0x20],rax ; mov rbx,rcx
    pattern = (
        rb"\x48\x8B\xC4\x48\x89\x58\x10\x48\x89\x70\x18\x55\x57\x41\x56"
        rb"\x48\x8D\x68\x88\x48\x81\xEC\x60\x01\x00\x00"
        rb"\x0F\x29\x70\xD8\x0F\x29\x78\xC8\x44\x0F\x29\x40\xB8"
        rb"\x48\x8B\x05....\x48\x33\xC4\x48\x89\x45\x20\x48\x8B\xD9"
    )
    instruction_length = 7  # mov rax,rsp (3) ; mov [rax+0x10],rbx (4)
    noops = 2               # jmp rel32 is 5 bytes; pad the 7-byte hole with 2 NOPs
    exports = [("manager_ptr", 8)]

    async def bytecode_generator(self, packed_exports):
        mgr = packed_exports[0][1]  # packed 8-byte address of manager_ptr slot
        return (
            b"\x48\xB8" + mgr          # mov rax, manager_ptr  (our export slot)
            + b"\x48\x89\x08"          # mov [rax], rcx        (store the manager 'this')
            # ---- original overwritten instructions (rax recomputed by mov rax,rsp) ----
            + b"\x48\x8B\xC4"          # mov rax, rsp
            + b"\x48\x89\x58\x10"      # mov [rax+0x10], rbx
        )


class ResolutionForcer:
    """Installs the resolution asm hooks on a client and forces crisp resolutions.

    Usage::

        forcer = ResolutionForcer(client)
        await forcer.install()
        await forcer.force(1920, 1080)   # device re-created at 1920x1080
        ...
        await forcer.release()           # stop overriding (game keeps last size)
        await forcer.uninstall()         # remove hooks
    """

    def __init__(self, client):
        self.client = client
        self.hook_handler = client.hook_handler
        self._setmode = None
        self._vm = None

    @property
    def installed(self) -> bool:
        return self._setmode is not None

    async def install(self):
        if self.installed:
            return
        # Ensure the shared codecave region is prepared (idempotent).
        await self.hook_handler._check_for_autobot()
        # Track each hook the instant it installs so a failure mid-install still
        # gets cleaned up (a dangling jump to a freed codecave would crash the game).
        try:
            self._setmode = SetModeResHook(self.hook_handler)
            await self._setmode.hook()
            self._vm = VideoManagerHook(self.hook_handler)
            await self._vm.hook()
        except Exception:
            await self.uninstall()
            raise

    async def uninstall(self):
        for hook in (self._setmode, self._vm):
            if hook is not None:
                try:
                    await hook.unhook()
                except Exception:
                    pass
        self._setmode = None
        self._vm = None

    async def _manager_address(self) -> int:
        """The captured video-manager pointer (0 until the checker has run once)."""
        if self._vm is None:
            return 0
        try:
            return await self.hook_handler.read_typed(self._vm.manager_ptr, Primitive.int64)
        except Exception:
            return 0

    async def force(self, width: int, height: int) -> bool:
        """Force the render resolution to width x height (in-process, crisp).

        Arms the setMode override and triggers the engine's own apply. Returns
        True if the apply was triggered (manager captured), False otherwise.
        """
        if not self.installed:
            return False
        await self.hook_handler.write_bytes(
            self._setmode.control_block, struct.pack("<III", 1, int(width), int(height))
        )
        mgr = await self._manager_address()
        if not mgr:
            return False
        # Trigger the engine's per-frame apply.
        await self.hook_handler.write_bytes(mgr + MGR_PENDING_FLAG_OFF, b"\x01")
        return True

    async def release(self):
        """Stop overriding setMode (the device keeps whatever size it last got)."""
        if self._setmode is not None:
            try:
                await self.hook_handler.write_bytes(
                    self._setmode.control_block, struct.pack("<III", 0, 0, 0)
                )
            except Exception:
                pass


# --- WndProc border hook (in-process drag-resize + frameless borderless) ---
# Hooks the game's WndProc to intercept two messages; everything else passes
# through unchanged. It reads a control block the host updates each tick (so no
# GetWindowRect/style queries in the codecave):
#   CTRL -> {left, top, right, bottom, margin, frameless} as 6x int32
#
# * WM_NCHITTEST (0x84): the game returns HTCLIENT even on a WS_THICKFRAME border,
#   so the window isn't grab-resizable out-of-process. For a cursor inside the
#   window near an edge (within `margin`) we return the matching resize hit-code
#   (HTLEFT/HTRIGHT/.../corners) so DefWindowProc enters its sizing loop.
#
# * WM_NCCALCSIZE (0x83): when `frameless` is set we return 0 with the proposed
#   window rect left untouched, so the client area fills the ENTIRE window — the
#   title bar and the WS_THICKFRAME sizing border become invisible. Combined with
#   the hit-test above (and WS_THICKFRAME kept for SC_SIZE), this makes a window
#   simultaneously borderless AND drag-resizable. When `frameless` is 0 the
#   message passes through so normally-framed windows keep their frame.

# Codecave assembly. CTRL -> {left,top,right,bottom,margin,frameless} as 6x int32.
_NCHIT_ASM = """
    push  rbx
    cmp   edx, 0x83
    je    nccalc
    cmp   edx, 0x84
    je    nchit
    jmp   done_pop
nccalc:
    test  r8d, r8d
    je    done_pop
    mov   r11, 0x{ctrl:x}
    mov   eax, [r11+20]
    test  eax, eax
    je    done_pop
    xor   eax, eax
    pop   rbx
    ret
nchit:
    movsx eax, r9w
    mov   r10d, r9d
    sar   r10d, 16
    mov   r11, 0x{ctrl:x}
    mov   ebx, [r11]
    add   ebx, [r11+16]
    cmp   eax, ebx
    jl    on_left
    mov   ebx, [r11+8]
    sub   ebx, [r11+16]
    cmp   eax, ebx
    jge   on_right
    jmp   check_vert
on_left:
    mov   ebx, [r11+4]
    add   ebx, [r11+16]
    cmp   r10d, ebx
    jl    ret_13
    mov   ebx, [r11+12]
    sub   ebx, [r11+16]
    cmp   r10d, ebx
    jge   ret_16
    jmp   ret_10
on_right:
    mov   ebx, [r11+4]
    add   ebx, [r11+16]
    cmp   r10d, ebx
    jl    ret_14
    mov   ebx, [r11+12]
    sub   ebx, [r11+16]
    cmp   r10d, ebx
    jge   ret_17
    jmp   ret_11
check_vert:
    mov   ebx, [r11+4]
    add   ebx, [r11+16]
    cmp   r10d, ebx
    jl    ret_12
    mov   ebx, [r11+12]
    sub   ebx, [r11+16]
    cmp   r10d, ebx
    jge   ret_15
    jmp   done_pop
ret_10: mov eax, 10
        jmp do_ret
ret_11: mov eax, 11
        jmp do_ret
ret_12: mov eax, 12
        jmp do_ret
ret_13: mov eax, 13
        jmp do_ret
ret_14: mov eax, 14
        jmp do_ret
ret_15: mov eax, 15
        jmp do_ret
ret_16: mov eax, 16
        jmp do_ret
ret_17: mov eax, 17
do_ret: pop rbx
        ret
done_pop:
    pop   rbx
"""


def _assemble(asm: str) -> bytes:
    import keystone  # optional dep; only needed for the resize-border hook
    asm = "\n".join(line.split(";")[0] for line in asm.splitlines())  # strip ; comments
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    return bytes(ks.asm(asm, 0)[0])


class WndProcNCHitHook(SimpleHook):
    """Resize hit-codes near the window edges + optional frameless WM_NCCALCSIZE,
    so a window can be drag-resizable and (when frameless is set) borderless."""

    # sub rsp,0x38 ; mov r10,rcx ; mov rcx,[rip+disp(wildcard)] ; test rcx,rcx ; je ;
    # mov rax,[rcx] ; mov [rsp+20],r9 ; mov r9,rax
    # NB: the scanner treats the pattern as a regex, so bytes that are regex
    # metacharacters must be wildcarded with `.` (any byte) — here 0x24 ('$') in
    # `mov [rsp+0x20]`; the 4 dots wildcard the rip-relative displacement.
    pattern = (
        rb"\x48\x83\xEC\x38\x4C\x8B\xD1\x48\x8B\x0D...."
        rb"\x48\x85\xC9\x74\x1C\x48\x8B\x01\x4C\x89\x4C.\x20\x4D\x8B\xC8"
    )
    instruction_length = 7  # sub rsp,0x38 ; mov r10,rcx
    exports = [("hit_rect", 24)]  # int32 left, top, right, bottom, margin, frameless

    async def get_hook_address(self, size: int) -> int:
        # The default 50 bytes isn't enough: body ~244 bytes + original (7) + jmp (5).
        return await self.alloc(320)

    async def get_hook_bytecode(self) -> bytes:
        # Allocate the export (sets self.hit_rect), assemble using its address, then
        # append the original overwritten bytes; SimpleHook appends the jump back.
        addr = self.hook_handler.process.allocate(self.exports[0][1])
        self.hit_rect = addr
        body = _assemble(_NCHIT_ASM.format(ctrl=addr))
        original = await self.read_bytes(self.jump_address, self.instruction_length)
        bytecode = body + original

        return_addr = self.jump_address + self.instruction_length
        rel = return_addr - (self.hook_address + len(bytecode)) - 5
        bytecode += b"\xE9" + struct.pack("<i", rel)
        return bytecode

    async def prehook(self):
        # Initialise to a no-edge sentinel (and frameless=0) before the jump goes
        # live, so the first messages never hit a stale/zeroed rect (which would
        # resize-grab) nor a stray frameless flag (which would drop the frame).
        await self.hook_handler.write_bytes(
            self.hit_rect, struct.pack("<iiiiii", -2_000_000_000, -2_000_000_000,
                                       2_000_000_000, 2_000_000_000, 0, 0)
        )

    async def unhook(self):
        await super().unhook()
        if getattr(self, "hit_rect", None):
            await self.free(self.hit_rect)


class WindowResizeBorder:
    """Installs the WndProc hook and keeps the window rect + frameless flag updated
    so the game window is drag-resizable (and borderless when frameless is set).
    Call update_rect(screen_rect, margin, frameless) each tick."""

    def __init__(self, client):
        self.client = client
        self.hook_handler = client.hook_handler
        self._hook = None

    @property
    def installed(self) -> bool:
        return self._hook is not None

    async def install(self):
        if self.installed:
            return
        await self.hook_handler._check_for_autobot()
        self._hook = WndProcNCHitHook(self.hook_handler)
        await self._hook.hook()

    async def uninstall(self):
        if self._hook is not None:
            try:
                await self._hook.unhook()
            except Exception:
                pass
            self._hook = None

    async def update_rect(self, left: int, top: int, right: int, bottom: int,
                          margin: int = 14, frameless: bool = False):
        if self._hook is None:
            return
        await self.hook_handler.write_bytes(
            self._hook.hit_rect,
            struct.pack("<iiiiii", left, top, right, bottom, margin, 1 if frameless else 0)
        )
