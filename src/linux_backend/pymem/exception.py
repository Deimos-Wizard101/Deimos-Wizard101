"""pymem-compatible exceptions (only what wizwalker catches)."""


class PymemError(Exception):
    pass


class MemoryReadError(PymemError):
    def __init__(self, address=0, length=0, error_code=None):
        self.address = address
        self.length = length
        self.error_code = error_code
        super().__init__(f"Could not read memory at {address:#x} (length {length})")


class MemoryWriteError(PymemError):
    def __init__(self, address=0, value=b"", error_code=None):
        self.address = address
        self.value = value
        self.error_code = error_code
        super().__init__(f"Could not write memory at {address:#x}")


class ProcessError(PymemError):
    pass
