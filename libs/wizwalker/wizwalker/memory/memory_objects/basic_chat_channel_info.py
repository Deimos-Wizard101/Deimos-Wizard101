from typing import List, Optional

from wizwalker.memory.memory_object import DynamicMemoryObject, PropertyClass
from wizwalker.constants import Primitive
from .basic_chat_player import DynamicBasicChatPlayer


# C++ class: BasicChatChannelInfo
# PropertyClass subclass (type hash: 2121388742)
# Source: type dump r794925_Wizard_1_600.json
#
# Class layout:
# ==============================================
# Offset  Type                                Description
# ------  ----                                -----------
# 0x000   PropertyClass                       Base (vtable + type info)
# 0x048   gid (uint64)                        Owner character GID
# 0x050   std::string                         Owner name blob
# 0x070   bool                                Is public channel
# 0x074   int32                               Invite-all cooldown time
# 0x078   std::list<shared_ptr<BasicChatPlayer>>  Player list


class BasicChatChannelInfo(PropertyClass):
    async def read_base_address(self) -> int:
        raise NotImplementedError()

    async def owner_character_id(self) -> int:
        """Owner character GID at offset 0x48."""
        return await self.read_value_from_offset(0x48, Primitive.uint64)

    async def owner_name_blob(self) -> str:
        """Owner packed/encoded name at offset 0x50."""
        return await self.read_string_from_offset(0x50)

    async def is_public(self) -> bool:
        """Whether this is a public channel at offset 0x70."""
        return await self.read_value_from_offset(0x70, Primitive.bool)

    async def invite_all_cooldown_time(self) -> int:
        """Invite-all cooldown in seconds at offset 0x74."""
        return await self.read_value_from_offset(0x74, Primitive.int32)

    async def player_list(self) -> List[DynamicBasicChatPlayer]:
        """List of BasicChatPlayer members in this channel at offset 0x78."""
        return await self.read_shared_linked_list(0x78)


class DynamicBasicChatChannelInfo(DynamicMemoryObject, BasicChatChannelInfo):
    pass
