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
        return self.process_handle.allocate(size)

    def free(self, address):
        # Cave allocations are not reclaimed; see zhol's Unix backend.
        return None

    def start_thread(self, address, *args, **kwargs):
        raise NotImplementedError(
            "remote thread execution is not supported on Linux (no CreateRemoteThread)"
        )


def open_process_from_id(process_id):
    p = Pymem()
    p.open_process_from_id(process_id)
    return p
