from typing import Optional

from wizwalker import XYZ, Orient
from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject
from .behavior_instance import DynamicBehaviorInstance
from .core_template import CoreTemplate


class CoreObject(DynamicMemoryObject, PropertyClass):
    async def global_id_full(self) -> int:
        return await self.read_value_from_offset(72, Primitive.uint64)

    async def write_global_id_full(self, val: int):
        await self.write_value_to_offset(72, val, Primitive.uint64)

    async def perm_id(self) -> int:
        return await self.read_value_from_offset(80, Primitive.uint64)

    async def write_perm_id(self, val: int):
        await self.write_value_to_offset(80, val, Primitive.uint64)

    # note: not defined
    async def object_template(self) -> CoreTemplate:
        addr = await self.read_value_from_offset(88, Primitive.int64)
        if addr == 0:
            return None
        return CoreTemplate(self.hook_handler, addr)

    async def template_id_full(self) -> int:
        return await self.read_value_from_offset(96, Primitive.uint64)

    async def write_template_id_full(self, val: int):
        await self.write_value_to_offset(96, val, Primitive.uint64)

    async def debug_name(self) -> str:
        return await self.read_string_from_offset(104)

    async def display_key(self) -> str:
        return await self.read_string_from_offset(136)

    async def location(self) -> XYZ:
        return await self.read_xyz(168)

    async def write_location(self, val: XYZ):
        await self.write_xyz(168, val)

    async def orientation(self) -> Orient:
        return await self.read_orient(180)

    async def write_orientation(self, val: Orient):
        await self.write_orient(180, val)

    async def speed_multiplier(self) -> int:
        return await self.read_value_from_offset(192, Primitive.int16)

    async def write_speed_multiplier(self, val: int):
        await self.write_value_to_offset(192, val, Primitive.int16)

    async def mobile_id(self) -> int:
        return await self.read_value_from_offset(194, Primitive.uint16)

    async def write_mobile_id(self, val: int):
        await self.write_value_to_offset(194, val, Primitive.uint16)

    async def scale(self) -> float:
        return await self.read_value_from_offset(196, Primitive.float32)

    async def write_scale(self, val: float):
        await self.write_value_to_offset(196, val, Primitive.float32)

    # note: not defined
    async def parent(self) -> Optional["CoreObject"]:
        addr = await self.read_value_from_offset(208, Primitive.int64)
        if addr == 0:
            return None
        return CoreObject(self.hook_handler, addr)

    async def inactive_behaviors(self) -> list[DynamicBehaviorInstance]:
        result = []
        for elem in await self.read_shared_vector(224):
            if elem != 0:
                result.append(DynamicBehaviorInstance(self.hook_handler, elem))
        return result

    async def zone_tag_id(self) -> int:
        return await self.read_value_from_offset(344, Primitive.uint32)

    async def write_zone_tag_id(self, val: int):
        await self.write_value_to_offset(344, val, Primitive.uint32)


    # utils
    async def search_behavior_by_name(self, name: str) -> DynamicBehaviorInstance | None:
        for behavior in await self.inactive_behaviors():
            if await behavior.behavior_name() == name:
                return behavior
        return None

