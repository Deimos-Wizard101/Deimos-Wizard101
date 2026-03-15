from .behavior_instance import DynamicBehaviorInstance
from .core_object import CoreObject
from .equipped_slot_info import EquippedSlotInfo
from .equipped_item_info import EquippedItemInfo
from .equipment_set import EquipmentSet


class ClientEquipmentBehavior(DynamicBehaviorInstance):
    async def item_list(self) -> list[CoreObject]:
        result = []
        for elem in await self.read_shared_linked_list(120):
            if elem != 0:
                result.append(CoreObject(self.hook_handler, elem))
        return result

    async def slot_list(self) -> list[EquippedSlotInfo]:
        result = []
        for elem in await self.read_shared_linked_list(136):
            if elem != 0:
                result.append(EquippedSlotInfo(self.hook_handler, elem))
        return result

    async def public_item_list(self) -> list[EquippedItemInfo]:
        result = []
        for elem in await self.read_shared_linked_list(152):
            if elem != 0:
                result.append(EquippedItemInfo(self.hook_handler, elem))
        return result

class ClientWizEquipmentBehavior(ClientEquipmentBehavior):
    async def equipment_sets(self) -> list[EquipmentSet]:
        result = []
        for elem in await self.read_shared_linked_list(232):
            if elem != 0:
                result.append(EquipmentSet(self.hook_handler, elem))
        return result
