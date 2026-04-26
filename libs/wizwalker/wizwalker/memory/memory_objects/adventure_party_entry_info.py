from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass


# C++ class: AdventurePartyEntryInfo (PropertyClass)
# RTTI: .?AVAdventurePartyEntryInfo@@
# Type registration: FUN_14145f190 -> FUN_1413ed1b0("AdventurePartyEntryInfo") (r792258)
# Field registration: FUN_14145f230 (r792258)
#
# Represents a single member within an adventure party.
# Listed inside AdventurePartyInfo.m_adventurePartyMemberList.
#
# PropertyClass field layout (base offset = 0):
# ==============================================
# Offset  Field                Type        Description
# ------  -----                ----        -----------
# 0x48    m_characterGID       GID/uint64  Character's global ID
# 0x50    m_lastLoginTime      uint32      Last login timestamp
# 0x54    m_partyJoinTime      uint32      When they joined the party
# 0x58    m_packedName         string      Packed character name (0x20 bytes)
# 0x78    m_level              uint32      Character level
# 0x7C    m_school             uint32      School ID
# 0x80    m_previousLoginTime  uint32      Previous login timestamp
# 0x88    m_zonePath           string      Current zone path (0x20 bytes)
# 0xA8    m_flags              uint32      Flags (bit 0 = owner/leader)
# 0xAC    m_provisionalTime    uint32      Provisional membership timer
# 0xB0    m_permissions        uint32      Permission bitmask
# 0xB8    m_accountGID         GID/uint64  Account global ID
#
# Flags bit 0:
#   The MSG_RequestAdventureParty handler (FUN_141208900, r792258) checks
#   (*(byte*)(entry + 0xA8) & 1) to distinguish the owner/leader entry
#   from regular members when rebuilding the sorted member list.


class AdventurePartyEntryInfo(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def character_gid(self) -> int:
        return await self.read_value_from_offset(0x48, Primitive.uint64)

    async def last_login_time(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.uint32)

    async def party_join_time(self) -> int:
        return await self.read_value_from_offset(0x54, Primitive.uint32)

    async def packed_name(self) -> str:
        return await self.read_string_from_offset(0x58)

    async def level(self) -> int:
        return await self.read_value_from_offset(0x78, Primitive.uint32)

    async def school(self) -> int:
        return await self.read_value_from_offset(0x7C, Primitive.uint32)

    async def previous_login_time(self) -> int:
        return await self.read_value_from_offset(0x80, Primitive.uint32)

    async def zone_path(self) -> str:
        return await self.read_string_from_offset(0x88)

    async def flags(self) -> int:
        return await self.read_value_from_offset(0xA8, Primitive.uint32)

    async def is_owner(self) -> bool:
        return (await self.flags() & 1) != 0

    async def provisional_time(self) -> int:
        return await self.read_value_from_offset(0xAC, Primitive.uint32)

    async def permissions(self) -> int:
        return await self.read_value_from_offset(0xB0, Primitive.uint32)

    async def account_gid(self) -> int:
        return await self.read_value_from_offset(0xB8, Primitive.uint64)


class DynamicAdventurePartyEntryInfo(DynamicMemoryObject, AdventurePartyEntryInfo):
    pass
