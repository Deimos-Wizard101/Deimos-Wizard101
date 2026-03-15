from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass


# C++ class: AdventurePartyJoinInfo (PropertyClass)
# RTTI: .?AVAdventurePartyJoinInfo@@
# Type registration: FUN_141460e70 -> FUN_1413ed1b0("AdventurePartyJoinInfo") (r792258)
# Field registration: FUN_141460f10 (r792258)
#
# Represents a joinable party entry in the Social Kiosk.
# Listed inside AdventurePartyJoinList.m_adventurePartyJoinList.
#
# PropertyClass field layout (base offset = 0):
# ==============================================
# Offset  Field                       Type        Description
# ------  -----                       ----        -----------
# 0x48    m_adventurePartyGID         GID/uint64  Party's global ID
# 0x50    m_adventurePartyName        uint32      Party name index
# 0x54    m_adventurePartyNameLocale  uint32      Party name locale index
# 0x58    m_purposeType               uint32      Purpose type (activity category)
# 0x5C    m_purposeWorldID            uint32      World ID for the purpose
# 0x60    m_partySize                 uint32      Current party size
# 0x64    m_onlineCount               uint32      Number of members online


class AdventurePartyJoinInfo(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def adventure_party_gid(self) -> int:
        return await self.read_value_from_offset(0x48, Primitive.uint64)

    async def adventure_party_name(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.uint32)

    async def adventure_party_name_locale(self) -> int:
        return await self.read_value_from_offset(0x54, Primitive.uint32)

    async def purpose_type(self) -> int:
        return await self.read_value_from_offset(0x58, Primitive.uint32)

    async def purpose_world_id(self) -> int:
        return await self.read_value_from_offset(0x5C, Primitive.uint32)

    async def party_size(self) -> int:
        return await self.read_value_from_offset(0x60, Primitive.uint32)

    async def online_count(self) -> int:
        return await self.read_value_from_offset(0x64, Primitive.uint32)


class DynamicAdventurePartyJoinInfo(DynamicMemoryObject, AdventurePartyJoinInfo):
    pass
