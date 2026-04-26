from typing import List

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass
from .unlock_trigger_info import DynamicUnlockTriggerInfo


# C++ class: UnlockTriggerList (PropertyClass)
# Registered: FUN_1413ed1b0("UnlockTriggerList") at FUN_141462300 (r792258)
# Field registration: FUN_1414623a0 (r792258)
#
# Offset  Field                Type
# ------  -----                ----
# 0x48    m_unlockTriggerList  std::list<shared_ptr<UnlockTriggerInfo>>
# 0x50    (list size)          uint64
#
# Total size: 0x58 (PropertyClass base 0x48 + std::list 0x10)
#
# In SocialSystemsManager this is embedded at offset 0x1E0, so:
#   m_unlockTriggerList = SocialSystemsManager + 0x1E0 + 0x48 = 0x228
#
# Populated by MSG_UnlockTriggerData (FUN_141213660, r792258):
#   The "Buffer" DML field is deserialized into this PropertyClass,
#   filling m_unlockTriggerList with the guild's unlock trigger entries.


class UnlockTriggerList(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def unlock_trigger_list(self) -> List[DynamicUnlockTriggerInfo]:
        result = []
        for addr in await self.read_shared_linked_list(0x48):
            result.append(DynamicUnlockTriggerInfo(self.hook_handler, addr))
        return result

    async def unlock_trigger_list_size(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.uint64)


class DynamicUnlockTriggerList(DynamicMemoryObject, UnlockTriggerList):
    pass
