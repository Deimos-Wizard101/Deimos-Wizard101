import regex
import struct
from collections import defaultdict

from .memory_reader import MemoryReader, Primitive
from wizwalker import MemoryReadError, PatternFailed


class InstanceFinder(MemoryReader):
    GET_TYPE_NAME_PATTERN = (
        rb"\x48\x89\x5C\x24\x10\x57\x48\x83\xEC\x20\xE8....\xBF\x02\x00\x00"
        rb"\x00\x48\x8B\xD8\x8B\xC7\xF0\x0F\xB1\x3D....\x74\x54\x48\x89\x74"
        rb"\x24\x30\xBE\x01\x00\x00\x00\x0F\x1F\x00\x33\xC0"
    )

    EXE_NAME = "WizardGraphicalClient.exe"

    def __init__(self, process, class_name: str):
        super().__init__(process)
        self.class_name = class_name

        self._all_jmp_instructions = None
        self._all_type_name_functions = None
        self._type_name_function_map = None
        self._jmp_functions = None

    async def read_null_terminated_string(
        self, address: int, max_size: int = 20, encoding: str = "utf-8"
    ):
        search_bytes = await self.read_bytes(address, max_size)
        string_end = search_bytes.find(b"\x00")

        if string_end == 0:
            return ""
        elif string_end == -1:
            raise MemoryReadError(address)

        # Don't include the 0 byte
        string_bytes = search_bytes[:string_end]
        return string_bytes.decode(encoding)

    async def scan_for_pointer(self, address: int):
        pattern = regex.escape(struct.pack("<q", address))
        try:
            return await self.pattern_scan(pattern, return_multiple=True)
        except PatternFailed:
            return []

    async def get_all_jmp_instructions(self):
        if self._all_jmp_instructions:
            return self._all_jmp_instructions

        self._all_jmp_instructions = await self.pattern_scan(
            b"\xE9", module=self.EXE_NAME, return_multiple=True
        )
        return self._all_jmp_instructions

    async def get_all_type_name_functions(self):
        if self._all_type_name_functions:
            return self._all_type_name_functions

        self._all_type_name_functions = await self.pattern_scan(
            self.GET_TYPE_NAME_PATTERN, module=self.EXE_NAME, return_multiple=True
        )
        return self._all_type_name_functions

    async def get_type_name_function_map(self):
        if self._type_name_function_map:
            return self._type_name_function_map

        func_name_map = defaultdict(lambda: list())

        for func in await self.get_all_type_name_functions():
            lea_instruction = func + 63
            lea_target = func + 66
            rip_offset = await self.read_typed(lea_target, Primitive.int32)

            type_name_addr = lea_instruction + rip_offset + 7

            # ClientShadowCreatureLevelTransitionCinematicAction is the longest class name
            type_name = await self.read_null_terminated_string(type_name_addr, 60)
            func_name_map[type_name].append(func)

        self._type_name_function_map = func_name_map
        return self._type_name_function_map

    async def get_type_name_functions(self):
        function_map = await self.get_type_name_function_map()
        return function_map[self.class_name]

    # TODO: add worker tasks with workers kwarg and default of 3
    async def get_jmp_functions(self):
        if self._jmp_functions:
            return self._jmp_functions

        all_jmps = await self.get_all_jmp_instructions()

        type_name_funcs = await self.get_type_name_functions()

        jmp_funcs = []
        for jmp in all_jmps:
            # I don't believe there are any cases where they have more than one
            # per func
            if len(jmp_funcs) == len(type_name_funcs):
                break

            offset = await self.read_typed(jmp + 1, Primitive.int32)

            for poss in type_name_funcs:
                if (offset + 5) == poss - jmp:
                    jmp_funcs.append(jmp)

        self._jmp_functions = jmp_funcs
        return self._jmp_functions

    async def get_instances(self):
        instances = []

        for jmp_function in await self.get_jmp_functions():
            vtable_function_pointers = await self.scan_for_pointer(jmp_function)
            for vtable_function in vtable_function_pointers:
                vtable_pointers = await self.scan_for_pointer(vtable_function)
                instances += vtable_pointers

        for type_name_function in await self.get_type_name_functions():
            vtable_function_pointers = await self.scan_for_pointer(type_name_function)
            for vtable_function in vtable_function_pointers:
                vtable_pointers = await self.scan_for_pointer(vtable_function)
                instances += vtable_pointers

        return instances
