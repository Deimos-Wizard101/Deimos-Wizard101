from enum import Enum

from .madlib_block import MadlibBlock
from .client_tag_list import ClientTagList
from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject


class GoalType(Enum):
    unknown = 0
    bounty = 1
    bountycollect = 2
    scavenge = 3
    persona = 4
    waypoint = 5
    scavengefake = 6
    achieverank = 7
    usage = 8
    completequest = 9
    sociarank = 10
    sociacurrency = 11
    sociaminigame = 12
    sociagiveitem = 13
    sociagetitem = 14
    collectafterbounty = 15
    encounter_waypoint_foreach = 16


class GoalData(DynamicMemoryObject):
    async def name_lang_key(self) -> str:
        return await self.read_string_from_offset(0x50)

    async def goal_status(self) -> bool:
        return await self.read_value_from_offset(0x74, Primitive.bool)

    async def goal_destination_zone(self) -> str:
        return await self.read_string_from_offset(0x98)

    async def goal_type(self) -> GoalType:
        return await self.read_enum(0xB8, GoalType)

    async def madlib_block(self) -> MadlibBlock:
        return MadlibBlock(self.hook_handler, await self.read_value_from_offset(0xC0, Primitive.uint64))

    async def client_tag_list(self) -> ClientTagList | None:
        addr = await self.read_value_from_offset(0x110, Primitive.uint64)
        if addr == 0:
            return None
        return ClientTagList(self.hook_handler, addr)

    async def no_quest_helper(self) -> bool:
        return await self.read_value_from_offset(0x140, Primitive.bool)

    async def pet_only_quest(self) -> bool:
        return await self.read_value_from_offset(0x141, Primitive.bool)

    async def has_active_results(self) -> bool:
        return await self.read_value_from_offset(0x142, Primitive.bool)

    async def hide_goal_floaty_text(self) -> bool:
        return await self.read_value_from_offset(0x143, Primitive.bool)
