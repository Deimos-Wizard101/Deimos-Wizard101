from typing import List

from wizwalker.memory.memory_object import Primitive, PropertyClass, DynamicMemoryObject


class CharacterRegistry(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    # async def displayed_tips(self) -> List[int]:
    #     sub_object_addrs = await self.read_linked_list(112)
    #
    #     res = []
    #     for sub_object in sub_object_addrs:
    #         res.append(await self.read_typed(sub_object, Primitive.uint64))
    #
    #     return res

    # todo add the useless properties

    async def active_quest_id(self) -> int:
        return await self.read_value_from_offset(304, Primitive.uint64)

    async def write_active_quest_id(self, active_quest_id: int):
        await self.write_value_to_offset(304, active_quest_id, Primitive.uint64)

    async def active_goal_id(self) -> int:
        return await self.read_value_from_offset(336, Primitive.uint32)

    async def write_active_goal_id(self, active_goal_id: int):
        await self.write_value_to_offset(336, active_goal_id, Primitive.uint32)


class DynamicCharacterRegistry(DynamicMemoryObject, CharacterRegistry):
    pass
