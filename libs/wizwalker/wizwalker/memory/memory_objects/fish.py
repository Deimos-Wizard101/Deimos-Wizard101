from enum import Enum

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject
from .actor_body import DynamicActorBody
from .fish_template import FishTemplate


class FishStatusCode(Enum):
    neutral = 0
    scared = 1
    unknown2 = 2
    unknown3 = 3 # works on sentinels
    escaped = 4 # works on sentinels
    unknown5 = 5
    unknown6 = 6


class Fish(DynamicMemoryObject):
    async def body(self) -> DynamicActorBody:
        addr = await self.read_value_from_offset(0x48, Primitive.uint64)
        return DynamicActorBody(self.hook_handler, addr)

    async def status_code(self) -> FishStatusCode:
        return await self.read_enum(0xB8, FishStatusCode)

    async def write_status_code(self, val: FishStatusCode):
        await self.write_enum(0xB8, val)

    async def template(self) -> FishTemplate:
        addr = await self.read_value_from_offset(0xD8, Primitive.uint64)
        return FishTemplate(self.hook_handler, addr)

    async def bobber_submerge_ease(self) -> float:
        return await self.read_value_from_offset(0xE0, Primitive.float32)

    async def write_bobber_submerge_ease(self, val: float):
        ## At 1.0 the bobber is guaranteed to go down
        await self.write_value_to_offset(0xE0, val, Primitive.float32)

    async def fish_id(self) -> int:
        return await self.read_value_from_offset(0xE4, Primitive.int32)

    async def template_id(self) -> int:
        return await self.read_value_from_offset(0xE8, Primitive.int32)

    async def size(self) -> float:
        return await self.read_value_from_offset(0xEC, Primitive.float32)

    async def is_chest(self) -> bool:
        return await self.read_value_from_offset(0xF0, Primitive.bool)
