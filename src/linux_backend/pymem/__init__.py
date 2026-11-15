"""A pymem-compatible facade backed by zhol's /proc memory backend.

Drop-in replacement for the Windows-only `pymem` so wizwalker's memory layer
runs on native Linux against a Proton-hosted client. Only the surface wizwalker
uses is implemented.
"""
import zhol

from . import exception, memory, process, ressources  # noqa: F401


class Pymem:
    def __init__(self, process_name=None):
        self.process_handle = None
        self.process_id = None
        # address -> size, so start_thread (thread-hijack on Linux) knows how many
        # bytes of shellcode to copy into executable memory. Windows doesn't need
        # it; CreateRemoteThread just jumps to the address. zhol doesn't expose the
        # requested size for an address, so we still track it here.
        self._alloc_sizes = {}
        if process_name is not None:
            raise NotImplementedError("open by name is unused; use open_process_from_id")

    def open_process_from_id(self, process_id):
        self.process_id = process_id
        self.process_handle = zhol.Process.open(process_id)
        return self.process_handle

    def read_bytes(self, address, length):
        try:
            return self.process_handle.read_bytes(address, length)
        except Exception as e:
            raise exception.MemoryReadError(address, length) from e

    def write_bytes(self, address, value, length):
        try:
            self.process_handle.write_bytes(address, value)
        except Exception as e:
            raise exception.MemoryWriteError(address, value) from e

    def allocate(self, size):
        # zhol's cave allocator reclaims freed blocks itself (see free()), so
        # repeated RPC allocations (freecam toggles, _switch_camera shellcode, ...)
        # reuse space instead of exhausting the arena.
        addr = self.process_handle.allocate(size)
        self._alloc_sizes[addr] = size
        return addr

    def allocation_size(self, address):
        """Size requested for a prior allocate(address), or None if unknown."""
        return self._alloc_sizes.get(address)

    def free(self, address):
        # Hand the block back to zhol's cave free list for reuse.
        self._alloc_sizes.pop(address, None)
        self.process_handle.free(address)
        return None

    def start_thread(self, address, *args, **kwargs):
        # Linux remote execution is a thread-hijack and needs the autobot + a
        # hijack site, which live on the HookHandler; it overrides start_thread
        # there. Reaching this means a non-HookHandler caller tried it.
        raise NotImplementedError(
            "remote thread execution on Linux goes through HookHandler.start_thread"
        )


def open_process_from_id(process_id):
    p = Pymem()
    p.open_process_from_id(process_id)
    return p
