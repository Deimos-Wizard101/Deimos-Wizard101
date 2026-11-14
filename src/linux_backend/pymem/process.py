"""Module discovery, mirroring pymem.process, backed by zhol."""


class Module:
    """The fields of a pymem module that wizwalker reads."""

    __slots__ = ("lpBaseOfDll", "SizeOfImage", "name")

    def __init__(self, base, size, name=""):
        self.lpBaseOfDll = base
        self.SizeOfImage = size
        self.name = name


def module_from_name(handle, module_name):
    res = handle.module(module_name)
    if res is None:
        return None
    base, size = res
    return Module(base, size, module_name)
