import struct
from enum import Enum
from typing import Any, List, Type

from wizwalker.constants import Primitive
from wizwalker.errors import (
    AddressOutOfRange,
    MemoryReadError,
    ReadingEnumFailed,
    PatternFailed,
    PatternMultipleResults
)
from wizwalker.utils import XYZ, Orient, Color
from .handler import HookHandler
from .memory_reader import MemoryReader


MAX_STRING = 5_000


# TODO: add .find_instances that find instances of whichever class used it
class MemoryObject(MemoryReader):
    """
    Class for any represented classes from memory
    """

    def __init__(self, hook_handler: HookHandler):
        super().__init__(hook_handler.process)
        self.hook_handler = hook_handler

        self._offset_lookup_cache = {}

    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def read_value_from_offset(self, offset: int, data_type: Primitive) -> Any:
        base_address = await self.read_base_address()
        return await self.read_typed(base_address + offset, data_type)

    async def write_value_to_offset(self, offset: int, value: Any, data_type: Primitive):
        base_address = await self.read_base_address()
        await self.write_typed(base_address + offset, value, data_type)

    async def pattern_scan_offset(
            self,
            pattern: bytes,
            instruction_length: int,
            static_backup: int = None,
    ) -> int:
        try:
            addr = await self.pattern_scan(pattern, module="WizardGraphicalClient.exe")
            return await self.read_typed(addr + instruction_length, Primitive.uint32)
        except (PatternFailed, PatternMultipleResults) as exc:
            if static_backup is not None:
                return static_backup

            raise exc

    async def pattern_scan_offset_cached(
            self,
            pattern: bytes,
            instruction_length: int,
            name: str,
            static_backup: int = None
    ):
        try:
            return self._offset_lookup_cache[name]
        except KeyError:
            offset = await self.pattern_scan_offset(pattern, instruction_length, static_backup)
            self._offset_lookup_cache[name] = offset
            return offset

    async def read_null_terminated_string(
        self, address: int, max_size: int = 20, encoding: str = "utf-8"
    ):
        search_bytes = await self.read_bytes(address, max_size)
        string_end = search_bytes.find(b"\x00")

        if string_end == 0:
            return ""
        elif string_end == -1:
            raise MemoryReadError(f"Couldn't read string at {address}; no end byte.")

        # Don't include the 0 byte
        string_bytes = search_bytes[:string_end]
        return string_bytes.decode(encoding)

    async def read_wide_string(self, address: int, encoding: str = "utf-16") -> str:
        string_len = await self.read_typed(address + 16, Primitive.int32)
        if string_len == 0:
            return ""

        # wide chars take 2 bytes
        string_len *= 2

        # wide strings larger than 8 bytes are pointers
        if string_len >= 8:
            string_address = await self.read_typed(address, Primitive.int64)
        else:
            string_address = address

        try:
            return (await self.read_bytes(string_address, string_len)).decode(encoding)
        except UnicodeDecodeError:
            return ""

    async def read_wide_string_from_offset(
        self, offset: int, encoding: str = "utf-16"
    ) -> str:
        base_address = await self.read_base_address()
        return await self.read_wide_string(base_address + offset, encoding)

    async def write_wide_string(
        self, address: int, string: str, encoding: str = "utf-16"
    ):
        string_len_addr = address + 16
        encoded = string.encode(encoding)
        # len(encoded) instead of string bc it can be larger in some encodings
        string_len = len(encoded)

        current_string_len = await self.read_typed(address + 16, Primitive.int32)

        # we need to create a pointer to the string data
        if string_len >= 7 > current_string_len:
            # +1 for 0 byte after
            pointer_address = await self.allocate(string_len + 1)

            # need 0 byte for some c++ null termination standard
            await self.write_bytes(pointer_address, encoded + b"\x00")
            await self.write_typed(address, pointer_address, Primitive.int64)

        # string is already a pointer
        elif string_len >= 7 and current_string_len >= 8:
            pointer_address = await self.read_typed(address, Primitive.int64)
            await self.write_bytes(pointer_address, encoded + b"\x00")

        # normal buffer string
        else:
            await self.write_bytes(address, encoded + b"\x00")

        # take 2 bytes
        await self.write_typed(string_len_addr, string_len // 2, Primitive.int32)

    async def write_wide_string_to_offset(
        self, offset: int, string: str, encoding: str = "utf-16"
    ):
        base_address = await self.read_base_address()
        await self.write_wide_string(base_address + offset, string, encoding)

    async def read_string(self, address: int, encoding: str = "utf-8") -> str:
        string_len = await self.read_typed(address + 16, Primitive.int32)

        if not 1 <= string_len <= MAX_STRING:
            return ""

        # strings larger than 16 bytes are pointers
        if string_len >= 16:
            string_address = await self.read_typed(address, Primitive.int64)
        else:
            string_address = address

        try:
            return (await self.read_bytes(string_address, string_len)).decode(encoding)
        except UnicodeDecodeError:
            return ""

    async def read_string_from_offset(
        self, offset: int, encoding: str = "utf-8"
    ) -> str:
        base_address = await self.read_base_address()
        return await self.read_string(base_address + offset, encoding)

    async def write_string(self, address: int, string: str, encoding: str = "utf-8"):
        string_len_addr = address + 16
        encoded = string.encode(encoding)
        # len(encoded) instead of string bc it can be larger in some encodings
        string_len = len(encoded)

        current_string_len = await self.read_typed(address + 16, Primitive.int32)

        # we need to create a pointer to the string data
        if string_len >= 15 > current_string_len:
            # +1 for 0 byte after
            pointer_address = await self.allocate(string_len + 1)

            # need 0 byte for some c++ null termination standard
            await self.write_bytes(pointer_address, encoded + b"\x00")
            await self.write_typed(address, pointer_address, Primitive.int64)

        # string is already a pointer
        elif string_len >= 15 and current_string_len >= 15:
            pointer_address = await self.read_typed(address, Primitive.int64)
            await self.write_bytes(pointer_address, encoded + b"\x00")

        # normal buffer string
        else:
            await self.write_bytes(address, encoded + b"\x00")

        await self.write_typed(string_len_addr, string_len, Primitive.int32)

    async def write_string_to_offset(
        self, offset: int, string: str, encoding: str = "utf-8"
    ):
        base_address = await self.read_base_address()
        await self.write_string(base_address + offset, string, encoding)

    # todo: rework this into from_offset and add read_vector which takes an address
    async def read_vector(self, offset: int, size: int = 3, data_type: Primitive = Primitive.float32):
        type_str = data_type.value.format.replace("<", "")
        size_per_type = struct.calcsize(type_str)

        base_address = await self.read_base_address()
        vector_bytes = await self.read_bytes(
            base_address + offset, size_per_type * size
        )

        return struct.unpack("<" + type_str * size, vector_bytes)

    async def write_vector(
        self, offset: int, value: tuple, size: int = 3, data_type: Primitive = Primitive.float32
    ):
        type_str = data_type.value.format.replace("<", "")

        base_address = await self.read_base_address()
        packed_bytes = struct.pack("<" + type_str * size, *value)

        await self.write_bytes(base_address + offset, packed_bytes)

    async def read_color(self, offset: int) -> Color:
        r, g, b = await self.read_vector(offset, 3, Primitive.uint8)
        return Color(r, g, b)

    async def write_color(self, offset: int, val: Color):
        await self.write_vector(offset, (val.r, val.g, val.b), 3, Primitive.uint8)

    async def read_xyz(self, offset: int) -> XYZ:
        x, y, z = await self.read_vector(offset)
        return XYZ(x, y, z)

    async def write_xyz(self, offset: int, xyz: XYZ):
        await self.write_vector(offset, (xyz.x, xyz.y, xyz.z))

    async def read_orient(self, offset: int) -> Orient:
        p, r, y = await self.read_vector(offset)
        return Orient(p, r, y)

    async def write_orient(self, offset, orient: Orient):
        await self.write_vector(offset, (orient.pitch, orient.roll, orient.yaw))

    async def read_enum(self, offset, enum: Type[Enum]):
        value = await self.read_value_from_offset(offset, Primitive.int32)
        try:
            res = enum(value)
        except ValueError:
            raise ReadingEnumFailed(enum, value)
        else:
            return res

    async def write_enum(self, offset, value: Enum):
        await self.write_value_to_offset(offset, value.value, Primitive.int32)

    async def read_shared_vector(
        self, offset: int, *, max_size: int = 1000
    ) -> List[int]:
        start_address = await self.read_value_from_offset(offset, Primitive.int64)
        end_address = await self.read_value_from_offset(offset + 8, Primitive.int64)
        size = end_address - start_address

        element_number = size // 16

        if size == 0:
            return []

        # dealloc
        if size < 0:
            return []

        if element_number > max_size:
            raise ValueError(f"Size was {element_number} and the max was {max_size}")

        try:
            shared_pointers_data = await self.read_bytes(start_address, size)
        except (ValueError, AddressOutOfRange, MemoryError):
            return []

        pointers = []
        data_pos = 0
        # Shared pointers are 16 in length
        for _ in range(element_number):
            # fmt: off
            shared_pointer_data = shared_pointers_data[data_pos: data_pos + 16]
            # fmt: on

            # first 8 bytes are the address
            pointers.append(struct.unpack("<q", shared_pointer_data[:8])[0])

            data_pos += 16

        return pointers

    async def read_dynamic_vector(
        self, offset: int, data_type: Primitive = Primitive.int64
    ) -> List[int]:
        """
        Read a vector that changes in size
        """
        start_address = await self.read_value_from_offset(offset, Primitive.int64)
        end_address = await self.read_value_from_offset(offset + 8, Primitive.int64)

        type_str = data_type.value.format.replace("<", "")
        size_per_type = struct.calcsize(type_str)

        size = (end_address - start_address) // size_per_type

        if size == 0:
            return []

        current_address = start_address
        pointers = []
        for _ in range(size):
            pointers.append(await self.read_typed(current_address, data_type))

            current_address += size_per_type

        return pointers

    async def read_inlined_vector(
            self,
            offset: int,
            object_size: int,
            object_type: type,
    ):
        start = await self.read_value_from_offset(offset, Primitive.uint64)
        end = await self.read_value_from_offset(offset + 16, Primitive.uint64)

        total_size = (end - start) // object_size

        current_addr = start

        res = []
        for _ in range(total_size):
            res.append(object_type(self.hook_handler, current_addr))
            current_addr += object_size

        return res

    async def read_shared_linked_list(self, offset: int):
        list_addr = await self.read_value_from_offset(offset, Primitive.int64)

        addrs = []
        # TODO: ensure this is always the case
        # skip first node
        next_node_addr = await self.read_typed(list_addr, Primitive.int64)
        list_size = await self.read_value_from_offset(offset + 8, Primitive.int32)

        for i in range(list_size):
            addr = await self.read_typed(next_node_addr + 16, Primitive.int64)
            addrs.append(addr)
            next_node_addr = await self.read_typed(next_node_addr, Primitive.int64)

        return addrs

    async def read_linked_list(self, offset: int) -> List[int]:
        list_addr = await self.read_value_from_offset(offset, Primitive.int64)
        list_size = await self.read_value_from_offset(offset + 8, Primitive.int32)

        if list_size < 1:
            return []

        addrs = []
        list_node = await self.read_typed(list_addr, Primitive.int64)
        # object starts +16 from node
        addrs.append(list_node + 16)
        # -1 because we've already read one node
        for _ in range(list_size - 1):
            list_node = await self.read_typed(list_node, Primitive.int64)
            addrs.append(list_node + 16)

        return addrs

    async def _get_std_map_children(self, node, mapped_type, mapped_return):
        # some keys may be smaller but the entire 8 bytes seemed to always be reserved
        is_leaf = await self.read_typed(node + 0x19, Primitive.bool)
        if not is_leaf:
            key = await self.read_typed(node + 0x20, Primitive.uint64)
            mapped_data = await self.read_typed(node + 0x28, Primitive.uint64)

            mapped_return[key] = mapped_type(self.hook_handler, mapped_data)

            if left_node := await self.read_typed(node, Primitive.uint64):
                await self._get_std_map_children(left_node, mapped_type, mapped_return)

            if right_node := await self.read_typed(node + 0x10, Primitive.uint64):
                await self._get_std_map_children(right_node, mapped_type, mapped_return)

    # TODO: 2.0 replace this with complex memory read type
    #  class StdMap(MemoryComplex):
    #      # impl method to read here
    #      ...
    #  read_complex_from_offset(0x80, StdMap)
    async def read_std_map(self, offset: int, mapped_type: Type["MemoryObject"]) -> dict:
        mapped_return = {}

        root = await self.read_value_from_offset(offset, Primitive.uint64)
        first_node = await self.read_typed(root + 0x8, Primitive.uint64)
        if first_node == root:
          return {}

        await self._get_std_map_children(first_node, mapped_type, mapped_return)
        return mapped_return

    async def read_hashset_basic(self, offset: int, primitive_type: Primitive) -> set[int]:
        result = set()
        root = DynamicMemoryObject(self.hook_handler, await self.read_value_from_offset(offset, Primitive.uint64))
        stack = [DynamicMemoryObject(self.hook_handler, await root.read_value_from_offset(8, Primitive.uint64))]
        while len(stack) > 0:
            node = stack.pop()
            is_leaf = await node.read_value_from_offset(0x19, Primitive.bool)
            if is_leaf:
                continue
            stack.extend([
                DynamicMemoryObject(self.hook_handler, await node.read_value_from_offset(0x00, Primitive.uint64)),
                DynamicMemoryObject(self.hook_handler, await node.read_value_from_offset(0x10, Primitive.uint64)),
            ])
            result.add(await node.read_value_from_offset(0x1C, primitive_type))
        return result

class DynamicMemoryObject(MemoryObject):
    def __init__(self, hook_handler: HookHandler, base_address: int):
        super().__init__(hook_handler)

        # sanity check
        if base_address == 0:
            raise RuntimeError(
                f"Dynamic object {type(self).__name__} passed 0 base address."
            )

        self.base_address = base_address

    async def read_base_address(self) -> int:
        return self.base_address

    def __repr__(self):
        return f"<{type(self).__name__} {self.base_address=}>"


class PropertyClass(MemoryObject):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def maybe_read_type_name(self) -> str:
        try:
            return await self.read_type_name()
        except (MemoryReadError, UnicodeDecodeError):
            return ""

    async def read_type_name(self) -> str:
        vtable = await self.read_value_from_offset(0, Primitive.int64)
        # first function
        get_class_name = await self.read_typed(vtable, Primitive.int64)
        # sometimes is a function with a jmp, sometimes just a body pointer
        maybe_jmp = await self.read_bytes(get_class_name, 5)
        # 233 is 0xE9 (jmp)
        if maybe_jmp[0] == 233:
            offset = struct.unpack("<i", maybe_jmp[1:])[0]
            # 5 is length of this jmp instruction
            actual_get_class_name = get_class_name + offset + 5
        else:
            actual_get_class_name = get_class_name

        # 63 is the length of the function up to the lea instruction
        lea_instruction = actual_get_class_name + 63
        # 48 8D 0D (here)
        lea_target = actual_get_class_name + 66
        rip_offset = await self.read_typed(lea_target, Primitive.int32)

        # 7 is the size of this line (rip is set at the next instruction when this one is executed)
        type_name_addr = lea_instruction + rip_offset + 7

        # some of the class names can be quite long
        # i.e ClientShadowCreatureLevelTransitionCinematicAction
        return await self.read_null_terminated_string(type_name_addr, 60)
