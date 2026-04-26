from typing import List

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject, PropertyClass
from .adventure_party_entry_info import DynamicAdventurePartyEntryInfo


# C++ class: AdventurePartyInfo (PropertyClass)
# RTTI: .?AVAdventurePartyInfo@@
# Type registration: FUN_14145fcd0 -> FUN_1413ed1b0("AdventurePartyInfo") (r792258)
# Field registration: FUN_14145fd70 (r792258)
#
# Represents a single adventure party with its metadata and member list.
# Listed inside AdventurePartyList.m_adventurePartyList.
#
# PropertyClass field layout (base offset = 0):
# ==============================================
# Offset  Field                          Type        Description
# ------  -----                          ----        -----------
# 0x48    m_adventurePartyGID            GID/uint64  Party's global ID
# 0x50    m_adventurePartyName           uint32      Party name index
# 0x54    m_adventurePartyNameLocale     uint32      Party name locale index
# 0x58    m_creationDate                 uint32      Creation timestamp
# 0x60    m_ownerGID                     GID/uint64  Owner's character GID
# 0x68    m_ownerName                    string      Owner's display name (0x20 bytes)
# 0x88    m_purposeType                  uint32      Purpose type (activity category)
# 0x8C    m_purposeWorldID               uint32      World ID for the purpose
# 0x90    m_flags                        uint32      Party flags
# 0x98    m_equippedHouseInstanceGID     GID/uint64  Equipped house instance GID
# 0xA0    m_equippedInteriorInstanceGID  GID/uint64  Equipped interior instance GID
# 0xA8    m_adventurePartyMemberList     list        std::list<shared_ptr<EntryInfo>>
# 0xB0    (list size)                    uint64      Member list size
# 0xB8    m_messageBoardList             list        Message board entries
# 0xC8    m_renameCooldownTime           uint32      Rename cooldown timestamp
# 0xCC    m_newOwnerTime                 uint32      New owner transfer timestamp


class AdventurePartyInfo(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def adventure_party_gid(self) -> int:
        return await self.read_value_from_offset(0x48, Primitive.uint64)

    async def adventure_party_name(self) -> int:
        return await self.read_value_from_offset(0x50, Primitive.uint32)

    async def adventure_party_name_locale(self) -> int:
        return await self.read_value_from_offset(0x54, Primitive.uint32)

    async def creation_date(self) -> int:
        return await self.read_value_from_offset(0x58, Primitive.uint32)

    async def owner_gid(self) -> int:
        return await self.read_value_from_offset(0x60, Primitive.uint64)

    async def owner_name(self) -> str:
        return await self.read_string_from_offset(0x68)

    async def purpose_type(self) -> int:
        return await self.read_value_from_offset(0x88, Primitive.uint32)

    async def purpose_world_id(self) -> int:
        return await self.read_value_from_offset(0x8C, Primitive.uint32)

    async def flags(self) -> int:
        return await self.read_value_from_offset(0x90, Primitive.uint32)

    async def equipped_house_instance_gid(self) -> int:
        return await self.read_value_from_offset(0x98, Primitive.uint64)

    async def equipped_interior_instance_gid(self) -> int:
        return await self.read_value_from_offset(0xA0, Primitive.uint64)

    async def adventure_party_member_list(self) -> List[DynamicAdventurePartyEntryInfo]:
        result = []
        for addr in await self.read_shared_linked_list(0xA8):
            result.append(DynamicAdventurePartyEntryInfo(self.hook_handler, addr))
        return result

    async def adventure_party_member_count(self) -> int:
        return await self.read_value_from_offset(0xB0, Primitive.uint64)

    async def rename_cooldown_time(self) -> int:
        return await self.read_value_from_offset(0xC8, Primitive.uint32)

    async def new_owner_time(self) -> int:
        return await self.read_value_from_offset(0xCC, Primitive.uint32)


class DynamicAdventurePartyInfo(DynamicMemoryObject, AdventurePartyInfo):
    pass
