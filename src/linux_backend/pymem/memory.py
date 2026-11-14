"""Module-level memory ops, mirroring pymem.memory, backed by zhol (/proc).

`handle` here is a zhol.Process (what Pymem.process_handle returns).
"""
from .ressources.structure import MEMORY_PROTECTION, MEMORY_STATE


class MemoryBasicInformation:
    """The fields of Windows' MEMORY_BASIC_INFORMATION that wizwalker reads."""

    __slots__ = ("BaseAddress", "RegionSize", "state", "protect")

    def __init__(self, base, size, state, protect):
        self.BaseAddress = base
        self.RegionSize = size
        self.state = state
        self.protect = protect


def _protect_of(readable, writable, executable):
    if executable and writable:
        return MEMORY_PROTECTION.PAGE_EXECUTE_READWRITE
    if executable:
        return MEMORY_PROTECTION.PAGE_EXECUTE_READ
    if writable:
        return MEMORY_PROTECTION.PAGE_READWRITE
    if readable:
        return MEMORY_PROTECTION.PAGE_READONLY
    return MEMORY_PROTECTION.PAGE_NOACCESS


def virtual_query(handle, address):
    base, size, r, w, x, committed = handle.query(address)
    state = MEMORY_STATE.MEM_COMMIT if committed else MEMORY_STATE.MEM_FREE
    return MemoryBasicInformation(base, size, state, _protect_of(r, w, x))


def read_bytes(handle, address, size):
    return handle.read_bytes(address, size)
