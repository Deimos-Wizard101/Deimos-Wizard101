from enum import Enum

from .goal_data import GoalData
from .client_tag_list import ClientTagList
from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject


class ActivityType(Enum):
    not_activity = 0
    spell = 1
    crafting = 2
    fishing = 3
    gardening = 4
    pet = 5


class QuestData(DynamicMemoryObject):
    async def name_lang_key(self) -> str:
        return await self.read_string_from_offset(112)

    async def goal_data(self) -> dict[int, GoalData]:
        return await self.read_std_map(176, GoalData)

    async def client_tags(self) -> ClientTagList:
        addr = await self.read_value_from_offset(0xC0, Primitive.uint64)
        if addr == 0:
            return None
        return ClientTagList(self.hook_handler, addr)

    async def quest_type(self) -> int:
        # 0xE0 is QuestType but the meaning is unknown
        return await self.read_value_from_offset(0xE0, Primitive.int32)

    async def quest_level(self) -> int:
        return await self.read_value_from_offset(0xE4, Primitive.int32)

    async def permit_quest_helper(self) -> bool:
        return await self.read_value_from_offset(0xF0, Primitive.bool)

    async def write_permit_quest_helper(self, val: bool):
        await self.write_value_to_offset(0xF0, val, Primitive.bool)

    async def mainline(self) -> bool:
        return await self.read_value_from_offset(0xF1, Primitive.bool)

    async def ready_to_turn_in(self) -> bool:
        return await self.read_value_from_offset(0xF2, Primitive.bool)

    async def activity_type(self) -> ActivityType:
        return await self.read_enum(0xF4, ActivityType)

    async def pet_only_quest(self) -> bool:
        return await self.read_value_from_offset(0xF9, Primitive.bool)
