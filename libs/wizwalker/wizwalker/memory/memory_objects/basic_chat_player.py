from wizwalker.memory.memory_object import DynamicMemoryObject, PropertyClass
from wizwalker.constants import Primitive


# C++ class: BasicChatPlayer
# PropertyClass subclass (type hash: 101684154)
# Source: type dump r794925_Wizard_1_600.json
#
# Class layout:
# ==============================================
# Offset  Type            Description
# ------  ----            -----------
# 0x000   PropertyClass   Base (vtable + type info)
# 0x048   gid (uint64)    Character GID
# 0x050   std::string     Name blob (packed/encoded name)
# 0x070   uint32          School + level composite
# 0x078   gid (uint64)    Object ID (in-world entity ID)
# 0x080   char (int8)     Platform type
# 0x081   bool            Disable cross-play flag


class BasicChatPlayer(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def character_id(self) -> int:
        """Character GID at offset 72 (0x48)."""
        return await self.read_value_from_offset(0x48, Primitive.uint64)

    async def name_blob(self) -> str:
        """Packed/encoded player name at offset 80 (0x50)."""
        return await self.read_string_from_offset(0x50)

    async def school_level(self) -> int:
        """School+level composite at offset 112 (0x70)."""
        return await self.read_value_from_offset(0x70, Primitive.uint32)

    async def object_id(self) -> int:
        """In-world object ID at offset 120 (0x78)."""
        return await self.read_value_from_offset(0x78, Primitive.uint64)

    async def platform_type(self) -> int:
        """Platform type at offset 128 (0x80)."""
        return await self.read_value_from_offset(0x80, Primitive.int8)

    async def disable_cross_play(self) -> bool:
        """Cross-play disabled flag at offset 129 (0x81)."""
        return await self.read_value_from_offset(0x81, Primitive.bool)


class DynamicBasicChatPlayer(DynamicMemoryObject, BasicChatPlayer):
    pass
