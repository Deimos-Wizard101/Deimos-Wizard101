from typing import List

from wizwalker.memory.memory_object import Primitive, DynamicMemoryObject
from .behavior_instance import DynamicBehaviorInstance


class SpellbookSpellEntry(DynamicMemoryObject):
    """
    Entry in the player's trained spell list (m_spellIDList).

    Each entry represents one spell the player has learned/trained.
    Ghidra: SpellbookSpellEntry__RegisterProperties @ 0x14206daa0 (r792258)
    """

    async def spell_id(self) -> int:
        """The spell template ID (m_spellID at +0x48)."""
        return await self.read_value_from_offset(72, Primitive.uint32)

    async def is_retired(self) -> bool:
        """Whether this spell has been superseded by a tier upgrade (m_isRetired at +0x4C)."""
        return await self.read_value_from_offset(76, Primitive.bool)

    async def tiered_spell_group_index(self) -> int:
        """Index into the global tiered spell group list (m_tieredSpellGroupIndex at +0x50).

        This is NOT a tier level. It's the position in a master list of
        tiered spell groups (upgrade chains). Both the base spell and all
        its upgraded tiers share the same index. Returns -1 if the spell
        is not part of any tiered upgrade chain.

        Computed by FindTieredSpellGroupIndex (0x141a842f0, r792258) during AddSpell.
        """
        return await self.read_value_from_offset(80, Primitive.int32)


class ClientSpellbookBehavior(DynamicBehaviorInstance):
    """
    Wrapper for the player's trained spellbook behavior.

    Contains the complete list of all spells the player has learned/trained.
    Ghidra: ClientSpellbookBehavior__RegisterProperties @ 0x14206dc70 (r792258)
    Behavior name: "BasicSpellbookBehavior"

    Offsets from behavior instance base:
        +0x70 (112): linked list of shared_ptr<SpellTemplate> (loaded spell objects)
        +0x80 (128): m_spellIDList - linked list of SpellbookSpellEntry
    """

    async def spell_id_list(self) -> List[SpellbookSpellEntry]:
        """Read m_spellIDList -- all trained spell entries with metadata."""
        result = []
        for addr in await self.read_shared_linked_list(128):  # 0x80
            if addr != 0:
                result.append(SpellbookSpellEntry(self.hook_handler, addr))
        return result

    async def trained_spell_ids(self) -> List[int]:
        """Convenience: get all trained spell template IDs."""
        entries = await self.spell_id_list()
        return [await entry.spell_id() for entry in entries]

    async def active_spell_ids(self) -> List[int]:
        """Convenience: get only non-retired trained spell template IDs."""
        entries = await self.spell_id_list()
        result = []
        for entry in entries:
            if not await entry.is_retired():
                result.append(await entry.spell_id())
        return result
