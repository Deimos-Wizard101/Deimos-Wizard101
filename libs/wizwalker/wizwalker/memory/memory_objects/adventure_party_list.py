from typing import List

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass
from .adventure_party_info import DynamicAdventurePartyInfo


# C++ class: AdventurePartyList (PropertyClass)
# RTTI: .?AVAdventurePartyList@@
# Type registration: FUN_141460cc0 -> FUN_1413ed1b0("AdventurePartyList") (r792258)
# Field registration: FUN_141460cc0 (inline) (r792258)
#
# Container PropertyClass holding a list of AdventurePartyInfo entries.
# Stored via shared_ptr at SocialSystemsManager offset 0xA8.
#
# Populated by MSG_RequestAdventureParty (FUN_141208900, r792258):
#   The "Buffer" DML field is deserialized into this PropertyClass.
#   The handler then iterates m_adventurePartyList (+0x48) to rebuild
#   sorted member lists for each party.
#
# PropertyClass field layout (base offset = 0):
# ==============================================
# Offset  Field                 Type        Description
# ------  -----                 ----        -----------
# 0x48    m_adventurePartyList  list        std::list<shared_ptr<AdventurePartyInfo>>
# 0x50    (list size)           uint64      Number of parties in the list


class AdventurePartyList(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def adventure_party_list(self) -> List[DynamicAdventurePartyInfo]:
        result = []
        for addr in await self.read_shared_linked_list(0x48):
            result.append(DynamicAdventurePartyInfo(self.hook_handler, addr))
        return result

    async def adventure_party_count(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.uint64)


class DynamicAdventurePartyList(DynamicMemoryObject, AdventurePartyList):
    pass
