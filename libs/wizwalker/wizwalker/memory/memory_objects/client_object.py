from typing import List, Optional

from wizwalker.memory.handler import HookHandler
from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject
from wizwalker.memory.memory_objects import DynamicActorBody
from .game_stats import DynamicGameStats
from .game_object_template import DynamicWizGameObjectTemplate
from .client_zone import DynamicClientZone
from .core_object import CoreObject
from .inventory_behavior import ClientWizInventoryBehavior
from .equipment_behavior import ClientWizEquipmentBehavior
from .spellbook_behavior import ClientSpellbookBehavior
from .deck_behavior import ClientDeckBehavior, ClientTreasureBookBehavior
from .behavior_template import NPCBehaviorTemplate


class ClientObject(CoreObject):
    """
    Base class for ClientObjects
    """
    async def try_get_inventory_behavior(self) -> ClientWizInventoryBehavior | None:
        base = await self.search_behavior_by_name("WizardInventoryBehavior")
        if base:
            return ClientWizInventoryBehavior(self.hook_handler, await base.read_base_address())
        return None

    async def try_get_equipment_behavior(self) -> ClientWizEquipmentBehavior | None:
        base = await self.search_behavior_by_name("WizardEquipmentBehavior")
        if base:
            return ClientWizEquipmentBehavior(self.hook_handler, await base.read_base_address())
        return None

    async def try_get_spellbook_behavior(self) -> ClientSpellbookBehavior | None:
        """Get the player's trained spellbook behavior (all learned spells)."""
        base = await self.search_behavior_by_name("BasicSpellbookBehavior")
        if base:
            return ClientSpellbookBehavior(self.hook_handler, await base.read_base_address())
        return None

    async def try_get_deck_behavior(self) -> ClientDeckBehavior | None:
        """Get the player's active deck behavior.

        Convenience shortcut. The DeckBehavior lives on the equipped deck
        item (not on the player CoreObject), so this searches all equipped
        items via CoreObject.search_behavior_by_name().
        """
        equip = await self.try_get_equipment_behavior()
        if not equip:
            return None
        for item in await equip.item_list():
            try:
                behavior = await item.search_behavior_by_name("BasicDeckBehavior")
                if behavior:
                    return ClientDeckBehavior(
                        self.hook_handler, await behavior.read_base_address()
                    )
            except Exception:
                continue
        return None

    async def try_get_treasure_book_behavior(self) -> ClientTreasureBookBehavior | None:
        """Get the player's treasure card collection behavior."""
        base = await self.search_behavior_by_name("BasicTreasureBookBehavior")
        if base:
            return ClientTreasureBookBehavior(self.hook_handler, await base.read_base_address())
        return None

    async def list_behavior_names(self) -> List[str]:
        """List all behavior template names on this client object. Useful for debugging."""
        names = []
        for behavior in await self.inactive_behaviors():
            name = await behavior.behavior_name()
            if name:
                names.append(name)
        return names

    # helper method
    async def actor_body(self) -> Optional[DynamicActorBody]:
        if behavior := await self.search_behavior_by_name("AnimationBehavior"):
            addr = await behavior.read_value_from_offset(0x70, Primitive.uint64)

            if addr == 0:
                return None

            return DynamicActorBody(self.hook_handler, addr)

    # helper method
    async def object_name(self) -> Optional[str]:
        """
        This client object's object name if it has one
        """
        object_template = await self.object_template()
        if object_template is not None:
            return await object_template.object_name()

        # explict None
        return None

    # helper method
    async def display_name(self) -> Optional[str]:
        """
        This client object's display name if it has one
        """
        object_template = await self.object_template()
        if object_template is not None:
            display_name_code = await object_template.display_name()
            # this is sometimes just a blank string
            if display_name_code:
                return await self.hook_handler.client.cache_handler.get_langcode_name(display_name_code)

        # explict None
        return None

    # note: not defined
    async def parent(self) -> Optional["DynamicClientObject"]:
        """
        This client object's parent or None if it is the root client object

        Returns:
            DynamicClientObject
        """
        core_object = await super().parent()
        if not core_object:
            return None
        return DynamicClientObject(self.hook_handler, await core_object.read_base_address())

    # note: not defined
    async def children(self) -> List["DynamicClientObject"]:
        """
        This client object's child client objects

        Returns:
            List of DynamicClientObject
        """
        children = []
        for addr in await self.read_shared_vector(392):
            children.append(DynamicClientObject(self.hook_handler, addr))

        return children

    # note: not defined
    async def client_zone(self) -> Optional["DynamicClientZone"]:
        """
        This client object's client zone or None

        Returns:
            DynamicClientZone
        """
        addr = await self.read_value_from_offset(304, Primitive.int64)

        if addr == 0:
            return None

        return DynamicClientZone(self.hook_handler, addr)

    # note: not defined
    async def object_template(self) -> Optional[DynamicWizGameObjectTemplate]:
        """
        This client object's template object

        Returns:
            DynamicWizGameObjectTemplate
        """
        core_template = await super().object_template()
        if not core_template:
            return None
        return DynamicWizGameObjectTemplate(core_template.hook_handler, await core_template.read_base_address())

    async def character_id(self) -> int:
        """
        This client object's character id
        """
        return await self.read_value_from_offset(448, Primitive.uint64)

    async def write_character_id(self, character_id: int):
        """
        Write this client object's character id

        Args:
            character_id: The character id to write
        """
        await self.write_value_to_offset(448, character_id, Primitive.uint64)

    # Note: not defined
    async def game_stats(self) -> Optional[DynamicGameStats]:
        """
        This client object's game stats or None if doesn't have them

        Returns:
            DynamicGameStats
        """
        addr = await self.read_value_from_offset(560, Primitive.int64)

        if addr == 0:
            return None

        return DynamicGameStats(self.hook_handler, addr)
    
    async def fetch_npc_behavior_template(self) -> NPCBehaviorTemplate | None:
        if behavior := await self.search_behavior_by_name("NPCBehavior"):
            templ = await behavior.behavior_template()
            return NPCBehaviorTemplate(templ.hook_handler, await templ.read_base_address())
        return None



class CurrentClientObject(ClientObject):
    """
    Client object tied to the client hook
    """
    def __init__(self, hook_handler: HookHandler):
        super(DynamicMemoryObject, self).__init__(hook_handler)

    async def read_base_address(self) -> int:
        return await self.hook_handler.read_current_client_base()


class DynamicClientObject(ClientObject):
    """
    Dynamic client object that can take an address
    """

    pass