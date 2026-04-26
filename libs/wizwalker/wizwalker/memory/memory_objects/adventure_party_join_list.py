from typing import List

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass
from .adventure_party_join_info import DynamicAdventurePartyJoinInfo


# C++ class: AdventurePartyJoinList (PropertyClass)
# RTTI: .?AVAdventurePartyJoinList@@
# Type registration: FUN_141461580 -> FUN_1413ed1b0("AdventurePartyJoinList") (r792258)
# Field registration: FUN_141461580 (inline) (r792258)
#
# Container PropertyClass holding a list of joinable parties (kiosk data).
#
# PropertyClass field layout (base offset = 0):
# ==============================================
# Offset  Field                     Type        Description
# ------  -----                     ----        -----------
# 0x48    m_adventurePartyJoinList  list        std::list<shared_ptr<JoinInfo>>
# 0x50    (list size)               uint64      Number of joinable parties


class AdventurePartyJoinList(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def adventure_party_join_list(self) -> List[DynamicAdventurePartyJoinInfo]:
        result = []
        for addr in await self.read_shared_linked_list(0x48):
            result.append(DynamicAdventurePartyJoinInfo(self.hook_handler, addr))
        return result

    async def adventure_party_join_count(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.uint64)


class DynamicAdventurePartyJoinList(DynamicMemoryObject, AdventurePartyJoinList):
    pass
