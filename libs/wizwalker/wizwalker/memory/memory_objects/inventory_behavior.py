from wizwalker import Primitive

from .behavior_instance import DynamicBehaviorInstance
from .core_object import CoreObject


class InventoryBehaviorBase(DynamicBehaviorInstance):
    async def item_list(self) -> list[CoreObject]:
        result = []
        for elem in await self.read_shared_linked_list(112):
            if elem != 0:
                result.append(CoreObject(self.hook_handler, elem))
        return result

class ClientInventoryBehavior(InventoryBehaviorBase):
    pass

class ClientWizInventoryBehavior(ClientInventoryBehavior):
    async def num_items_allowed(self) -> int:
        return await self.read_value_from_offset(160, Primitive.int32)

    async def write_num_items_allowed(self, val: int):
        await self.write_value_to_offset(160, val, Primitive.int32)

    async def num_jewels_allowed(self) -> int:
        return await self.read_value_from_offset(164, Primitive.int32)

    async def write_num_jewels_allowed(self, val: int):
        await self.write_value_to_offset(164, val, Primitive.int32)

    async def num_ce_emotes_allowed(self) -> int:
        return await self.read_value_from_offset(168, Primitive.int32)

    async def write_num_ce_emotes_allowed(self, val: int):
        await self.write_value_to_offset(168, val, Primitive.int32)

    async def num_ce_teleports_allowed(self) -> int:
        return await self.read_value_from_offset(172, Primitive.int32)

    async def write_num_ce_teleports_allowed(self, val: int):
        await self.write_value_to_offset(172, val, Primitive.int32)
