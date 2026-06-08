from wizwalker.memory.memory_object import DynamicMemoryObject, PropertyClass
from wizwalker.constants import Primitive


# C++ class: GuildChatInfo
# PropertyClass subclass (type hash: 1628314597)
# Source: type dump r794925_Wizard_1_600.json
#
# Class layout:
# ==============================================
# Offset  Type            Description
# ------  ----            -----------
# 0x000   PropertyClass   Base (vtable + type info)
# 0x048   gid (uint64)    Sender character GID
# 0x050   std::string     Packed sender name
# 0x070   std::string     Message text
# 0x090   uint32          Message ID
# 0x094   uint8           Send filter
# 0x098   uint32          Message timestamp (epoch seconds)


class GuildChatInfo(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def character_gid(self) -> int:
        """Sender character GID at offset 0x48."""
        return await self.read_value_from_offset(0x48, Primitive.uint64)

    async def packed_name(self) -> str:
        """Packed sender name at offset 0x50."""
        return await self.read_string_from_offset(0x50)

    async def message(self) -> str:
        """Chat message text at offset 0x70."""
        return await self.read_string_from_offset(0x70)

    async def message_id(self) -> int:
        """Server-assigned message ID at offset 0x90."""
        return await self.read_value_from_offset(0x90, Primitive.uint32)

    async def send_filter(self) -> int:
        """Send filter flags at offset 0x94."""
        return await self.read_value_from_offset(0x94, Primitive.uint8)

    async def message_time(self) -> int:
        """Message timestamp (epoch seconds) at offset 0x98."""
        return await self.read_value_from_offset(0x98, Primitive.uint32)


class DynamicGuildChatInfo(DynamicMemoryObject, GuildChatInfo):
    pass
